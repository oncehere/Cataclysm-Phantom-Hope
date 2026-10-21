#!/usr/bin/env python3
"""Prepare and run small, isolated CPH manual acceptance scenarios."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
MANIFESTS = Path(__file__).resolve().parent / "manifests"
MARKER = "cph-scenario-run.json"
ID = re.compile(r"[a-z][a-z0-9-]{0,59}\Z")


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_manifest(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    fields = {"schema_version", "id", "title", "mods", "fixture_files", "setup", "checks"}
    if not isinstance(value, dict) or set(value) != fields or value["schema_version"] != 1:
        raise ValueError(f"Invalid scenario manifest: {path.name}")
    if not isinstance(value["id"], str) or not ID.fullmatch(value["id"]):
        raise ValueError("Invalid scenario ID")
    if not isinstance(value["title"], str) or not value["title"].strip():
        raise ValueError("Scenario title is required")
    for field in ("mods", "fixture_files", "setup"):
        if not isinstance(value[field], list) or not all(isinstance(x, str) and x for x in value[field]):
            raise ValueError(f"Invalid {field}")
    if not value["mods"] or len(set(value["mods"])) != len(value["mods"]):
        raise ValueError("Scenario needs distinct Mod IDs")
    for item in value["fixture_files"]:
        parts = item.replace("\\", "/").split("/")
        if any(x in ("", ".", "..") for x in parts) or ":" in item or item.startswith("/"):
            raise ValueError("Fixture paths must stay relative to source")
    checks = value["checks"]
    if not isinstance(checks, list) or not checks:
        raise ValueError("Scenario needs manual checks")
    check_ids = set()
    for check in checks:
        if (not isinstance(check, dict) or set(check) != {"id", "steps", "expected"}
                or not isinstance(check["id"], str) or not ID.fullmatch(check["id"])
                or check["id"] in check_ids):
            raise ValueError("Invalid or duplicate manual check")
        check_ids.add(check["id"])
        if not all(isinstance(check[x], str) and check[x].strip() for x in ("steps", "expected")):
            raise ValueError("Manual steps and expected observations are required")
    return value


def manifests() -> dict[str, tuple[Path, dict]]:
    result = {}
    for path in sorted(MANIFESTS.glob("*.json")):
        value = load_manifest(path)
        if value["id"] in result:
            raise ValueError("Duplicate scenario ID")
        result[value["id"]] = (path, value)
    return result


def checklist(manifest: dict) -> str:
    lines = [f"# {manifest['title']}", "", "所有游戏内结果初始为 NOT_RUN；启动成功不代表验收通过。",
             "", "## 准备", "", f"世界仅启用这些 Mod：{', '.join(manifest['mods'])}", "",
             "新隔离 config 已预设上述默认 Mod；创建世界时在 GUI 核对即可，不用重复添加。已有世界不受影响。", ""]
    lines.extend(f"- {item}" for item in manifest["setup"])
    for check in manifest["checks"]:
        lines.extend(["", f"## {check['id']} — NOT_RUN", "", check["steps"], "",
                      "预期：" + check["expected"], "", "实际观察 / PASS 或 FAIL："])
    return "\n".join(lines) + "\n"


def prepare(scenario: str, run_dir: Path, game: Path, source: Path, base: Path) -> dict:
    choices = manifests()
    if scenario not in choices:
        raise ValueError("Unknown scenario; use list")
    manifest_path, manifest = choices[scenario]
    run_dir, game, source, base = [x.resolve() for x in (run_dir, game, source, base)]
    if not game.is_file() or not (base / "data" / "mods").is_dir() or not (source / "data" / "mods").is_dir():
        raise ValueError("Game binary, base path and CPH source data must exist")
    fixtures = {}
    for name in manifest["fixture_files"]:
        path = (source / name).resolve()
        if not path.is_relative_to(source) or not path.is_file():
            raise ValueError(f"Missing or escaped fixture: {name}")
        fixtures[name] = digest(path)
        asset = (base / name).resolve()
        if not asset.is_relative_to(base) or not asset.is_file() or digest(asset) != fixtures[name]:
            raise ValueError(f"Base path needs the matching scenario fixture: {name}; use the source root as --basepath or update the test app data")
    if run_dir.exists():
        raise ValueError("Run directory must not exist; use run/rerun for an existing prepared run")
    run_dir.mkdir(parents=True)
    for name in ("userdata", "config", "attempts"):
        (run_dir / name).mkdir()
    # The game's existing default-Mod contract affects newly created worlds;
    # it is not a world save and never modifies an existing run's configuration.
    write_json(run_dir / "config" / "user-default-mods.json", {
        "type": "MOD_INFO", "id": "user:default", "conflicts": [],
        "dependencies": manifest["mods"],
        "//": "Scenario defaults for newly created isolated test worlds only.",
        "obsolete": True,
    })
    record = {"schema_version": 1, "kind": "cph-isolated-scenario", "run_dir": str(run_dir),
              "scenario": scenario, "created_at": stamp(), "game": str(game),
              "game_sha256": digest(game), "source_root": str(source), "base_path": str(base),
              "fixture_sha256": fixtures, "manifest_sha256": digest(manifest_path)}
    (run_dir / "scenario.json").write_bytes(manifest_path.read_bytes())
    (run_dir / "CHECKLIST.md").write_text(checklist(manifest), encoding="utf-8")
    write_json(run_dir / MARKER, record)
    return record


def read_run(run_dir: Path) -> tuple[Path, dict, dict]:
    run_dir = run_dir.resolve()
    record = json.loads((run_dir / MARKER).read_text(encoding="utf-8"))
    if (record.get("kind") != "cph-isolated-scenario" or record.get("schema_version") != 1
            or record.get("run_dir") != str(run_dir)):
        raise ValueError("This is not the original prepared scenario directory")
    manifest = load_manifest(run_dir / "scenario.json")
    if manifest["id"] != record["scenario"] or digest(run_dir / "scenario.json") != record["manifest_sha256"]:
        raise ValueError("Prepared manifest changed; prepare a fresh run instead")
    game, source = Path(record["game"]), Path(record["source_root"])
    if digest(game) != record["game_sha256"]:
        raise ValueError("Game binary changed; prepare a fresh run instead")
    for name, expected in record["fixture_sha256"].items():
        path = (source / name).resolve()
        if not path.is_relative_to(source) or digest(path) != expected:
            raise ValueError("Scenario fixture changed; prepare a fresh run instead")
        base = Path(record["base_path"])
        asset = (base / name).resolve()
        if not asset.is_relative_to(base) or digest(asset) != expected:
            raise ValueError("Base-path scenario fixture changed; prepare a fresh run instead")
    for name in ("userdata", "config", "attempts"):
        path = run_dir / name
        if path.is_symlink() or not path.is_dir() or path.resolve() != path:
            raise ValueError("Scenario output directories must stay inside their prepared run")
    return run_dir, record, manifest


def directory_arg(path: Path) -> str:
    return path.as_posix().rstrip("/") + "/"


def command(run_dir: Path, record: dict, manifest: dict, check_mods: bool) -> list[str]:
    args = [record["game"], "--basepath", directory_arg(Path(record["base_path"])),
            "--userdir", directory_arg(run_dir / "userdata"),
            "--configdir", directory_arg(run_dir / "config")]
    if check_mods:
        args.extend(["--datadir", directory_arg(Path(record["base_path"]) / "data")])
        # This option consumes the remainder of argv. Never append launcher options after it.
        args.extend(["--check-mods", *manifest["mods"]])
    return args


@contextmanager
def run_lock(run_dir: Path):
    lock = run_dir / "launch.lock"
    try:
        stream = lock.open("x", encoding="utf-8")
    except FileExistsError as error:
        raise ValueError("A launch lock exists. Close that game first; after a crash verify it exited before removing launch.lock") from error
    ownership = {"release": True}
    try:
        with stream:
            stream.write(stamp() + "\n")
        yield ownership
    finally:
        if ownership["release"]:
            lock.unlink()


def launch(run_dir: Path, *, check_mods: bool = False, dry_run: bool = False) -> int:
    run_dir, record, manifest = read_run(run_dir)
    args = command(run_dir, record, manifest, check_mods)
    if dry_run:
        print(json.dumps({"argv": args, "cwd": record["base_path"], "gameplay": "NOT_RUN"}, ensure_ascii=False))
        return 0
    with run_lock(run_dir) as ownership:
        attempts = run_dir / "attempts"
        number = max((int(path.stem) for path in attempts.glob("*.json") if path.stem.isdigit()), default=0) + 1
        path = attempts / f"{number:04d}.json"
        result = {"started_at": stamp(), "command": args, "mode": "check-mods" if check_mods else "play",
                  "gameplay": "NOT_RUN", "exit_code": None}
        write_json(path, result)
        process = None
        try:
            process = subprocess.Popen(args, cwd=record["base_path"])
            result["exit_code"] = process.wait()
            return result["exit_code"]
        finally:
            if process is not None and process.poll() is None:
                # Ctrl-C or another parent-side failure must not permit a second
                # game against the still-running child's userdata.
                ownership["release"] = False
                result["game_still_running"] = True
            result["finished_at"] = stamp()
            write_json(path, result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("list", help="List the supplied manual scenarios")
    setup = sub.add_parser("prepare", help="Create a new isolated run; never copy real saves/configuration")
    setup.add_argument("scenario")
    setup.add_argument("--run-dir", required=True, type=Path)
    setup.add_argument("--game", required=True, type=Path)
    setup.add_argument("--source-root", type=Path, default=ROOT)
    setup.add_argument("--basepath", type=Path, default=ROOT, help="Game assets root, normally source root or installed app directory")
    for name in ("run", "rerun", "check-mods"):
        entry = sub.add_parser(name, help="Launch the same isolated userdata again" if name == "rerun" else None)
        entry.add_argument("--run-dir", required=True, type=Path)
        entry.add_argument("--dry-run", action="store_true", help="Print argv only; launch no process")
    args = parser.parse_args(argv)
    try:
        if args.operation == "list":
            for key, (_, value) in manifests().items():
                print(f"{key}: {value['title']}")
            return 0
        if args.operation == "prepare":
            record = prepare(args.scenario, args.run_dir, args.game, args.source_root, args.basepath)
            print(f"Prepared {record['run_dir']}; read CHECKLIST.md before launching")
            return 0
        return launch(args.run_dir, check_mods=args.operation == "check-mods", dry_run=args.dry_run)
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"Scenario error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
