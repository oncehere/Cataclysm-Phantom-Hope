"""Local control-model tests; fixture bytes are not game/platform proof."""

import copy
import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "release_contract", Path(__file__).resolve().parents[2] /
    "tools/project/release_contract.py")
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)


def candidate(character="a", code=43):
    source = character * 40
    inputs = "f" * 64
    return {"source_sha": source, "inputs_digest": inputs,
            **contract.identity(source, inputs), "android_version_code": code}


def observation(identity, release_id, draft=False):
    receipt = {"release_id": release_id, "identity": identity,
               "manifest_sha256": "e" * 64,
               "contract_verified": not draft}
    release = {"id": release_id, "draft": draft, "prerelease": True,
               "tag_name": identity["tag"],
               "published_at": None if draft else "2026-09-25T01:00:00Z",
               "tag_source_sha": identity["source_sha"],
               "manifest_sha256": receipt["manifest_sha256"]}
    return release, receipt


class ManifestModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cph-release-model-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.packages = self.root / "packages"
        self.evidence = self.root / "evidence"
        self.packages.mkdir()
        self.evidence.mkdir()
        inputs = {key: "c" * 64 for key in [
            "asset_lock_sha256", "target_config_sha256",
            "check_policy_sha256", "toolchain_config_sha256"]}
        inputs["policy_sha"] = "b" * 40
        manifest = {
            "schema_version": 1, "channel": "development",
            "source_sha": "a" * 40, "source_tree": "d" * 40,
            "ccb_integrated_sha": "e" * 40, "policy_sha": "b" * 40,
            "inputs_digest": contract.digest(inputs), "repository_id": 999,
            "version_name": "MODEL-ONLY-NOT-A-GAME", "android_version_code": 7,
            "platforms": [], "artifacts": [], "checks": [],
            "asset_sources": [{"source": "fixture-only", "sha256": "c" * 64}],
            "toolchain_versions": [{"tool": "fixture", "version": "model"}],
            "licenses": ["Fixture bytes only"], "known_issues": [],
            "manual_validation_scope": [],
            "unverified_scope": ["All actual game/platform/signing behavior"],
        }
        manifest.update(contract.identity(
            manifest["source_sha"], manifest["inputs_digest"]))
        signing = {}
        for system in sorted(contract.SYSTEMS):
            target = "fixture-" + system
            manifest["platforms"].append({
                "target_id": target, "os": system, "arch": "fixture-arch",
                "format": "fixture-bytes", "build_configuration": "fixture",
                "application_id": "org.example.fixture." + system,
                "identity_status": "permanent",
                "acceptance_profile": "fixture",
            })
            package = self.packages / (target + ".fixture")
            package.write_bytes(b"MODEL ONLY: not a valid game package\n")
            evidence = self.evidence / (target + ".txt")
            evidence.write_bytes(b"MODEL ONLY: no actual check executed\n")
            proof = self.evidence / (target + "-signature.txt")
            proof.write_bytes(b"MODEL ONLY: no actual signature\n")
            size, sha = contract.file_digest(self.packages, package.name)
            _, evidence_sha = contract.file_digest(
                self.evidence, evidence.name)
            _, proof_sha = contract.file_digest(self.evidence, proof.name)
            provenance = {
                "repository_id": 999, "workflow_id": 101,
                "workflow_path": ".github/workflows/fixture.yml",
                "event": "workflow_dispatch", "run_id": 102, "run_attempt": 1,
                "tested_source": manifest["source_sha"],
                "tested_tree": manifest["source_tree"],
                "inputs_digest": manifest["inputs_digest"],
            }
            manifest["artifacts"].append({
                "name": package.name, "target_id": target, "size": size,
                "sha256": sha, **provenance, "signing": {
                    "status": "VERIFIED", "identity": "fixture-certificate",
                    "payload_sha256": sha, "evidence_reference": proof.name,
                    "evidence_sha256": proof_sha,
                },
            })
            manifest["checks"].append({
                "check_id": target + "-test", "target_id": target,
                "required_scope": "release", "kind": "test",
                "execution_environment": "fixture-only",
                "command": ["fixture"],
                "cwd": "/fixture", "actually_executed": True, "status": "PASS",
                "executed_commands": 1, "test_count": 2, "assertion_count": 3,
                "evidence_reference": evidence.name,
                "evidence_sha256": evidence_sha, **provenance,
                "policy_sha": manifest["policy_sha"],
            })
            signing[target] = {"required": True,
                               "identity": "fixture-certificate"}
        self.manifest = manifest
        self.expected = {
            "schema_version": 1, "configuration_status": "READY",
            "decision_reference": "fixture-only-not-a-project-decision",
            "inputs": inputs, "manifest": copy.deepcopy(manifest),
            "signing_requirements": signing, "android_allocation": {
                "candidate_id": manifest["candidate_id"], "version_code": 7,
                "last_published_version_code": 6,
            },
        }

    def verify(self):
        return contract.verify(self.manifest, self.expected,
                               self.packages, self.evidence)

    def reject(self):
        with self.assertRaises((contract.ContractError, OSError)):
            self.verify()

    def match_expected(self):
        self.expected["manifest"] = copy.deepcopy(self.manifest)

    def test_control_model_pass_never_authorizes_publication(self):
        result = self.verify()
        self.assertTrue(result["local_contract_verified"])
        self.assertFalse(result["public_release_ready"])
        self.assertEqual(result["deployment"], "IMPLEMENTED_NOT_DEPLOYED")

    def test_cli_requires_independent_pin_and_never_publishes(self):
        manifest = self.root / "manifest.json"
        expected = self.root / "expected.json"
        manifest.write_text(json.dumps(self.manifest))
        expected.write_text(json.dumps(self.expected))
        pin = hashlib.sha256(expected.read_bytes()).hexdigest()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = contract.main([
                "verify", "--manifest", str(manifest), "--expected",
                str(expected), "--expected-sha256", pin,
                "--artifacts-root", str(self.packages),
                "--evidence-root", str(self.evidence),
            ])
        self.assertEqual(result, 0)
        self.assertFalse(json.loads(output.getvalue())["public_release_ready"])
        expected.write_text(json.dumps({"changed": True}))
        with self.assertRaises(contract.ContractError):
            contract.load_pinned(expected, pin)

    def test_t09_missing_platform_or_artifact(self):
        for key in ["platforms", "artifacts", "checks"]:
            with self.subTest(key=key):
                saved = copy.deepcopy(self.manifest[key])
                self.manifest[key].pop()
                self.match_expected()
                self.reject()
                self.manifest[key] = saved

    def test_t09_empty_or_modified_actual_package(self):
        package = self.packages / self.manifest["artifacts"][0]["name"]
        for contents in [b"", b"different bytes"]:
            package.write_bytes(contents)
            self.reject()

    def test_t09_wrong_arch_source_tree_resources(self):
        for group, field in [("platforms", "arch"),
                             ("artifacts", "tested_source"),
                             ("artifacts", "tested_tree"),
                             ("artifacts", "inputs_digest")]:
            with self.subTest(field=field):
                original = self.manifest[group][0][field]
                self.manifest[group][0][field] = "0" * len(original)
                self.reject()
                self.manifest[group][0][field] = original

    def test_t10_same_name_wrong_repository_run_or_attempt(self):
        for group in ["artifacts", "checks"]:
            for key in ["repository_id", "workflow_id", "run_id",
                        "run_attempt"]:
                with self.subTest(group=group, key=key):
                    self.manifest[group][0][key] += 1
                    self.reject()
                    self.manifest[group][0][key] -= 1

    def test_self_reported_success_cannot_replace_trusted_expectation(self):
        self.expected["manifest"]["checks"][0]["run_attempt"] = 2
        self.reject()

    def test_required_check_skip_empty_cancel_neutral_rejected(self):
        for key, value in [("status", "skipped"), ("status", "neutral"),
                           ("status", "cancelled"),
                           ("actually_executed", False),
                           ("executed_commands", 0), ("test_count", 0),
                           ("assertion_count", 0), ("command", [])]:
            with self.subTest(key=key, value=value):
                original = self.manifest["checks"][0][key]
                self.manifest["checks"][0][key] = value
                self.match_expected()
                self.reject()
                self.manifest["checks"][0][key] = original

    def test_changed_actual_evidence_rejected(self):
        item = self.manifest["checks"][0]
        (self.evidence / item["evidence_reference"]).write_bytes(b"changed")
        self.reject()

    def test_t16_wrong_signature_identity(self):
        self.manifest["artifacts"][0]["signing"]["identity"] = "other-fixture"
        self.match_expected()
        self.reject()

    def test_android_signing_cannot_be_waived(self):
        target = "fixture-android"
        self.expected["signing_requirements"][target] = {
            "required": False, "identity": ""}
        artifact = next(item for item in self.manifest["artifacts"]
                        if item["target_id"] == target)
        artifact["signing"].update(
            status="NOT_REQUIRED", identity="", evidence_reference="",
            evidence_sha256="")
        self.match_expected()
        self.reject()

    def test_t16_signature_still_binds_pre_mutation_bytes(self):
        item = self.manifest["artifacts"][0]
        (self.packages / item["name"]).write_bytes(b"modified after signing")
        item["size"], item["sha256"] = contract.file_digest(
            self.packages, item["name"])
        self.match_expected()
        self.reject()

    def test_t16_android_allocation_cannot_rewind_or_change_candidate(self):
        allocation = self.expected["android_allocation"]
        allocation["last_published_version_code"] = 7
        self.reject()
        allocation["last_published_version_code"] = 6
        allocation["candidate_id"] = "different"
        self.reject()

    def test_t21_stable_and_unknown_channel_controls_rejected(self):
        self.manifest["channel"] = "stable"
        self.match_expected()
        self.reject()
        self.manifest["channel"] = "development"
        self.manifest["promote_to_stable"] = True
        self.match_expected()
        self.reject()

    def test_test_identity_and_missing_signing_policy_rejected(self):
        self.manifest["platforms"][0]["identity_status"] = "temporary"
        self.match_expected()
        self.reject()
        self.manifest["platforms"][0]["identity_status"] = "permanent"
        self.match_expected()
        self.expected["signing_requirements"].clear()
        self.reject()

    def test_missing_configuration_does_not_default_ready(self):
        self.expected["configuration_status"] = "BLOCKED"
        self.reject()

    def test_wrong_canonical_inputs_and_duplicate_target_rejected(self):
        self.expected["inputs"]["asset_lock_sha256"] = "0" * 64
        self.reject()
        self.expected["inputs"]["asset_lock_sha256"] = "c" * 64
        self.manifest["platforms"][1] = self.manifest["platforms"][0]
        self.match_expected()
        self.reject()

    def test_package_symlink_and_path_traversal_rejected(self):
        item = self.manifest["artifacts"][0]
        path = self.packages / item["name"]
        path.rename(self.root / "outside")
        path.symlink_to(self.root / "outside")
        self.reject()
        path.unlink()
        (self.root / "outside").rename(path)
        self.manifest["checks"][0]["evidence_reference"] = "../outside"
        self.match_expected()
        self.reject()

    def test_boolean_integer_and_duplicate_json_keys_rejected(self):
        self.manifest["android_version_code"] = True
        self.match_expected()
        self.reject()
        path = self.root / "duplicate.json"
        path.write_text('{"success":true,"success":false}')
        with self.assertRaises(contract.ContractError):
            contract.load(path)


