#!/usr/bin/env python3
"""CCB synchronization controller; candidate execution never receives a token.

Run only from the reviewed default-branch controller checkout. The state branch
is independent of game history. This module creates PRs, never merges them.
"""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

from check_merge_evidence import decode, protected_changes
from sync_dry_run import (
    BASE, UPSTREAM, Rehearsal, Stop, protection_policy, sha,
)


TARGET = "oncehere/Cataclysm-Phantom-Hope"
REPOSITORY_ID = 1389460908
CCB = "CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb"
CDDA = "CleverRaven/Cataclysm-DDA"
STATE_BRANCH = "codex/sync-state"
STATE_FILE = "state.json"
CI_WORKFLOW = "project-ci.yml"
API_ROOT = "https://api.github.com"
MAX_JSON = 2 * 1024 * 1024


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class GitHub:
    def __init__(self, token=None):
        self.token = token

    def request(self, method, path, data=None, missing=False):
        require(path.startswith("repos/"), "unexpected API path")
        if method != "GET":
            require(path.startswith("repos/" + TARGET + "/"),
                    "writes outside the authorized target are forbidden")
            require(self.token, "write credential is required")
        headers = {"Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "cph-remote-sync"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(
            API_ROOT + "/" + path, headers=headers, method=method,
            data=None if data is None else canonical(data))
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read(MAX_JSON + 1)
        except urllib.error.HTTPError as error:
            if missing and error.code == 404:
                return None
            raise ValueError(f"GitHub {method} returned HTTP {error.code}")
        require(len(raw) <= MAX_JSON, "oversized GitHub response")
        return json.loads(raw) if raw else None

    def repo(self, suffix, method="GET", data=None, missing=False):
        return self.request(method, "repos/" + TARGET + "/" + suffix,
                            data, missing)


def verify_target(api):
    repo = api.request("GET", "repos/" + TARGET)
    require(repo.get("id") == REPOSITORY_ID and
            repo.get("full_name") == TARGET and repo.get("fork") is True and
            repo.get("parent", {}).get("full_name") == CDDA and
            repo.get("source", {}).get("full_name") == CDDA and
            repo.get("default_branch") == "main",
            "target identity, fork parent or default branch changed")
    return repo


def validate_state(state):
    require(isinstance(state, dict) and state.get("schema_version") == 1 and
            state.get("repository_id") == REPOSITORY_ID,
            "invalid sync state identity")
    require(type(state.get("revision")) is int and state["revision"] >= 0,
            "invalid sync state revision")
    for key in ("sync_paused", "merge_paused", "auto_merge_enabled"):
        require(type(state.get(key)) is bool, "invalid operator control")
    sha(state.get("last_integrated_sha"))
    blocked = state.get("blocked_candidates")
    require(isinstance(blocked, list) and len(blocked) == len(set(blocked)),
            "invalid blocked candidates")
    for item in blocked:
        require(isinstance(item, str) and re.fullmatch(
            r"ccb-[0-9a-f]{40}", item), "invalid blocked candidate")
    locks = state.get("verified_rulesets", [])
    require(isinstance(locks, list), "invalid verified ruleset list")
    identifiers = set()
    for lock in locks:
        require(isinstance(lock, dict) and set(lock) == {
            "id", "updated_at", "visible_sha256", "bypass_actors"},
            "invalid verified ruleset fields")
        require(type(lock["id"]) is int and lock["id"] > 0 and
                lock["id"] not in identifiers and
                isinstance(lock["updated_at"], str) and
                bool(lock["updated_at"].strip()) and
                isinstance(lock["visible_sha256"], str) and
                re.fullmatch(r"[0-9a-f]{64}", lock["visible_sha256"]) and
                lock["bypass_actors"] == [],
                "invalid administrator-verified ruleset lock")
        identifiers.add(lock["id"])
    require(isinstance(state.get("tasks"), dict), "missing task state")
    for key, task in state["tasks"].items():
        sha(key)
        require(isinstance(task, dict) and
                task.get("task_key") == "ccb-" + key,
                "invalid task identity")
    return state


