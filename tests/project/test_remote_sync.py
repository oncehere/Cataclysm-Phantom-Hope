"""Local controller tests; no GitHub writes or platform acceptance claims."""

import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_sync_dry_run


TOOLS = Path(__file__).resolve().parents[2] / "tools/project"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location(
    "remote_sync", TOOLS / "remote_sync.py")
remote = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(remote)


class FakeAPI:
    """Explicit remote-state model; never represents real GitHub acceptance."""

    def __init__(self):
        self.token = "fixture-token-not-a-secret"
        self.state = remote.initial_state()
        self.state["sync_paused"] = False
        self.revision = "a" * 40
        self.base = "b" * 40
        self.upstream = remote.UPSTREAM
        self.writes = []
        self.ref = None
        self.commits = {}
        self.pr = None

    def request(self, method, path, data=None, missing=False):
        if path == "repos/" + remote.TARGET:
            return {"id": remote.REPOSITORY_ID, "full_name": remote.TARGET,
                    "fork": True, "parent": {"full_name": remote.CDDA},
                    "source": {"full_name": remote.CDDA},
                    "default_branch": "main"}
        if path == "repos/" + remote.CCB + "/git/ref/heads/master":
            return {"object": {"sha": self.upstream}}
        raise AssertionError((method, path, data))

    def repo(self, path, method="GET", data=None, missing=False):
        if method != "GET":
            self.writes.append((method, path, data))
            if path == "git/blobs":
                self.written_state = json.loads(data["content"])
                return {"sha": "1" * 40}
            if path == "git/trees":
                return {"sha": "2" * 40}
            if path == "git/commits":
                return {"sha": "3" * 40}
            if path.startswith("git/refs"):
                self.revision = data["sha"]
                self.state = copy.deepcopy(self.written_state)
                return {"object": {"sha": self.revision}}
            raise AssertionError((method, path, data))
        if path == "git/ref/heads/" + remote.STATE_BRANCH:
            return {"object": {"sha": self.revision}}
        if path == "git/commits/" + self.revision:
            return {"tree": {"sha": "d" * 40}}
        if path == "git/trees/" + "d" * 40:
            return {"tree": [{"path": "state.json", "mode": "100644",
                              "type": "blob", "sha": "e" * 40}]}
        if path == "git/blobs/" + "e" * 40:
            data = remote.canonical(self.state)
            return {"encoding": "base64", "size": len(data),
                    "content": base64.b64encode(data).decode()}
        if path == "git/ref/heads/main":
            return {"object": {"sha": self.base}}
        if path.startswith("compare/"):
            return {"behind_by": 0}
        if path.startswith("git/ref/heads/codex/ccb-"):
            return self.ref
        if path.startswith("git/commits/"):
            return self.commits[path.removeprefix("git/commits/")]
        if path.startswith("pulls/"):
            return self.pr
        raise AssertionError((method, path, data))


class StateTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeAPI()

    def test_state_initializes_paused_with_fixed_upstream(self):
        state = remote.initial_state()
        self.assertTrue(state["sync_paused"])
        self.assertTrue(state["merge_paused"])
        self.assertFalse(state["auto_merge_enabled"])
        self.assertEqual(state["last_integrated_sha"], remote.UPSTREAM)
        self.assertEqual(state["verified_rulesets"], [])

    def test_legacy_state_without_ruleset_locks_remains_readable(self):
        state = remote.initial_state()
        del state["verified_rulesets"]
        remote.validate_state(state)
        self.assertNotIn("verified_rulesets", state)

    def test_ruleset_locks_require_unique_ids_digest_and_no_bypass(self):
        lock = {"id": 42, "updated_at": "2026-09-26T23:00:00Z",
                "visible_sha256": "a" * 64, "bypass_actors": []}
        state = remote.initial_state()
        state["verified_rulesets"] = [lock]
        remote.validate_state(state)
        for key, value in (("id", True), ("updated_at", " "),
                           ("visible_sha256", "bad"),
                           ("bypass_actors", [{"actor_id": 1}])):
            with self.subTest(field=key):
                invalid = copy.deepcopy(state)
                invalid["verified_rulesets"][0][key] = value
                with self.assertRaises(ValueError):
                    remote.validate_state(invalid)
        for locks in (None, [lock, lock], [{**lock, "unexpected": True}]):
            invalid = copy.deepcopy(state)
            invalid["verified_rulesets"] = locks
            with self.assertRaises(ValueError):
                remote.validate_state(invalid)

    def test_load_state_and_cas_preserve_single_file_and_no_force(self):
        state, commit = remote.load_state(self.api)
        self.assertEqual(state, self.api.state)
        remote.save_state(self.api, state, commit)
        commit_write = next(data for _, path, data in self.api.writes
                            if path == "git/commits")
        self.assertEqual(commit_write["parents"], ["a" * 40])
        self.assertEqual(self.api.writes[-1][2],
                         {"sha": "3" * 40, "force": False})

    def test_stale_state_never_writes(self):
        with self.assertRaisesRegex(ValueError, "state changed"):
            remote.save_state(self.api, self.api.state, "f" * 40)
        self.assertEqual(self.api.writes, [])

    def test_no_change_never_clones_or_creates_pr(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(remote, "GitHub", return_value=self.api), \
                    patch.object(remote, "bind_controller"), \
                    patch.object(remote, "fetch_source") as fetch:
                result = remote.prepare(Path(temp) / "evidence")
            fetch.assert_not_called()
            self.assertEqual(result["result"], "no_new_upstream_commits")
            self.assertEqual(self.api.writes, [])

    def test_pause_and_block_rechecked_at_final_action(self):
        plan = remote.snapshot(self.api)
        for field, value in (("sync_paused", True),
                             ("blocked_candidates", [plan["task_key"]])):
            self.api.state = remote.initial_state()
            self.api.state["sync_paused"] = False
            self.api.state[field] = value
            with self.assertRaises(ValueError):
                remote.fresh_controls(self.api, plan)
            self.assertEqual(self.api.writes, [])

    def test_moving_refs_and_changed_controls_block(self):
        plan = remote.snapshot(self.api)
        self.api.base = "c" * 40
        with self.assertRaisesRegex(ValueError, "main moved"):
            remote.fresh_controls(self.api, plan)
        self.api.base = plan["base"]
        self.api.upstream = "c" * 40
        with self.assertRaisesRegex(ValueError, "CCB moved"):
            remote.fresh_controls(self.api, plan)
        self.api.upstream = plan["upstream"]
        self.api.state["revision"] += 1
        with self.assertRaisesRegex(ValueError, "operator controls changed"):
            remote.fresh_controls(self.api, plan)

    def test_merge_disabled_independently_of_sync(self):
        state = self.api.state
        remote.check_controls(state, "ccb-" + remote.UPSTREAM)
        with self.assertRaisesRegex(ValueError, "merging is paused"):
            remote.check_controls(state, "ccb-" + remote.UPSTREAM, merge=True)
        state.update(merge_paused=False, auto_merge_enabled=True)
        remote.check_controls(state, "ccb-" + remote.UPSTREAM, merge=True)

    def test_same_merge_tree_reuses_existing_head(self):
        plan = remote.snapshot(self.api)
        plan["tree"] = "f" * 40
        existing = "c" * 40
        self.api.ref = {"object": {"sha": existing}}
        self.api.commits[existing] = {
            "parents": [{"sha": plan["base"]}, {"sha": plan["upstream"]}],
            "tree": {"sha": plan["tree"]}}
        branch, head = remote.branch_for(self.api, plan)
        self.assertEqual(head, existing)
        self.assertEqual(branch, "codex/ccb-" + plan["upstream"])

    def test_unexpected_branch_history_never_force_updates(self):
        plan = remote.snapshot(self.api)
        plan["tree"] = "f" * 40
        existing = "c" * 40
        self.api.ref = {"object": {"sha": existing}}
        self.api.commits[existing] = {"parents": [],
                                      "tree": {"sha": plan["tree"]}}
        with self.assertRaisesRegex(ValueError, "never force"):
            remote.branch_for(self.api, plan)
        self.assertEqual(self.api.writes, [])

    def test_conflict_is_persisted_as_same_task_without_pr(self):
        plan = remote.snapshot(self.api)
        plan.update(status="FAIL", reason="merge conflict", conflicts=["x"])
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "plan.json").write_bytes(remote.canonical(plan))
            with patch.object(remote, "bind_controller"):
                result = remote.publish(directory, directory / "work",
                                        self.api)
        task = self.api.written_state["tasks"][plan["upstream"]]
        self.assertEqual(task["conflicts"], ["x"])
        self.assertEqual(task["task_key"], plan["task_key"])
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(any("pulls" in path
                             for _, path, _ in self.api.writes))

    def test_external_repository_write_rejected_before_network(self):
        with self.assertRaisesRegex(ValueError, "outside the authorized"):
            remote.GitHub("fixture").request(
                "POST", "repos/" + remote.CCB + "/pulls", {})

    def test_stale_controller_is_rejected(self):
        with patch.object(remote, "git", return_value="f" * 40):
            with self.assertRaisesRegex(ValueError, "controller is not"):
                remote.bind_controller({"base": "b" * 40})

    def test_token_and_git_overrides_absent_from_candidate_environment(self):
        with patch.dict(os.environ, {"GH_TOKEN": "fixture",
                                     "GITHUB_TOKEN": "fixture",
                                     "GIT_CONFIG_COUNT": "100",
                                     "SSH_ASKPASS": "untrusted"}):
            env = remote.clean_env()
        for name in ("GH_TOKEN", "GITHUB_TOKEN", "GIT_CONFIG_COUNT",
                     "SSH_ASKPASS"):
            self.assertNotIn(name, env)

    def test_record_merged_requires_remote_fact(self):
        self.api.state["tasks"][remote.UPSTREAM] = {
            "task_key": "ccb-" + remote.UPSTREAM,
            "head": "c" * 40, "pr_number": 7}
        self.api.pr = {"merged": False, "head": {"sha": "c" * 40},
                       "base": {"ref": "main",
                                "repo": {"id": remote.REPOSITORY_ID}}}
        with self.assertRaisesRegex(ValueError, "not the recorded merged"):
            remote.record_merged(self.api, remote.UPSTREAM, "c" * 40)
        self.assertEqual(self.api.writes, [])

    def test_remote_merge_recovers_lost_state_update(self):
        self.api.state["tasks"][remote.UPSTREAM] = {
            "task_key": "ccb-" + remote.UPSTREAM,
            "head": "c" * 40, "pr_number": 7, "status": "PR_OPEN"}
        self.api.pr = {"merged": True, "head": {"sha": "c" * 40},
                       "base": {"ref": "main",
                                "repo": {"id": remote.REPOSITORY_ID}}}
        self.assertEqual(remote.recover_merged(self.api), [remote.UPSTREAM])
        self.assertEqual(self.api.written_state["tasks"]
                         [remote.UPSTREAM]["status"], "MERGED")

    def test_divergent_integrated_source_is_rejected(self):
        self.api.state["last_integrated_sha"] = "f" * 40
        self.api.state["tasks"][remote.UPSTREAM] = {
            "task_key": "ccb-" + remote.UPSTREAM,
            "head": "c" * 40, "pr_number": 7, "status": "PR_OPEN"}
        self.api.pr = {"merged": True, "head": {"sha": "c" * 40},
                       "base": {"ref": "main",
                                "repo": {"id": remote.REPOSITORY_ID}}}
        original = self.api.repo

        def divergence(path, *args, **kwargs):
            if path in {
                "compare/" + "f" * 40 + "..." + remote.UPSTREAM,
                "compare/" + remote.UPSTREAM + "..." + "f" * 40,
            }:
                return {"behind_by": 1}
            return original(path, *args, **kwargs)

        self.api.repo = divergence
        with self.assertRaisesRegex(ValueError, "histories diverged"):
            remote.record_merged(self.api, remote.UPSTREAM, "c" * 40)
        self.assertEqual(self.api.writes, [])

    def test_recovery_order_never_regresses_cursor_or_strands_old_task(self):
        for older, newer in (("f" * 40, "a" * 40),
                             ("a" * 40, "f" * 40)):
            with self.subTest(recovery_order=sorted((older, newer))):
                api = FakeAPI()
                prs = {}
                for number, upstream in enumerate((older, newer), 1):
                    head = str(number) * 40
                    api.state["tasks"][upstream] = {
                        "task_key": "ccb-" + upstream, "head": head,
                        "pr_number": number, "status": "PR_OPEN"}
                    prs["pulls/" + str(number)] = {
                        "merged": True, "head": {"sha": head},
                        "base": {"ref": "main", "repo": {
                            "id": remote.REPOSITORY_ID}}}
                ranks = {remote.UPSTREAM: 0, older: 1, newer: 2, "main": 3}
                original = api.repo

                def ordered_history(path, *args, **kwargs):
                    if path in prs:
                        return prs[path]
                    if path.startswith("compare/"):
                        base, head = path[8:].split("...")
                        return {"behind_by": int(ranks[base] > ranks[head])}
                    return original(path, *args, **kwargs)

                api.repo = ordered_history
                self.assertEqual(remote.recover_merged(api),
                                 sorted((older, newer)))
                self.assertEqual(api.state["last_integrated_sha"], newer)
                self.assertTrue(all(task["status"] == "MERGED"
                                    for task in api.state["tasks"].values()))
                self.assertEqual(remote.recover_merged(api), [])

    def test_invalid_controls_never_default_open(self):
        for key, value in (("sync_paused", None), ("revision", True),
                           ("last_integrated_sha", "bad")):
            state = copy.deepcopy(self.api.state)
            state[key] = value
            with self.assertRaises((ValueError, remote.Stop)):
                remote.validate_state(state)


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_sync_dry_run.MergeFixture()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_real_merge_validated_and_forged_tree_rejected(self):
        fixture = self.fixture
        newer = fixture.upstream()
        report = fixture.probe(newer).run()
        self.assertEqual(report["status"], "PASS")
        plan = {"base": fixture.h, "upstream": newer,
                "previous_integrated": fixture.u,
                "head": report["candidate_commit"],
                "tree": report["candidate_tree"]}
        with patch.object(remote, "BASE", fixture.b), \
                patch.object(remote, "UPSTREAM", fixture.u), \
                patch.object(remote, "hydrate_tree"):
            remote.validate_candidate(
                Path(report["candidate_directory"]), plan)
            plan["tree"] = "f" * 40
            with self.assertRaisesRegex(ValueError, "tree differs"):
                remote.validate_candidate(
                    Path(report["candidate_directory"]), plan)

    def test_candidate_cannot_restore_workflow_or_modify_gate(self):
        fixture = self.fixture
        newer = fixture.upstream()
        report = fixture.probe(newer).run()
        candidate = Path(report["candidate_directory"])
        forbidden = candidate / ".github/workflows/restored.yml"
        forbidden.parent.mkdir(parents=True)
        forbidden.write_text("on: push\n")
        remote.git(candidate, "add", ".github")
        remote.git(candidate, "commit", "--amend", "--no-edit")
        plan = {"base": fixture.h, "upstream": newer,
                "previous_integrated": fixture.u,
                "head": remote.git(candidate, "rev-parse", "HEAD"),
                "tree": remote.git(candidate, "rev-parse", "HEAD^{tree}")}
        with patch.object(remote, "BASE", fixture.b), \
                patch.object(remote, "UPSTREAM", fixture.u):
            with self.assertRaisesRegex(ValueError, "trusted surfaces"):
                remote.validate_candidate(candidate, plan)

    def test_forged_ordinary_content_fails_merge_tree_recomputation(self):
        fixture = self.fixture
        newer = fixture.upstream()
        report = fixture.probe(newer).run()
        candidate = Path(report["candidate_directory"])
        (candidate / "new.txt").write_text("forged content\n")
        remote.git(candidate, "add", "new.txt")
        remote.git(candidate, "commit", "--amend", "--no-edit")
        plan = {"base": fixture.h, "upstream": newer,
                "previous_integrated": fixture.u,
                "head": remote.git(candidate, "rev-parse", "HEAD"),
                "tree": remote.git(candidate, "rev-parse", "HEAD^{tree}")}
        with patch.object(remote, "BASE", fixture.b), \
                patch.object(remote, "UPSTREAM", fixture.u), \
                patch.object(remote, "hydrate_tree"):
            with self.assertRaisesRegex(ValueError, "expected merge tree"):
                remote.validate_candidate(candidate, plan)


if __name__ == "__main__":
    unittest.main()
