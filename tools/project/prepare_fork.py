#!/usr/bin/env python3
"""Prepare an E2 review checklist using local Git and optional GET requests."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote

import preflight


class GitHubReads:
    """Use existing gh authentication without reading or printing its token."""

    def __init__(self):
        self.requests = []

    def get(self, endpoint):
        argv = ["gh", "api", "--hostname", "github.com", "--method", "GET",
                "--include", endpoint]
        env = dict(os.environ)
        env.pop("GH_DEBUG", None)
        try:
            result = subprocess.run(argv, capture_output=True, timeout=45,
                                    env=env)
        except (OSError, subprocess.TimeoutExpired) as error:
            self.requests.append({"method": "GET", "endpoint": endpoint,
                                  "http_status": None,
                                  "error_type": type(error).__name__})
            return None, None
        status, data = parse_response(result.stdout)
        self.requests.append({"method": "GET", "endpoint": endpoint,
                              "http_status": status,
                              "exit_code": result.returncode})
        if result.returncode and status == 200:
            return None, None
        return status, data


def parse_response(raw):
    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
    match = re.match(r"HTTP/\S+ (\d{3})[^\n]*\n", text)
    if not match:
        return None, None
    try:
        data = json.loads(text.split("\n\n", 1)[1])
    except (IndexError, ValueError):
        data = None
    return int(match.group(1)), data


def checklist(target, branch, head):
    """Descriptions only: deliberately no executable shell or write client."""
    return [
        {"id": "native_cdda_fork", "target": target,
         "review_request": {"method": "POST",
                            "endpoint": "/repos/" +
                            preflight.SOURCES["cdda"][0] + "/forks",
                            "body": {"name": target.split("/")[1]}
                            if target else None},
         "requirements": [
             "Use GitHub's native CDDA fork mechanism under the explicit "
             "personal account; never create an empty repository or fork CCB.",
             "An existing fork or name collision requires an explicit "
             "reuse decision; never delete, overwrite or migrate it."]},
        {"id": "keep_actions_off", "target": target,
         "requirements": [
             "Keep Actions disabled while inspecting the new fork. Verify "
             "this remotely before any project branch is uploaded.",
             "Do not configure signing secrets, an AI key, scheduled "
             "automation or public release permissions."]},
        {"id": "verify_fork_parent", "target": target,
         "requirements": [
             "Read back fork=true, personal owner and parent.full_name=" +
             preflight.SOURCES["cdda"][0] + "."]},
        {"id": "seed_new_branch", "target": target, "branch": branch,
         "source_commit": head,
         "requirements": [
             "Recheck local preflight and the inherited workflow quarantine.",
             "Recheck this exact target and that the destination branch is "
             "still absent immediately before the authorized upload.",
             "Upload only the new branch with original B/U history; preserve "
             "every existing ref. No force push, mirror, squash or rebase."]},
        {"id": "select_project_default", "target": target,
         "branch": branch,
         "requirements": [
             "After verifying the uploaded SHA/tree, change only this "
             "explicit project's default branch; preserve the old branch."]},
        {"id": "controlled_checks_only", "target": target,
         "requirements": [
             "Verify inherited release, notification and privileged callback "
             "entries are quarantined before enabling reviewed checks.",
             "Do not configure linear-history enforcement or require "
             "rewriting/signing all inherited commits.",
             "Windows/Linux PR gates require real protected-PR evidence; "
             "ordinary dispatch success is not that evidence.",
             "Keep automatic merge, daily public releases, stable releases "
             "and signing disabled until their separate readiness gates."]},
    ]


def prepare(repo, lock, target=None, branch=None, online=False, client=None):
    probe = preflight.Probe(repo)
    local = probe.run(lock, target=target)
    branch = branch or local.get("branch")
    report = {"schema_version": 1, "mode": "dry-run",
              "deployment_status": "IMPLEMENTED_NOT_DEPLOYED",
              "remote_writes_executed": False, "target": target,
              "branch": branch, "preflight": local,
              "blockers": [], "github_reads": []}

    def block(name, detail):
        report["blockers"].append({"id": name, "detail": detail,
                                   "status": "BLOCKED"})

    if local["local_status"] != "PASS":
        block("local_preflight", "Use a clean, trusted isolated checkout.")
    if not branch:
        block("branch", "Detached HEAD requires explicit --branch.")
    elif probe.git("check-ref-format", "--branch", branch)[0]:
        block("branch", "Destination is not a valid Git branch name.")
    if not target:
        block("target", "Supply the unique authorized OWNER/REPO; no owner "
              "or repository is inferred from account or machine names.")
    else:
        # A previous personal CCB fork used as the source cache is not CPH.
        remote_check = next((c for c in local["checks"]
                             if c["id"] == "fixed_read_only_remotes"), None)
        if remote_check and remote_check["status"] == "PASS":
            _, names = probe.git("remote")
            if "source-cache" in names.splitlines():
                _, cache = probe.git("remote", "get-url", "source-cache")
                cached = preflight.Probe(cache)
                code, origin = cached.git("remote", "get-url", "--all",
                                          "origin")
                push_code, push = cached.git("remote", "get-url", "--push",
                                             "--all", "origin")
                report["source_cache_read"] = cached.report["commands"]
                urls = origin.splitlines() + push.splitlines()
                identities = [preflight.github_repository(url)
                              for url in urls if url != "DISABLED"]
                if code or push_code or not identities or None in identities:
                    block("source_cache_identity",
                          "Cannot verify the source cache's origin.")
                elif target.lower() in {name.lower() for name in identities}:
                    block("source_cache_identity",
                          "The source cache's existing fork is not a new "
                          "authorized CPH target.")
        if online:
            client = client or GitHubReads()
            inspect_remote(client, target, branch, report, block)
            report["github_reads"] = client.requests
        else:
            block("remote_unverified", "Use --github for read-only account, "
                  "target-parent and branch checks; offline is not deployed.")
    report["checklist"] = checklist(target, branch, local.get("head"))
    report["status"] = "BLOCKED" if report["blockers"] else "PASS"
    report["execution_available"] = False
    return report


def inspect_remote(client, target, branch, report, block):
    owner = target.split("/")[0]
    status, user = client.get("/user")
    if (status != 200 or not isinstance(user, dict) or
            user.get("type") != "User" or
            user.get("login", "").lower() != owner.lower()):
        block("account", "Authenticated personal account must match target "
              "owner; missing/failed authentication is not permission.")
        return
    report["account"] = {"login": user["login"], "type": user["type"]}
    status, data = client.get("/repos/" + target)
    if status == 404:
        report["target_state"] = "NOT_FOUND_404"
        block("native_fork_needed", "Target returned HTTP 404. Confirm "
              "visibility/name availability, then create a native CDDA fork "
              "in a separately authorized execution step; nothing created.")
        return
    if status != 200 or not isinstance(data, dict):
        report["target_state"] = "READ_FAILED"
        block("target_read", "Target read failed (HTTP " + str(status) +
              "); never treat authorization/rate/network errors as absence.")
        return
    parent = (data.get("parent") or {}).get("full_name")
    report["target_state"] = "EXISTS"
    report["target_metadata"] = {
        "full_name": data.get("full_name"), "fork": data.get("fork"),
        "parent": parent, "default_branch": data.get("default_branch"),
        "admin_permission_reported": (data.get("permissions") or {})
        .get("admin"),
    }
    valid = (data.get("full_name", "").lower() == target.lower() and
             data.get("fork") is True and
             parent == preflight.SOURCES["cdda"][0] and
             (data.get("owner") or {}).get("type") == "User")
    if not valid:
        block("target_identity", "Existing name is not the requested "
              "personal CDDA fork; do not replace or modify it.")
        return
    if not (data.get("permissions") or {}).get("admin"):
        block("administration", "Target management permission is not "
              "confirmed; settings changes remain blocked.")
    block("existing_fork_scope", "Existing CDDA fork found; confirm the "
          "specific reuse/modification scope before any write.")
    if branch:
        endpoint = "/repos/" + target + "/git/ref/heads/" + quote(branch,
                                                                  safe="")
        status, ref = client.get(endpoint)
        if status == 200:
            block("branch_collision", "Destination branch already exists; "
                  "select a new unused branch without resetting this one.")
        elif status != 404:
            block("branch_read", "Branch read failed (HTTP " + str(status) +
                  "); absence was not established.")
        report["branch_http_status"] = status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--lock", type=Path,
                        default=Path(__file__).resolve().parents[2] /
                        "project/upstreams.lock.json")
    parser.add_argument("--target", help="explicit authorized OWNER/REPO")
    parser.add_argument("--branch", help="new remote branch; default: local "
                        "current branch, without changing local refs")
    parser.add_argument("--github", action="store_true")
    parser.add_argument("--dry-run", action="store_true", default=True)
    args = parser.parse_args(argv)
    if args.target and (not re.fullmatch(
            r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.target) or
            args.target.lower() in {v[0].lower()
                                    for v in preflight.SOURCES.values()}):
        parser.error("--target must name a distinct project repository")
    try:
        report = prepare(args.repo, preflight.read_lock(args.lock),
                         args.target, args.branch, args.github)
    except (OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired) as error:
        report = {"status": "FAIL", "mode": "dry-run",
                  "remote_writes_executed": False,
                  "error_type": type(error).__name__}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] == "FAIL" or \
            report.get("preflight", {}).get("local_status") == "FAIL":
        return 1
    return 3 if report["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    sys.exit(main())
