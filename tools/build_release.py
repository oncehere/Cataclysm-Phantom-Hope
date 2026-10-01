#!/usr/bin/env python3
"""Assemble a candidate from built artifacts; never infer acceptance or publish."""
from __future__ import annotations

import argparse
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import zipfile

VERSION = "0.1.0"
MOD_PREFIX = "cph_ai_companion/resources/mod/"
PROTOCOL_FILE = "cph_ai_companion/resources/protocol/protocol.json"


class ReleaseError(ValueError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mod_payloads(wheel: Path) -> tuple[dict[str, bytes], str]:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ReleaseError("duplicate_wheel_entries")
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise ReleaseError("invalid_wheel_metadata")
        metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
        if metadata.get("Name") != "cph-ai-companion" or metadata.get("Version") != VERSION:
            raise ReleaseError("wrong_project_wheel")
        if metadata.get("Requires-Python") != "<3.13,>=3.12":
            raise ReleaseError("wrong_python_requirement")
        payloads = {}
        for name in names:
            if not name.startswith(MOD_PREFIX) or name.endswith("/"):
                continue
            relative = name[len(MOD_PREFIX):]
            path = PurePosixPath(relative)
            if not relative or path.is_absolute() or ".." in path.parts or "\\" in relative:
                raise ReleaseError("invalid_mod_resource")
            payloads[relative] = archive.read(name)
        if not {"mod.lua", "main.lua"}.issubset(payloads):
            raise ReleaseError("mod_resources_missing")
        if PROTOCOL_FILE not in names:
            raise ReleaseError("protocol_resource_missing")
        protocol_data = archive.read(PROTOCOL_FILE)
        protocol = json.loads(protocol_data)
        if protocol.get("protocol_version") != "1.0":
            raise ReleaseError("unsupported_protocol")
        return payloads, hashlib.sha256(protocol_data).hexdigest()


def _copy(source: Path, destination: Path) -> None:
    if source.resolve() != destination.resolve():
        shutil.copyfile(source, destination)


def assemble(dist: Path, *, root: Path, compatibility: Path | None = None) -> dict:
    dist = dist.resolve()
    root = root.resolve()
    if not dist.is_dir():
        raise ReleaseError("built_artifact_directory_missing")
    wheels = sorted(dist.glob(f"cph_ai_companion-{VERSION}-*.whl"))
    sdists = sorted(dist.glob(f"cph_ai_companion-{VERSION}.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ReleaseError("exact_wheel_and_sdist_required")
    payloads, digest = mod_payloads(wheels[0])
    record = json.loads((compatibility or root / "docs/compatibility.json").read_text(encoding="utf-8"))
    if (not isinstance(record, dict) or record.get("schema_version") != 1
            or record.get("package_version") != VERSION or record.get("protocol_version") != "1.0"
            or not isinstance(record.get("validated_combinations"), list)):
        raise ReleaseError("invalid_compatibility_record")
    # Package assembly cannot turn an untested candidate into a validated pair.
    record["schema_digest"] = digest
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
    return {"state": "candidate_assembled", "version": VERSION, "schema_digest": digest,
            "validated_combinations": record["validated_combinations"], "published": False,
            "artifacts": sorted([*artifact_names, checksums.name])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--compatibility", type=Path)
    args = parser.parse_args()
    try:
        result = assemble(args.dist, root=Path(__file__).resolve().parents[1], compatibility=args.compatibility)
    except (ReleaseError, OSError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, "release assembly failed: " + (str(error) if isinstance(error, ReleaseError) else type(error).__name__) + "\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
