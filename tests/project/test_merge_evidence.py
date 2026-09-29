"""Synthetic local model tests, never game/platform/GitHub acceptance."""

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/project"))
SPEC = importlib.util.spec_from_file_location(
    "merge_evidence", ROOT / "tools/project/check_merge_evidence.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class MergeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cph-e4-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "candidate"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "CPH synthetic fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.repo / "game.txt").write_text("base\n")
        self.git("add", "game.txt")
        self.git("commit", "-m", "synthetic base")
        self.base = self.git("rev-parse", "HEAD")
        self.git("checkout", "-b", "topic")
        (self.repo / "game.txt").write_text("candidate\n")
        self.git("commit", "-am", "synthetic candidate")
        self.head = self.git("rev-parse", "HEAD")
        self.tree = self.git("rev-parse", "HEAD^{tree}")
        self.merge = self.git("commit-tree", self.tree, "-p", self.base,
                              "-p", self.head, "-m", "synthetic tested merge")
        self.trust = self.root / "trusted"
        self.trust.mkdir()
        for name in ("check-policy.json", "protected-surfaces.json"):
            shutil.copyfile(ROOT / "project" / name, self.trust / name)
        self.policy_path = self.trust / "check-policy.json"
        self.policy = json.loads(self.policy_path.read_text())
        self.policy_sha = digest(self.policy_path)
        self.evidence = self.root / "artifacts"
        self.evidence.mkdir()
        self.context_path = self.trust / "context.json"
        self.context = {
            "schema_version": 1, "repository_id": 123, "pull_request": 7,
            "base_ref": "refs/heads/main", "head_ref": "refs/heads/topic",
            "base_sha": self.base, "head_sha": self.head,
            "tested_commit": self.merge, "tested_tree": self.tree,
            "policy_sha": self.policy_sha, "inputs_digest": "a" * 64,
            "scope_authorized": True, "source_verified": True,
            "conflicts_resolved": True, "merge_paused": False, "runs": {},
            "informational": {
                "macos": {"status": "FAIL"}, "android": {"status": "FAIL"},
            },
        }
        self.receipts = {}
        for name in ("windows", "linux"):
            layout = {key: "C:\\fixture\\" + key if name == "windows" else
                      "/fixture/" + key for key in
                      ("source", "build", "evidence")}
            run = {"workflow_path": ".github/workflows/fixture.yml",
                   "workflow_id": 1, "event": "pull_request", "run_id": 2,
                   "run_attempt": 1, "layout": layout, "parallel": 2}
            self.context["runs"][name] = run
            target = self.policy["targets"][name]
            receipt = {key: self.context[key] for key in gate.BINDINGS}
            receipt.update({key: run[key] for key in gate.RUN_BINDINGS})
            receipt.update(schema_version=1, target=target, checks=[],
                           execution_environment={"os": name,
                                                  "arch": "x86_64",
                                                  "native": True},
                           binaries={})
            for check_id, argv in gate.commands(target, run).items():
                check = {"id": check_id, "status": "PASS",
                         "actually_executed": True, "exit_code": 0,
                         "argv": argv, "cwd": layout["source"],
                         "log": self.file(name + "/" + check_id + ".log",
                                          b"SYNTHETIC: no game executed\n")}
                if check_id in target["tests"]:
                    check["junit"] = self.file(
                        name + "/" + check_id + ".xml",
                        b'<testsuites tests="2"><testsuite tests="2">'
                        b'<testcase name="synthetic"/></testsuite>'
                        b'</testsuites>')
                receipt["checks"].append(check)
            for index, binary in enumerate(target["binaries"]):
                receipt["binaries"][binary] = self.file(
                    name + "/binary-" + str(index),
                    b"SYNTHETIC NOT EXECUTABLE")
            self.receipts[name] = receipt
        self.save()

    def git(self, *args):
        process = subprocess.run(
            ["git", "-C", str(self.repo), *args], check=True,
            capture_output=True, text=True)
        return process.stdout.strip()

    def file(self, name, data):
        path = self.evidence / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {"path": name, "sha256": digest(path)}

    def save(self):
        for name, receipt in self.receipts.items():
            path = self.evidence / name / "receipt.json"
            write_json(path, receipt)
            self.context["runs"][name]["receipt"] = {
                "path": name + "/receipt.json", "sha256": digest(path)}
        write_json(self.context_path, self.context)
        self.context_sha = digest(self.context_path)

    def evaluate(self):
        return gate.evaluate(self.repo, self.evidence, self.policy_path,
                             self.policy_sha, self.context_path,
                             self.context_sha)

    def assert_rejected(self):
        result = self.evaluate()
        self.assertEqual(result["status"], "FAIL", result)
        self.assertFalse(result["evidence_accepted"])
        self.assertFalse(result["merge_ready"])
        return result

    def test_t01_each_required_platform_failure_rejected(self):
        for name in ("windows", "linux"):
            with self.subTest(platform=name):
                check = self.receipts[name]["checks"][0]
                check["exit_code"] = 1
                self.save()
                self.assert_rejected()
                check["exit_code"] = 0

    def test_t02_other_platform_failure_does_not_block_local_evidence(self):
        result = self.evaluate()
        self.assertEqual(result["status"], "PASS", result)
        self.assertTrue(result["evidence_accepted"])
        for name in ("macos", "android"):
            self.assertEqual(result["platforms"][name]["reported"]["status"],
                             "FAIL")
        self.assertFalse(result["merge_ready"])
        self.assertFalse(result["github_gate_verified"])
        self.assertFalse(result["public_release_ready"])

    def test_t03_non_success_statuses_rejected(self):
        for status in ("skipped", "neutral", "timeout", "cancelled", "FAIL"):
            with self.subTest(status=status):
                self.receipts["linux"]["checks"][0]["status"] = status
                self.save()
                self.assert_rejected()

    def test_t03_missing_and_empty_required_checks_rejected(self):
        for count in (1, 0):
            self.receipts["linux"]["checks"] = \
                self.receipts["linux"]["checks"][:count]
            self.save()
            self.assert_rejected()

    def test_t03_zero_assertions_even_with_case_rejected(self):
        check = self.receipts["linux"]["checks"][2]
        check["junit"] = self.file(
            "linux/zero.xml", b'<testsuite tests="0"><testcase/></testsuite>')
        self.save()
        self.assert_rejected()

    def test_t03_failure_node_even_with_zero_exit_rejected(self):
        check = self.receipts["linux"]["checks"][2]
        check["junit"] = self.file(
            "linux/fail.xml", b'<testsuite tests="2"><testcase><failure/>'
            b'</testcase></testsuite>')
        self.save()
        self.assert_rejected()

    def test_t04_dispatch_same_name_green_rejected(self):
        for name in ("windows", "linux"):
            self.context["runs"][name]["event"] = "workflow_dispatch"
            self.receipts[name]["event"] = "workflow_dispatch"
        self.save()
        self.assert_rejected()

    def test_t05_base_or_head_movement_rejected(self):
        for ref in ("refs/heads/main", "refs/heads/topic"):
            with self.subTest(ref=ref):
                original = self.git("rev-parse", ref)
                self.git("update-ref", ref, self.merge)
                self.assert_rejected()
                self.git("update-ref", ref, original)

    def test_t05_fixed_sha_cannot_substitute_for_current_ref(self):
        for key in ("base", "head"):
            with self.subTest(key=key):
                ref_key = key + "_ref"
                original = self.context[ref_key]
                self.context[ref_key] = self.context[key + "_sha"]
                self.save()
                self.assert_rejected()
                self.context[ref_key] = original

    def test_t05_ref_movement_during_verification_rejected(self):
        original = gate.platform_result

        def moving(*args):
            result = original(*args)
            self.git("update-ref", "refs/heads/main", self.merge)
            return result

        with patch.object(gate, "platform_result", side_effect=moving):
            self.assert_rejected()

    def test_t06_protected_change_cannot_self_approve(self):
        directory = self.repo / "tools/project"
        directory.mkdir(parents=True)
        (directory / "check_merge_evidence.py").write_text("approve=True\n")
        self.git("add", "tools/project/check_merge_evidence.py")
        self.git("commit", "-m", "synthetic protection attack")
        self.context["head_sha"] = self.git("rev-parse", "HEAD")
        self.context["tested_tree"] = self.git("rev-parse", "HEAD^{tree}")
        self.context["tested_commit"] = self.git(
            "commit-tree", self.context["tested_tree"], "-p", self.base,
            "-p", self.context["head_sha"], "-m", "new synthetic merge")
        self.context["protected_changes_approved"] = True
        for receipt in self.receipts.values():
            for key in gate.BINDINGS:
                receipt[key] = self.context[key]
        self.save()
        result = self.assert_rejected()
        self.assertEqual(result["protected_changes"],
                         ["tools/project/check_merge_evidence.py"])

    def test_t06_candidate_policy_path_rejected(self):
        self.policy_path = self.repo / "own-policy.json"
        write_json(self.policy_path, self.policy)
        self.policy_sha = digest(self.policy_path)
        self.assert_rejected()

    def test_trust_digest_cannot_be_changed_by_candidate(self):
        self.policy["required_platforms"] = []
        write_json(self.policy_path, self.policy)
        self.assert_rejected()

    def test_context_in_artifact_directory_rejected(self):
        self.context_path = self.evidence / "own-context.json"
        self.save()
        self.assert_rejected()

    def test_policy_surface_digest_mismatch_rejected(self):
        (self.trust / "protected-surfaces.json").write_text("{}")
        self.assert_rejected()

    def test_stale_or_foreign_receipt_binding_rejected(self):
        receipt = self.receipts["linux"]
        for key, value in (("repository_id", 999), ("pull_request", 9),
                           ("base_sha", "b" * 40),
                           ("head_sha", "c" * 40),
                           ("tested_tree", "d" * 40),
                           ("policy_sha", "e" * 64),
                           ("inputs_digest", "f" * 64),
                           ("workflow_id", 999), ("run_id", 999),
                           ("run_attempt", 2),
                           ("workflow_path", ".github/workflows/other.yml")):
            with self.subTest(binding=key):
                original = receipt[key]
                receipt[key] = value
                self.save()
                self.assert_rejected()
                receipt[key] = original

    def test_duplicate_check_and_wrong_command_rejected(self):
        checks = self.receipts["linux"]["checks"]
        original = copy.deepcopy(checks)
        checks[-1] = copy.deepcopy(checks[0])
        self.save()
        self.assert_rejected()
        self.receipts["linux"]["checks"] = original
        original[2]["argv"][1] = "[empty-filter]"
        self.save()
        self.assert_rejected()

    def test_claimed_execution_and_bool_exit_rejected(self):
        check = self.receipts["linux"]["checks"][0]
        check["actually_executed"] = False
        self.save()
        self.assert_rejected()
        check["actually_executed"] = True
        check["exit_code"] = False
        self.save()
        self.assert_rejected()

    def test_empty_or_changed_log_and_binary_rejected(self):
        log = self.evidence / "linux/build.log"
        log.write_bytes(b"")
        self.assert_rejected()
        log.write_bytes(b"CHANGED")
        self.assert_rejected()

    def test_no_missing_binary_allowed(self):
        (self.evidence / "linux/binary-0").unlink()
        self.assert_rejected()

    def test_empty_log_with_matching_digest_rejected(self):
        check = self.receipts["linux"]["checks"][0]
        check["log"] = self.file("linux/empty.log", b"")
        self.save()
        self.assert_rejected()

    def test_report_malformed_zero_case_or_bad_total_rejected(self):
        for data in (
            b"not XML", b'<testsuite tests="2"/>',
            b'<testsuites tests="3"><testsuite tests="2"><testcase/>'
            b'</testsuite></testsuites>',
            b'<testsuites tests="2"><testcase/><testsuite tests="2">'
            b'<testcase/></testsuite></testsuites>',
        ):
            with self.subTest(data=data):
                check = self.receipts["linux"]["checks"][2]
                check["junit"] = self.file("linux/bad.xml", data)
                self.save()
                self.assert_rejected()

    def test_malformed_record_emits_failure_report(self):
        self.receipts["linux"]["execution_environment"] = []
        self.save()
        self.assert_rejected()

    def test_wrong_configuration_rejected(self):
        self.receipts["linux"]["target"] = copy.deepcopy(
            self.policy["targets"]["linux"])
        self.receipts["linux"]["target"]["options"]["LOCALIZE"] = False
        self.save()
        self.assert_rejected()

    def test_missing_platform_is_rejected_and_other_result_collected(self):
        del self.context["runs"]["windows"]
        write_json(self.context_path, self.context)
        self.context_sha = digest(self.context_path)
        result = self.assert_rejected()
        self.assertEqual(result["platforms"]["linux"]["status"], "PASS")

    def test_empty_required_test_set_rejected(self):
        target = copy.deepcopy(self.policy["targets"]["linux"])
        target["tests"] = {}
        with self.assertRaisesRegex(ValueError, "empty required regression"):
            gate.commands(target, self.context["runs"]["linux"])

    def test_artifact_traversal_and_symlink_rejected(self):
        receipt = self.receipts["linux"]
        log = receipt["checks"][0]["log"]
        original = log["path"]
        for path in ("../outside", "/tmp/outside", "linux\\build.log"):
            log["path"] = path
            self.save()
            self.assert_rejected()
        log["path"] = original
        path = self.evidence / original
        target = self.root / "outside"
        path.rename(target)
        path.symlink_to(target)
        self.save()
        self.assert_rejected()

    def test_tested_parent_or_tree_mismatch_rejected(self):
        self.context["tested_commit"] = self.head
        self.save()
        self.assert_rejected()
        self.context["tested_commit"] = self.merge
        self.context["tested_tree"] = "a" * 40
        self.save()
        self.assert_rejected()

    def test_final_merge_may_differ_sha_with_same_parents_tree(self):
        self.context["final_merge_commit"] = self.git(
            "commit-tree", self.tree, "-p", self.base, "-p", self.head,
            "-m", "final synthetic merge with different message")
        self.assertNotEqual(self.context["final_merge_commit"], self.merge)
        self.save()
        self.assertTrue(self.evaluate()["evidence_accepted"])

    def test_final_merge_wrong_parents_rejected(self):
        self.context["final_merge_commit"] = self.head
        self.save()
        self.assert_rejected()

    def test_rules_claim_cannot_make_deployment_ready(self):
        self.context["github_rules_verified"] = True
        self.context["merge_ready"] = True
        self.save()
        result = self.evaluate()
        self.assertTrue(result["evidence_accepted"])
        self.assertFalse(result["merge_ready"])
        self.assertFalse(result["github_gate_verified"])

    def test_unresolved_authorization_and_pause_rejected(self):
        for key in ("scope_authorized", "source_verified",
                    "conflicts_resolved", "merge_paused"):
            old = self.context[key]
            self.context[key] = not old
            self.save()
            self.assert_rejected()
            self.context[key] = old

    def test_cross_compile_is_not_native_execution(self):
        self.receipts["windows"]["execution_environment"]["native"] = False
        self.save()
        self.assert_rejected()

    def test_duplicate_json_keys_rejected(self):
        data = self.context_path.read_bytes().replace(
            b'"schema_version": 1,',
            b'"schema_version": 1, "schema_version": 1,')
        self.context_path.write_bytes(data)
        self.context_sha = digest(self.context_path)
        self.assert_rejected()

    def test_git_override_replace_and_graft_rejected(self):
        with patch.dict(os.environ, {"GIT_DIR": str(self.repo / ".git")}):
            self.assert_rejected()
        self.git("replace", self.head, self.base)
        self.assert_rejected()
        self.git("replace", "-d", self.head)
        (self.repo / ".git/info/grafts").write_text("")
        self.assert_rejected()

    def test_fixed_git_isolation_still_uses_the_declared_repository(self):
        for isolation in (
            {"GIT_CONFIG_GLOBAL": os.devnull},
            {"GIT_CONFIG_NOSYSTEM": "1"},
            {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"},
        ):
            with self.subTest(isolation=isolation), patch.dict(
                os.environ, isolation
            ):
                self.assertEqual(gate.git(self.repo, "rev-parse", "HEAD"),
                                 self.head)

    def test_unsafe_git_configuration_is_rejected_before_subprocess(self):
        for name, value in (
            ("GIT_CONFIG_GLOBAL", "private-fixture-config"),
            ("GIT_CONFIG_GLOBAL", ""),
            ("GIT_CONFIG_NOSYSTEM", "0"),
            ("GIT_CONFIG_NOSYSTEM", ""),
            ("GIT_CONFIG_COUNT", "0"),
        ):
            with self.subTest(name=name, value=value), patch.dict(
                os.environ, {"GIT_CONFIG_GLOBAL": os.devnull,
                             "GIT_CONFIG_NOSYSTEM": "1", name: value}
            ), patch.object(gate.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "environment") as ctx:
                    gate.git(self.repo, "rev-parse", "HEAD")
                run.assert_not_called()
                self.assertNotIn("private-fixture-config", str(ctx.exception))

    def test_scan_without_context_is_blocked_not_merge_permission(self):
        result = gate.evaluate(
            self.repo, self.evidence, self.policy_path, self.policy_sha,
            base="refs/heads/main", head="refs/heads/topic")
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertEqual(result["changed_paths"], ["game.txt"])
        self.assertFalse(result["evidence_accepted"])
        self.assertFalse(result["merge_ready"])

    def test_protection_includes_parent_symlink_and_deleted_paths(self):
        surfaces = json.loads((self.trust /
                               "protected-surfaces.json").read_text())
        paths = ["tools", ".github/workflows/old.yml",
                 "project/check-policy.json", "src/item.cpp"]
        self.assertEqual(gate.protected_changes(paths, surfaces), paths[:3])

    def test_identity_install_and_nested_instructions_protected(self):
        surfaces = json.loads((self.trust /
                               "protected-surfaces.json").read_text())
        paths = [
            "src/CMakeLists.txt", "data/CMakeLists.txt",
            "CMakeModules/new-module.cmake", "build-data/cph-test/launcher",
            "src/main_menu.cpp", "src/translations.cpp",
            "src/AGENTS.md", "data/mods/example/AGENTS.override.md",
        ]
        self.assertEqual(gate.protected_changes(paths, surfaces), paths)

    def test_windows_contract_has_one_config_and_real_version_user_path(self):
        commands = gate.commands(self.policy["targets"]["windows"],
                                 self.context["runs"]["windows"])
        self.assertEqual(commands["build"].count("--config"), 1)
        self.assertEqual(commands["game-version"][-3:],
                         ["--userdir", "C:\\fixture\\evidence\\version-user",
                          "--version"])


if __name__ == "__main__":
    unittest.main()
