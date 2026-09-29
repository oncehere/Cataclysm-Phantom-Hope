#!/usr/bin/env python3
"""Exercise --check-mods with a matching native binary and isolated user Mods.

Run explicitly; this is a native content-loading test, not a Python-only unit
test.  The source data directory is read-only and every fixture is temporary.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


MOD_ID = "cph_check_mods_fixture"
DEPENDENCY_ID = "cph_check_mods_dependency"
EOC_ID = "EOC_CPH_CHECK_MODS_FIXTURE"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def mod_info(identifier, dependencies):
    return [{"type": "MOD_INFO", "id": identifier,
             "name": identifier, "authors": ["CPH native test"],
             "description": "Disposable content-loading fixture.",
             "category": "content", "dependencies": dependencies}]


def eoc(condition):
    return {"type": "effect_on_condition", "id": EOC_ID,
            "condition": {"math": [condition]}, "effect": []}


def run_case(binary, source, name):
    with tempfile.TemporaryDirectory(prefix="cph-check-mods-") as directory:
        root = Path(directory)
        user = root / "user"
        config = root / "config"
        config.mkdir()
        mod = user / "mods" / MOD_ID
        dependencies = ["ccb"]
        objects = [eoc("0 == 1")]
        if name == "inactive_interaction":
            write_json(mod / "mod_interactions" / "absent_fixture_mod" /
                       "overlay.json", [eoc("1 == 1")])
        elif name == "active_dependency_interaction":
            dependencies.append(DEPENDENCY_ID)
            write_json(user / "mods" / DEPENDENCY_ID / "modinfo.json",
                       mod_info(DEPENDENCY_ID, ["ccb"]))
            # Finalization must find the parent from the active interaction.
            # The EOC override also requires a distinct interaction source.
            objects.append({"type": "ITEM", "id": "cph_check_mods_child",
                            "copy-from": "cph_check_mods_parent",
                            "name": "integration child"})
            write_json(mod / "mod_interactions" / DEPENDENCY_ID /
                       "overlay.json", [
                           eoc("1 == 1"),
                           {"type": "ITEM", "id": "cph_check_mods_parent",
                            "copy-from": "rock", "name": "integration parent"},
                       ])
        elif name == "duplicate_source":
            objects.append(eoc("1 == 1"))
        else:
            raise ValueError(name)
        write_json(mod / "modinfo.json", mod_info(MOD_ID, dependencies))
        write_json(mod / "objects.json", objects)

        environment = dict(os.environ, SDL_VIDEODRIVER="dummy",
                           SDL_AUDIODRIVER="dummy", LANG="C", LC_ALL="C",
                           XDG_CACHE_HOME=str(root / "cache"),
                           XDG_CONFIG_HOME=str(root / "xdg-config"),
                           XDG_DATA_HOME=str(root / "xdg-data"))
        command = [str(binary), "--datadir", str(source / "data") + "/",
                   "--userdir", str(user) + "/",
                   "--configdir", str(config) + "/", "--check-mods", MOD_ID]
        start = time.monotonic()
        result = subprocess.run(command, cwd=source, env=environment,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                timeout=180)
        if name == "duplicate_source":
            passed = (result.returncode == 1 and
                      f"{EOC_ID} (effect_on_condition) has two definitions "
                      f"from the same source ({MOD_ID})!" in result.stdout)
        else:
            passed = result.returncode == 0
        return {"name": name, "command": command, "cwd": str(source),
                "exit_code": result.returncode, "passed": passed,
                "elapsed_seconds": round(time.monotonic() - start, 3),
                "output": result.stdout,
                "logs": {path.name: path.read_text(errors="replace")
                         for path in config.glob("*.log")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--source", type=Path,
                        default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    source = args.source.resolve(strict=True)
    binary_hash = hashlib.sha256(binary.read_bytes()).hexdigest()
    records = []
    for name in ("inactive_interaction", "active_dependency_interaction",
                 "duplicate_source"):
        result = run_case(binary, source, name)
        records.append(result)
        print(f"{name}: {'PASS' if result['passed'] else 'FAIL'} "
              f"(native exit {result['exit_code']})", flush=True)
    binary_unchanged = hashlib.sha256(binary.read_bytes()).hexdigest() == binary_hash
    report = {"binary": str(binary), "binary_sha256": binary_hash,
              "binary_unchanged": binary_unchanged,
              "source": str(source), "cases": records}
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    return int(not binary_unchanged or not all(row["passed"] for row in records))


if __name__ == "__main__":
    raise SystemExit(main())
