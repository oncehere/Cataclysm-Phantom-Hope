#!/usr/bin/env python3
"""Export a fixed protocol snapshot; never fetch a moving remote version."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RESOURCE = ROOT / "src/cph_ai_companion/resources/protocol"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cph-root", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    changed = subprocess.check_output(["git", "status", "--porcelain", "--", str(RESOURCE.relative_to(ROOT))], cwd=ROOT, text=True)
    if changed:
        parser.error("commit the authoritative protocol before exporting")
    destination = args.cph_root.resolve() / "data/reference/actor_control"
    version = json.loads((RESOURCE / "protocol.json").read_text())["protocol_version"]
    meta = {"schema_version": 1, "protocol_version": version, "source_project": "cph-ai-companion",
            "source_revision": revision, "files": {}}
    for name in ("protocol.json", "fixtures.json"):
        data = (RESOURCE / name).read_bytes()
        meta["files"][name] = hashlib.sha256(data).hexdigest()
        if args.check:
            if not (destination / name).is_file() or (destination / name).read_bytes() != data:
                parser.error("CPH protocol snapshot differs")
        else:
            destination.mkdir(parents=True, exist_ok=True)
            (destination / name).write_bytes(data)
    encoded = (json.dumps(meta, indent=2, sort_keys=True) + "\n").encode()
    if args.check:
        existing = json.loads((destination / "source.json").read_text())
        # Later independent commits need not replace a matching immutable snapshot.
        if existing["files"] != meta["files"] or existing["protocol_version"] != version:
            parser.error("CPH source metadata differs")
    else:
        (destination / "source.json").write_bytes(encoded)
    subprocess.run(["python3", str(args.cph_root / "tools/actor_control/generate_protocol.py"),
                    *(["--check"] if args.check else [])], cwd=args.cph_root, check=True)


if __name__ == "__main__":
    main()
