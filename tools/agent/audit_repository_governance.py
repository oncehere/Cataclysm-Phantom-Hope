#!/usr/bin/env python3
"""Validate CPH's read-only GitHub snapshot and deferred governance gates."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[2]
TARGET_PATH = ROOT / "ai/repository-settings.target.yml"
SCHEMA_PATH = ROOT / "ai/repository-settings.target.schema.json"
DEPENDABOT_PATH = ROOT / ".github/dependabot.yml"
ALLOWED_PERMISSION_LEVELS = {"none", "read", "write"}
ALLOWED_PERMISSION_SCOPES = {
    "actions", "attestations", "checks", "contents", "deployments",
    "discussions", "id-token", "issues", "models", "packages", "pages",
    "pull-requests", "security-events", "statuses",
}


def load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain a mapping")
    return data


def tracked_paths(*pathspecs: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", *pathspecs],
        cwd=ROOT, check=True, capture_output=True,
    )
    return sorted(
        item.decode("utf-8") for item in result.stdout.split(b"\0") if item
    )


def validate_target(
    target: dict, *, as_of: date | None = None,
    max_age_days: int | None = None,
) -> list[str]:
    """Check local consistency; never treat a snapshot as live deployment proof."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    errors = [
        f"schema {'.'.join(map(str, error.absolute_path)) or '<root>'}: "
        f"{error.message}"
        for error in sorted(validator.iter_errors(target), key=str)
    ]
    if errors:
        return errors

    audit = target["audit"]
    repository = audit["repository"]
    entry = target["entries"][0]
    rulesets = audit["rulesets"]
    main_rulesets = [item for item in rulesets if item["branch"] == "main"]
    master_rulesets = [item for item in rulesets if item["branch"] == "master"]
    if len(main_rulesets) != 1 or len(master_rulesets) != 1:
        errors.append("audit must identify one main and one inherited master ruleset")
    else:
        main, master = main_rulesets[0], master_rulesets[0]
        if (entry["observed_ruleset_id"] != main["id"]
                or entry["observed_enforcement"] != main["enforcement"]):
            errors.append("main gate observation differs from the audited ruleset")
        if master["enforcement"] != "active":
            errors.append("inherited master preservation ruleset is not active")
    ids = [item["id"] for item in rulesets]
    if len(ids) != len(set(ids)):
        errors.append("duplicate audited ruleset IDs")

    if audit["actions"]["default_workflow_permissions"] != "read":
        errors.append("default Actions token permissions must remain read-only")
    if repository["allow_auto_merge"]:
        errors.append("repository auto-merge must remain disabled")
    if entry["observed_enforcement"] == "active" and not repository["main_protected"]:
        errors.append("active main ruleset conflicts with unprotected main snapshot")

    prerequisites = entry["prerequisites"]
    ready = all(prerequisites.values()) and not entry["blockers"]
    if entry["ready_to_enable"] != ready:
        errors.append("main gate readiness disagrees with its prerequisites/blockers")
    if entry["observed_enforcement"] == "active":
        if not entry["enabled_at"]:
            errors.append("active main gate needs an activation record")
        if not all(prerequisites.values()):
            errors.append("active main gate lacks verified Windows/Linux or trusted gate")
    elif entry["enabled_at"]:
        errors.append("disabled main gate must not claim an activation time")
    operational = (entry["observed_enforcement"] == "active"
                   and entry["post_activation_probe_verified"])
    if entry["operational"] != operational:
        errors.append("operational state needs an active gate and protected PR probe")
    if entry["post_activation_probe_verified"] and not entry["enabled_at"]:
        errors.append("protected PR probe cannot precede main gate activation")

    intake = target["post_merge_intake"]
    if intake["ready_to_enable"] != intake["cleanup_pr_merged"]:
        errors.append("public intake readiness requires the cleanup PR merge")
    if not intake["cleanup_pr_merged"] and (
        repository["has_issues"] or audit["security"]["private_vulnerability_reporting"]
    ):
        errors.append("Issues/PVR became active before the recorded cleanup PR merge")

    if max_age_days is not None:
        if max_age_days < 1:
            errors.append("max audit age must be positive")
        else:
            observed = date.fromisoformat(audit["observed_at"])
            reference = as_of or date.today()
            age = (reference - observed).days
            if age < 0:
                errors.append("audit date is later than the comparison date")
            elif age > max_age_days:
                errors.append(f"repository audit is {age} days old; limit is {max_age_days}")
    return errors


