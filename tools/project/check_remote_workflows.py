#!/usr/bin/env python3
"""Audit the reviewed successor to the zero-workflow initialization policy.

This bounded file/action inventory complements actionlint and remote permission
readback. It does not claim that text inspection validates workflow semantics.
"""

import argparse
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
ACTION = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}")
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*(\S+)", re.MULTILINE)


def inspect(repo):
    repo = Path(repo)
    policy_path = repo / "project/remote-actions-policy.json"
    policy = json.loads(policy_path.read_text())
    allowed = set(policy["allowed_actions"])
    if not allowed or any(not ACTION.fullmatch(ref) for ref in allowed):
        raise ValueError("allowed actions must be exact full-SHA references")
    directory = repo / ".github/workflows"
    found = set()
    errors = []
    references = set()
    if directory.is_symlink():
        raise ValueError("workflow directory cannot be a symlink")
    for path in sorted(directory.iterdir()):
        if path.is_symlink() or not path.is_file():
            errors.append("unexpected workflow entry: " + path.name)
            continue
        if path.suffix not in (".yml", ".yaml"):
            errors.append("unexpected workflow file: " + path.name)
            continue
        found.add(path.name)
        for ref in USES.findall(path.read_text()):
            references.add(ref)
            if ref not in allowed:
                errors.append("unapproved action in " + path.name + ": " + ref)
    if found != set(policy["workflows"]):
        errors.append("active workflow inventory differs from reviewed policy")
    return {"status": "FAIL" if errors else "PASS",
            "scope": "workflow_inventory_and_action_pins_only",
            "workflows": sorted(found), "actions": sorted(references),
            "findings": errors, "remote_settings_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        report = inspect(args.repo)
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"status": "FAIL", "reason": str(error)}))
        return 1
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
