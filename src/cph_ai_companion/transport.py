"""Explicit, authenticated loopback sessions with bounded NDJSON messages."""

from __future__ import annotations

import json
import contextlib
import os
import re
import socket
import stat
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .protocol import MAX_MESSAGE_BYTES, PROTOCOL_VERSION, schema_digest


MAX_DESCRIPTOR_BYTES = 16384


class TransportError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise TransportError("invalid_json")
        value[key] = item
    return value


def _constant(_: str) -> None:
    raise TransportError("invalid_json")


def strict_json(data: bytes) -> dict[str, Any]:
    try:
        result = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise TransportError("invalid_json") from None
    if not isinstance(result, dict):
        raise TransportError("invalid_json")
    return result


def runtime_directory() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime) / "cph-ai-companion"
    cache = os.environ.get("XDG_CACHE_HOME")
    return (Path(cache) if cache else Path.home() / ".cache") / "cph-ai-companion" / "run"


def _private_directory(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError:
        raise TransportError("session_missing") from None
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise TransportError("insecure_session_permissions")


def _read_private(path: Path, maximum: int) -> bytes:
    _private_directory(path.parent)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise TransportError("session_file_unavailable") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise TransportError("insecure_session_permissions")
        if info.st_size > maximum:
            raise TransportError("session_file_too_large")
        with os.fdopen(fd, "rb", closefd=False) as source:
            result = source.read(maximum + 1)
        if len(result) > maximum:
            raise TransportError("session_file_too_large")
        return result
    finally:
        os.close(fd)


@dataclass(frozen=True)
class SessionDescriptor:
    path: Path
    session_id: str
    host: str
    port: int
    credential_file: Path
    protocol_version: str
    schema_digest: str
    pid: int | None = None
    process_start: str | None = None
    user_dir: str | None = None
    config_dir: str | None = None
    save_dir: str | None = None

    @classmethod
    def load(cls, path: str | Path) -> "SessionDescriptor":
        path = Path(path).absolute()
        raw = strict_json(_read_private(path, MAX_DESCRIPTOR_BYTES))
        session_id = raw.get("session_id")
        host, port = raw.get("host"), raw.get("port")
        credential_name = raw.get("credential_file")
        if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
            raise TransportError("invalid_session_descriptor")
        if host not in {"127.0.0.1", "::1"} or type(port) is not int or not 1 <= port <= 65535:
            raise TransportError("invalid_session_endpoint")
        if not isinstance(credential_name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", credential_name):
            raise TransportError("invalid_credential_path")
        if credential_name in {".", "..", path.name}:
            raise TransportError("invalid_credential_path")
        protocol = raw.get("protocol_version")
        digest = raw.get("schema_digest")
        if protocol != PROTOCOL_VERSION or digest != schema_digest():
            raise TransportError("incompatible_bridge")
        pid = raw.get("pid")
        if pid is not None and (type(pid) is not int or pid <= 0):
            raise TransportError("invalid_session_descriptor")
        start = raw.get("process_start")
        if start is not None and not isinstance(start, str):
            raise TransportError("invalid_session_descriptor")
        directories = {}
        for name in ("user_dir", "config_dir", "save_dir"):
            directory = raw.get(name)
            if directory is not None and (not isinstance(directory, str) or not Path(directory).is_absolute()):
                raise TransportError("invalid_session_descriptor")
            directories[name] = directory
        return cls(path, session_id, host, port, path.parent / credential_name, protocol, digest,
                   pid, start, **directories)

    def credential(self) -> str:
        try:
            value = _read_private(self.credential_file, 4096).decode("ascii").strip()
        except UnicodeError:
            raise TransportError("invalid_session_credential") from None
        if not re.fullmatch(r"[A-Za-z0-9_+/=-]{32,256}", value):
            raise TransportError("invalid_session_credential")
        return value

    def public_info(self) -> dict[str, Any]:
        return {"session_id": self.session_id, "descriptor": str(self.path),
                "protocol_version": self.protocol_version, "pid": self.pid,
                "user_dir": self.user_dir}


def discover_sessions(root: str | Path | None = None) -> list[SessionDescriptor]:
    directory = Path(root) if root is not None else runtime_directory()
    if not directory.exists():
        return []
    _private_directory(directory)
    try:
        candidates = sorted(directory.glob("*/session.json"))
    except OSError:
        raise TransportError("session_discovery_failed") from None
    if len(candidates) > 128:
        raise TransportError("too_many_sessions")
    result = []
    for path in candidates:
        try:
            result.append(SessionDescriptor.load(path))
        except TransportError:
            # Invalid/stale advertisements are never selected automatically.
            continue
    return result


def resolve_session(value: str, root: str | Path | None = None) -> SessionDescriptor:
    if "/" in value or value.endswith(".json"):
        return SessionDescriptor.load(value)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise TransportError("invalid_session_id")
    directory = Path(root) if root is not None else runtime_directory()
    return SessionDescriptor.load(directory / value / "session.json")


class JsonRpcClient:
    """No automatic retries: replaying a mutation is the engine's decision."""

    def __init__(self, descriptor: SessionDescriptor, *, timeout: float = 2.0) -> None:
        self.descriptor = descriptor
        self.timeout = timeout
        self._socket: socket.socket | None = None
        self._buffer = bytearray()
        self._lock = threading.Lock()

    def connect(self) -> dict[str, Any]:
        if self._socket is not None:
            raise TransportError("already_connected")
        credential = self.descriptor.credential()
        try:
            self._socket = socket.create_connection((self.descriptor.host, self.descriptor.port), self.timeout)
            result = self.request("hello", {"credential": credential,
                                           "protocol_version": PROTOCOL_VERSION,
                                           "schema_digest": schema_digest()})
            if not isinstance(result, dict):
                raise TransportError("invalid_handshake")
            if result.get("protocol_version") != PROTOCOL_VERSION:
                raise TransportError("incompatible_bridge")
            if result.get("schema_digest") != schema_digest():
                raise TransportError("incompatible_bridge")
            if result.get("session_id") != self.descriptor.session_id:
                raise TransportError("session_identity_mismatch")
            return result
        except (OSError, TimeoutError):
            self.close()
            raise TransportError("bridge_unavailable") from None
        except BaseException:
            self.close()
            raise

    def request(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        if not isinstance(method, str) or not re.fullmatch(r"[a-z_]{1,64}", method):
            raise TransportError("invalid_method")
        with self._lock:
            if self._socket is None:
                raise TransportError("disconnected")
            request_id = uuid.uuid4().hex
            try:
                data = json.dumps({"id": request_id, "method": method, "params": dict(params or {})},
                                  ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
            except (ValueError, TypeError, RecursionError):
                raise TransportError("invalid_request") from None
            if len(data) > MAX_MESSAGE_BYTES:
                raise TransportError("message_too_large")
            deadline = time.monotonic() + self.timeout
            try:
                self._socket.settimeout(self.timeout)
                self._socket.sendall(data + b"\n")
                while b"\n" not in self._buffer:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TransportError("bridge_timeout")
                    self._socket.settimeout(remaining)
                    chunk = self._socket.recv(min(65536, MAX_MESSAGE_BYTES + 1 - len(self._buffer)))
                    if not chunk:
                        raise TransportError("disconnected")
                    self._buffer.extend(chunk)
                    if len(self._buffer) > MAX_MESSAGE_BYTES and b"\n" not in self._buffer:
                        raise TransportError("message_too_large")
                line, _, tail = self._buffer.partition(b"\n")
                if len(line) > MAX_MESSAGE_BYTES:
                    raise TransportError("message_too_large")
                self._buffer = bytearray(tail)
                response = strict_json(bytes(line))
                if response.get("id") != request_id or type(response.get("ok")) is not bool:
                    raise TransportError("invalid_response")
                if response["ok"] is False:
                    remote = response.get("error")
                    code = remote.get("code") if isinstance(remote, dict) else None
                    safe_codes = {
                        "unsupported_method", "unsupported_action", "invalid_request", "stale_request",
                        "invalid_plan", "not_bound", "actor_unavailable", "busy", "policy_rejected",
                        "unauthorized", "incompatible_bridge", "detached", "session_stopped",
                        "memory_conflict", "checkpoint_mismatch", "not_ready",
                    }
                    raise TransportError(code if code in safe_codes else "bridge_rejected")
                if "result" not in response:
                    raise TransportError("invalid_response")
                return response["result"]
            except (OSError, TimeoutError):
                self.close()
                raise TransportError("disconnected") from None
            except TransportError as exc:
                if exc.code in {"invalid_json", "invalid_response", "disconnected", "message_too_large", "bridge_timeout"}:
                    self.close()
                raise

    def close(self) -> None:
        connection, self._socket = self._socket, None
        self._buffer.clear()
        if connection is not None:
            with contextlib.suppress(OSError):
                connection.close()

    def __enter__(self) -> "JsonRpcClient":
        self.connect()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


def process_start(pid: int) -> str | None:
    """Linux process identity, including start time to reject recycled PIDs."""
    try:
        value = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        return value[value.rfind(")") + 2:].split()[19]
    except (OSError, UnicodeError, IndexError):
        return None