def validate_dependabot(config: dict) -> list[str]:
    errors: list[str] = []
    if config.get("version") != 2:
        errors.append("Dependabot config must use version 2")
    updates = config.get("updates")
    if not isinstance(updates, list):
        return errors + ["Dependabot updates must be a list"]
    actions = [
        item for item in updates
        if item.get("package-ecosystem") == "github-actions"
        and item.get("directory") == "/"
    ]
    if len(actions) != 1:
        return errors + ["Dependabot needs one root github-actions update"]
    schedule = actions[0].get("schedule", {})
    if schedule.get("interval") != "weekly":
        errors.append("GitHub Actions Dependabot updates must be weekly")
    if schedule.get("timezone") != "Asia/Shanghai":
        errors.append("Dependabot schedule must record Asia/Shanghai")
    limit = actions[0].get("open-pull-requests-limit")
    if not isinstance(limit, int) or limit < 1:
        errors.append("Dependabot open pull request limit must be positive")
    return errors


def workflow_permission_errors(path: str, workflow: dict) -> list[str]:
    errors: list[str] = []

    def check(value: object, location: str) -> None:
        if value == "write-all":
            errors.append(f"{path}: {location} uses forbidden write-all")
            return
        if value is None or value == "read-all":
            return
        if not isinstance(value, dict):
            errors.append(f"{path}: invalid permissions at {location}")
            return
        for scope, level in value.items():
            if scope not in ALLOWED_PERMISSION_SCOPES:
                errors.append(f"{path}: unknown {scope} permission at {location}")
            elif level not in ALLOWED_PERMISSION_LEVELS:
                errors.append(f"{path}: invalid {scope} permission at {location}: {level}")

    check(workflow.get("permissions"), "workflow")
    jobs = workflow.get("jobs", {})
    if not isinstance(jobs, dict):
        return errors + [f"{path}: jobs must be a mapping"]
    for job_id, job in jobs.items():
        if isinstance(job, dict):
            check(job.get("permissions"), f"job {job_id}")
    return errors


def validate_workflow_permissions() -> list[str]:
    errors: list[str] = []
    for path in tracked_paths(".github/workflows"):
        if path.endswith((".yml", ".yaml")):
            errors.extend(workflow_permission_errors(path, load_yaml(ROOT / path)))
    return errors


def validate_repository(
    *, as_of: date | None = None, max_age_days: int | None = None,
) -> tuple[dict, list[str]]:
    target = load_yaml(TARGET_PATH)
    errors = validate_target(target, as_of=as_of, max_age_days=max_age_days)
    errors.extend(validate_dependabot(load_yaml(DEPENDABOT_PATH)))
    errors.extend(validate_workflow_permissions())
    return target, errors


def summary(target: dict) -> str:
    audit = target["audit"]
    gate = target["entries"][0]
    return (
        "CPH governance snapshot is internally consistent: "
        f"main={audit['repository']['main_sha'][:12]}; "
        f"main-gate={gate['observed_enforcement']}; "
        f"operational={gate['operational']}; "
        f"issues={audit['repository']['has_issues']}; "
        f"PVR={audit['security']['private_vulnerability_reporting']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--as-of", type=date.fromisoformat)
    parser.add_argument("--max-age-days", type=int)
    parser.add_argument("--ruleset-json", action="store_true",
                        help="retired: CPH target is not a deployable ruleset payload")
    args = parser.parse_args()
    if args.ruleset_json:
        print("--ruleset-json is retired; inspect the live GitHub ruleset and gate policy",
              file=sys.stderr)
        return 2
    try:
        target, errors = validate_repository(
            as_of=args.as_of, max_age_days=args.max_age_days,
        )
    except (OSError, ValueError, subprocess.CalledProcessError,
            yaml.YAMLError) as error:
        print(error, file=sys.stderr)
        return 1
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(summary(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
