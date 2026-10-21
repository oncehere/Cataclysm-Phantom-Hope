"""Local files, writer locks and process identity for the supported hosts.

Windows uses kernel handles and a protected DACL, not POSIX mode-bit emulation.
Callers keep their existing data formats and lifecycle rules.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import re

WINDOWS = os.name == "nt"

if WINDOWS:
    import ctypes as ct
    from ctypes import wintypes as wt
    import msvcrt

    kernel = ct.WinDLL("kernel32", use_last_error=True)
    security = ct.WinDLL("advapi32", use_last_error=True)

    def _bind(dll, name, result, *arguments):
        function = getattr(dll, name)
        function.restype, function.argtypes = result, arguments
        return function

    _create = _bind(kernel, "CreateFileW", wt.HANDLE, wt.LPCWSTR, wt.DWORD,
                    wt.DWORD, ct.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE)
    _close = _bind(kernel, "CloseHandle", wt.BOOL, wt.HANDLE)
    _current = _bind(kernel, "GetCurrentProcess", wt.HANDLE)
    _open_token = _bind(security, "OpenProcessToken", wt.BOOL, wt.HANDLE,
                        wt.DWORD, ct.POINTER(wt.HANDLE))
    _token_info = _bind(security, "GetTokenInformation", wt.BOOL, wt.HANDLE,
                        ct.c_int, ct.c_void_p, wt.DWORD, ct.POINTER(wt.DWORD))
    _sid_string = _bind(security, "ConvertSidToStringSidW", wt.BOOL,
                        ct.c_void_p, ct.POINTER(wt.LPWSTR))
    _free = _bind(kernel, "LocalFree", wt.HANDLE, wt.HANDLE)
    _convert_sd = _bind(security, "ConvertStringSecurityDescriptorToSecurityDescriptorW",
                        wt.BOOL, wt.LPCWSTR, wt.DWORD, ct.POINTER(ct.c_void_p),
                        ct.POINTER(wt.DWORD))
    _set_security = _bind(security, "SetFileSecurityW", wt.BOOL, wt.LPCWSTR,
                          wt.DWORD, ct.c_void_p)
    _get_security = _bind(security, "GetSecurityInfo", wt.DWORD, wt.HANDLE,
                          ct.c_int, wt.DWORD, ct.POINTER(ct.c_void_p),
                          ct.c_void_p, ct.POINTER(ct.c_void_p), ct.c_void_p,
                          ct.POINTER(ct.c_void_p))
    _get_ace = _bind(security, "GetAce", wt.BOOL, ct.c_void_p, wt.DWORD,
                     ct.POINTER(ct.c_void_p))
    _get_info = _bind(kernel, "GetFileInformationByHandle", wt.BOOL,
                      wt.HANDLE, ct.c_void_p)
    _open_process = _bind(kernel, "OpenProcess", wt.HANDLE, wt.DWORD, wt.BOOL, wt.DWORD)
    _process_times = _bind(kernel, "GetProcessTimes", wt.BOOL, wt.HANDLE,
                           ct.POINTER(wt.FILETIME), ct.POINTER(wt.FILETIME),
                           ct.POINTER(wt.FILETIME), ct.POINTER(wt.FILETIME))
    _move = _bind(kernel, "MoveFileExW", wt.BOOL, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD)

    class _Attributes(ct.Structure):
        _fields_ = [("length", wt.DWORD), ("descriptor", ct.c_void_p), ("inherit", wt.BOOL)]

    class _FileInfo(ct.Structure):
        _fields_ = [("attributes", wt.DWORD), ("created", wt.FILETIME),
                    ("accessed", wt.FILETIME), ("written", wt.FILETIME),
                    ("volume", wt.DWORD), ("size_high", wt.DWORD), ("size_low", wt.DWORD),
                    ("links", wt.DWORD), ("index_high", wt.DWORD), ("index_low", wt.DWORD)]

    class _Acl(ct.Structure):
        _fields_ = [("revision", wt.BYTE), ("reserved", wt.BYTE), ("size", wt.WORD),
                    ("count", wt.WORD), ("reserved2", wt.WORD)]

    def _sid_text(sid) -> str:
        text = wt.LPWSTR()
        if not _sid_string(sid, ct.byref(text)):
            raise ct.WinError(ct.get_last_error())
        try:
            return text.value
        finally:
            _free(ct.cast(text, wt.HANDLE))

    def _process_owner(handle) -> str:
        token = wt.HANDLE()
        if not _open_token(handle, 0x0008, ct.byref(token)):
            raise ct.WinError(ct.get_last_error())
        try:
            size = wt.DWORD()
            _token_info(token, 1, None, 0, ct.byref(size))
            buffer = ct.create_string_buffer(size.value)
            if not _token_info(token, 1, buffer, size, ct.byref(size)):
                raise ct.WinError(ct.get_last_error())
            return _sid_text(ct.c_void_p.from_buffer(buffer))
        finally:
            _close(token)

    def _private_sd():
        result = ct.c_void_p()
        # Owner and SYSTEM only; inheritance is explicitly protected.
        sddl = "O:" + _process_owner(_current()) + "D:P(A;;FA;;;SY)(A;;FA;;;" + _process_owner(_current()) + ")"
        if not _convert_sd(sddl, 1, ct.byref(result), None):
            raise ct.WinError(ct.get_last_error())
        return result

    def _private_handle(handle) -> bool:
        owner, acl, descriptor = ct.c_void_p(), ct.c_void_p(), ct.c_void_p()
        error = _get_security(handle, 1, 0x5, ct.byref(owner), None,
                              ct.byref(acl), None, ct.byref(descriptor))
        if error:
            raise ct.WinError(error)
        try:
            current_sid = _process_owner(_current())
            if not owner.value or _sid_text(owner) != current_sid or not acl.value:
                return False
            header = ct.cast(acl, ct.POINTER(_Acl)).contents
            for index in range(header.count):
                ace = ct.c_void_p()
                if not _get_ace(acl, index, ct.byref(ace)):
                    raise ct.WinError(ct.get_last_error())
                kind = ct.c_ubyte.from_address(ace.value).value
                # Simple deny entries do not grant access. Reject unfamiliar
                # access-granting ACE types instead of misinterpreting a SID.
                if kind == 1:
                    continue
                if kind != 0 or _sid_text(ace.value + 8) not in {current_sid, "S-1-5-18"}:
                    return False
            return True
        finally:
            _free(descriptor)


def reject_links(path: str | Path, *, missing: bool = False) -> None:
    """Reject symlinks and all Windows reparse points, including ancestors."""
    path = Path(path).absolute()
    if WINDOWS:
        devices = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                   *(f"LPT{i}" for i in range(1, 10))}
        for name in path.relative_to(path.anchor).parts:
            if (":" in name or name.endswith((".", " "))
                    or name.split(".", 1)[0].upper() in devices):
                raise OSError("unsafe_path")
    for part in reversed((path, *path.parents)):
        try:
            info = part.lstat()
        except FileNotFoundError:
            if missing:
                continue
            raise
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise OSError("unsafe_link")


def private_directory(path: str | Path, *, create: bool = False) -> Path:
    path = Path(path).absolute()
    reject_links(path, missing=create)
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if WINDOWS:
            descriptor = _private_sd()
            try:
                if not _set_security(str(path), 0x80000005, descriptor):
                    raise ct.WinError(ct.get_last_error())
            finally:
                _free(descriptor)
        else:
            path.chmod(0o700)
    if not path.is_dir():
        raise OSError("not_a_directory")
    if WINDOWS:
        handle = _create(str(path), 0x00020000, 7, None, 3, 0x02200000, None)
        if handle == wt.HANDLE(-1).value:
            raise ct.WinError(ct.get_last_error())
        try:
            info = _FileInfo()
            if not _get_info(handle, ct.byref(info)) or info.attributes & 0x400 or not _private_handle(handle):
                raise OSError("insecure_permissions")
        finally:
            _close(handle)
    else:
        info = path.lstat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise OSError("insecure_permissions")
    return path


def open_file(path: str | Path, flags: int, mode: int = 0o600) -> int:
    """Open without links; use atomic_write instead of destructive truncation."""
    if flags & os.O_TRUNC:
        raise OSError("use_atomic_write")
    if not WINDOWS:
        return os.open(path, flags | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, mode)
    reject_links(path, missing=bool(flags & os.O_CREAT))
    desired = 0x80000000 if not flags & os.O_WRONLY else 0
    if flags & (os.O_WRONLY | os.O_RDWR):
        desired |= 0x40000000
    desired |= 0x00020000  # READ_CONTROL, for owner/DACL validation.
    creation = (1 if flags & os.O_EXCL else 4) if flags & os.O_CREAT else 3
    descriptor = _private_sd() if flags & os.O_CREAT else None
    attributes = _Attributes(ct.sizeof(_Attributes), descriptor, False)
    try:
        handle = _create(str(Path(path).absolute()), desired, 7, ct.byref(attributes),
                         creation, 0x00200080, None)
        if handle == wt.HANDLE(-1).value:
            raise ct.WinError(ct.get_last_error())
    finally:
        if descriptor:
            _free(descriptor)
    try:
        info = _FileInfo()
        if not _get_info(handle, ct.byref(info)) or info.attributes & (0x400 | 0x10) or info.links != 1:
            raise OSError("unsafe_file")
        fd = msvcrt.open_osfhandle(handle, os.O_BINARY | os.O_NOINHERIT |
                                  (flags & (os.O_WRONLY | os.O_RDWR | os.O_APPEND)))
        handle = None
        return fd
    finally:
        if handle is not None:
            _close(handle)


def private_file(fd: int) -> bool:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        return False
    if WINDOWS:
        return _private_handle(msvcrt.get_osfhandle(fd))
    return info.st_uid == os.getuid() and not info.st_mode & 0o077


def lock_file(fd: int, *, blocking: bool = True) -> None:
    if WINDOWS:
        class Overlapped(ct.Structure):
            _fields_ = [("internal", ct.c_size_t), ("internal_high", ct.c_size_t),
                        ("offset", wt.DWORD), ("offset_high", wt.DWORD), ("event", wt.HANDLE)]
        lock = _bind(kernel, "LockFileEx", wt.BOOL, wt.HANDLE, wt.DWORD, wt.DWORD,
                     wt.DWORD, wt.DWORD, ct.POINTER(Overlapped))
        state = Overlapped()
        if not lock(msvcrt.get_osfhandle(fd), 2 | (0 if blocking else 1), 0,
                    1, 0, ct.byref(state)):
            raise ct.WinError(ct.get_last_error())
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))


def replace_file(source: str | Path, destination: str | Path) -> None:
    reject_links(destination, missing=True)
    if WINDOWS:
        # Same-volume replacement, with write-through completion.
        if not _move(str(Path(source).absolute()), str(Path(destination).absolute()), 0x9):
            raise ct.WinError(ct.get_last_error())
    else:
        os.replace(source, destination)
        sync_directory(Path(destination).parent)


def atomic_write(path: str | Path, data: bytes) -> None:
    path = Path(path)
    temporary = path.with_name("." + path.name + "-" + os.urandom(16).hex() + ".tmp")
    fd = open_file(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        replace_file(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def sync_directory(path: str | Path) -> None:
    if not WINDOWS:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    # Windows replacement uses MoveFileExW WRITE_THROUGH. Individual new files
    # must be flushed before publication; Windows has no POSIX directory fsync.


def process_start(pid: int) -> str | None:
    if WINDOWS:
        handle = _open_process(0x1000, False, pid)
        if not handle:
            return None
        try:
            if _process_owner(handle) != _process_owner(_current()):
                return None
            times = [wt.FILETIME() for _ in range(4)]
            if not _process_times(handle, *(ct.byref(value) for value in times)):
                return None
            return str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
        except OSError:
            return None
        finally:
            _close(handle)
    try:
        if Path(f"/proc/{pid}").stat().st_uid != os.getuid():
            return None
        value = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        return value[value.rfind(")") + 2:].split()[19]
    except (OSError, UnicodeError, IndexError):
        return None


def _event_name(nonce: str) -> str:
    if not isinstance(nonce, str) or not re.fullmatch(r"[a-f0-9]{32}", nonce):
        raise ValueError("invalid_runtime_identity")
    return "Local\\CPH-AI-" + nonce


class StopEvent:
    """Private Windows notification; POSIX continues using its signal handler."""

    def __init__(self, nonce: str):
        self.handle = None
        if WINDOWS:
            create = _bind(kernel, "CreateEventW", wt.HANDLE, ct.c_void_p, wt.BOOL, wt.BOOL, wt.LPCWSTR)
            descriptor = _private_sd()
            attributes = _Attributes(ct.sizeof(_Attributes), descriptor, False)
            try:
                self.handle = create(ct.byref(attributes), True, False, _event_name(nonce))
                error = ct.get_last_error()
                if not self.handle or error == 183:
                    self.close()
                    raise OSError("runtime_stop_unavailable")
            finally:
                _free(descriptor)

    def is_set(self) -> bool:
        if self.handle is None:
            return False
        wait = _bind(kernel, "WaitForSingleObject", wt.DWORD, wt.HANDLE, wt.DWORD)
        return wait(self.handle, 0) == 0

    def close(self) -> None:
        if self.handle is not None:
            _close(self.handle)
            self.handle = None


def request_stop_event(pid: int, identity: str, nonce: str) -> bool:
    # The random event name is advertised only in the private runtime record.
    # Do not signal a newly reused PID, or fall back to terminating by PID.
    if process_start(pid) != identity:
        return False
    open_event = _bind(kernel, "OpenEventW", wt.HANDLE, wt.DWORD, wt.BOOL, wt.LPCWSTR)
    event = open_event(2, False, _event_name(nonce))
    if not event:
        raise OSError("runtime_stop_unavailable")
    try:
        signal_event = _bind(kernel, "SetEvent", wt.BOOL, wt.HANDLE)
        if not signal_event(event):
            raise OSError("runtime_stop_unavailable")
        return True
    finally:
        _close(event)
