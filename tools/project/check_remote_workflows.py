#!/usr/bin/env python3
"""Audit the reviewed successor to the zero-workflow initialization policy.

This bounded file/action inventory and checkout-depth check complement
actionlint and remote permission readback, not a full workflow security audit.
"""

import argparse
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
ACTION = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}")
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*(\S+)", re.MULTILINE)


def candidate_checkout_errors(contents):
    """Tooling needs frozen migration history; native needs two merge parents."""
    import yaml

    try:
        document = yaml.safe_load(contents)
    except yaml.YAMLError as error:
        raise ValueError("invalid project CI YAML") from error
    jobs = document.get("jobs", {}) if isinstance(document, dict) else {}
    errors = []
    for name, depth in (("tooling", 0), ("native", 2)):
        job = jobs.get(name, {})
        steps = job.get("steps", []) if isinstance(job, dict) else []
        candidates = [
            step
            for step in steps
            if isinstance(step, dict)
            and step.get("name") == "Checkout exact merge candidate"
        ]
        if len(candidates) != 1:
            errors.append(
                "missing or duplicate " + name + " candidate checkout"
            )
            continue
        value = candidates[0].get("with", {}).get("fetch-depth")
        if type(value) is not int or value != depth:
            errors.append(
                f"{name} candidate checkout requires fetch-depth {depth}"
            )
    return errors


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
        if path.name == "project-ci.yml":
            errors.extend(candidate_checkout_errors(path.read_text()))
        for ref in USES.findall(path.read_text()):
            references.add(ref)
            if ref not in allowed:
                errors.append("unapproved action in " + path.name + ": " + ref)
    if found != set(policy["workflows"]):
        errors.append("active workflow inventory differs from reviewed policy")
    return {"status": "FAIL" if errors else "PASS",
            "scope": "workflow_inventory_action_pins_and_checkout_depths",
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