def load_state(api):
    ref = api.repo("git/ref/heads/" + STATE_BRANCH, missing=True)
    require(ref is not None, "sync state is not initialized")
    commit = sha(ref["object"]["sha"])
    tree = api.repo("git/commits/" + commit)["tree"]["sha"]
    entries = api.repo("git/trees/" + sha(tree))
    require(not entries.get("truncated") and len(entries["tree"]) == 1,
            "unexpected files in state branch")
    item = entries["tree"][0]
    require(item["path"] == STATE_FILE and item["type"] == "blob" and
            item["mode"] == "100644", "invalid state branch tree")
    blob = api.repo("git/blobs/" + sha(item["sha"]))
    require(blob["encoding"] == "base64" and blob["size"] <= MAX_JSON,
            "invalid state blob")
    state = decode(base64.b64decode(blob["content"]))
    return validate_state(state), commit


def save_state(api, state, expected_commit=None):
    """Competing children cannot both fast-forward the state ref."""
    validate_state(state)
    if expected_commit is not None:
        current = api.repo("git/ref/heads/" + STATE_BRANCH)
        require(current["object"]["sha"] == expected_commit,
                "state changed; retry with fresh controls")
    blob = api.repo("git/blobs", "POST", {
        "content": canonical(state).decode() + "\n", "encoding": "utf-8"})
    tree = api.repo("git/trees", "POST", {"tree": [{
        "path": STATE_FILE, "mode": "100644", "type": "blob",
        "sha": sha(blob["sha"])}]})
    commit = api.repo("git/commits", "POST", {
        "message": "Update CPH synchronization state",
        "tree": sha(tree["sha"]),
        "parents": [expected_commit] if expected_commit else []})
    new = sha(commit["sha"])
    if expected_commit:
        api.repo("git/refs/heads/" + STATE_BRANCH, "PATCH",
                 {"sha": new, "force": False})
    else:
        api.repo("git/refs", "POST", {
            "ref": "refs/heads/" + STATE_BRANCH, "sha": new})
    require(api.repo("git/ref/heads/" + STATE_BRANCH)["object"]["sha"] == new,
            "state readback differs")
    return new


def check_controls(state, candidate, merge=False):
    validate_state(state)
    require(not state["sync_paused"], "synchronization is paused")
    require(candidate not in state["blocked_candidates"],
            "candidate is blocked")
    if merge:
        require(not state["merge_paused"] and state["auto_merge_enabled"],
                "automatic merging is paused or disabled")


def initial_state():
    return {"schema_version": 1, "repository_id": REPOSITORY_ID,
            "revision": 0, "sync_paused": True, "merge_paused": True,
            "auto_merge_enabled": False, "blocked_candidates": [],
            "verified_rulesets": [], "last_integrated_sha": UPSTREAM,
            "tasks": {}}


def clean_env():
    env = {key: os.environ[key] for key in (
        "PATH", "HOME", "TMPDIR", "SYSTEMROOT", "WINDIR")
        if key in os.environ}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0",
               GIT_PAGER="cat", LC_ALL="C")
    return env


def git(repo, *args, data=None, token=None):
    env = clean_env()
    if token:
        env.update(GIT_CONFIG_COUNT="1",
                   GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
                   GIT_CONFIG_VALUE_0="AUTHORIZATION: basic " +
                   base64.b64encode(("x-access-token:" + token).encode())
                   .decode())
    command = ["git", "--no-replace-objects", "-c",
               "core.hooksPath=" + os.devnull, "-c", "core.fsmonitor=false",
               "-c", "core.attributesFile=" + os.devnull,
               "-c", "protocol.allow=never",
               "-c", "protocol.https.allow=always",
               "-c", "submodule.recurse=false", "-c", "gc.auto=0",
               "-c", "maintenance.auto=false", "-c", "commit.gpgSign=false",
               "-C", str(repo), *args]
    process = subprocess.run(command, env=env, input=data, text=True,
                             capture_output=True, timeout=1800)
    require(process.returncode == 0,
            f"git {args[0]} failed with exit {process.returncode}")
    return process.stdout.strip()


def public_fetch(repo, remote, ref):
    git(repo, "fetch", "--no-tags", "--no-write-fetch-head",
        "--recurse-submodules=no", "--filter=blob:none", remote, ref)


