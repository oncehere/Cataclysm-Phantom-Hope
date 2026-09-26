"""E2 local Git/API fixtures; these do not prove real GitHub deployment."""

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_preflight


TOOLS = Path(__file__).resolve().parents[2] / "tools/project"
with patch.object(sys, "path", [str(TOOLS), *sys.path]):
    SPEC = importlib.util.spec_from_file_location(
        "prepare_fork", TOOLS / "prepare_fork.py")
    prepare_fork = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(prepare_fork)


class FixtureReads:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def get(self, endpoint):
        status, data = self.responses[endpoint]
        self.requests.append({"method": "GET", "endpoint": endpoint,
                              "http_status": status})
        return status, data


class PrepareForkTests(unittest.TestCase):
    def setUp(self):
        # Reuse the disposable Git fixture without rerunning its tests.
        self.fixture = test_preflight.PreflightTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.repo = self.fixture.repo
        self.lock = self.fixture.lock
        self.target = "fixture/project"
        self.responses = {
            "/user": (200, {"login": "fixture", "type": "User"}),
            "/repos/fixture/project": (200, {
                "full_name": self.target, "fork": True,
                "parent": {"full_name": "CleverRaven/Cataclysm-DDA"},
                "owner": {"type": "User"}, "default_branch": "master",
                "permissions": {"admin": True}}),
            "/repos/fixture/project/git/ref/heads/fixture": (404, {}),
        }

    def prepare(self, target="fixture/project", online=True, branch=None):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("GIT_")}
        self.client = FixtureReads(self.responses)
        with patch.dict(os.environ, env, clear=True), \
                patch.object(prepare_fork.preflight.Probe, "environment"):
            return prepare_fork.prepare(self.repo, self.lock, target, branch,
                                        online, self.client)

    def blockers(self, report):
        return {item["id"] for item in report["blockers"]}

    def test_missing_target_blocks_remote_without_guessing_owner(self):
        report = self.prepare(target=None)
        self.assertEqual(report["preflight"]["local_status"], "PASS")
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("target", self.blockers(report))
        self.assertIsNone(report["target"])
        self.assertEqual(self.client.requests, [])

    def test_offline_never_reads_github(self):
        report = self.prepare(online=False)
        self.assertEqual(self.client.requests, [])
        self.assertIn("remote_unverified", self.blockers(report))

    def test_correct_existing_fork_requires_explicit_reuse_scope(self):
        report = self.prepare()
        self.assertEqual(report["target_state"], "EXISTS")
        self.assertEqual(report["branch_http_status"], 404)
        self.assertEqual(self.blockers(report), {"existing_fork_scope"})
        self.assertFalse(report["remote_writes_executed"])
        self.assertFalse(report["execution_available"])

    def test_target_404_is_separate_from_read_errors(self):
        endpoint = "/repos/fixture/project"
        self.responses[endpoint] = (404, {})
        report = self.prepare()
        self.assertEqual(report["target_state"], "NOT_FOUND_404")
        self.assertIn("native_fork_needed", self.blockers(report))
        for status in (403, 429, None):
            with self.subTest(status=status):
                self.responses[endpoint] = (status, None)
                report = self.prepare()
                self.assertEqual(report["target_state"], "READ_FAILED")
                self.assertIn("target_read", self.blockers(report))
                self.assertNotIn("native_fork_needed", self.blockers(report))

    def test_wrong_or_unauthenticated_account_blocks_target_reads(self):
        for status, data in (
            (401, {}), (200, {"login": "another", "type": "User"}),
            (200, {"login": "fixture", "type": "Organization"}),
        ):
            with self.subTest(status=status, data=data):
                self.responses["/user"] = status, data
                report = self.prepare()
                self.assertIn("account", self.blockers(report))
                self.assertEqual(len(self.client.requests), 1)

    def test_nonfork_or_wrong_parent_never_reused(self):
        endpoint = "/repos/fixture/project"
        original = copy.deepcopy(self.responses[endpoint][1])
        for change in ({"fork": False},
                       {"parent": {"full_name":
                        "CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb"}}):
            with self.subTest(change=change):
                self.responses[endpoint] = 200, {**original, **change}
                report = self.prepare()
                self.assertIn("target_identity", self.blockers(report))
                self.assertNotIn("branch_http_status", report)

    def test_branch_conflict_does_not_plan_reset(self):
        endpoint = "/repos/fixture/project/git/ref/heads/fixture"
        self.responses[endpoint] = 200, {"ref": "refs/heads/fixture"}
        report = self.prepare()
        self.assertIn("branch_collision", self.blockers(report))
        self.assertEqual(self.fixture.git("symbolic-ref", "--short", "HEAD"),
                         "fixture")

    def test_branch_read_errors_are_not_absence(self):
        endpoint = "/repos/fixture/project/git/ref/heads/fixture"
        for status in (403, 429, None):
            with self.subTest(status=status):
                self.responses[endpoint] = status, None
                self.assertIn("branch_read", self.blockers(self.prepare()))

    def test_management_permissions_must_be_reported(self):
        self.responses["/repos/fixture/project"][1]["permissions"] = {}
        self.assertIn("administration", self.blockers(self.prepare()))

    def test_source_cache_personal_fork_cannot_be_target(self):
        cache = Path(self.fixture.temp.name) / "cache"
        self.fixture.git("clone", "-q", str(self.repo), str(cache))
        subprocess.run(["git", "-C", str(cache), "remote", "set-url",
                        "origin", "https://github.com/fixture/project.git"],
                       env=self.fixture.env, check=True)
        self.fixture.git("remote", "add", "source-cache", str(cache))
        self.fixture.git("remote", "set-url", "--push", "source-cache",
                         "DISABLED")
        self.assertIn("source_cache_identity",
                      self.blockers(self.prepare(online=False)))
        subprocess.run(["git", "-C", str(cache), "remote", "set-url",
                        "--push", "origin",
                        "https://github.com/fixture/project.git"],
                       env=self.fixture.env, check=True)
        subprocess.run(["git", "-C", str(cache), "remote", "set-url",
                        "origin", "https://github.com/" +
                        self.lock["ccb"]["repository"] + ".git"],
                       env=self.fixture.env, check=True)
        self.assertIn("source_cache_identity",
                      self.blockers(self.prepare(online=False)))

    def test_dirty_local_files_are_not_bypassed(self):
        (self.repo / "user-file").write_text("preserve me\n")
        report = self.prepare(online=False)
        self.assertIn("local_preflight", self.blockers(report))
        self.assertEqual((self.repo / "user-file").read_text(),
                         "preserve me\n")

    def test_invalid_branch_fails_without_changing_refs(self):
        report = self.prepare(branch="../unsafe", online=False)
        self.assertIn("branch", self.blockers(report))
        self.assertEqual(self.fixture.git("branch", "--format=%(refname)"),
                         "refs/heads/fixture")

    def test_read_client_hardcodes_get_and_never_logs_body(self):
        body = b'HTTP/2.0 403 Forbidden\nHeader: fixture\n\n{"token":"secret"}'
        result = subprocess.CompletedProcess([], 1, body, b"secret stderr")
        with patch.object(prepare_fork.subprocess, "run",
                          return_value=result) as run:
            client = prepare_fork.GitHubReads()
            self.assertEqual(client.get("/user")[0], 403)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--method") + 1], "GET")
        self.assertNotIn("secret", json.dumps(client.requests))

    def test_network_failure_does_not_look_like_404(self):
        with patch.object(prepare_fork.subprocess, "run",
                          side_effect=subprocess.TimeoutExpired("gh", 45)):
            client = prepare_fork.GitHubReads()
            self.assertEqual(client.get("/user"), (None, None))
        self.assertIsNone(client.requests[0]["http_status"])

    def test_upstreams_and_execute_flag_are_rejected(self):
        for extra in (["--target", "CleverRaven/Cataclysm-DDA"],
                      ["--target",
                       "CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb"],
                      ["--execute"]):
            with self.subTest(extra=extra), \
                    contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as result:
                prepare_fork.main(["--repo", str(self.repo), *extra])
            self.assertEqual(result.exception.code, 2)

    def test_checklist_has_no_executable_push_command(self):
        report = self.prepare(target=None)
        text = json.dumps(report["checklist"])
        self.assertNotIn("git push", text)
        self.assertEqual(report["checklist"][0]["review_request"]["endpoint"],
                         "/repos/CleverRaven/Cataclysm-DDA/forks")
        self.assertEqual(report["deployment_status"],
                         "IMPLEMENTED_NOT_DEPLOYED")


if __name__ == "__main__":
    unittest.main()
