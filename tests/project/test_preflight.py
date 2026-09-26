"""E0 tests using temporary Git history, never game/platform acceptance."""

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "preflight", ROOT / "tools/project/preflight.py"
)
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(
            prefix="cph-preflight-fixture-"
        )
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.env = {
            k: v for k, v in os.environ.items() if not k.startswith("GIT_")
        }
        self.env.update(
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_AUTHOR_NAME="CPH preflight test fixture",
            GIT_AUTHOR_EMAIL="fixture@example.invalid",
            GIT_COMMITTER_NAME="CPH preflight test fixture",
            GIT_COMMITTER_EMAIL="fixture@example.invalid",
        )
        self.git("init", "-q", "--initial-branch=fixture")
        (self.repo / "tracked.txt").write_text("base\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        self.git("commit", "-qm", "synthetic preflight fixture B")
        base = self.git("rev-parse", "HEAD")
        (self.repo / "tracked.txt").write_text("baseline\n", encoding="utf-8")
        self.git("commit", "-qam", "synthetic preflight fixture U")
        baseline = self.git("rev-parse", "HEAD")
        self.lock = {"schema_version": 1}
        for name, sha in (("cdda", base), ("ccb", baseline)):
            repository, remote = preflight.SOURCES[name]
            self.lock[name] = {
                "repository": repository,
                "remote": remote,
                "commit": sha,
                "tree": self.git("rev-parse", sha + "^{tree}"),
            }
            self.git(
                "remote",
                "add",
                remote,
                "https://github.com/" + repository + ".git",
            )
            self.git("remote", "set-url", "--push", remote, "DISABLED")
        self.lock["ccb"]["ref"] = "refs/heads/master"

    def git(self, *args):
        result = subprocess.run(
            ["git", "-C", str(self.repo), *args],
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def probe(self, repo=None, lock=None, env=None, target=None, online=False):
        clean_env = {
            k: v for k, v in os.environ.items() if not k.startswith("GIT_")
        }
        clean_env.update(env or {})
        with (
            patch.dict(os.environ, clean_env, clear=True),
            patch.object(preflight.Probe, "environment"),
        ):
            return preflight.Probe(repo or self.repo).run(
                lock or self.lock, target, online
            )

    def check_status(self, report, name, expected):
        check = next(c for c in report["checks"] if c["id"] == name)
        self.assertEqual(check["status"], expected, report)

    def test_clean_history_passes_without_target(self):
        report = self.probe()
        self.assertEqual(report["local_status"], "PASS")
        self.check_status(report, "target_fork", "BLOCKED")
        self.assertEqual(report["remote_operations"], "BLOCKED")

    def test_missing_required_argument_exits_two(self):
        with (
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as result,
        ):
            preflight.main([])
        self.assertEqual(result.exception.code, 2)

    def test_wrong_object_fails(self):
        lock = copy.deepcopy(self.lock)
        lock["ccb"]["commit"] = "f" * 40
        self.check_status(self.probe(lock=lock), "ccb_commit", "FAIL")

    def test_wrong_tree_fails(self):
        lock = copy.deepcopy(self.lock)
        lock["ccb"]["tree"] = "f" * 40
        self.check_status(self.probe(lock=lock), "ccb_tree", "FAIL")

    def test_nonancestor_objects_fail(self):
        lock = copy.deepcopy(self.lock)
        for key in ("commit", "tree"):
            lock["cdda"][key], lock["ccb"][key] = (
                lock["ccb"][key],
                lock["cdda"][key],
            )
        self.check_status(
            self.probe(lock=lock), "cdda_is_ccb_ancestor", "FAIL"
        )

    def test_shallow_history_fails(self):
        shallow = Path(self.temp.name) / "shallow"
        self.git("clone", "-q", "--depth=1", self.repo.as_uri(), str(shallow))
        self.check_status(self.probe(repo=shallow), "full_history", "FAIL")

    def test_subdirectory_is_not_accepted_as_root(self):
        nested = self.repo / "nested"
        nested.mkdir()
        self.check_status(self.probe(repo=nested), "repository_root", "FAIL")

    def test_nonrepository_fails(self):
        self.check_status(
            self.probe(repo=Path(self.temp.name)), "repository_root", "FAIL"
        )

    def test_wrong_head_fails_even_with_objects_present(self):
        self.git("checkout", "--detach", self.lock["cdda"]["commit"])
        self.check_status(self.probe(), "head_contains_baseline", "FAIL")

    def test_wrong_remote_fails(self):
        self.git(
            "remote",
            "set-url",
            "ccb",
            "https://github.com/unrelated/project.git",
        )
        self.check_status(self.probe(), "fixed_read_only_remotes", "FAIL")

    def test_writable_upstream_remote_fails(self):
        self.git("config", "--unset", "remote.ccb.pushurl")
        self.check_status(self.probe(), "fixed_read_only_remotes", "FAIL")

    def test_unexpected_origin_without_target_fails(self):
        self.git(
            "remote", "add", "origin", "https://github.com/example/project.git"
        )
        self.git("remote", "set-url", "--push", "origin", "DISABLED")
        self.check_status(self.probe(), "fixed_read_only_remotes", "FAIL")

    def test_optional_local_source_cache_does_not_replace_provenance(self):
        self.git(
            "remote",
            "add",
            "source-cache",
            str(Path(self.temp.name) / "local-cache"),
        )
        self.git("remote", "set-url", "--push", "source-cache", "DISABLED")
        self.check_status(self.probe(), "fixed_read_only_remotes", "PASS")

    def test_dirty_tracked_file_fails(self):
        (self.repo / "tracked.txt").write_text(
            "user modification\n", encoding="utf-8"
        )
        self.check_status(self.probe(), "clean_worktree", "FAIL")

    def test_hidden_source_edits_fail_without_changing_user_work(self):
        tracked = self.repo / "tracked.txt"
        original = tracked.read_bytes()
        index = self.repo / ".git/index"
        for flag in ("assume-unchanged", "skip-worktree"):
            with self.subTest(flag=flag):
                self.git("update-index", "--" + flag, "tracked.txt")
                try:
                    tracked.write_bytes(b"hidden user modification\n")
                    self.assertEqual(self.git("status", "--porcelain"), "")
                    flags = self.git("ls-files", "-v", "tracked.txt")
                    before = index.read_bytes(), index.stat().st_mtime_ns
                    report = self.probe()
                    self.assertEqual(
                        before, (index.read_bytes(), index.stat().st_mtime_ns)
                    )
                    self.assertEqual(
                        flags, self.git("ls-files", "-v", "tracked.txt")
                    )
                    self.assertEqual(
                        tracked.read_bytes(), b"hidden user modification\n"
                    )
                    self.check_status(report, "clean_worktree", "FAIL")
                    self.assertEqual(report["local_status"], "FAIL")
                finally:
                    self.git("update-index", "--no-" + flag, "tracked.txt")
                    tracked.write_bytes(original)

    def test_index_flag_read_failure_rejects_clean_worktree(self):
        original_git = preflight.Probe.git

        def failed_index_read(probe, *args):
            if args[0] == "ls-files":
                return 1, ""
            return original_git(probe, *args)

        with patch.object(preflight.Probe, "git", failed_index_read):
            report = self.probe()
        self.check_status(report, "clean_worktree", "FAIL")
        self.assertEqual(report["local_status"], "FAIL")

    def test_dirty_untracked_file_fails(self):
        (self.repo / "user-file.txt").write_text(
            "preserve me\n", encoding="utf-8"
        )
        self.check_status(self.probe(), "clean_worktree", "FAIL")

    def test_staged_file_fails(self):
        (self.repo / "tracked.txt").write_text(
            "user staging\n", encoding="utf-8"
        )
        self.git("add", "tracked.txt")
        self.check_status(self.probe(), "clean_worktree", "FAIL")

    def test_prohibited_cache_is_excluded(self):
        # This directory exists only in the disposable test fixture.
        cache = self.repo / "obj-lua"
        cache.mkdir()
        (cache / "untracked.txt").write_text(
            "fixture cache\n", encoding="utf-8"
        )
        self.check_status(self.probe(), "clean_worktree", "PASS")

    def test_replace_ref_fails(self):
        self.git(
            "replace", self.lock["ccb"]["commit"], self.lock["cdda"]["commit"]
        )
        self.check_status(self.probe(), "no_replace_refs", "FAIL")

    def test_graft_file_fails(self):
        graft = self.repo / ".git/info/grafts"
        graft.write_text(self.lock["ccb"]["commit"] + "\n", encoding="utf-8")
        self.check_status(self.probe(), "no_grafts", "FAIL")

    def test_environment_redirection_fails_without_logging_value(self):
        for key in (
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_OBJECT_DIRECTORY",
            "GIT_CONFIG_COUNT",
            "GIT_REPLACE_REF_BASE",
        ):
            with self.subTest(key=key):
                report = self.probe(env={key: "sensitive-environment-value"})
                self.check_status(report, "git_environment", "FAIL")
                self.assertNotIn(
                    "sensitive-environment-value", json.dumps(report)
                )
                self.assertFalse(report["commands"])

    def test_harmless_pager_environment_is_overridden(self):
        self.assertEqual(
            self.probe(env={"GIT_PAGER": "false"})["local_status"], "PASS"
        )
        with patch.dict(os.environ, {"GIT_PAGER": "false"}):
            self.assertEqual(
                preflight.Probe(self.repo).env["GIT_PAGER"], "cat"
            )

    def test_url_credentials_are_not_logged(self):
        self.git(
            "remote",
            "set-url",
            "ccb",
            "https://private-user:private-token@github.com/"
            "CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb.git"
            "?token=private-query",
        )
        report = self.probe()
        self.check_status(report, "fixed_read_only_remotes", "FAIL")
        rendered = json.dumps(report)
        for secret in ("private-user", "private-token", "private-query"):
            self.assertNotIn(secret, rendered)

    def test_git_read_controls_and_index_unchanged(self):
        probe = preflight.Probe(self.repo)
        self.assertEqual(probe.env["GIT_OPTIONAL_LOCKS"], "0")
        self.assertEqual(probe.env["GIT_NO_LAZY_FETCH"], "1")
        index = self.repo / ".git/index"
        before = index.read_bytes(), index.stat().st_mtime_ns
        self.probe()
        self.assertEqual(
            before, (index.read_bytes(), index.stat().st_mtime_ns)
        )

    def test_offline_probe_does_not_call_network(self):
        with patch.object(
            preflight.urllib.request,
            "urlopen",
            side_effect=AssertionError("unexpected network"),
        ):
            self.assertEqual(self.probe()["local_status"], "PASS")

    def test_fork_metadata_requires_cdda_parent_and_personal_owner(self):
        # Simulated API metadata tests policy only, not live GitHub behavior.
        for parent, owner_type, expected in (
            (preflight.SOURCES["cdda"][0], "User", "PASS"),
            (preflight.SOURCES["ccb"][0], "User", "FAIL"),
            (preflight.SOURCES["cdda"][0], "Organization", "FAIL"),
        ):
            with self.subTest(parent=parent, owner_type=owner_type):
                metadata = {
                    "full_name": "fixture/project", "fork": True,
                    "parent": {"full_name": parent},
                    "owner": {"type": owner_type},
                }
                with patch.object(preflight.Probe, "api",
                                  return_value=metadata):
                    report = self.probe(target="fixture/project", online=True)
                self.check_status(report, "target_fork", expected)
                self.assertEqual(report["remote_operations"], "BLOCKED")

    def test_lock_rejects_changed_source_identity(self):
        lock = copy.deepcopy(self.lock)
        lock["ccb"]["repository"] = "unrelated/project"
        path = Path(self.temp.name) / "lock.json"
        path.write_text(json.dumps(lock), encoding="utf-8")
        with self.assertRaises(ValueError):
            preflight.read_lock(path)

    def test_upstream_cannot_be_target(self):
        with (
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as result,
        ):
            preflight.main(
                [
                    "--repo",
                    str(self.repo),
                    "--target",
                    preflight.SOURCES["ccb"][0],
                ]
            )
        self.assertEqual(result.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