def hydrate(repo, remote, heads, boundary=None):
    """Fetch the range and its actual boundary blobs without lazy fetching."""
    args = ["rev-list", "--objects", "--no-object-names", "--missing=print",
            *heads]
    if boundary:
        args.extend(("--not", boundary))
    missing = [line[1:] for line in git(repo, *args).splitlines()
               if line.startswith("?")]
    if missing:
        for item in missing:
            sha(item)
        git(repo, "fetch", "--no-tags", "--no-write-fetch-head",
            "--recurse-submodules=no", "--filter=blob:none", remote,
            "--stdin", data="\n".join(missing) + "\n")
    if boundary:
        # A merged side branch can meet the excluded history before the main
        # merge base. Its old blobs are absent from the range, but bundle's
        # thin pack may still read them when considering delta bases.
        boundaries = git(repo, "rev-list", "--boundary", *heads,
                         "--not", sha(boundary)).splitlines()
        for line in boundaries:
            if line.startswith("-"):
                hydrate_tree(repo, remote, sha(line[1:]))


def hydrate_tree(repo, remote, commit):
    entries = git(repo, "ls-tree", "-r", sha(commit)).splitlines()
    objects = {line.split()[2] for line in entries
               if line.split()[1] == "blob"}
    if not objects:
        return
    result = git(repo, "cat-file", "--batch-check=%(objectname) %(objecttype)",
                 data="\n".join(sorted(objects)) + "\n")
    missing = [line.split()[0] for line in result.splitlines()
               if line.endswith(" missing")]
    if missing:
        git(repo, "fetch", "--no-tags", "--no-write-fetch-head",
            "--filter=blob:none", "--recurse-submodules=no", remote,
            "--stdin", data="\n".join(missing) + "\n")


def fetch_source(path, base, upstream, checkout=False):
    path.mkdir()
    git(path, "init", "--template=")
    for name, repository in (("origin", TARGET), ("ccb", CCB),
                             ("upstream", CDDA)):
        git(path, "remote", "add", name,
            "https://github.com/" + repository + ".git")
        git(path, "config", "remote." + name + ".promisor", "true")
        git(path, "config", "remote." + name + ".partialclonefilter",
            "blob:none")
    public_fetch(path, "origin", sha(base))
    public_fetch(path, "ccb", sha(upstream))
    git(path, "update-ref", "refs/remotes/ccb/master", upstream)
    if checkout:
        hydrate_tree(path, "origin", base)
        hydrate_tree(path, "ccb", upstream)
        common = git(path, "merge-base", base, upstream)
        hydrate_tree(path, "ccb", common)
        # Candidate bundles retain all new upstream history, not only its tree.
        hydrate(path, "ccb", [upstream], base)
        git(path, "config", "user.name", "github-actions[bot]")
        git(path, "config", "user.email",
            "41898282+github-actions[bot]@users.noreply.github.com")
        git(path, "checkout", "--detach", base)


def snapshot(api):
    verify_target(api)
    state, revision = load_state(api)
    base = sha(api.repo("git/ref/heads/main")["object"]["sha"])
    upstream = sha(api.request(
        "GET", "repos/" + CCB + "/git/ref/heads/master")["object"]["sha"])
    return {"schema_version": 1, "repository_id": REPOSITORY_ID,
            "base": base, "upstream": upstream,
            "previous_integrated": state["last_integrated_sha"],
            "state_commit": revision, "controls_revision": state["revision"],
            "task_key": "ccb-" + upstream,
            "paused": state["sync_paused"] or
            "ccb-" + upstream in state["blocked_candidates"]}


def bind_controller(plan):
    controller = Path(__file__).resolve().parents[2]
    require(git(controller, "rev-parse", "HEAD") == plan["base"],
            "controller is not the fixed current main; rerun from main")


