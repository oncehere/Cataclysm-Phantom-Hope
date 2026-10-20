#!/usr/bin/env python3
"""Assemble a candidate from built artifacts; never infer acceptance or publish."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import zipfile

_wheel_spec = importlib.util.spec_from_file_location("cph_companion_wheel_payload", Path(__file__).with_name("wheel_payload.py"))
_wheel = importlib.util.module_from_spec(_wheel_spec)
_wheel_spec.loader.exec_module(_wheel)
VERSION, PROTOCOL_VERSION = _wheel.VERSION, _wheel.PROTOCOL_VERSION
MOD_PREFIX, PROTOCOL_FILE = _wheel.MOD_PREFIX, _wheel.PROTOCOL_FILE
ReleaseError = _wheel.ReleaseError
_check_metadata, mod_payloads = _wheel._check_metadata, _wheel.mod_payloads


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_sdist(sdist: Path, payloads: dict[str, bytes], digest: str) -> None:
    """Read referenced members in place; never extract a source archive."""
    prefix = f"cph_ai_companion-{VERSION}/"
    try:
        with tarfile.open(sdist, "r:gz") as archive:
            members = {}
            for member in archive.getmembers():
                name = member.name.rstrip("/") if member.isdir() else member.name
                path = PurePosixPath(name)
                if (not name or path.is_absolute() or ".." in path.parts or "\\" in name
                        or "\0" in name or path.as_posix() != name
                        or (name != prefix[:-1] and not name.startswith(prefix))
                        or (name == prefix[:-1] and not member.isdir())):
                    raise ReleaseError("invalid_sdist_path")
                if name in members:
                    raise ReleaseError("duplicate_sdist_entries")
                members[name] = member
            for name in members:
                for parent in PurePosixPath(name).parents:
                    ancestor = members.get(parent.as_posix())
                    if ancestor is not None and not ancestor.isdir():
                        raise ReleaseError("invalid_sdist_path")

            def read(name: str) -> bytes:
                member = members.get(prefix + name)
                if member is None:
                    raise ReleaseError("sdist_resource_missing")
                if not member.isfile():
                    raise ReleaseError("nonregular_sdist_resource")
                stream = archive.extractfile(member)
                if stream is None:
                    raise ReleaseError("nonregular_sdist_resource")
                with stream:
                    return stream.read()

            _check_metadata(read("PKG-INFO"), "sdist")
            if hashlib.sha256(read("src/" + PROTOCOL_FILE)).hexdigest() != digest:
                raise ReleaseError("sdist_protocol_mismatch")
            mod_prefix = prefix + "src/" + MOD_PREFIX
            source_payloads = {name[len(mod_prefix):]: read(name[len(prefix):])
                               for name, member in members.items()
                               if name.startswith(mod_prefix) and not member.isdir()}
            if source_payloads != payloads:
                raise ReleaseError("sdist_mod_mismatch")
    except (tarfile.TarError, EOFError, OSError):
        raise ReleaseError("invalid_sdist_archive") from None


def _copy(source: Path, destination: Path) -> None:
    if source.resolve() != destination.resolve():
        shutil.copyfile(source, destination)


def _candidate_record(digest: str, platform: str = "linux-x86_64") -> dict:
    checks = ("artifact_install", "python_tests", "native_tests", "installed_native_joint",
              "full_game_build", "full_gnu_game", "gnu_module", "full_native_suite", "mod_load",
              "gui", "gameplay", "real_provider", "save_reload", "actual_user_environment",
              "complete_physical_crash_campaign", "live_multiplayer", "hosted_ci", "hosted_cph_result")
    return {"schema_version": 1, "package_version": VERSION, "protocol_version": PROTOCOL_VERSION,
            "schema_digest": digest, "python": ">=3.12,<3.13", "target_platform": platform,
            "candidate": {"status": "UNVALIDATED_PACKAGE_CANDIDATE", "native_head": None},
            "acceptance": {**{name: "NOT_RUN" for name in checks}, "published": "NOT_PUBLISHED"},
            "validated_combinations": []}


def _compatibility_record(path: Path, digest: str, wheel_digest: str) -> dict:
    record = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(record, dict) or type(record.get("schema_version")) is not int
            or record["schema_version"] != 1 or record.get("package_version") != VERSION
            or record.get("protocol_version") != PROTOCOL_VERSION
            or not isinstance(record.get("validated_combinations"), list)):
        raise ReleaseError("invalid_compatibility_record")
    if "schema_digest" in record and record["schema_digest"] != digest:
        raise ReleaseError("compatibility_schema_mismatch")
    for combination in record["validated_combinations"]:
        if not isinstance(combination, dict) or combination.get("wheel_sha256") != wheel_digest:
            raise ReleaseError("compatibility_wheel_mismatch")
        if (combination.get("package_version", VERSION) != VERSION
                or combination.get("protocol_version", PROTOCOL_VERSION) != PROTOCOL_VERSION
                or combination.get("schema_digest", digest) != digest):
            raise ReleaseError("invalid_compatibility_record")
    if not record["validated_combinations"]:
        return _candidate_record(digest)
    # Explicit evidence remains evidence for this exact wheel, not a result
    # inferred by assembly. Never carry claims for another artifact into it.
    record["schema_digest"] = digest
    return record


def assemble(dist: Path, *, root: Path, compatibility: Path | None = None,
             candidate_only: bool = False, windows_python: Path | None = None,
             windows_site_packages: Path | None = None, windows_game_root: Path | None = None) -> dict:
    if candidate_only and compatibility is not None:
        raise ReleaseError("incompatible_assembly_options")
    windows_inputs = (windows_python, windows_site_packages, windows_game_root)
    windows_bundle = any(value is not None for value in windows_inputs)
    if windows_bundle and any(value is None for value in windows_inputs):
        raise ReleaseError("complete_windows_bundle_inputs_required")
    dist = dist.resolve()
    root = root.resolve()
    if not dist.is_dir():
        raise ReleaseError("built_artifact_directory_missing")
    wheels = sorted(dist.glob(f"cph_ai_companion-{VERSION}-*.whl"))
    sdists = sorted(dist.glob(f"cph_ai_companion-{VERSION}.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ReleaseError("exact_wheel_and_sdist_required")
    payloads, digest = mod_payloads(wheels[0])
    validate_sdist(sdists[0], payloads, digest)
    record = (_compatibility_record(compatibility, digest, sha256(wheels[0]))
              if compatibility is not None else _candidate_record(digest))
    if windows_bundle and not record["validated_combinations"]:
        record["target_platform"] = "windows-x86_64"
    mod_zip = dist / f"cph_ai_companion-{VERSION}-mod.zip"
    with zipfile.ZipFile(mod_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(payloads.items()):
            info = zipfile.ZipInfo("cph_ai_companion/" + name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    artifact_names = [wheels[0].name, sdists[0].name, mod_zip.name]
    for name in ("requirements.lock", "build-requirements.lock", "uv.lock", "LICENSE", "NOTICE", "THIRD_PARTY.md", "README.md"):
        source = root / name
        if not source.is_file():
            raise ReleaseError("release_material_missing")
        _copy(source, dist / name)
        artifact_names.append(name)
    record["artifacts"] = {
        name: {"sha256": sha256(dist / name), "bytes": (dist / name).stat().st_size}
        for name in sorted(artifact_names)
    }
    manifest = dist / "compatibility.json"
    manifest.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifact_names.append(manifest.name)
    checksums = dist / "SHA256SUMS"
    checksums.write_text("".join(f"{sha256(dist / name)}  {name}\n" for name in sorted(artifact_names)), encoding="ascii")
    result = {"state": "candidate_assembled", "version": VERSION, "schema_digest": digest,
            "validated_combinations": record["validated_combinations"], "published": False,
            "artifacts": sorted([*artifact_names, checksums.name])}
    if windows_bundle:
        spec = importlib.util.spec_from_file_location("cph_windows_bundle", Path(__file__).with_name("build_windows_bundle.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result["windows_bundle"] = module.bundle(windows_python, windows_site_packages, wheels[0],
                                                 windows_game_root, root / "requirements.lock")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--windows-python", type=Path, help="CPython 3.12 Windows x64 installation to ship")
    parser.add_argument("--windows-site-packages", type=Path, help="SDK-only environment installed from requirements.lock")
    parser.add_argument("--windows-game-root", type=Path, help="fresh staged game root receiving the built-in Mod and runtime")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--candidate-only", action="store_true",
                      help="assemble an unvalidated candidate without importing recorded PASS results (default)")
    mode.add_argument("--compatibility", type=Path,
                      help="explicit evidence file; every validated combination must name this exact wheel hash")
    args = parser.parse_args()
    try:
        result = assemble(args.dist, root=Path(__file__).resolve().parents[1],
                          compatibility=args.compatibility, candidate_only=args.candidate_only,
                          windows_python=args.windows_python, windows_site_packages=args.windows_site_packages,
                          windows_game_root=args.windows_game_root)
    except (ReleaseError, OSError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, "release assembly failed: " + (str(error) if isinstance(error, ReleaseError) else type(error).__name__) + "\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
