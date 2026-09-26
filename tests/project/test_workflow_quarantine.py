"""E0 fixture tests only; these do not validate GitHub enforcement or games."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = (
    Path(__file__).resolve().parents[2] /
    "tools/project/check_workflow_quarantine.py"
)
SPEC = importlib.util.spec_from_file_location("workflow_quarantine", SCRIPT)
QUARANTINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QUARANTINE)


class WorkflowQuarantineTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="cph-workflow-fixture-"
        )
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.run_git("init", "--quiet")
        active = self.repo / ".github/workflows"
        active.mkdir(parents=True)
        (active / "release.yml").write_bytes(
            b"name: Fixture only\non: workflow_dispatch\n"
            b"permissions:\n  contents: write\n"
        )
        (active / "test.yaml").write_bytes(b"name: Fixture check\non: push\n")
        self.run_git("add", ".github")
        self.run_git(
            "-c", "user.name=Fixture", "-c", "user.email=fixture@invalid",
            "commit", "--quiet", "--no-gpg-sign", "-m",
            "Synthetic test fixture",
        )
        self.baseline = self.run_git("rev-parse", "HEAD").strip()
        self.archive = self.repo / "project/inherited-workflows"
        self.archive.mkdir(parents=True)
        for path in active.iterdir():
            path.rename(self.archive / path.name)
        self.manifest = QUARANTINE.source_manifest(self.repo, self.baseline)
        (self.archive / "manifest.json").write_text(json.dumps(self.manifest))

    def run_git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.repo), *args],
            stderr=subprocess.PIPE, text=True,
        )

    def report(self):
        return QUARANTINE.inspect(self.repo, self.baseline)

    def assert_rejected(self, fragment):
        result = self.report()
        self.assertEqual("FAIL", result["status"])
        self.assertTrue(
            any(fragment in item for item in result["findings"]), result
        )

    def test_preserves_source_bytes_without_an_active_entrypoint(self):
        result = self.report()
        self.assertEqual("PASS", result["status"])
        self.assertEqual(2, result["expected_workflows"])
        self.assertFalse(result["github_deployment_verified"])

    def test_changed_archive_and_forged_manifest_do_not_override_git(self):
        path = self.archive / "release.yml"
        path.write_bytes(path.read_bytes() + b"# modified\n")
        self.manifest["workflows"][0]["sha256"] = "0" * 64
        (self.archive / "manifest.json").write_text(json.dumps(self.manifest))
        self.assert_rejected("differs from source")
        self.assert_rejected("manifest differs")

    def test_missing_archive_is_rejected(self):
        (self.archive / "test.yaml").unlink()
        self.assert_rejected("missing quarantined")

    def test_unknown_archive_is_rejected(self):
        (self.archive / "extra.yml").write_text("on: push\n")
        self.assert_rejected("unrecorded quarantined")

    def test_every_active_workflow_is_rejected_even_if_named_project(self):
        active = self.repo / ".github/workflows/project-local.yml"
        active.write_text(
            "on: workflow_dispatch\npermissions:\n  contents: read\n"
        )
        self.assert_rejected("active workflow forbidden")

    def test_missing_manifest_is_rejected(self):
        (self.archive / "manifest.json").unlink()
        self.assert_rejected("manifest is missing")

    def test_workflow_symlink_is_rejected(self):
        path = self.archive / "test.yaml"
        content = path.read_bytes()
        path.unlink()
        original = self.repo / "same-bytes.yaml"
        original.write_bytes(content)
        path.symlink_to(original)
        self.assert_rejected("contains symlink")

    def test_active_directory_symlink_is_rejected(self):
        active = self.repo / ".github/workflows"
        active.rmdir()
        active.symlink_to(self.archive, target_is_directory=True)
        self.assert_rejected("active workflow path contains symlink")

    def test_invalid_baseline_and_wrong_repository_are_errors(self):
        for baseline in ("HEAD", "0" * 40):
            with self.subTest(baseline=baseline):
                with self.assertRaises(QUARANTINE.InspectionError):
                    QUARANTINE.inspect(self.repo, baseline)
        with self.assertRaises(QUARANTINE.InspectionError):
            QUARANTINE.inspect(self.archive, self.baseline)

    def test_empty_workflow_source_cannot_pass(self):
        self.run_git("rm", "-r", "--cached", ".github")
        self.run_git(
            "-c", "user.name=Fixture", "-c", "user.email=fixture@invalid",
            "commit", "--quiet", "--no-gpg-sign", "-m", "Empty fixture source",
        )
        empty = self.run_git("rev-parse", "HEAD").strip()
        with self.assertRaises(QUARANTINE.InspectionError):
            QUARANTINE.inspect(self.repo, empty)

    def test_git_environment_overrides_are_rejected_without_values(self):
        for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_CONFIG_COUNT",
                    "GIT_REPLACE_REF_BASE", "GIT_CONFIG_GLOBAL"):
            with self.subTest(key=key), mock.patch.dict(
                os.environ, {key: "secret-fixture-value"}
            ):
                with self.assertRaises(QUARANTINE.InspectionError) as caught:
                    self.report()
                self.assertIn(key, str(caught.exception))
                self.assertNotIn("secret-fixture-value", str(caught.exception))

    def test_replacement_refs_are_rejected(self):
        self.run_git(
            "update-ref", "refs/replace/" + self.baseline, self.baseline
        )
        with self.assertRaisesRegex(
            QUARANTINE.InspectionError, "replacement refs"
        ):
            self.report()

    def test_legacy_grafts_are_rejected(self):
        (self.repo / ".git/info/grafts").write_text(self.baseline + "\n")
        with self.assertRaisesRegex(QUARANTINE.InspectionError, "graft"):
            self.report()

    def test_user_global_configuration_cannot_redirect_repository(self):
        fake_home = self.repo / "fixture-home"
        fake_home.mkdir()
        (fake_home / ".gitconfig").write_text(
            "[core]\n  worktree = /nonexistent-redirect\n"
        )
        with mock.patch.dict(os.environ, {"HOME": str(fake_home)}):
            self.assertEqual("PASS", self.report()["status"])

    def test_missing_promisor_blob_does_not_invoke_transport(self):
        marker = self.repo / "transport-was-invoked"
        helper_dir = self.repo / "fixture-bin"
        helper_dir.mkdir()
        helper = helper_dir / "git-remote-cphfixture"
        helper.write_text(
            "#!/usr/bin/env python3\nfrom pathlib import Path\n" +
            f"Path({str(marker)!r}).touch()\nraise SystemExit(1)\n"
        )
        helper.chmod(0o755)
        self.run_git("config", "remote.origin.url", "cphfixture://missing")
        self.run_git("config", "protocol.cphfixture.allow", "always")
        self.run_git("config", "remote.origin.promisor", "true")
        self.run_git("config", "remote.origin.partialclonefilter", "blob:none")
        blob = self.manifest["workflows"][0]["blob_id"]
        (self.repo / ".git/objects" / blob[:2] / blob[2:]).unlink()
        original_run = subprocess.run
        fixture_path = (
            str(helper_dir) + os.pathsep + os.environ.get("PATH", os.defpath)
        )
        with mock.patch.dict(os.environ, {"PATH": fixture_path}):
            with mock.patch.object(
                QUARANTINE.subprocess, "run", wraps=original_run
            ) as run:
                with self.assertRaises(QUARANTINE.InspectionError):
                    self.report()
        self.assertFalse(
            marker.exists(), "read-only inspection invoked a Git transport"
        )
        for call in run.call_args_list:
            self.assertEqual("1", call.kwargs["env"]["GIT_NO_LAZY_FETCH"])
            self.assertEqual("0", call.kwargs["env"]["GIT_OPTIONAL_LOCKS"])
            self.assertIn("protocol.allow=never", call.args[0])
        control_env = dict(os.environ, PATH=fixture_path)
        control_env.pop("GIT_NO_LAZY_FETCH", None)
        control = subprocess.run(
            ["git", "-C", str(self.repo), "cat-file", "blob", blob],
            env=control_env, capture_output=True, timeout=30,
        )
        self.assertNotEqual(0, control.returncode)
        self.assertTrue(
            marker.exists(), "fixture transport detector was not exercised"
        )

    def test_cli_exit_codes(self):
        command = [sys.executable, str(SCRIPT), "--repo", str(self.repo),
                   "--baseline", self.baseline]
        passed = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(0, passed.returncode, passed.stderr)
        (self.archive / "test.yaml").unlink()
        self.assertEqual(
            1, subprocess.run(command, capture_output=True).returncode
        )
        self.assertEqual(
            2, subprocess.run(
                [sys.executable, str(SCRIPT)], capture_output=True
            ).returncode
        )


if __name__ == "__main__":
    unittest.main()