def prepare(output):
    require(not output.exists(), "output directory must be new")
    output.mkdir(parents=True)
    plan = snapshot(GitHub())
    bind_controller(plan)
    if plan["paused"]:
        plan.update(status="PAUSED", reason="operator control is paused")
    elif plan["upstream"] == plan["previous_integrated"]:
        comparison = GitHub().repo("compare/" + plan["upstream"] + "...main")
        require(comparison["behind_by"] == 0,
                "recorded integrated source is absent from main")
        plan.update(status="PASS", result="no_new_upstream_commits",
                    reason="CCB has no new commits; no candidate or PR")
    else:
        source = output / "source"
        fetch_source(source, plan["base"], plan["upstream"], checkout=True)
        lock = decode((Path(__file__).resolve().parents[2] /
                       "project/upstreams.lock.json").read_bytes())
        require(lock["cdda"]["commit"] == BASE and
                lock["ccb"]["commit"] == UPSTREAM,
                "controller initial history changed")
        rehearsal = Rehearsal(
            source, output / "rehearsal", plan["base"], plan["upstream"],
            plan["previous_integrated"], lock)
        report = rehearsal.run()
        plan.update(status=report["status"], reason=report["reason"],
                    result=report.get("result"),
                    protected_changes=report.get("protected_changes", []),
                    conflicts=report.get("conflicts", []))
        if report.get("result") == "merge_candidate_only":
            candidate = Path(report["candidate_directory"])
            head = report["candidate_commit"]
            git(candidate, "update-ref", "refs/heads/candidate", head)
            bundle = output / "candidate.bundle"
            git(candidate, "bundle", "create", str(bundle),
                "refs/heads/candidate", "^" + plan["base"])
            plan.update(head=head, tree=report["candidate_tree"],
                        bundle_sha256=file_digest(bundle))
    (output / "plan.json").write_bytes(canonical(plan) + b"\n")
    return plan


def file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fresh_controls(api, plan):
    verify_target(api)
    state, revision = load_state(api)
    require(state["revision"] == plan["controls_revision"],
            "operator controls changed; start a fresh attempt")
    require(state["last_integrated_sha"] == plan["previous_integrated"],
            "integrated source changed; start a fresh attempt")
    check_controls(state, plan["task_key"])
    require(api.repo("git/ref/heads/main")["object"]["sha"] == plan["base"],
            "main moved; rebuild and retest")
    require(api.request("GET", "repos/" + CCB + "/git/ref/heads/master")
            ["object"]["sha"] == plan["upstream"],
            "CCB moved; rebuild and retest")
    return state, revision


def validate_candidate(repo, plan):
    head, base, upstream = [sha(plan[key]) for key in
                            ("head", "base", "upstream")]
    require(git(repo, "show", "-s", "--format=%P", head).split() ==
            [base, upstream], "candidate merge parents differ")
    require(git(repo, "rev-parse", head + "^{tree}") == sha(plan["tree"]),
            "candidate tree differs")
    for older, newer in ((BASE, UPSTREAM), (UPSTREAM, upstream),
                         (plan["previous_integrated"], base),
                         (plan["previous_integrated"], upstream)):
        git(repo, "merge-base", "--is-ancestor", sha(older), sha(newer))
    surfaces, _ = protection_policy()
    paths = git(repo, "diff", "--name-only", "--no-renames", "-z",
                plan["previous_integrated"], upstream).split("\0")
    require(not protected_changes([p for p in paths if p], surfaces),
            "upstream touches protected surfaces")
    paths = git(repo, "diff", "--name-only", "--no-renames", "-z",
                base, head).split("\0")
    require(not protected_changes([p for p in paths if p], surfaces),
            "candidate changes trusted surfaces")
    # Check the candidate really is Git's merge tree, not a forged artifact.
    hydrate_tree(repo, "origin", base)
    hydrate_tree(repo, "ccb", upstream)
    hydrate_tree(repo, "ccb", git(repo, "merge-base", base, upstream))
    merged = git(repo, "merge-tree", "--write-tree", base, upstream)
    require(merged.splitlines()[0] == plan["tree"],
            "candidate is not the expected merge tree")


def branch_for(api, plan):
    stem = "codex/ccb-" + plan["upstream"]
    for branch in (stem, stem + "-" + plan["base"]):
        ref = api.repo("git/ref/heads/" + branch, missing=True)
        if ref is None:
            return branch, None
        head = sha(ref["object"]["sha"])
        commit = api.repo("git/commits/" + head)
        if ([p["sha"] for p in commit["parents"]] ==
                [plan["base"], plan["upstream"]] and
                commit["tree"]["sha"] == plan["tree"]):
            return branch, head
    raise ValueError("existing attempt branch differs; never force update")


