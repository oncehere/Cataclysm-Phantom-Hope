"""Read the exact companion identity, Mod bytes and protocol from a wheel."""
from __future__ import annotations

from email.parser import BytesParser
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

VERSION = "0.1.2.dev0"
PROTOCOL_VERSION = "1.2"
MOD_PREFIX = "cph_ai_companion/resources/mod/"
PROTOCOL_FILE = "cph_ai_companion/resources/protocol/protocol.json"


class ReleaseError(ValueError):
    pass


def _check_metadata(body: bytes, artifact: str) -> None:
    metadata = BytesParser().parsebytes(body)
    for field in ("Name", "Version", "Requires-Python"):
        if len(metadata.get_all(field, [])) != 1:
            raise ReleaseError("invalid_" + artifact + "_metadata")
    if metadata["Name"] != "cph-ai-companion" or metadata["Version"] != VERSION:
        raise ReleaseError("wrong_project_" + artifact)
    if metadata["Requires-Python"] != "<3.13,>=3.12":
        raise ReleaseError("wrong_python_requirement")


def mod_payloads(wheel: Path) -> tuple[dict[str, bytes], str]:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ReleaseError("duplicate_wheel_entries")
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise ReleaseError("invalid_wheel_metadata")
        _check_metadata(archive.read(metadata_names[0]), "wheel")
        payloads = {}
        for name in names:
            if not name.startswith(MOD_PREFIX) or name.endswith("/"):
                continue
            relative = name[len(MOD_PREFIX):]
            path = PurePosixPath(relative)
            if (not relative or path.is_absolute() or ".." in path.parts or "\\" in relative
                    or "\0" in relative or path.as_posix() != relative):
                raise ReleaseError("invalid_mod_resource")
            payloads[relative] = archive.read(name)
        if not {"mod.lua", "main.lua"}.issubset(payloads):
            raise ReleaseError("mod_resources_missing")
        if PROTOCOL_FILE not in names:
            raise ReleaseError("protocol_resource_missing")
        protocol_data = archive.read(PROTOCOL_FILE)
        protocol = json.loads(protocol_data)
        if protocol.get("protocol_version") != PROTOCOL_VERSION:
            raise ReleaseError("unsupported_protocol")
        return payloads, hashlib.sha256(protocol_data).hexdigest()
