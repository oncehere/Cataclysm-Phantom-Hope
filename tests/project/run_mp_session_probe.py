#!/usr/bin/env python3
"""Run the real MP Catch case in two isolated native processes and retain \
evidence."""

import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--timeout", type=float, default=120,
        help=("Whole-process limit including game-data initialization; "
              "case limit is 20s."))
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    source = args.source_dir.resolve(strict=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ")
    output = Path(tempfile.mkdtemp(
        prefix=f"session-{stamp}-", dir=args.output_dir.resolve()))
    ipc = output / "ipc"
    ipc.mkdir()
    processes: dict[str, subprocess.Popen] = {}
    logs = {}
    commands = {}
    started = time.monotonic()
    timed_out = False
    try:
        for role in ("host", "client"):
            user_dir = output / f"{role}-user"
            user_dir.mkdir()
            command = [str(binary), "mp_native_two_process_session",
                       "--rng-seed", "424242", "--mods", "ccb", "--user-dir",
                       str(user_dir), "--drop-world"]
            commands[role] = command
            env = os.environ.copy()
            env["CPH_MP_PROBE_ROLE"] = role
            env["CPH_MP_PROBE_IPC"] = str(ipc)
            logs[role] = (output / f"{role}.log").open("wb")
            processes[role] = subprocess.Popen(
                command, cwd=source, env=env, stdout=logs[role],
                stderr=subprocess.STDOUT)
        while any(process.poll() is None
                  for process in processes.values()):
            if any(process.poll() not in (None, 0)
                   for process in processes.values()):
                (ipc / "abort").write_text(
                    "peer process failed\n", encoding="utf-8")
            if time.monotonic() - started > args.timeout:
                timed_out = True
                (ipc / "abort").write_text(
                    "launcher timeout\n", encoding="utf-8")
                break
            time.sleep(0.05)
    finally:
        for process in processes.values():
            if process.poll() is None:
                process.terminate()
        for process in processes.values():
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for log in logs.values():
            log.close()
    returncodes = {role: process.returncode
                   for role, process in processes.items()}
    completed = all((ipc / f"{role}-done").is_file()
                    for role in ("host", "client"))
    passed = len(processes) == 2 and not timed_out and completed and all(
        code == 0 for code in returncodes.values())
    result = {
        "status": "PASS" if passed else "FAIL",
        "test_case": "mp_native_two_process_session",
        "binary": str(binary),
        "source_dir": str(source),
        "rng_seed": 424242,
        "commands": commands,
        "returncodes": returncodes,
        "timed_out": timed_out,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "completed_checkpoints": sorted(
            path.name for path in ipc.iterdir() if path.is_file()),
        "coverage": ("real JOIN/proxies, intent sender/receiver reset, "
                     "grant/move/state, sleep ACK, disconnect"),
        "limits": ("loopback native processes; no GUI, WAN, real save, "
                   "Windows runtime or hosted CI"),
    }
    (output / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({"status": result["status"], "evidence": str(output)},
                     ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
