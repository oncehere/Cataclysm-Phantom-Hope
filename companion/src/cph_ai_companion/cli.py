"""Explicit local lifecycle commands. Importing this module starts nothing."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
from importlib import metadata
from importlib.resources import files
import json
import os
from pathlib import Path
import signal
import sys
import time
from typing import Any
from uuid import uuid4

from .config import ConfigError, default_config, load_config
from .memory import MemoryStore, MemoryStoreError
from .personality import PersonalityError
from .protocol import PROTOCOL_VERSION, ProtocolError, schema_digest
from .provider import ProviderConfig, ProviderError
from .runtime import AgentRuntime, RuntimeErrorCode
from .transport import (JsonRpcClient, SessionDescriptor, TransportError,
                        _read_private, discover_sessions, process_start, resolve_session, strict_json)


class CliError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _new_file(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as out:
            out.write(data)
            out.flush()
            os.fsync(fd)
    finally:
        os.close(fd)


def _resource_tree(root: Any, prefix: str = "") -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for child in root.iterdir():
        name = f"{prefix}{child.name}"
        if child.is_dir():
            result.update(_resource_tree(child, name + "/"))
        elif child.is_file():
            result[name] = child.read_bytes()
    return result


# CPH treats every *.json under a MOD as game data, even hidden files.
INSTALL_MANIFEST = ".cph-ai-companion-install-manifest"


def install_mod(user_dir: str | Path) -> Path:
    base = Path(user_dir).expanduser().resolve() / "mods"
    target = base / "cph_ai_companion"
    payloads = _resource_tree(files("cph_ai_companion").joinpath("resources/mod"))
    if not payloads or not {"mod.lua", "main.lua"}.issubset(payloads):
        raise CliError("mod_resources_missing")
    if target.is_symlink():
        raise CliError("unsafe_mod_destination")
    manifest_path = target / INSTALL_MANIFEST
    if target.exists() and not manifest_path.is_file():
        raise CliError("unowned_mod_destination")
    if manifest_path.exists():
        old = _load_install_manifest(target)
        for name, digest in old["files"].items():
            path = _owned_path(target, name)
            if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise CliError("modified_installed_mod")
        if set(payloads) != set(old["files"]):
            raise CliError("mod_upgrade_requires_explicit_removal")
    for name, data in payloads.items():
        path = _owned_path(target, name)
        if path.exists() and path.read_bytes() != data:
            raise CliError("mod_file_conflict")
    base.mkdir(parents=True, exist_ok=True)
    target.mkdir(mode=0o700, exist_ok=True)
    for name, data in payloads.items():
        path = _owned_path(target, name)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not path.exists():
            _new_file(path, data)
    manifest = {"schema_version": 1, "package_version": "0.1.2.dev0", "protocol_version": PROTOCOL_VERSION,
                "schema_digest": schema_digest(),
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}}
    if not manifest_path.exists():
        _new_file(manifest_path, _json(manifest))
    return target


def _owned_path(target: Path, name: str) -> Path:
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts or name == INSTALL_MANIFEST:
        raise CliError("invalid_install_manifest")
    path = target / relative
    current = target
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise CliError("unsafe_mod_destination")
    return path


def _load_install_manifest(target: Path) -> dict[str, Any]:
    if target.is_symlink() or (target / INSTALL_MANIFEST).is_symlink():
        raise CliError("unsafe_mod_destination")
    try:
        data = json.loads((target / INSTALL_MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise CliError("invalid_install_manifest") from None
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("files"), dict):
        raise CliError("invalid_install_manifest")
    for name, digest in data["files"].items():
        if not isinstance(name, str) or not isinstance(digest, str) or len(digest) != 64:
            raise CliError("invalid_install_manifest")
        _owned_path(target, name)
    return data


def remove_mod(user_dir: str | Path, descriptor: SessionDescriptor) -> dict[str, Any]:
    target = Path(user_dir).expanduser().resolve() / "mods" / "cph_ai_companion"
    manifest = _load_install_manifest(target)
    if descriptor.user_dir is None or Path(descriptor.user_dir).resolve() != Path(user_dir).expanduser().resolve():
        raise CliError("game_user_directory_mismatch")
    for name, digest in manifest["files"].items():
        path = _owned_path(target, name)
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise CliError("modified_installed_mod")
    if _runtime_record(descriptor) is not None:
        stop_session(descriptor)
        deadline = time.monotonic() + 5
        while _runtime_record(descriptor) is not None:
            if time.monotonic() >= deadline:
                raise CliError("runtime_stop_pending")
            time.sleep(0.05)
    client = JsonRpcClient(descriptor)
    try:
        client.connect()
        result = client.request("remove_mod_check", {})
    finally:
        client.close()
    if not isinstance(result, dict) or result.get("safe_to_remove") is not True or result.get("world_dependencies") != []:
        raise CliError("mod_removal_not_confirmed_safe")
    for name, digest in manifest["files"].items():
        path = _owned_path(target, name)
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise CliError("modified_installed_mod")
    # All checks precede removal. Unknown files and every profile/save remain.
    for name in manifest["files"]:
        _owned_path(target, name).unlink(missing_ok=True)
    (target / INSTALL_MANIFEST).unlink()
    directories = sorted((p for p in target.rglob("*") if p.is_dir() and not p.is_symlink()),
                         key=lambda p: len(p.parts), reverse=True)
    for directory in [*directories, target]:
        with contextlib.suppress(OSError):
            directory.rmdir()
    return {"state": "removed", "preserved_profile_and_saves": True}


def initialize_profile(profile: str | Path, *, actor_id: int | None = None,
                       user_dir: str | Path | None = None) -> dict[str, Any]:
    root = Path(profile).expanduser().resolve()
    config_path, background_path = root / "config.json", root / "background.md"
    if config_path.exists() or background_path.exists() or config_path.is_symlink() or background_path.is_symlink():
        raise CliError("profile_already_initialized")
    config = default_config()
    config["profile_id"] = uuid4().hex
    config["actor_id"] = actor_id
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    _new_file(config_path, _json(config))
    _new_file(background_path, files("cph_ai_companion").joinpath("resources/templates/background.md").read_bytes())
    if user_dir is not None:
        install_mod(user_dir)
    return {"state": "initialized", "profile": str(root), "model_started": False}


def doctor(profile: str | Path, *, session: str | None = None) -> dict[str, Any]:
    config = load_config(profile)
    root = Path(profile).expanduser().resolve()
    background = Path(config["paths"]["background"])
    checks: dict[str, bool | str] = {
        "python_3_12": sys.version_info[:2] == (3, 12),
        "config_schema": True, "background_exists": background.is_file(),
        "background_is_file": not background.is_symlink(),
        "protocol_version": PROTOCOL_VERSION, "schema_digest": schema_digest(),
        "profile_absolute": root.is_absolute(), "model_called": False,
    }
    try:
        checks["sdk_3_22_1"] = metadata.version("openai") == "3.22.1"
    except metadata.PackageNotFoundError:
        checks["sdk_3_22_1"] = False
    try:
        ProviderConfig.from_mapping(config)
        checks["endpoint_configured"] = True
    except ProviderError:
        checks["endpoint_configured"] = False
    checks["credential_available"] = bool(os.environ.get(config["llm"]["api_key_env"]))
    if session is not None:
        # Descriptor validation is offline: no socket connection or repair.
        resolve_session(session)
        checks["session_descriptor"] = True
    return {"state": "checked", "checks": checks}


def _runtime_record(descriptor: SessionDescriptor) -> dict[str, Any] | None:
    path = descriptor.path.parent / "runtime.json"
    try:
        record = strict_json(_read_private(path, 16384))
    except TransportError as exc:
        if exc.code == "session_file_unavailable":
            return None
        raise
    pid = record.get("pid")
    if (record.get("session_id") != descriptor.session_id or type(pid) is not int or pid <= 0
            or not isinstance(record.get("process_start"), str)):
        raise CliError("invalid_runtime_identity")
    if process_start(pid) != record["process_start"]:
        return None
    try:
        if Path(f"/proc/{pid}").stat().st_uid != os.getuid():
            raise CliError("runtime_owner_mismatch")
    except OSError:
        return None
    return record


def _signal_owned_runtime(record: dict[str, Any]) -> bool:
    """Signal the exact Linux process handle after checking its advertised age."""
    try:
        process_fd = os.pidfd_open(record["pid"], 0)
    except ProcessLookupError:
        return False
    except (AttributeError, OSError):
        raise CliError("runtime_stop_unavailable") from None
    try:
        if process_start(record["pid"]) != record["process_start"]:
            return False
        try:
            signal.pidfd_send_signal(process_fd, signal.SIGTERM)
        except ProcessLookupError:
            return False
        except (AttributeError, OSError):
            raise CliError("runtime_stop_unavailable") from None
        return True
    finally:
        os.close(process_fd)


def stop_session(descriptor: SessionDescriptor) -> dict[str, Any]:
    record = _runtime_record(descriptor)
    if record is not None:
        # The authenticated bridge admits one client. Ask its owned runtime to
        # cancel the worker and release control instead of opening client #2.
        if _signal_owned_runtime(record):
            return {"state": "stop_requested", "safe_detach_complete": False}
    client = JsonRpcClient(descriptor)
    try:
        client.connect()
        client.request("cancel", {})
        result = client.request("stop", {})
        return {"state": "stop_requested", "detach": result}
    finally:
        client.close()


def run_session(descriptor: SessionDescriptor, profile: str | Path) -> dict[str, Any]:
    config = load_config(profile)
    ProviderConfig.from_mapping(config)  # Invalid endpoints never start a worker.
    registry = descriptor.path.parent / "runtime.json"
    if _runtime_record(descriptor) is not None:
        raise CliError("session_runtime_already_running")
    # Remove only a stale advertisement in this explicitly selected session.
    if registry.exists():
        registry.unlink()
    nonce = uuid4().hex
    record = {"session_id": descriptor.session_id, "pid": os.getpid(),
              "process_start": process_start(os.getpid()), "nonce": nonce,
              "profile_id": config["profile_id"]}
    if record["process_start"] is None:
        raise CliError("unsupported_process_identity")
    handlers: dict[int, Any] = {}
    runtime: AgentRuntime | None = None
    memory: MemoryStore | None = None
    _new_file(registry, _json(record))
    try:
        memory = MemoryStore(profile, config)
        runtime = AgentRuntime(config, memory, JsonRpcClient(descriptor), profile=profile)
        for sig in (signal.SIGINT, signal.SIGTERM):
            handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, lambda *_: runtime.request_stop())
        result = runtime.run()
        # The result is lifecycle-only; runtime never prints prompts or plans.
        return result
    finally:
        if runtime is not None:
            runtime.close()
        if memory is not None:
            memory.close()
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
        with contextlib.suppress(OSError, ValueError, TransportError):
            current = strict_json(_read_private(registry, 16384))
            if current.get("nonce") == nonce:
                registry.unlink()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="cph-ai-companion")
    commands = result.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create local files without starting the game/model")
    init.add_argument("--profile", required=True)
    init.add_argument("--actor-id", type=int)
    init.add_argument("--install-mod", action="store_true")
    init.add_argument("--game-userdir")
    check = commands.add_parser("doctor", help="Offline configuration and installation checks")
    check.add_argument("--offline", action="store_true", required=True)
    check.add_argument("--profile", required=True)
    check.add_argument("--session")
    commands.add_parser("list-sessions")
    run = commands.add_parser("run")
    run.add_argument("--session", required=True)
    run.add_argument("--profile", required=True)
    stop = commands.add_parser("stop")
    stop.add_argument("--session", required=True)
    remove = commands.add_parser("remove-mod")
    remove.add_argument("--session", required=True)
    remove.add_argument("--game-userdir", required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            if args.actor_id is not None and args.actor_id < 0:
                raise CliError("invalid_actor_id")
            if args.install_mod != bool(args.game_userdir):
                raise CliError("install_mod_requires_game_userdir")
            result = initialize_profile(args.profile, actor_id=args.actor_id,
                                        user_dir=args.game_userdir if args.install_mod else None)
        elif args.command == "doctor":
            result = doctor(args.profile, session=args.session)
        elif args.command == "list-sessions":
            result = {"sessions": [item.public_info() for item in discover_sessions()]}
        elif args.command == "run":
            result = run_session(resolve_session(args.session), args.profile)
        elif args.command == "stop":
            result = stop_session(resolve_session(args.session))
        else:
            result = remove_mod(args.game_userdir, resolve_session(args.session))
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except (CliError, ProviderError, TransportError, MemoryStoreError, PersonalityError,
            RuntimeErrorCode, ProtocolError) as exc:
        print(json.dumps({"error": {"code": exc.code}}), file=sys.stderr)
        return 2
    except ConfigError:
        print('{"error":{"code":"invalid_configuration"}}', file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyboardInterrupt):
        print('{"error":{"code":"local_operation_failed"}}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
