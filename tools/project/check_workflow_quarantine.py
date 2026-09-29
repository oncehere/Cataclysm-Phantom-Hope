#!/usr/bin/env python3
"""Read-only E0 check: Git workflow provenance, no active CI entrypoints.

This is an initialization safeguard, not a GitHub merge or release gate.
Enabling a workflow requires an explicitly reviewed successor policy.
No command-line allowlist silently makes a workflow trusted.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from preflight import rejected_git_environment


BASELINE = "bcb85682f3d28ab0f0123b05e45651bb9888b61b"
SOURCE_REPOSITORY = "CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb"
SOURCE_DIRECTORY = ".github/workflows"
QUARANTINE_DIRECTORY = "project/inherited-workflows"


class InspectionError(Exception):
    """The Git source of truth could not be inspected."""


def git(repo, *args):
    unexpected = rejected_git_environment(os.environ)
    if unexpected:
        raise InspectionError(
            "refusing Git environment overrides: " + ", ".join(unexpected)
        )
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    environment.update(
        GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1",
        GIT_TERMINAL_PROMPT="0", GIT_PAGER="cat",
        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, LC_ALL="C",
    )
    result = subprocess.run(
        ["git", "--no-replace-objects", "-c", "core.fsmonitor=false",
         "-c", "core.untrackedCache=false",
         "-c", "core.hooksPath=" + os.devnull,
         "-c", "protocol.allow=never", "-C", str(repo), *args],
        capture_output=True, check=False, env=environment, timeout=120,
    )
    if result.returncode:
        raise InspectionError(
            f"git {args[0]} failed with exit code {result.returncode}"
        )
    return result.stdout


def source_manifest(repo, baseline):
    if not re.fullmatch(r"[0-9a-f]{40}", baseline):
        raise InspectionError("baseline must be a full lowercase commit SHA")
    git(repo, "cat-file", "-e", f"{baseline}^{{commit}}")
    tree = git(repo, "ls-tree", "-rz", baseline, SOURCE_DIRECTORY)
    workflows = []
    for entry in tree.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, blob_id = metadata.decode("ascii").split()
        path = raw_path.decode("utf-8")
        if Path(path).suffix not in (".yml", ".yaml"):
            continue
        if mode not in ("100644", "100755") or kind != "blob":
            raise InspectionError(
                f"source workflow is not a regular file: {path}"
            )
        content = git(repo, "cat-file", "blob", blob_id)
        workflows.append({
            "name": path.removeprefix(SOURCE_DIRECTORY + "/"),
            "source_path": path,
            "blob_id": blob_id,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        })
    if not workflows:
        raise InspectionError("baseline contains no workflow files")
    return {
        "schema_version": 1,
        "source_repository": SOURCE_REPOSITORY,
        "source_commit": baseline,
        "workflow_count": len(workflows),
        "workflows": workflows,
    }


def symlink_component(repo, relative):
    current = repo
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            return current.relative_to(repo).as_posix()
    return None


def inspect(repo, baseline=BASELINE):
    repo = Path(repo).resolve()
    root = Path(git(repo, "rev-parse", "--show-toplevel").decode().strip())
    if root.resolve() != repo:
        raise InspectionError("--repo must name the Git repository root")
    replacements = git(
        repo, "for-each-ref", "--format=%(refname)", "refs/replace/"
    )
    if replacements.strip():
        raise InspectionError(
            "replacement refs are not accepted for source verification"
        )
    common_path = git(repo, "rev-parse", "--git-common-dir").decode().strip()
    common = (repo / common_path).resolve()
    grafts = common / "info/grafts"
    if grafts.exists() or grafts.is_symlink():
        raise InspectionError(
            "legacy graft file is not accepted for source verification"
        )
    expected = source_manifest(repo, baseline)
    findings = []
    manifest_matches = False
    active = []
    quarantine = repo / QUARANTINE_DIRECTORY
    unsafe = symlink_component(repo, QUARANTINE_DIRECTORY)
    if unsafe:
        findings.append(f"quarantine path contains symlink: {unsafe}")
    else:
        # Originals remain in the pinned Git history; keep only the inventory
        # and audit metadata here, not another maintained copy of each YAML.
        if quarantine.exists():
            for path in sorted(quarantine.rglob("*")):
                relative = path.relative_to(quarantine).as_posix()
                if path.is_symlink():
                    findings.append(f"symlink in quarantine: {relative}")
                elif path.suffix in (".yml", ".yaml"):
                    findings.append(
                        f"redundant workflow copy in inventory: {relative}"
                    )
        manifest_path = quarantine / "manifest.json"
        if manifest_path.is_symlink():
            findings.append("quarantine manifest must not be a symlink")
        else:
            try:
                manifest = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                findings.append(
                    "quarantine manifest is missing or invalid JSON"
                )
            else:
                manifest_matches = manifest == expected
                if not manifest_matches:
                    findings.append(
                        "quarantine manifest differs from Git source inventory"
                    )

    unsafe_active = symlink_component(repo, SOURCE_DIRECTORY)
    if unsafe_active:
        findings.append(
            f"active workflow path contains symlink: {unsafe_active}"
        )
    else:
        for path in sorted((repo / SOURCE_DIRECTORY).rglob("*")):
            relative = path.relative_to(repo).as_posix()
            if path.is_symlink():
                findings.append(
                    f"symlink in active workflow directory: {relative}"
                )
            if path.suffix in (".yml", ".yaml"):
                active.append(relative)
                findings.append(
                    "active workflow forbidden during initialization: " +
                    relative
                )
    return {
        "status": "FAIL" if findings else "PASS",
        "scope": "local_initialization_quarantine_only",
        "source_commit": baseline,
        "source_storage": "git_objects",
        "expected_workflows": expected["workflow_count"],
        "checked_workflows": expected["workflows"],
        "manifest_matches_source": manifest_matches,
        "active_workflows": active,
        "github_deployment_verified": False,
        "findings": findings,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument(
        "--baseline", default=BASELINE,
        help="source commit (override only for explicit fixture/source audit)",
    )
    args = parser.parse_args(argv)
    try:
        report = inspect(args.repo, args.baseline)
    except (InspectionError, OSError, UnicodeError, ValueError,
            subprocess.TimeoutExpired) as error:
        print(json.dumps(
            {"status": "FAIL", "error": str(error)}, ensure_ascii=False
        ))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