class ReleaseStateModelTests(unittest.TestCase):
    def setUp(self):
        old, old_receipt = observation(candidate("a", 41), 11)
        new, new_receipt = observation(candidate("b", 42), 12)
        self.pages = [
            {"repository_id": 999, "page": 1, "http_status": 200,
             "error": None, "next_page": 2, "releases": [old]},
            {"repository_id": 999, "page": 2, "http_status": 200,
             "error": None, "next_page": None, "releases": [new]},
        ]
        self.trusted = {"repository_id": 999, "requested": candidate("c", 43),
                        "verified_receipts": [old_receipt, new_receipt],
                        "draft_visibility_verified": True,
                        "observations_digest": contract.digest(self.pages),
                        "blocked_candidates": [], "superseded_candidates": []}

    def state(self):
        # Model a trusted collector capturing this fixture's exact API pages.
        self.trusted["observations_digest"] = contract.digest(self.pages)
        return contract.release_state(self.pages, self.trusted)

    def test_t11_prerelease_on_later_page_is_latest_without_stable(self):
        result = self.state()
        self.assertEqual(result["latest_development"]["release_id"], 12)
        self.assertEqual(result["pages_consumed"], 2)
        self.assertFalse(result["public_release_ready"])

    def test_t11_unrelated_stable_is_ignored(self):
        item = copy.deepcopy(self.pages[0]["releases"][0])
        item.update(id=10, tag_name="unrelated-stable", prerelease=False)
        self.pages[0]["releases"].insert(0, item)
        self.assertEqual(self.state()["latest_development"]["release_id"], 12)

    def test_t12_errors_are_never_empty_history(self):
        for status, error in [(403, None), (429, None), (404, None),
                              (None, "network timeout")]:
            with self.subTest(status=status):
                self.pages[1].update(http_status=status, error=error)
                with self.assertRaises(contract.ContractError):
                    self.state()

    def test_t12_incomplete_or_wrong_repository_pages_rejected(self):
        self.trusted["observations_digest"] = contract.digest(self.pages[:1])
        with self.assertRaises(contract.ContractError):
            contract.release_state(self.pages[:1], self.trusted)
        self.pages[1]["repository_id"] = 998
        with self.assertRaises(contract.ContractError):
            self.state()

    def test_draft_invisible_reads_cannot_prove_no_candidate(self):
        self.trusted["draft_visibility_verified"] = False
        with self.assertRaises(contract.ContractError):
            self.state()

    def test_untrusted_snapshot_cannot_change_publication_flags(self):
        self.pages[1]["releases"][0]["draft"] = True
        with self.assertRaises(contract.ContractError):
            contract.release_state(self.pages, self.trusted)

    def test_empty_successful_complete_history_is_distinct(self):
        self.pages = [dict(self.pages[0], next_page=None, releases=[])]
        self.trusted["verified_receipts"] = []
        self.assertIsNone(self.state()["latest_development"])
        self.assertEqual(self.state()["action"], "NEW_CANDIDATE")

    def test_missing_or_renamed_draft_cannot_free_reserved_version_code(self):
        _, receipt = observation(candidate("d", 43), 13, draft=True)
        self.trusted["verified_receipts"].append(receipt)
        with self.assertRaises(contract.ContractError):
            self.state()
        draft, _ = observation(candidate("d", 43), 13, draft=True)
        draft["tag_name"] = "renamed-outside-project"
        self.pages[1]["releases"].append(draft)
        with self.assertRaises(contract.ContractError):
            self.state()

    def test_unobserved_malformed_receipt_is_not_silently_ignored(self):
        self.trusted["verified_receipts"].append({"release_id": 13})
        with self.assertRaises(contract.ContractError):
            self.state()

    def test_t13_retry_draft_keeps_candidate_and_version_allocation(self):
        draft, receipt = observation(self.trusted["requested"], 13, draft=True)
        self.pages[1]["releases"].append(draft)
        self.trusted["verified_receipts"].append(receipt)
        self.assertEqual(self.state()["action"], "RETRY_SAME_CANDIDATE")
        self.assertEqual(self.state()["latest_development"]["release_id"], 12)
        self.trusted["requested"] = dict(self.trusted["requested"],
                                         android_version_code=44)
        with self.assertRaises(contract.ContractError):
            self.state()

    def test_t13_already_published_is_not_published_again(self):
        self.trusted["requested"] = candidate("b", 42)
        self.assertEqual(self.state()["action"], "ALREADY_PUBLISHED")

    def test_requested_version_cannot_reuse_another_draft_reservation(self):
        draft, receipt = observation(candidate("d", 43), 13, draft=True)
        self.pages[1]["releases"].append(draft)
        self.trusted["verified_receipts"].append(receipt)
        with self.assertRaises(contract.ContractError):
            self.state()

    def test_late_old_candidate_and_blocked_candidate_stay_blocked(self):
        self.trusted["requested"] = candidate("c", 40)
        self.assertEqual(self.state()["action"], "BLOCKED_OLD_CANDIDATE")
        self.trusted["requested"] = candidate("c", 43)
        self.trusted["blocked_candidates"] = [
            candidate("c", 43)["candidate_id"]]
        self.assertEqual(self.state()["action"], "BLOCKED")

    def test_t21_promoted_dev_release_rejected(self):
        self.pages[1]["releases"][0]["prerelease"] = False
        with self.assertRaises(contract.ContractError):
            self.state()

    def test_unverified_or_changed_remote_manifest_and_tag_rejected(self):
        for field in ["manifest_sha256", "tag_source_sha"]:
            item = self.pages[1]["releases"][0]
            original = item[field]
            item[field] = "0" * len(original)
            with self.assertRaises(contract.ContractError):
                self.state()
            item[field] = original
        self.trusted["verified_receipts"][1]["contract_verified"] = False
        with self.assertRaises(contract.ContractError):
            self.state()

    def test_t13_identity_excludes_date_and_run_attempt(self):
        first = contract.identity("a" * 40, "b" * 64)
        self.assertEqual(first, contract.identity("a" * 40, "b" * 64))
        self.assertNotEqual(first, contract.identity("a" * 40, "c" * 64))

    def test_duplicate_remote_candidate_or_version_allocation_rejected(self):
        for identity in [candidate("b", 42), candidate("c", 42)]:
            with self.subTest(identity=identity):
                release, receipt = observation(identity, 13)
                self.pages[1]["releases"].append(release)
                self.trusted["verified_receipts"].append(receipt)
                with self.assertRaises(contract.ContractError):
                    self.state()
                self.pages[1]["releases"].pop()
                self.trusted["verified_receipts"].pop()


if __name__ == "__main__":
    unittest.main()