def task_result(api, plan, **extra):
    state, revision = fresh_controls(api, plan)
    task = {key: plan[key] for key in (
        "task_key", "base", "upstream", "status", "reason")}
    task.update(extra)
    state["tasks"][plan["upstream"]] = task
    save_state(api, state, revision)


def publish(directory, work, api):
    plan = decode((directory / "plan.json").read_bytes())
    require(plan.get("schema_version") == 1 and
            plan.get("repository_id") == REPOSITORY_ID,
            "invalid plan identity")
    for key in ("base", "upstream", "previous_integrated", "state_commit"):
        sha(plan.get(key))
    require(plan.get("task_key") == "ccb-" + plan["upstream"],
            "invalid plan task identity")
    bind_controller(plan)
    recovered = recover_merged(api)
    if recovered:
        return {"status": "RECOVERED", "merged_sources": recovered,
                "reason": "remote merge recorded; next run uses fresh state"}
    if plan["status"] == "PAUSED":
        return plan
    state, _ = fresh_controls(api, plan)
    if plan["status"] != "PASS":
        require(plan["status"] in ("FAIL", "BLOCKED"), "invalid plan status")
        task_result(api, plan, conflicts=plan.get("conflicts", []),
                    protected_changes=plan.get("protected_changes", []))
        return plan
    if plan.get("result") == "no_new_upstream_commits":
        return plan
    require(plan.get("result") == "merge_candidate_only",
            "unexpected candidate result")
    bundle = directory / "candidate.bundle"
    require(bundle.is_file() and not bundle.is_symlink() and
            file_digest(bundle) == plan.get("bundle_sha256"),
            "candidate bundle differs")
    fetch_source(work, plan["base"], plan["upstream"])
    git(work, "bundle", "verify", str(bundle.resolve()))
    git(work, "bundle", "unbundle", str(bundle.resolve()))
    validate_candidate(work, plan)
    branch, head = branch_for(api, plan)
    old = state["tasks"].get(plan["upstream"], {})
    if head is None:
        fresh_controls(api, plan)
        hydrate(work, "ccb", [plan["upstream"]], plan["base"])
        git(work, "push", "--porcelain", "--no-thin", "--no-force",
            "--no-follow-tags", "https://github.com/" + TARGET + ".git",
            plan["head"] + ":refs/heads/" + branch, token=api.token)
        head = plan["head"]
    require(api.repo("git/ref/heads/" + branch)["object"]["sha"] == head,
            "candidate branch readback differs")
    query = urllib.parse.urlencode({"state": "all", "base": "main",
                                    "head": "oncehere:" + branch})
    prs = api.repo("pulls?" + query)
    require(len(prs) <= 1, "ambiguous PR identity")
    if prs:
        pr = prs[0]
        require(pr["head"]["sha"] == head and pr["state"] == "open",
                "existing PR closed or changed; explicit retry required")
    else:
        fresh_controls(api, plan)
        pr = api.repo("pulls", "POST", {
            "title": "Integrate CCB " + plan["upstream"][:12],
            "head": branch, "base": "main", "body": (
                "Integrates CCB master and retains its original history.\n\n"
                "Source: `" + plan["upstream"] + "`\n"
                "Project base: `" + plan["base"] + "`\n\n"
                "Local history/merge checks passed. Native Windows/Linux "
                "checks must pass before merging.\n\n"
                "Responsible human: @oncehere\n"
                "Documentation impact: no protected documentation changes\n"
                "Related CCB-Docs PR: none\n"
                "Affected documentation IDs: none\n"
                "Generated reference impact: none\n\n"
                "<!-- cph-sync:" + plan["task_key"] + " -->")})
    task_result(api, plan, head=head, tree=plan["tree"], branch=branch,
                pr_number=pr["number"], status="PR_OPEN")
    # A replacement attempt uses a new branch; never rewrites prior history.
    if old.get("pr_number") and old["pr_number"] != pr["number"]:
        fresh_controls(api, plan)
        api.repo("pulls/" + str(old["pr_number"]), "PATCH",
                 {"state": "closed"})
    fresh_controls(api, plan)
    api.repo("actions/workflows/" + CI_WORKFLOW + "/dispatches", "POST", {
        "ref": "main", "inputs": {
            "pr_number": str(pr["number"]), "base_sha": plan["base"],
            "head_sha": head}})
    return {**plan, "status": "PR_OPEN", "head": head,
            "pr_number": pr["number"], "branch": branch}


