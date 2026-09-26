#!/usr/bin/env python3
"""Local operator-control storage; never merges, publishes or enables jobs."""

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import tempfile


FIELDS = {
    "schema_version",
    "revision",
    "sync_paused",
    "release_paused",
    "blocked_candidates",
}


def candidate(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", value
    ):
        raise ValueError("invalid candidate identifier")
    return value


def validate(value):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("invalid operator-control fields")
    if (
        type(value["schema_version"]) is not int or
        value["schema_version"] != 1
    ):
        raise ValueError("unsupported operator-control schema")
    if type(value["revision"]) is not int or value["revision"] < 0:
        raise ValueError("invalid operator-control revision")
    for key in ("sync_paused", "release_paused"):
        if type(value[key]) is not bool:
            raise ValueError("pause fields must be booleans")
    blocked = value["blocked_candidates"]
    if (
        not isinstance(blocked, list) or
        not all(isinstance(item, str) for item in blocked) or
        len(blocked) != len(set(blocked))
    ):
        raise ValueError("invalid blocked-candidate list")
    for item in blocked:
        candidate(item)
    return value


def path_check(path):
    if not path.is_absolute() or path.is_symlink():
        raise ValueError("state must be an absolute non-symlink path")
    for parent in path.parents:
        if parent.is_symlink():
            raise ValueError("state parent may not be a symlink")
    source = Path(__file__).resolve().parents[2]
    if path.resolve().is_relative_to(source):
        raise ValueError("operator state must be outside this source checkout")
    if not path.parent.is_dir():
        raise ValueError("state parent directory must already exist")


@contextmanager
def locked(path):
    path_check(path)
    lock = path.with_name(path.name + ".lock")
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        path_check(path)
        yield
    finally:
        os.close(descriptor)


def read(path):
    path_check(path)
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("missing or oversized operator state; action denied")
    return validate(json.loads(path.read_text(encoding="utf-8")))


def save(path, state):
    validate(state)
    descriptor, name = tempfile.mkstemp(
        prefix=path.name + ".", dir=path.parent
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(state, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def initialize(path):
    with locked(path):
        if path.exists():
            raise ValueError("refusing to replace existing operator state")
        state = {
            "schema_version": 1,
            "revision": 0,
            "sync_paused": True,
            "release_paused": True,
            "blocked_candidates": [],
        }
        save(path, state)
        return state


def update(path, revision, action, identifier=None):
    with locked(path):
        state = read(path)
        if type(revision) is not int or revision != state["revision"]:
            raise ValueError(
                "stale operator revision; read current state again"
            )
        if action in {"pause-sync", "resume-sync"}:
            state["sync_paused"] = action == "pause-sync"
        elif action in {"pause-release", "resume-release"}:
            state["release_paused"] = action == "pause-release"
        elif action in {"block", "unblock"}:
            identifier = candidate(identifier)
            blocked = set(state["blocked_candidates"])
            if action == "block":
                blocked.add(identifier)
            else:
                blocked.discard(identifier)
            state["blocked_candidates"] = sorted(blocked)
        else:
            raise ValueError("unknown operator action")
        state["revision"] += 1
        save(path, state)
        return state


def check(path, action, identifier, expected_revision):
    """Re-read immediately before a future action; this is one prerequisite."""
    identifier = candidate(identifier)
    state = read(path)
    reasons = []
    if action not in {"merge", "publish-dev"}:
        reasons.append("unsupported action; stable is never authorized")
    if (
        type(expected_revision) is not int or
        expected_revision != state["revision"]
    ):
        reasons.append("operator state changed since this attempt began")
    if identifier in state["blocked_candidates"]:
        reasons.append("candidate is blocked")
    if action == "merge" and state["sync_paused"]:
        reasons.append("synchronization is paused")
    if action == "publish-dev" and state["release_paused"]:
        reasons.append("development publication is paused")
    return {
        "status": "BLOCKED" if reasons else "PASS",
        "revision": state["revision"],
        "candidate_id": identifier,
        "allowed_by_operator_controls": not reasons,
        "reasons": reasons,
        "action_executed": False,
        "deployment_verified": False,
        "scope": (
            "local operator prerequisite only; not merge/release readiness"
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument(
        "action",
        choices=(
            "init",
            "inspect",
            "pause-sync",
            "resume-sync",
            "pause-release",
            "resume-release",
            "block",
            "unblock",
            "check-merge",
            "check-dev",
        ),
    )
    parser.add_argument("--revision", type=int)
    parser.add_argument("--candidate")
    args = parser.parse_args(argv)
    try:
        if args.action == "init":
            result = initialize(args.state)
        elif args.action == "inspect":
            result = read(args.state)
        elif args.action.startswith("check-"):
            if args.revision is None:
                raise ValueError("--revision is required")
            result = check(
                args.state,
                "merge" if args.action == "check-merge" else "publish-dev",
                args.candidate,
                args.revision,
            )
        else:
            result = update(
                args.state, args.revision, args.action, args.candidate
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 3 if result.get("status") == "BLOCKED" else 0
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
