#!/usr/bin/env python3
"""Trusted default-branch collector for low-privilege CPH native CI.

Never checks out or executes candidate code. Dispatch job checks are evidence;
the separately published commit status is the protected-branch contract.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import time
import urllib.request
import zipfile

from check_merge_evidence import (
    check_junit,
    decode,
    protected_changes,
    require,
)


REPOSITORY = "oncehere/Cataclysm-Phantom-Hope"
REPOSITORY_ID = 1389460908
WORKFLOW = ".github/workflows/project-ci.yml"
CONTEXT = "cph/trusted-gate"
MAX_ARCHIVE = 128 * 1024 * 1024
RULESET_FIELDS = (
    "id", "target", "source_type", "source", "enforcement", "conditions",
    "rules", "updated_at",
)
TITLE = re.compile(
    r"CPH CI PR ([1-9][0-9]*) base ([0-9a-f]{40}) head ([0-9a-f]{40})"
)
BUILD_STEPS = (
    "Checkout trusted control revision",
    "Checkout exact merge candidate",
    "Select compatible CMake",
    "Build and execute required tests",
    "Preserve logs and evidence on success or failure",
)
TOOLING_STEPS = (
    "Checkout trusted control revision",
    "Checkout exact merge candidate",
    "Select fixed tooling Python",
    "Install tooling system dependencies",
    "Run tool regressions and generated checks",
    "Preserve tooling evidence on success or failure",
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def archive(data):
    """Read bounded flat evidence without extracting any untrusted path."""
    require(len(data) <= MAX_ARCHIVE, "oversized compressed artifact")
    result = {}
    with zipfile.ZipFile(io.BytesIO(data)) as bundle:
        members = bundle.infolist()
        require(0 < len(members) <= 300, "invalid artifact member count")
        require(
            sum(item.file_size for item in members) <= MAX_ARCHIVE,
            "oversized expanded artifact",
        )
        for item in members:
            name = item.filename
            path = PurePosixPath(name)
            require(
                not path.is_absolute() and
                ".." not in path.parts and
                "\\" not in name and
                ":" not in name and
                str(path) == name.rstrip("/"),
                "unsafe artifact path",
            )
            require(
                (item.external_attr >> 16) & 0o170000 != 0o120000,
                "artifact symlink forbidden",
            )
            if item.is_dir():
                continue
            require(
                item.file_size <= 32 * 1024 * 1024 and name not in result,
                "oversized or duplicate artifact member",
            )
            result[name] = bundle.read(item)
    return result


def validate_report(files, platform, expected, policy):
    require("report.json" in files, "missing native report")
    report = decode(files["report.json"])
    require(
        report.get("schema_version") == 1 and
        report.get("kind") == "cph-native-ci" and
        report.get("status") == "PASS" and
        report.get("platform") == platform,
        "native report did not pass",
    )
    identity = report.get("identity", {})
    for key, value in expected.items():
        require(identity.get(key) == value, "report identity mismatch: " + key)
    require(
        report.get("checks") == dict.fromkeys(
            ("configure", "build", "version", "isolation"), "PASS"
        ),
        "incomplete native acceptance",
    )
    require(
        report.get("isolation_scope") == "explicit-userdir-sentinels",
        "missing isolation scope",
    )
    target = policy["targets"][platform]
    actual = report.get("configuration", {})
    for key in (
        "target_id",
        "preset",
        "generator",
        "configuration",
        "options",
    ):
        require(
            actual.get(key) == target[key], "configuration mismatch: " + key
        )
    binaries = report.get("binaries", [])
    require(
        isinstance(binaries, list) and len(binaries) == 2,
        "missing game/test binaries",
    )
    for item in binaries:
        require(
            type(item.get("bytes")) is int and
            item["bytes"] > 0 and
            re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")),
            "invalid built binary evidence",
        )
    require(
        [item.get("path") for item in binaries] == target["binaries"],
        "unexpected built executable paths",
    )
    require("commands.jsonl" in files, "missing command execution ledger")
    commands = [
        decode(line) for line in files["commands.jsonl"].splitlines() if line
    ]
    require(commands, "empty command execution ledger")
    for command in commands:
        require(
            type(command.get("exit_code")) is int and
            command["exit_code"] == 0 and
            command.get("status") == "PASS",
            "command did not succeed",
        )
        log = command.get("log")
        require(
            log in files and digest(files[log]) == command.get("log_sha256"),
            "command log digest mismatch",
        )
    tests = report.get("tests", [])
    require(
        isinstance(tests, list) and len(tests) == len(target["tests"]),
        "missing or surplus regression results",
    )
    seen = set()
    for item in tests:
        check = item.get("check")
        require(
            check in target["tests"] and check not in seen,
            "unexpected or repeated regression",
        )
        seen.add(check)
        require(
            item.get("selection") == target["tests"][check] and
            item.get("status") == "PASS",
            "wrong regression selection",
        )
        name = item.get("report")
        require(
            name == check + ".xml" and
            name in files and
            digest(files[name]) == item.get("report_sha256"),
            "missing or changed JUnit report",
        )
        counts = check_junit(files[name])
        require(
            all(
                type(item.get(key)) is int and item[key] == count
                for key, count in counts.items()
            ),
            "JUnit count mismatch",
        )
        executed = [
            command
            for command in commands
            if command.get("log") == check + ".log"
        ]
        require(
            len(executed) == 1 and
            len(executed[0].get("argv", [])) > 2 and
            executed[0]["argv"][1] == target["tests"][check],
            "regression command missing or selection changed",
        )
    for name in ("configure", "build", "game-version"):
        require(
            len(
                [
                    command
                    for command in commands
                    if command.get("log") == name + ".log"
                ]
            ) == 1,
            "required command evidence missing: " + name,
        )
    return report


def validate_jobs(jobs):
    required = {
        "CPH Plan": (
            "Checkout trusted control revision",
            "Bind current PR and merge tree",
        ),
        "CPH Linux": BUILD_STEPS,
        "CPH Windows": BUILD_STEPS,
        "CPH Tooling": TOOLING_STEPS,
    }
    for name, steps in required.items():
        found = [job for job in jobs if job.get("name") == name]
        require(len(found) == 1, "missing or duplicate required job: " + name)
        job = found[0]
        require(
            job.get("status") == "completed" and
            job.get("conclusion") == "success",
            "required job failed: " + name,
        )
        for step_name in steps:
            matches = [
                step
                for step in job.get("steps", [])
                if step.get("name") == step_name
            ]
            require(
                len(matches) == 1 and
                matches[0].get("conclusion") == "success",
                "required step not successful: " + step_name,
            )


def validate_tooling(files, expected, policy, requirements_sha):
    """Validate the complete required tool profile without executing it."""
    require("tooling-report.json" in files, "missing tooling report")
    report = decode(files["tooling-report.json"])
    require(
        report.get("schema_version") == 1
        and report.get("kind") == "cph-tooling-ci"
        and report.get("status") == "PASS",
        "tooling did not pass",
    )
    require(report.get("identity") == expected, "tooling identity mismatch")
    require(
        report.get("python_version") == policy["python_version"]
        and report.get("requirements_sha256") == requirements_sha,
        "tooling interpreter or dependencies changed",
    )
    require(
        report.get("checks") == list(policy["checks"]),
        "missing or changed generated check",
    )
    suites = report.get("suites", [])
    require(
        isinstance(suites, list)
        and [item.get("name") for item in suites] == list(policy["suites"]),
        "missing or repeated tooling suite",
    )
    require("commands.jsonl" in files, "missing tooling command ledger")
    commands = [
        decode(line) for line in files["commands.jsonl"].splitlines() if line
    ]
    names = ["dependencies", *policy["suites"], *policy["checks"]]
    require(
        [item.get("log") for item in commands]
        == [name + ".log" for name in names],
        "tooling commands missing or changed",
    )
    indexed = {}
    for name, command in zip(names, commands):
        log = command["log"]
        require(
            type(command.get("exit_code")) is int
            and command["exit_code"] == 0
            and command.get("status") == "PASS",
            "tooling command failed",
        )
        require(
            log in files and digest(files[log]) == command.get("log_sha256"),
            "tooling command log changed",
        )
        require(isinstance(command.get("argv"), list), "invalid tooling argv")
        indexed[name] = command["argv"]
    for name, arguments in policy["checks"].items():
        require(
            indexed[name][1:] == arguments, "generated check command changed"
        )
    for item in suites:
        name = item["name"]
        filename = name + ".json"
        require(
            item.get("report") == filename
            and filename in files
            and digest(files[filename]) == item.get("sha256"),
            "tooling suite report changed",
        )
        suite, config = decode(files[filename]), policy["suites"][name]
        require(
            suite.get("status") == "PASS"
            and suite.get("directory") == config["directory"]
            and suite.get("pattern") == "test_*.py"
            and suite.get("excluded_prefixes") == config["excluded_prefixes"],
            "tooling suite selection changed",
        )
        for key in (
            "failures",
            "errors",
            "skipped",
            "expected_failures",
            "unexpected_successes",
        ):
            require(
                type(suite.get(key)) is int and suite[key] == 0,
                "tooling suite failed or skipped",
            )
        selected, excluded = (
            suite.get("selected_tests"),
            suite.get("excluded_tests"),
        )
        require(
            isinstance(selected, list)
            and isinstance(excluded, list)
            and all(isinstance(value, str) for value in selected + excluded),
            "invalid tooling test inventory",
        )
        require(
            type(suite.get("tests")) is int
            and suite["tests"] > 0
            and len(selected) == suite["tests"]
            and type(suite.get("selected_count")) is int
            and suite["selected_count"] == len(selected)
            and type(suite.get("excluded_count")) is int
            and suite["excluded_count"] == len(excluded)
            and len(set(selected + excluded)) == len(selected + excluded),
            "empty or duplicate tooling tests",
        )
        prefixes = tuple(config["excluded_prefixes"])
        require(
            all(value.startswith(prefixes) for value in excluded)
            and not any(value.startswith(prefixes) for value in selected),
            "tooling exclusions changed",
        )
        argv = indexed[name]
        require(
            len(argv) == 9
            and Path(argv[1]).name == "ci_tooling.py"
            and argv[2:5] == ["suite", "--directory", config["directory"]]
            and argv[5] == "--excluded"
            and json.loads(argv[6]) == config["excluded_prefixes"]
            and argv[7] == "--output"
            and Path(argv[8]).name == filename,
            "tooling regression command changed",
        )
    return report


def validate_protection(value):
    checks = value.get("required_status_checks") or {}
    require(checks.get("strict") is True, "strict status protection missing")
    sources = [
        item
        for item in checks.get("checks", [])
        if item.get("context") == CONTEXT
    ]
    require(
        len(sources) == 1 and
        type(sources[0].get("app_id")) is int and
        sources[0]["app_id"] > 0,
        "trusted status app source not pinned",
    )
    require(
        value.get("enforce_admins", {}).get("enabled") is True,
        "administrator bypass remains enabled",
    )
    for field in (
        "allow_force_pushes",
        "allow_deletions",
        "required_linear_history",
    ):
        require(
            value.get(field, {}).get("enabled") is False,
            "incompatible protection: " + field,
        )
    return sources[0]["app_id"]


def page(api, path, field=None):
    """Do not silently accept truncated jobs, artifacts or PR file lists."""
    result = []
    expected = None
    for number in range(1, 32):
        separator = "&" if "?" in path else "?"
        value = api.repo(path + separator + f"per_page=100&page={number}")
        rows = value[field] if field else value
        require(isinstance(rows, list), "invalid paginated response")
        if field and "total_count" in value:
            require(
                expected in (None, value["total_count"]), "pagination changed"
            )
            expected = value["total_count"]
        result.extend(rows)
        if len(rows) < 100:
            require(
                expected is None or len(result) == expected,
                "incomplete paginated response",
            )
            return result
    raise ValueError("pagination limit exceeded")


def read_pr(api, number, base, head, surfaces):
    pr = api.repo(f"pulls/{number}")
    require(
        pr.get("state") == "open" and
        not pr.get("draft") and
        pr["base"]["ref"] == "main" and
        pr["base"]["repo"]["id"] == REPOSITORY_ID and
        pr["base"]["sha"] == base and
        pr["head"]["sha"] == head,
        "PR closed, draft, or base/head changed",
    )
    require(
        pr.get("mergeable") is True and pr.get("merge_commit_sha"),
        "PR merge tree is not ready",
    )
    files = page(api, f"pulls/{number}/files")
    require(len(files) == pr.get("changed_files"), "truncated changed paths")
    paths = []
    for item in files:
        paths.append(item["filename"])
        if item.get("previous_filename"):
            paths.append(item["previous_filename"])
    require(
        not protected_changes(paths, surfaces),
        "candidate changes protected surfaces",
    )
    merge = api.repo("git/commits/" + pr["merge_commit_sha"])
    require(
        [item["sha"] for item in merge["parents"]] == [base, head],
        "unexpected merge parents",
    )
    return pr, merge["tree"]["sha"]


def download_artifact(api, identifier):
    url = (f"https://api.github.com/repos/{REPOSITORY}/"
           f"actions/artifacts/{identifier}/zip")
    request = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json"}
    )
    # Authentication applies only to the GitHub API request, never its
    # storage redirect.
    request.add_unredirected_header("Authorization", "Bearer " + api.token)
    with urllib.request.urlopen(request, timeout=60) as response:
        require(
            response.url.startswith("https://"), "insecure artifact redirect"
        )
        data = response.read(MAX_ARCHIVE + 1)
    return data


def publish(api, head, state, run_id, description):
    return api.repo(
        "statuses/" + head,
        "POST",
        {
            "state": state,
            "context": CONTEXT,
            "description": description[:140],
            "target_url": (f"https://github.com/{REPOSITORY}/"
                           f"actions/runs/{run_id}"),
        },
    )


def ruleset_timestamp(value):
    """GitHub may serialize one instant in the requester's local timezone."""
    require(isinstance(value, str), "invalid ruleset timestamp")
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(instant.tzinfo is not None, "ruleset timestamp lacks timezone")
    return instant.astimezone(timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")


def ruleset_digest(ruleset):
    """Digest only public fields, identically for admin and runtime reads."""
    require(all(key in ruleset for key in RULESET_FIELDS),
            "incomplete public ruleset metadata")
    visible = {key: ruleset[key] for key in RULESET_FIELDS}
    visible["updated_at"] = ruleset_timestamp(visible["updated_at"])
    return digest(json.dumps(
        visible, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8"))


def active_rules(api, state):
    """Bind public rules to an administrator-verified no-bypass snapshot."""
    locks = state.get("verified_rulesets")
    require(isinstance(locks, list) and locks,
            "administrator-verified ruleset locks are missing")
    indexed = {}
    for lock in locks:
        require(
            isinstance(lock, dict) and type(lock.get("id")) is int and
            lock["id"] > 0 and lock["id"] not in indexed and
            lock.get("bypass_actors") == [] and
            isinstance(lock.get("updated_at"), str) and
            bool(lock["updated_at"]) and
            isinstance(lock.get("visible_sha256"), str) and
            re.fullmatch(r"[0-9a-f]{64}", lock["visible_sha256"]),
            "invalid administrator-verified ruleset lock",
        )
        indexed[lock["id"]] = lock
    rules = page(api, "rules/branches/main")
    types = {item["type"] for item in rules}
    require(
        {
            "required_status_checks",
            "non_fast_forward",
            "deletion",
            "pull_request",
        } <=
        types and
        "required_linear_history" not in types,
        "missing or incompatible active branch rules",
    )
    found = []
    for item in rules:
        if item["type"] == "pull_request":
            require(
                "merge"
                in item.get("parameters", {}).get(
                    "allowed_merge_methods", ["merge"]
                ),
                "merge history is disallowed by repository rules",
            )
        if item["type"] == "required_status_checks":
            parameters = item.get("parameters", {})
            if parameters.get("strict_required_status_checks_policy") is True:
                found.extend(
                    check
                    for check in parameters.get("required_status_checks", [])
                    if check.get("context") == CONTEXT
                )
    require(
        len(found) == 1 and
        type(found[0].get("integration_id")) is int and
        found[0]["integration_id"] > 0,
        "trusted status source not required",
    )
    # Low-privilege API reads may hide bypass_actors. Its absence is not
    # evidence: the trusted admin snapshot must still match every public field.
    for identifier in {item["ruleset_id"] for item in rules}:
        require(identifier in indexed,
                "active ruleset lacks administrator verification")
        lock = indexed[identifier]
        ruleset = api.repo("rulesets/" + str(identifier))
        require(
            ruleset.get("id") == identifier and
            ruleset.get("target") == "branch" and
            ruleset.get("source_type") == "Repository" and
            ruleset.get("source") == REPOSITORY and
            ruleset.get("enforcement") == "active",
            "ruleset source or enforcement changed",
        )
        require(
            ruleset_timestamp(ruleset.get("updated_at")) ==
            ruleset_timestamp(lock["updated_at"]) and
            ruleset_digest(ruleset) == lock["visible_sha256"],
            "administrator-verified ruleset lock is stale",
        )
        if "bypass_actors" in ruleset:
            require(ruleset["bypass_actors"] == [],
                    "ruleset exposes a bypass identity")
    return found[0]["integration_id"]


def wait_for_merge(api, result, state, upstream, task, sleep=time.sleep):
    """Wait briefly for GitHub to evaluate the newly published status."""
    from remote_sync import check_controls, load_state

    def current_candidate():
        fresh, _ = load_state(api)
        check_controls(fresh, "ccb-" + upstream, merge=True)
        require(
            fresh["revision"] == state["revision"] and
            fresh["tasks"].get(upstream) == task and
            fresh.get("verified_rulesets") == state.get("verified_rulesets"),
            "state changed before merge",
        )
        current, tree = read_pr(
            api, result["pr_number"], result["base_sha"],
            result["head_sha"], result["surfaces"],
        )
        require(
            tree == result["merge_tree"] and
            current["merge_commit_sha"] == result["merge_sha"],
            "candidate changed while waiting for GitHub",
        )
        return current, fresh

    for attempt in range(6):
        current, fresh = current_candidate()
        if current.get("mergeable_state") == "clean":
            active_rules(api, fresh)
            # Pause or source changes while fetching rules still stop merging.
            current, _ = current_candidate()
            if current.get("mergeable_state") == "clean":
                return
        require(
            current.get("mergeable_state") in (
                "blocked", "unstable", "unknown",
            ),
            "GitHub rejected the protected candidate",
        )
        if attempt < 5:
            sleep(5)
    raise ValueError("GitHub did not accept the status within six checks")


def finish(api, result, sleep=time.sleep):
    from remote_sync import (
        check_controls,
        load_state,
        record_merged,
        verify_target,
    )

    verify_target(api)
    number, base, head = (
        result[key] for key in ("pr_number", "base_sha", "head_sha")
    )
    state, _ = load_state(api)
    tasks = [
        (upstream, task)
        for upstream, task in state["tasks"].items()
        if task.get("pr_number") == number
    ]
    require(len(tasks) <= 1, "ambiguous synchronization task")
    if tasks:
        upstream, task = tasks[0]
        require(
            task.get("head") == head and
            task.get("base") == base and
            task.get("tree") == result["merge_tree"] and
            task.get("status") == "PR_OPEN",
            "controller task changed",
        )
        check_controls(state, "ccb-" + upstream)
    current, tree = read_pr(api, number, base, head, result["surfaces"])
    require(
        tree == result["merge_tree"], "tree moved before status publication"
    )
    publish(
        api,
        head,
        "success",
        result["run_id"],
        "Native Windows/Linux evidence verified",
    )
    result["status"] = "PASS"
    result["merged"] = False
    if not tasks or not state["auto_merge_enabled"] or state["merge_paused"]:
        return
    check_controls(state, "ccb-" + upstream, merge=True)
    require(
        current["head"]["repo"]["id"] == REPOSITORY_ID and
        current["head"]["ref"] == task.get("branch") and
        current.get("user", {}).get("login") == "github-actions[bot]",
        "automatic merge restricted to controller-created CCB PRs",
    )
    commit = api.repo("git/commits/" + head)
    require(
        [item["sha"] for item in commit["parents"]] == [base, upstream],
        "CCB candidate history changed",
    )
    wait_for_merge(api, result, state, upstream, task, sleep)
    response = api.repo(
        f"pulls/{number}/merge", "PUT", {"sha": head, "merge_method": "merge"}
    )
    require(response.get("merged") is True, "GitHub refused protected merge")
    merged = api.repo("git/commits/" + response["sha"])
    require(
        merged["tree"]["sha"] == result["merge_tree"] and
        [item["sha"] for item in merged["parents"]] == [base, head],
        "merged result differs from accepted evidence",
    )
    record_merged(api, upstream, head)
    result["merged"] = True
    result["merged_sha"] = response["sha"]


def collect(
    api, run_id, attempt, control_sha, control, downloader=download_artifact
):
    """Validate trusted workflow and candidate before publishing success."""
    run = api.repo(f"actions/runs/{run_id}")
    require(
        run.get("repository", {}).get("id") == REPOSITORY_ID and
        run.get("repository", {}).get("full_name") == REPOSITORY,
        "unexpected workflow repository",
    )
    workflow = api.repo("actions/workflows/project-ci.yml")
    require(
        run.get("workflow_id") == workflow.get("id") and
        run.get("path") == WORKFLOW and
        workflow.get("path") == WORKFLOW,
        "unexpected workflow identity",
    )
    require(
        run.get("run_attempt") == attempt and run.get("status") == "completed",
        "stale or incomplete workflow attempt",
    )
    require(
        run.get("event") in ("workflow_dispatch", "pull_request"),
        "unexpected CI event",
    )
    match = TITLE.fullmatch(run.get("display_title", ""))
    require(match is not None, "missing immutable PR run binding")
    number, base, head = int(match[1]), match[2], match[3]
    recent = api.repo("actions/workflows/project-ci.yml/runs?per_page=100")
    same = [
        item
        for item in recent.get("workflow_runs", [])
        if item.get("display_title") == run["display_title"]
    ]
    require(
        same and same[0].get("id") == run_id,
        "a newer CI run superseded this evidence",
    )
    require(base == control_sha, "policy/base moved since testing")
    if run["event"] == "workflow_dispatch":
        require(
            run.get("head_sha") == base and run.get("head_branch") == "main",
            "dispatch did not use trusted main workflow",
        )
    else:
        require(run.get("head_sha") == head, "PR run head mismatch")
    policy_bytes = (control / "project/check-policy.json").read_bytes()
    policy = decode(policy_bytes)
    surface_bytes = (control / "project/protected-surfaces.json").read_bytes()
    require(
        digest(surface_bytes) == policy["protected_surfaces"]["sha256"],
        "trusted protection digest mismatch",
    )
    surfaces = decode(surface_bytes)
    pr, tree = read_pr(api, number, base, head, surfaces)
    try:
        require(run.get("conclusion") == "success", "native workflow failed")
        jobs = page(
            api, f"actions/runs/{run_id}/attempts/{attempt}/jobs", "jobs"
        )
        validate_jobs(jobs)
        artifacts = page(api, f"actions/runs/{run_id}/artifacts", "artifacts")
        for platform in ("tooling", "linux", "windows"):
            name = f"cph-ci-{platform}-{run_id}-{attempt}"
            matches = [item for item in artifacts if item.get("name") == name]
            require(
                len(matches) == 1 and matches[0].get("expired") is False,
                "missing or ambiguous platform artifact",
            )
            item = matches[0]
            require(
                item.get("size_in_bytes", MAX_ARCHIVE + 1) <= MAX_ARCHIVE and
                item.get("workflow_run", {}).get("id") == run_id,
                "artifact provenance/size mismatch",
            )
            raw = downloader(api, item["id"])
            # GitHub artifact digest is the uploaded archive's SHA-256.
            require(
                item.get("digest") == "sha256:" + digest(raw),
                "artifact digest mismatch",
            )
            expected = {
                "repository": REPOSITORY,
                "repository_id": str(REPOSITORY_ID),
                "pr_number": number,
                "base_sha": base,
                "head_sha": head,
                "merge_sha": pr["merge_commit_sha"],
                "merge_tree": tree,
                "control_sha": base,
                "event": run["event"],
                "run_id": str(run_id),
                "run_attempt": str(attempt),
                "policy_sha": digest(policy_bytes),
                "workflow_ref": f"{REPOSITORY}/{WORKFLOW}@" +
                (
                    "refs/heads/main"
                    if run["event"] == "workflow_dispatch"
                    else f"refs/pull/{number}/merge"
                ),
            }
            if platform == "tooling":
                validate_tooling(
                    archive(raw),
                    expected,
                    policy["tooling"],
                    digest(
                        (
                            control / policy["tooling"]["requirements"]
                        ).read_bytes()
                    ),
                )
            else:
                validate_report(archive(raw), platform, expected, policy)
        # Re-read after downloads: a successful old combination is never
        # reusable.
        current, current_tree = read_pr(api, number, base, head, surfaces)
        require(
            current_tree == tree and
            current["merge_commit_sha"] == pr["merge_commit_sha"],
            "candidate merge tree changed",
        )
    except (ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        publish(api, head, "failure", run_id, "CPH native evidence rejected")
        raise ValueError(str(error)) from error
    return {
        "pr_number": number,
        "base_sha": base,
        "head_sha": head,
        "merge_sha": pr["merge_commit_sha"],
        "merge_tree": tree,
        "run_id": run_id,
        "run_attempt": attempt,
        "surfaces": surfaces,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--attempt", required=True, type=int)
    parser.add_argument("--control-sha", required=True)
    args = parser.parse_args(argv)
    try:
        from remote_sync import GitHub

        api = GitHub(os.environ["GH_TOKEN"])
        result = collect(
            api,
            args.run_id,
            args.attempt,
            args.control_sha,
            Path(__file__).resolve().parents[2],
        )
        finish(api, result)
        print(
            json.dumps(
                {
                    key: value
                    for key, value in result.items()
                    if key != "surfaces"
                },
                sort_keys=True,
            )
        )
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
