#!/usr/bin/env python3
"""Offline one-shot Podman smoke test; build the image before running this."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="localhost/po-keeper:0.1.0rc1")
    parser.add_argument("--storage-root", type=Path)
    parser.add_argument("--runroot", type=Path)
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    prefix = ["podman"]
    if args.storage_root:
        prefix += ["--root", str(args.storage_root), "--storage-driver", "vfs"]
    if args.runroot:
        prefix += ["--runroot", str(args.runroot)]
    env = dict(os.environ)
    if args.runtime_dir:
        env["XDG_RUNTIME_DIR"] = str(args.runtime_dir)
    env.pop("GEMINI_API_KEY", None)
    env.pop("GOOGLE_API_KEY", None)
    record = {"commands": [], "status": "FAIL"}

    def execute(argv):
        result = subprocess.run(argv, env=env, capture_output=True, text=True)
        record["commands"].append({"argv": argv, "exit_code": result.returncode,
                                   "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode:
            raise RuntimeError(f"container command failed: {argv}")
        return result.stdout

    try:
        record["image_id"] = execute(prefix + ["image", "inspect", "--format", "{{.Id}}", args.image]).strip()
        probe = "import pathlib,json,hashlib; p=pathlib.Path('/opt/pokeeper/src/pokeeper'); print(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.glob('*.py')}))"
        record["source_sha256"] = json.loads(execute(prefix + ["run", "--rm", "--network=none", "--entrypoint", "python", args.image, "-c", probe]))
        source = Path(__file__).resolve().parents[1] / "src" / "pokeeper"
        expected = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob("*.py")}
        assert record["source_sha256"] == expected, "container source differs from current source"
        with tempfile.TemporaryDirectory(prefix="pokeeper-container-smoke-") as temp:
            root = Path(temp)
            demo = Path(__file__).resolve().parents[1] / "examples" / "demo"
            for name in ("project.toml", "messages.pot", "upstream.po"):
                shutil.copyfile(demo / name, root / name)
            run = prefix + ["run", "--rm", "--userns=keep-id", "--network=none",
                            "-v", f"{root}:/work", "-w", "/work", args.image]
            execute(run + ["--version"])
            execute(run + ["plan", "--config", "project.toml", "--candidate", "review-1"])
            execute(run + ["apply", "review-1"])
            execute(run + ["check", "--config", "project.toml"])
            execute(run + ["compile", "--config", "project.toml", "--output", "output.mo"])
            original = (root / "output.po").read_bytes()
            state = (root / ".pokeeper" / "state.json").read_bytes()
            execute(run + ["plan", "--config", "project.toml", "--candidate", "review-2"])
            execute(run + ["apply", "review-2"])
            assert (root / "output.po").read_bytes() == original
            assert (root / ".pokeeper" / "state.json").read_bytes() == state
            report = json.loads((root / "review-2" / "report.json").read_bytes())
            assert not report["human_changes"] and len(report["gaps"]) == 1
            record["po_sha256"] = hashlib.sha256(original).hexdigest()
            record["mo_bytes"] = (root / "output.mo").stat().st_size
            record["unchanged_po_and_state"] = True
            record["network"] = "none"
        record["status"] = "PASS"
    finally:
        args.evidence.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": record["status"], "evidence": str(args.evidence)}))


if __name__ == "__main__":
    main()
