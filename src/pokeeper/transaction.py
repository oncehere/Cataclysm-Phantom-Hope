"""Durable candidates and recoverable two-file application.

This is a journaled protocol, *not* a cross-file atomic transaction. Readers
must refuse to use a PO/state pair while ``<state>.pending`` exists. Locks
coordinate tool invocations; external editors must be closed during apply.
"""

from __future__ import annotations

import base64
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from typing import Iterator


class TransactionError(RuntimeError):
    """Candidate, input or recovery validation failed without permission to overwrite."""


_SHA = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED = {"candidate.po", "state.json", "report.json"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path(path: Path | str) -> Path:
    return Path(os.path.abspath(path))


def _safe_path(path: Path) -> None:
    """Reject symlinks, including ancestors, rather than resolve away evidence."""
    for component in [*reversed(path.parents), path]:
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise TransactionError(f"symlink path is not supported: {component}")
        if component != path and not stat.S_ISDIR(info.st_mode):
            raise TransactionError(f"non-directory parent: {component}")


def _read(path: Path) -> bytes | None:
    _safe_path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise TransactionError(f"not a regular file: {path}")
        return stream.read()


def file_digest(path: Path) -> str | None:
    data = _read(_path(path))
    return None if data is None else digest(data)


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _mkdir(path: Path) -> None:
    _safe_path(path)
    if path.exists():
        if not path.is_dir():
            raise TransactionError(f"not a directory: {path}")
        return
    _mkdir(path.parent)
    try:
        path.mkdir()
    except FileExistsError:
        _safe_path(path)
        if not path.is_dir():
            raise TransactionError(f"not a directory: {path}")
    _fsync_dir(path.parent)


def atomic_write(path: Path, data: bytes) -> None:
    """Replace one regular file durably; this does not transact several files."""
    path = _path(path)
    _safe_path(path)
    _mkdir(path.parent)
    mode = 0o600
    if path.exists():
        if not path.is_file():
            raise TransactionError(f"not a regular file: {path}")
        mode = stat.S_IMODE(path.stat().st_mode)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _safe_path(path)
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _hash(value: object, *, missing: bool = False) -> bool:
    return (missing and value is None) or isinstance(value, str) and bool(_SHA.fullmatch(value))


def _inputs(inputs: dict[str, str | None]) -> dict[str, str | None]:
    if not isinstance(inputs, dict):
        raise TransactionError("inputs must be a path/hash object")
    for name, expected in inputs.items():
        if not isinstance(name, str) or not Path(name).is_absolute() or str(_path(name)) != name:
            raise TransactionError(f"input path must be absolute and normalized: {name}")
        if not _hash(expected, missing=True):
            raise TransactionError(f"invalid input hash: {name}")
    return inputs


def check_inputs(inputs: dict[str, str | None]) -> None:
    for name, expected in _inputs(inputs).items():
        if file_digest(Path(name)) != expected:
            raise TransactionError(f"input changed: {name}")


def _related(a: Path, b: Path) -> bool:
    return a == b or a in b.parents or b in a.parents


def _targets(targets: dict[str, str]) -> dict[str, Path]:
    if not isinstance(targets, dict) or set(targets) != {"po", "state", "snapshots"}:
        raise TransactionError("targets must contain exactly po, state, snapshots")
    result = {}
    for key, value in targets.items():
        if not isinstance(value, str) or not Path(value).is_absolute() or str(_path(value)) != value:
            raise TransactionError(f"target must be absolute and normalized: {key}")
        path = Path(value)
        _safe_path(path)
        if path.exists() and (not path.is_dir() if key == "snapshots" else not path.is_file()):
            raise TransactionError(f"wrong target type: {path}")
        result[key] = path
    paths = [*result.values(), Path(str(result["state"]) + ".lock"), Path(str(result["state"]) + ".pending")]
    for index, a in enumerate(paths):
        for b in paths[index + 1 :]:
            if _related(a, b) or a.exists() and b.exists() and os.path.samefile(a, b):
                raise TransactionError(f"targets overlap or alias: {a}, {b}")
    return result


def _file_names(files: dict[str, object]) -> None:
    if not isinstance(files, dict) or not _REQUIRED <= files.keys():
        raise TransactionError("candidate is missing required files")
    for name in files:
        if not isinstance(name, str):
            raise TransactionError("invalid candidate filename")
        if name in _REQUIRED:
            continue
        parts = PurePosixPath(name).parts
        if len(parts) != 2 or parts[0] != "snapshots" or not parts[1].endswith(".po") or not _hash(parts[1][:-3]):
            raise TransactionError(f"unexpected candidate file: {name}")


def _json(data: object) -> bytes:
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def _load(data: bytes | None, name: str) -> dict:
    try:
        value = json.loads(data if data is not None else b"")
    except (ValueError, UnicodeError) as exc:
        raise TransactionError(f"invalid JSON: {name}") from exc
    if not isinstance(value, dict):
        raise TransactionError(f"expected JSON object: {name}")
    return value


@contextlib.contextmanager
def _lock(path: Path) -> Iterator[None]:
    _safe_path(path)
    _mkdir(path.parent)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise TransactionError(f"not a regular lock file: {path}")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def assert_no_pending(state: Path) -> None:
    pending = Path(str(_path(state)) + ".pending")
    _safe_path(pending)
    if pending.exists():
        raise TransactionError(f"unfinished application; run recover first: {pending}")


def publish_candidate(
    destination: Path,
    files: dict[str, bytes],
    inputs: dict[str, str | None],
    targets: dict[str, str],
    config: str | None = None,
) -> Path:
    """Publish a complete checked candidate; never update an existing candidate."""
    destination = _path(destination)
    _safe_path(destination)
    target_paths = _targets(targets)
    _file_names(files)
    _inputs(inputs)
    if config is not None and config not in inputs:
        raise TransactionError("candidate config must be guarded by its input digest")
    if not {str(target_paths["po"]), str(target_paths["state"])} <= inputs.keys():
        raise TransactionError("inputs must include the current PO and state (None if absent)")
    if any(_related(destination, target) for target in target_paths.values()):
        raise TransactionError("candidate directory overlaps its targets")
    hashes = {name: digest(data) for name, data in files.items()}
    for name, checksum in hashes.items():
        if name.startswith("snapshots/") and PurePosixPath(name).stem != checksum:
            raise TransactionError(f"snapshot name is not its content hash: {name}")
    assert_no_pending(target_paths["state"])
    check_inputs(inputs)
    _mkdir(destination.parent)
    # The publication lock avoids two cooperating publishers replacing each
    # other's empty destination. The final rename publishes all files together.
    with _lock(Path(str(destination) + ".lock")):
        if destination.exists():
            raise TransactionError(f"candidate already exists: {destination}")
        temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
        try:
            for name, data in files.items():
                atomic_write(temporary / name, data)
            atomic_write(temporary / "manifest.json", _json({
                "version": 1, "files": hashes, "inputs": inputs, "targets": targets, "config": config,
            }))
            check_inputs(inputs)
            assert_no_pending(target_paths["state"])
            _safe_path(destination)
            if destination.exists():
                raise TransactionError(f"candidate already exists: {destination}")
            os.rename(temporary, destination)
            _fsync_dir(destination.parent)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    return destination


def _candidate(candidate: Path) -> tuple[dict, dict[str, bytes]]:
    candidate = _path(candidate)
    manifest = _load(_read(candidate / "manifest.json"), "candidate manifest")
    if set(manifest) != {"version", "files", "inputs", "targets", "config"} or manifest["version"] != 1:
        raise TransactionError("unsupported or malformed candidate manifest")
    _file_names(manifest["files"])
    _targets(manifest["targets"])
    _inputs(manifest["inputs"])
    if not {manifest["targets"]["po"], manifest["targets"]["state"]} <= manifest["inputs"].keys():
        raise TransactionError("candidate does not guard PO/state inputs")
    contents = {}
    for name, expected in manifest["files"].items():
        data = _read(candidate / name)
        if not _hash(expected) or data is None or digest(data) != expected:
            raise TransactionError(f"candidate file failed hash check: {name}")
        if name.startswith("snapshots/") and PurePosixPath(name).stem != expected:
            raise TransactionError(f"snapshot name is not its hash: {name}")
        contents[name] = data
    return manifest, contents


def _packed(data: bytes | None) -> dict:
    return {"sha256": None if data is None else digest(data), "data": None if data is None else base64.b64encode(data).decode("ascii")}


def _unpacked(value: object) -> bytes | None:
    if not isinstance(value, dict) or set(value) != {"sha256", "data"}:
        raise TransactionError("malformed recovery payload")
    if value["data"] is None and value["sha256"] is None:
        return None
    try:
        data = base64.b64decode(value["data"], validate=True)
    except (ValueError, TypeError) as exc:
        raise TransactionError("invalid recovery payload encoding") from exc
    if not _hash(value["sha256"]) or digest(data) != value["sha256"]:
        raise TransactionError("recovery payload hash mismatch")
    return data


def _guard_targets(targets: dict[str, Path], versions: dict) -> None:
    for kind in ("po", "state"):
        allowed = {versions[kind]["old"]["sha256"], versions[kind]["new"]["sha256"]}
        if file_digest(targets[kind]) not in allowed:
            raise TransactionError(f"target changed outside transaction; refusing overwrite: {targets[kind]}")


def _unlink(path: Path) -> None:
    _safe_path(path)
    path.unlink(missing_ok=True)
    _fsync_dir(path.parent)


def apply_candidate(candidate: Path, *, require_config: bool = True) -> None:
    manifest, files = _candidate(candidate)
    targets = _targets(manifest["targets"])
    state = targets["state"]
    with _lock(Path(str(state) + ".lock")):
        assert_no_pending(state)
        check_inputs(manifest["inputs"])
        if manifest["config"] is None:
            if require_config:
                raise TransactionError("application requires a candidate bound to its project config")
        else:
            from .validation import validate_candidate
            validate_candidate(manifest, files)
        # Recovery must also guard previously persisted reference snapshots;
        # those are absent from this candidate's newly bundled files.
        snapshot_hashes = {name: checksum for name, checksum in manifest["inputs"].items()
                           if Path(name).parent == targets["snapshots"]}
        for name, data in files.items():
            if name.startswith("snapshots/"):
                path = targets["snapshots"] / PurePosixPath(name).name
                previous = file_digest(path)
                checksum = digest(data)
                if previous not in (None, checksum):
                    raise TransactionError(f"existing snapshot is corrupt: {path}")
                if previous is None:
                    atomic_write(path, data)
                snapshot_hashes[str(path)] = checksum
        check_inputs(manifest["inputs"])
        versions = {kind: {"old": _packed(_read(targets[kind])), "new": _packed(files[name])}
                    for kind, name in (("po", "candidate.po"), ("state", "state.json"))}
        journal = {"version": 1, "targets": manifest["targets"], "versions": versions, "snapshots": snapshot_hashes}
        pending = Path(str(state) + ".pending")
        # The journal itself holds durable complete payloads. Recovery therefore
        # works even after the candidate directory is moved or removed.
        atomic_write(pending, _json(journal))
        check_inputs(manifest["inputs"])
        for kind in ("po", "state"):
            _guard_targets(targets, versions)
            atomic_write(targets[kind], _unpacked(versions[kind]["new"]))
        for kind in ("po", "state"):
            if file_digest(targets[kind]) != versions[kind]["new"]["sha256"]:
                raise TransactionError(f"application verification failed: {targets[kind]}")
        _unlink(pending)


def recover(state: Path, action: str) -> None:
    """Finish or roll back only the exact old/new versions recorded in a journal."""
    if action not in ("finish", "rollback"):
        raise TransactionError("recovery action must be finish or rollback")
    state = _path(state)
    pending = Path(str(state) + ".pending")
    with _lock(Path(str(state) + ".lock")):
        journal = _load(_read(pending), "pending journal")
        if set(journal) != {"version", "targets", "versions", "snapshots"} or journal["version"] != 1:
            raise TransactionError("unsupported or malformed recovery journal")
        targets = _targets(journal["targets"])
        if targets["state"] != state:
            raise TransactionError("journal belongs to another state path")
        versions = journal["versions"]
        if not isinstance(versions, dict) or set(versions) != {"po", "state"}:
            raise TransactionError("malformed recovery versions")
        payloads = {}
        for kind, version in versions.items():
            if not isinstance(version, dict) or set(version) != {"old", "new"}:
                raise TransactionError("malformed recovery versions")
            payloads[kind] = {side: _unpacked(item) for side, item in version.items()}
            if payloads[kind]["new"] is None:
                raise TransactionError("new transaction payload cannot be absent")
        snapshots = _inputs(journal["snapshots"])
        for name, checksum in snapshots.items():
            path = Path(name)
            if path.parent != targets["snapshots"] or path.suffix != ".po" or path.stem != checksum:
                raise TransactionError("invalid recovery snapshot reference")
        if action == "finish":
            check_inputs(snapshots)
        _guard_targets(targets, versions)
        side = "new" if action == "finish" else "old"
        for kind in ("po", "state"):
            _guard_targets(targets, versions)
            data = payloads[kind][side]
            if data is None:
                _unlink(targets[kind])
            else:
                atomic_write(targets[kind], data)
        for kind in ("po", "state"):
            if file_digest(targets[kind]) != versions[kind][side]["sha256"]:
                raise TransactionError(f"recovery verification failed: {targets[kind]}")
        _unlink(pending)
