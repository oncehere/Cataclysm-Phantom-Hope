#!/usr/bin/env python3
"""Read-only E4 evidence consistency check. Never authorizes a GitHub merge.

Run this reviewed file from a trusted control checkout, never from the
candidate. Trusted policy/context paths and digests are caller-owned inputs.
"""

import argparse
import hashlib
import json
import ntpath
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

from preflight import rejected_git_environment

BINDINGS = (
    "repository_id", "pull_request", "base_sha", "head_sha",
    "tested_commit", "tested_tree", "policy_sha", "inputs_digest",
)
RUN_BINDINGS = (
    "workflow_path", "workflow_id", "event", "run_id", "run_attempt",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(value, length=64):
    require(isinstance(value, str) and re.fullmatch(
        "[0-9a-f]{" + str(length) + "}", value), "invalid digest")
    return value


def positive(value):
    require(type(value) is int and value > 0, "expected positive integer")


def regular(path):
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        require(not item.is_symlink(), "symlink input: " + str(item))
    require(path.is_file(), "missing regular input: " + str(path))
    return path


def relative(name):
    require(isinstance(name, str) and bool(name), "empty input path")
    path = PurePosixPath(name)
    require(not path.is_absolute() and ".." not in path.parts and
            "\\" not in name and ":" not in name and
            str(path) == name, "unsafe relative path: " + name)
    return name


def read_verified(path, expected, materialize=True):
    sha(expected)
    checksum, data, size = hashlib.sha256(), bytearray(), 0
    with regular(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
            size += len(chunk)
            if materialize:
                data.extend(chunk)
    require(size > 0, "empty evidence: " + str(path))
    require(checksum.hexdigest() == expected,
            "digest mismatch: " + str(path))
    return bytes(data)


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def decode(data):
    result = json.loads(data, object_pairs_hook=no_duplicate_keys)
    require(isinstance(result, dict), "expected JSON object")
    return result


def trusted(path, expected, repo, evidence):
    path = regular(path)
    for forbidden in (repo.resolve(), evidence.resolve()):
        require(not path.is_relative_to(forbidden),
                "trusted input is inside candidate/evidence directory")
    return decode(read_verified(path, expected))


def git(repo, *args):
    overrides = rejected_git_environment(os.environ)
    require(not overrides, "refusing Git environment overrides")
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1",
               GIT_TERMINAL_PROMPT="0", GIT_PAGER="cat",
               GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               LC_ALL="C")
    process = subprocess.run(
        ["git", "--no-replace-objects", "-c", "core.fsmonitor=false",
         "-c", "core.untrackedCache=false", "-c",
         "core.hooksPath=" + os.devnull, "-c", "protocol.allow=never",
         "-C", str(repo), *args], capture_output=True, env=env,
        check=False, timeout=120,
    )
    require(process.returncode == 0,
            f"git {args[0]} exit {process.returncode}")
    return process.stdout.decode("utf-8").rstrip("\n")


def inspect_repo(repo):
    require(Path(git(repo, "rev-parse", "--show-toplevel")).resolve() ==
            repo.resolve(), "repo must be the repository root")
    require(git(repo, "rev-parse", "--is-shallow-repository") == "false",
            "shallow history is not accepted")
    require(not git(repo, "for-each-ref", "--format=%(refname)",
                    "refs/replace/"), "replace refs are not accepted")
    common = Path(git(repo, "rev-parse", "--git-common-dir"))
    grafts = (repo / common / "info/grafts")
    require(not grafts.exists() and not grafts.is_symlink(),
            "grafts are not accepted")


def commit(repo, ref):
    require(isinstance(ref, str) and (
        re.fullmatch(r"[0-9a-f]{40}", ref) or
        re.fullmatch(r"refs/[A-Za-z0-9._/-]+", ref)
    ), "expected full SHA or explicit ref")
    return git(repo, "rev-parse", "--verify", "--end-of-options",
               ref + "^{commit}")


def changed_paths(repo, base, head):
    raw = git(repo, "diff", "--no-ext-diff", "--no-textconv",
              "--name-only", "-z", "--no-renames", base, head,
              "--", ".", ":(exclude)obj-lua")
    return sorted(set(raw.rstrip("\0").split("\0"))) if raw else []


def protected_changes(paths, surfaces):
    require(surfaces.get("schema_version") == 1, "unsupported surfaces")
    prefixes, exact = surfaces["prefixes"], surfaces["paths"]
    basenames = surfaces["basenames"]
    require(isinstance(prefixes, list) and prefixes and
            isinstance(exact, list) and exact and
            isinstance(basenames, list) and basenames,
            "empty protection policy")
    for name in prefixes + exact + basenames:
        relative(name)
    result = []
    for path in paths:
        relative(path)
        match = any(
            path == name or name.startswith(path + "/") or
            (name in prefixes and path.startswith(name + "/"))
            for name in prefixes + exact)
        if PurePosixPath(path).name in basenames or match:
            result.append(path)
    return result


def check_junit(data):
    root = ET.fromstring(data)
    require(root.tag in ("testsuite", "testsuites"), "not JUnit")
    suites = [root] if root.tag == "testsuite" else list(root)
    require(bool(suites) and all(s.tag == "testsuite" for s in suites),
            "missing or nested JUnit suites")
    total = cases = 0
    for suite in suites:
        count = suite.get("tests", "")
        require(count.isdecimal() and int(count) > 0,
                "JUnit has zero/missing assertions")
        executed = suite.findall("testcase")
        require(bool(executed), "JUnit has no executed testcases")
        require(len(executed) == len(list(suite.iter("testcase"))),
                "JUnit has orphan testcases")
        total += int(count)
        cases += len(executed)
    for element in root.iter():
        require(element.tag not in ("failure", "error", "skipped",
                                    "disabled"), "JUnit contains failure")
        for key in ("failures", "errors", "skipped", "disabled"):
            value = element.get(key, "0")
            require(value.isdecimal() and int(value) == 0,
                    "JUnit contains non-success counts")
    if root.tag == "testsuites" and root.get("tests") is not None:
        require(root.get("tests", "").isdecimal() and
                int(root.get("tests")) == total, "JUnit total mismatch")
    return {"test_cases": cases, "assertions": total}


def commands(target, run):
    require(isinstance(target.get("tests"), dict) and target["tests"],
            "empty required regression set")
    require(isinstance(target.get("binaries"), list) and
            len(target["binaries"]) == 2, "expected game and test binaries")
    require(target.get("native") is True, "native target is required")
    layout = run["layout"]
    require(set(layout) == {"source", "build", "evidence"},
            "invalid execution layout")
    for key in ("source", "build", "evidence"):
        value = layout[key]
        require(isinstance(value, str) and value and "\0" not in value,
                "invalid execution directory")
    path = ntpath if target["os"] == "windows" else posixpath
    require(all(path.isabs(layout[k]) for k in layout),
            "execution directories must be absolute")
    positive(run["parallel"])
    build = ["cmake", "--build", layout["build"]]
    if target["os"] == "windows":
        build += ["--config", target["configuration"]]
    build += ["--parallel", str(run["parallel"]), "--target",
              "cataclysm-tiles", "cata_test-tiles"]
    game, test = [path.join(layout["build"], *name.split("/"))
                  for name in target["binaries"]]
    version = [game]
    if target["os"] == "windows":
        version += ["--userdir", path.join(layout["evidence"], "version-user")]
    version += ["--version"]
    result = {"build": build, "game-version": version}
    for check_id, selection in target["tests"].items():
        require(isinstance(selection, str) and bool(selection),
                "empty test selection")
        result[check_id] = [
            test, selection, "--rng-seed", "4902", "--order", "lex",
            "--user-dir", path.join(layout["evidence"], check_id + "-user"),
            "--reporter", "junit", "--out",
            path.join(layout["evidence"], check_id + ".xml"),
        ]
    return result


def artifact(evidence, item, materialize=True):
    return read_verified(evidence / relative(item["path"]), item["sha256"],
                         materialize)


def platform_result(policy, context, name, evidence):
    target = policy["targets"][name]
    run = context["runs"][name]
    for key in ("workflow_id", "run_id", "run_attempt"):
        positive(run[key])
    workflow = relative(run["workflow_path"])
    require(workflow.startswith(".github/workflows/") and
            PurePosixPath(workflow).suffix in (".yml", ".yaml"),
            "invalid workflow path")
    require(run["event"] == "pull_request" == policy["required_event"],
            "required check is not pull_request sourced")
    receipt = decode(artifact(evidence, run["receipt"]))
    require(receipt.get("schema_version") == 1, "unsupported receipt")
    for key in BINDINGS:
        require(type(receipt.get(key)) is type(context[key]) and
                receipt[key] == context[key], "stale binding: " + key)
    for key in RUN_BINDINGS:
        require(type(receipt.get(key)) is type(run[key]) and
                receipt[key] == run[key], "wrong run binding: " + key)
    require(json.dumps(receipt.get("target"), sort_keys=True) ==
            json.dumps(target, sort_keys=True), "wrong target configuration")
    environment = receipt.get("execution_environment", {})
    require(environment.get("os") == name and
            environment.get("arch") == target["arch"] and
            environment.get("native") is True,
            "native execution environment mismatch")
    expected = commands(target, run)
    checks = receipt["checks"]
    require(isinstance(checks, list) and len(checks) == len(expected),
            "missing/extra required checks")
    results = {}
    for check in checks:
        check_id = check["id"]
        require(check_id in expected and check_id not in results,
                "unknown/duplicate required check")
        require(check.get("status") == "PASS" and
                check.get("actually_executed") is True and
                type(check.get("exit_code")) is int and
                check["exit_code"] == 0, "required command did not succeed")
        require(check.get("argv") == expected[check_id] and
                check.get("cwd") == run["layout"]["source"],
                "wrong required command/cwd")
        artifact(evidence, check["log"], materialize=False)
        results[check_id] = {"status": "PASS", "exit_code": 0}
        if check_id in target["tests"]:
            results[check_id].update(check_junit(
                artifact(evidence, check["junit"])))
    binaries = receipt["binaries"]
    require(isinstance(binaries, dict) and
            set(binaries) == set(target["binaries"]), "missing binaries")
    for item in binaries.values():
        artifact(evidence, item, materialize=False)
    return results


def verify_context(repo, context, policy_sha):
    require(context.get("schema_version") == 1, "unsupported context")
    for key in ("repository_id", "pull_request"):
        positive(context[key])
    require(context["policy_sha"] == policy_sha, "wrong policy binding")
    sha(context["inputs_digest"])
    for key in ("base_sha", "head_sha", "tested_commit", "tested_tree"):
        sha(context[key], 40)
    for key in ("base_ref", "head_ref"):
        require(isinstance(context[key], str) and
                context[key].startswith("refs/"),
                "current context requires explicit moving refs")
    current = [commit(repo, context[key + "_ref"])
               for key in ("base", "head")]
    require(current == [context["base_sha"], context["head_sha"]],
            "base/head moved; rebuild and retest the combination")
    tested = context["tested_commit"]
    parents = git(repo, "show", "-s", "--format=%P", tested).split()
    require(parents == current, "tested merge does not have base/head parents")
    require(git(repo, "rev-parse", tested + "^{tree}") ==
            context["tested_tree"], "tested merge tree mismatch")
    # A final commit can have another SHA, but must have these parents/tree.
    if "final_merge_commit" in context:
        final = sha(context["final_merge_commit"], 40)
        require(git(repo, "show", "-s", "--format=%P", final).split() ==
                current and git(repo, "rev-parse", final + "^{tree}") ==
                context["tested_tree"], "final merge differs from tested tree")
    for key in ("scope_authorized", "source_verified", "conflicts_resolved"):
        require(context.get(key) is True, "unresolved scope/source: " + key)
    require(context.get("merge_paused") is False, "merge is paused/unknown")
    return current


def evaluate(repo, evidence, policy_path, policy_sha,
             context_path=None, context_sha=None, base=None, head=None):
    """Return local consistency only; no true deployment/merge readiness."""
    report = {
        "status": "FAIL", "evidence_accepted": False,
        "merge_ready": False, "github_gate_verified": False,
        "public_release_ready": False,
        "validation_scope": "local_evidence_consistency_only",
        "deployment_status": "IMPLEMENTED_NOT_DEPLOYED",
        "protected_changes": [], "platforms": {}, "errors": [],
    }
    try:
        repo, evidence = Path(repo).resolve(), Path(evidence).absolute()
        inspect_repo(repo)
        policy = trusted(policy_path, policy_sha, repo, evidence)
        report["policy_sha"] = policy_sha
        require(policy.get("schema_version") == 1 and
                policy.get("required_platforms") == ["windows", "linux"] and
                policy.get("informational_platforms") == ["macos", "android"],
                "invalid required platform policy")
        surfaces_ref = policy["protected_surfaces"]
        surfaces = trusted(
            Path(policy_path).parent / relative(surfaces_ref["path"]),
            surfaces_ref["sha256"], repo, evidence)
        if context_path is None:
            before = [commit(repo, base), commit(repo, head)]
            paths = changed_paths(repo, *before)
            report["protected_changes"] = protected_changes(paths, surfaces)
            require(before == [commit(repo, base), commit(repo, head)],
                    "refs changed during protection scan")
            report.update(status="BLOCKED", changed_paths=paths,
                          reason="No trusted PR/run context; scan only")
            return report
        context = trusted(context_path, context_sha, repo, evidence)
        report["context_sha"] = context_sha
        report["binding"] = {key: context[key] for key in BINDINGS}
        before = verify_context(repo, context, policy_sha)
        paths = changed_paths(repo, before[0], context["tested_commit"])
        report["changed_paths"] = paths
        report["protected_changes"] = protected_changes(paths, surfaces)
        if report["protected_changes"]:
            report["errors"].append("protected changes need separate review")
        for name in policy["required_platforms"]:
            try:
                result = platform_result(policy, context, name, evidence)
                report["platforms"][name] = {
                    "status": "PASS", "checks": result}
            except (ValueError, KeyError, TypeError, AttributeError, OSError,
                    ET.ParseError) as e:
                report["platforms"][name] = {"status": "FAIL", "error": str(e)}
                report["errors"].append(name + ": " + str(e))
        for name in policy["informational_platforms"]:
            report["platforms"][name] = {
                "required_for_merge": False,
                "reported": context.get("informational", {}).get(
                    name, {"status": "NOT_RUN"}),
                "verified_by_this_tool": False,
            }
        require(before == verify_context(repo, context, policy_sha),
                "base/head changed during verification")
        # Re-read trust roots to reject concurrent replacements.
        trusted(policy_path, policy_sha, repo, evidence)
        trusted(Path(policy_path).parent / surfaces_ref["path"],
                surfaces_ref["sha256"], repo, evidence)
        trusted(context_path, context_sha, repo, evidence)
        report["evidence_accepted"] = not report["errors"]
        report["status"] = "PASS" if not report["errors"] else "FAIL"
    except (ValueError, KeyError, TypeError, AttributeError, OSError,
            subprocess.SubprocessError) as error:
        report["errors"].append(str(error))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--trusted-policy", type=Path, required=True)
    parser.add_argument("--policy-sha256", required=True)
    parser.add_argument("--trusted-context", type=Path)
    parser.add_argument("--context-sha256")
    parser.add_argument("--base", help="full SHA/ref for context-free scan")
    parser.add_argument("--head", help="full SHA/ref for context-free scan")
    args = parser.parse_args(argv)
    if bool(args.trusted_context) != bool(args.context_sha256):
        parser.error("context path and digest are required together")
    if args.trusted_context is None and not (args.base and args.head):
        parser.error("scan requires --base and --head")
    result = evaluate(args.repo, args.evidence, args.trusted_policy,
                      args.policy_sha256, args.trusted_context,
                      args.context_sha256, args.base, args.head)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 3}[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
