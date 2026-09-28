from __future__ import annotations

import copy
import unittest
from datetime import date

from audit_repository_governance import (
    DEPENDABOT_PATH, load_yaml, validate_dependabot,
    validate_repository, validate_target, workflow_permission_errors,
)


class RepositoryGovernanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.target, errors = validate_repository(as_of=date(2026, 9, 28))
        self.assertEqual(errors, [])

    def test_recorded_cph_fork_and_active_gate_snapshot(self) -> None:
        audit = self.target["audit"]
        self.assertEqual(audit["repository"]["full_name"],
                         "oncehere/Cataclysm-Phantom-Hope")
        self.assertEqual(audit["repository"]["parent"],
                         "CleverRaven/Cataclysm-DDA")
        self.assertEqual(audit["repository"]["default_branch"], "main")
        self.assertEqual(audit["repository"]["main_sha"],
                         "abd9222e01b77ac9e187f53cd6cfe85275453a69")
        self.assertTrue(audit["repository"]["main_protected"])
        self.assertTrue(audit["actions"]["can_approve_pull_request_reviews"])
        self.assertTrue(audit["repository"]["has_discussions"])
        self.assertTrue(audit["repository"]["has_issues"])
        self.assertTrue(audit["security"]["private_vulnerability_reporting"])
        gate = self.target["entries"][0]
        self.assertEqual(gate["observed_enforcement"], "active")
        self.assertTrue(gate["ready_to_enable"])
        self.assertTrue(gate["post_activation_probe_verified"])
        self.assertTrue(gate["operational"])

    def test_ccb_repository_identity_is_rejected(self) -> None:
        target = copy.deepcopy(self.target)
        target["audit"]["repository"]["full_name"] = (
            "CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb"
        )
        self.assertTrue(any("schema" in error for error in validate_target(target)))

    def test_gate_cannot_claim_readiness_without_checks(self) -> None:
        target = copy.deepcopy(self.target)
        target["entries"][0]["prerequisites"]["windows_linux_checks_verified"] = False
        target["entries"][0]["ready_to_enable"] = True
        self.assertTrue(any("readiness" in error for error in validate_target(target)))

    def test_protected_pr_probe_is_after_activation(self) -> None:
        target = copy.deepcopy(self.target)
        gate = target["entries"][0]
        gate["observed_enforcement"] = "disabled"
        gate["enabled_at"] = None
        gate["post_activation_probe_verified"] = False
        gate["operational"] = False
        target["audit"]["rulesets"][0]["enforcement"] = "disabled"
        target["audit"]["repository"]["main_protected"] = False
        gate["post_activation_probe_verified"] = True
        self.assertTrue(any("cannot precede" in error for error in validate_target(target)))

    def test_operational_claim_requires_actual_probe(self) -> None:
        target = copy.deepcopy(self.target)
        target["entries"][0]["post_activation_probe_verified"] = False
        target["entries"][0]["operational"] = True
        self.assertTrue(any("operational" in error for error in validate_target(target)))

    def test_activation_sequence_has_no_protected_probe_deadlock(self) -> None:
        target = copy.deepcopy(self.target)
        gate = target["entries"][0]
        gate["observed_enforcement"] = "disabled"
        gate["enabled_at"] = None
        gate["post_activation_probe_verified"] = False
        gate["operational"] = False
        target["audit"]["rulesets"][0]["enforcement"] = "disabled"
        target["audit"]["repository"]["main_protected"] = False
        gate["prerequisites"] = {
            "windows_linux_checks_verified": True,
            "trusted_gate_verified": True,
        }
        gate["blockers"] = []
        gate["ready_to_enable"] = True
        self.assertEqual(validate_target(target), [])
        gate["observed_enforcement"] = "active"
        target["audit"]["rulesets"][0]["enforcement"] = "active"
        target["audit"]["repository"]["main_protected"] = True
        gate["enabled_at"] = "2026-09-27T07:17:28.669Z"
        self.assertEqual(validate_target(target), [])
        gate["post_activation_probe_verified"] = True
        gate["operational"] = True
        self.assertEqual(validate_target(target), [])

    def test_active_rule_cannot_claim_unprotected_main(self) -> None:
        target = copy.deepcopy(self.target)
        target["audit"]["repository"]["main_protected"] = False
        errors = validate_target(target)
        self.assertTrue(any("unprotected main" in error for error in errors))

    def test_public_intake_waits_for_cleanup_merge(self) -> None:
        target = copy.deepcopy(self.target)
        target["post_merge_intake"]["cleanup_pr_merged"] = False
        self.assertTrue(any("cleanup PR merge" in error for error in validate_target(target)))

    def test_auto_merge_is_rejected(self) -> None:
        target = copy.deepcopy(self.target)
        target["audit"]["repository"]["allow_auto_merge"] = True
        self.assertTrue(any("auto-merge" in error for error in validate_target(target)))

    def test_freshness_is_only_enforced_when_requested(self) -> None:
        self.assertEqual(validate_target(self.target, as_of=date(2027, 1, 1)), [])
        errors = validate_target(self.target, as_of=date(2027, 1, 1),
                                 max_age_days=50)
        self.assertTrue(any("days old" in error for error in errors))

    def test_dependabot_actions_schedule_is_valid(self) -> None:
        self.assertEqual(validate_dependabot(load_yaml(DEPENDABOT_PATH)), [])

    def test_write_all_workflow_permission_is_rejected(self) -> None:
        errors = workflow_permission_errors(
            ".github/workflows/example.yml",
            {"jobs": {"release": {"permissions": "write-all"}}},
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("forbidden write-all", errors[0])

    def test_unknown_workflow_permission_is_rejected(self) -> None:
        errors = workflow_permission_errors(
            ".github/workflows/example.yml",
            {"permissions": {"repository-projects": "write"}, "jobs": {}},
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("unknown repository-projects", errors[0])


if __name__ == "__main__":
    unittest.main()
