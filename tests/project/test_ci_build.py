"""Trusted PR and evidence controls; these are not native-build proof."""

import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[2] / "tools/project"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location(
    "ci_build", TOOLS / "ci_build.py"
)
ci = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ci)
BASE, HEAD, MERGE, TREE = [char * 40 for char in "abcd"]


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.pr = {
            "number": 7,
            "state": "open",
            "base": {
                "repo": {"full_name": ci.REPOSITORY},
                "ref": "main",
                "sha": BASE,
            },
            "head": {"sha": HEAD},
        }
        self.merge = {
            "sha": MERGE,
            "tree": {"sha": TREE},
            "parents": [{"sha": BASE}, {"sha": HEAD}],
        }

    def test_fixed_merge_matches_current_pr(self):
        ci.validate_pr(self.pr, self.merge, 7, BASE, HEAD)

    def test_closed_wrong_repository_or_stale_pr_rejected(self):
        for path, replacement in (
            (["state"], "closed"),
            (["number"], 8),
            (["base", "repo", "full_name"], "other/repo"),
            (["base", "ref"], "master"),
            (["base", "sha"], HEAD),
            (["head", "sha"], BASE),
        ):
            altered = copy.deepcopy(self.pr)
            target = altered
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = replacement
            with self.subTest(path=path), self.assertRaises(ValueError):
                ci.validate_pr(altered, self.merge, 7, BASE, HEAD)

    def test_wrong_or_extra_merge_parent_rejected(self):
        for parents in ([HEAD, BASE], [BASE], [BASE, HEAD, MERGE]):
            altered = copy.deepcopy(self.merge)
            altered["parents"] = [{"sha": item} for item in parents]
            with self.subTest(parents=parents), self.assertRaises(ValueError):
                ci.validate_pr(self.pr, altered, 7, BASE, HEAD)

    def test_invalid_object_id_rejected(self):
        for value in ("main", "deadbee", "-bad", "A" * 40, "a" * 39 + "\n"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ci.require_sha(value)


class ExecutionTests(unittest.TestCase):
    def test_candidate_environment_removes_credentials_and_runner_channels(
        self,
    ):
        with mock.patch.dict(
            os.environ,
            {
                "HOME": "/real/home",
                "PATH": "/toolchain",
                "INCLUDE": "headers",
                "GH_TOKEN": "secret",
                "CUSTOM_ACCESS_KEY": "secret",
                "GITHUB_ENV": "/runner/commands",
                "ACTIONS_RUNTIME_TOKEN": "secret",
                "GIT_CONFIG_COUNT": "9",
                "CPH_CI_PLAN": "unneeded",
            },
            clear=True,
        ):
            env = ci.clean_environment()
        self.assertEqual(env["HOME"], "/real/home")
        self.assertEqual(env["INCLUDE"], "headers")
        self.assertEqual(env["PATH"], "/toolchain")
        for key in (
            "GH_TOKEN",
            "CUSTOM_ACCESS_KEY",
            "GITHUB_ENV",
            "ACTIONS_RUNTIME_TOKEN",
            "GIT_CONFIG_COUNT",
            "CPH_CI_PLAN",
        ):
            self.assertNotIn(key, env)

    def test_failed_command_is_recorded_and_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = ci.Runner(root, ci.clean_environment())
            with self.assertRaises(RuntimeError):
                runner.run(
                    "negative",
                    [sys.executable, "-c", "raise SystemExit(17)"],
                    root,
                )
            report = json.loads((root / "commands.jsonl").read_text())
            self.assertEqual(report["exit_code"], 17)
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(
                report["log_sha256"], ci.digest(root / "negative.log")
            )

    def test_sentinel_edit_or_new_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root, expected = ci.create_sentinels(Path(directory))
            ci.verify_sentinels(root, expected)
            (root / "new").write_text("unexpected")
            with self.assertRaises(ValueError):
                ci.verify_sentinels(root, expected)
            (root / "new").unlink()
            (root / "config/options.json").write_text("changed")
            with self.assertRaises(ValueError):
                ci.verify_sentinels(root, expected)

    def test_identity_verifies_parents_tree_and_tracked_cleanliness(self):
        identity = {
            "merge_sha": MERGE,
            "merge_tree": TREE,
            "base_sha": BASE,
            "head_sha": HEAD,
        }
        with mock.patch.object(
            ci, "git", side_effect=[MERGE, TREE, BASE, HEAD, ""]
        ):
            ci.verify_checkout(Path("candidate"), {}, identity)
        for replies in (
            [MERGE, TREE, BASE, MERGE],
            [MERGE, TREE, BASE, HEAD, "diff"],
        ):
            with (
                mock.patch.object(ci, "git", side_effect=replies),
                self.assertRaises(ValueError),
            ):
                ci.verify_checkout(Path("candidate"), {}, identity)


if __name__ == "__main__":
    unittest.main()