def record_merged(api, upstream, head):
    """Called after merge API success; verify the remote again."""
    verify_target(api)
    state, revision = load_state(api)
    task = state["tasks"].get(sha(upstream), {})
    require(task.get("head") == sha(head), "merged task head differs")
    require(type(task.get("pr_number")) is int and task["pr_number"] > 0,
            "invalid recorded PR number")
    pr = api.repo("pulls/" + str(task["pr_number"]))
    require(pr.get("merged") is True and pr["head"]["sha"] == head and
            pr["base"]["ref"] == "main" and
            pr["base"]["repo"]["id"] == REPOSITORY_ID,
            "PR is not the recorded merged candidate")
    comparison = api.repo("compare/" + upstream + "...main")
    require(comparison["behind_by"] == 0,
            "main did not retain integrated upstream history")
    continuity = api.repo("compare/" + state["last_integrated_sha"] +
                          "..." + upstream)
    if continuity["behind_by"] == 0:
        state["last_integrated_sha"] = upstream
    else:
        already_integrated = api.repo(
            "compare/" + upstream + "..." + state["last_integrated_sha"])
        require(already_integrated["behind_by"] == 0,
                "integrated source histories diverged")
        # An older completed task may be recovered after a newer one. Keep
        # the newer cursor and repair only the older task's factual status.
    task["status"] = "MERGED"
    save_state(api, state, revision)


def recover_merged(api):
    """Recover a successful merge whose state-write response was lost."""
    verify_target(api)
    state, _ = load_state(api)
    recovered = []
    for upstream, task in state["tasks"].items():
        if task.get("status") != "PR_OPEN":
            continue
        number = task.get("pr_number")
        require(type(number) is int and number > 0, "invalid recorded PR")
        pr = api.repo("pulls/" + str(number))
        if pr.get("merged") is True:
            record_merged(api, upstream, task["head"])
            recovered.append(upstream)
    return recovered


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    command = commands.add_parser("prepare")
    command.add_argument("--output", type=Path, required=True)
    command = commands.add_parser("publish")
    command.add_argument("--input", type=Path, required=True)
    command.add_argument("--work", type=Path, required=True)
    commands.add_parser("init-state")
    command = commands.add_parser("controls")
    command.add_argument("--revision", type=int, required=True)
    command.add_argument("--sync", choices=("pause", "resume"))
    command.add_argument("--merge", choices=("pause", "resume"))
    command.add_argument("--auto-merge", choices=("enable", "disable"))
    command.add_argument("--block")
    command.add_argument("--unblock")
    args = parser.parse_args(argv)
    try:
        if args.action == "prepare":
            result = prepare(args.output.resolve())
        else:
            api = GitHub(os.environ.get("GH_TOKEN"))
            verify_target(api)
            if args.action == "publish":
                result = publish(args.input.resolve(),
                                 args.work.resolve(), api)
            elif args.action == "init-state":
                state = initial_state()
                comparison = api.repo("compare/" + UPSTREAM + "...main")
                require(comparison["behind_by"] == 0,
                        "initial CCB source is absent from main")
                save_state(api, state)
                result = state
            else:
                state, commit = load_state(api)
                require(state["revision"] == args.revision,
                        "operator revision changed")
                for key, value in (("sync_paused", args.sync),
                                   ("merge_paused", args.merge)):
                    if value:
                        state[key] = value == "pause"
                if args.auto_merge:
                    state["auto_merge_enabled"] = args.auto_merge == "enable"
                blocked = set(state["blocked_candidates"])
                if args.block:
                    blocked.add(args.block)
                if args.unblock:
                    blocked.discard(args.unblock)
                state["blocked_candidates"] = sorted(blocked)
                state["revision"] += 1
                save_state(api, state, commit)
                result = state
        print(json.dumps(result, ensure_ascii=False, indent=2))
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as stream:
                stream.write("### CCB synchronization\n\n```json\n" +
                             json.dumps(result, indent=2) + "\n```\n")
        return 1 if result.get("status") in ("FAIL", "BLOCKED") else 0
    except (Stop, ValueError, KeyError, TypeError, OSError,
            subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "FAIL", "reason": str(error)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
