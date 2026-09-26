"""Operator-control model tests, not a deployed GitHub gate."""

import importlib.util
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "operator_controls",
    Path(__file__).resolve().parents[2] / "tools/project/operator_controls.py",
)
control = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(control)


class ControlsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/tmp")
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "controls.json"
        control.initialize(self.state)

    def test_initial_state_denies_both_actions(self):
        for action in ("merge", "publish-dev"):
            self.assertFalse(
                control.check(self.state, action, "candidate-1", 0)[
                    "allowed_by_operator_controls"
                ]
            )

    def test_independent_pause_switches(self):
        control.update(self.state, 0, "resume-sync")
        self.assertTrue(
            control.check(self.state, "merge", "candidate-1", 1)[
                "allowed_by_operator_controls"
            ]
        )
        self.assertFalse(
            control.check(self.state, "publish-dev", "candidate-1", 1)[
                "allowed_by_operator_controls"
            ]
        )

    def test_inflight_attempt_rechecks_pause_and_revision(self):
        control.update(self.state, 0, "resume-sync")
        control.update(self.state, 1, "pause-sync")
        result = control.check(self.state, "merge", "candidate-1", 1)
        self.assertFalse(result["allowed_by_operator_controls"])
        self.assertEqual(len(result["reasons"]), 2)

    def test_block_survives_resume_and_only_applies_to_candidate(self):
        control.update(self.state, 0, "block", "candidate-1")
        control.update(self.state, 1, "resume-release")
        self.assertFalse(
            control.check(self.state, "publish-dev", "candidate-1", 2)[
                "allowed_by_operator_controls"
            ]
        )
        self.assertTrue(
            control.check(self.state, "publish-dev", "candidate-2", 2)[
                "allowed_by_operator_controls"
            ]
        )

    def test_unblock_does_not_resume_publication(self):
        control.update(self.state, 0, "block", "candidate-1")
        control.update(self.state, 1, "unblock", "candidate-1")
        self.assertFalse(
            control.check(self.state, "publish-dev", "candidate-1", 2)[
                "allowed_by_operator_controls"
            ]
        )

    def test_stale_writer_never_overwrites_new_control(self):
        control.update(self.state, 0, "block", "candidate-1")
        before = self.state.read_bytes()
        with self.assertRaisesRegex(ValueError, "stale"):
            control.update(self.state, 0, "resume-release")
        self.assertEqual(before, self.state.read_bytes())

    def test_stable_cannot_be_authorized_by_unpausing(self):
        control.update(self.state, 0, "resume-release")
        self.assertFalse(
            control.check(self.state, "publish-stable", "candidate-1", 1)[
                "allowed_by_operator_controls"
            ]
        )

    def test_missing_corrupt_or_empty_state_is_not_unpaused(self):
        for text in ("", "{}", "null", '{"sync_paused": false}'):
            self.state.write_text(text)
            with self.assertRaises(ValueError):
                control.check(self.state, "merge", "candidate-1", 0)
        self.state.unlink()
        with self.assertRaises(ValueError):
            control.check(self.state, "merge", "candidate-1", 0)

    def test_existing_state_not_reinitialized(self):
        before = self.state.read_bytes()
        with self.assertRaises(ValueError):
            control.initialize(self.state)
        self.assertEqual(before, self.state.read_bytes())

    def test_source_checkout_state_is_rejected(self):
        path = Path(__file__).resolve().parents[2] / "operator-state.json"
        with self.assertRaisesRegex(ValueError, "outside"):
            control.read(path)

    def test_symlink_state_and_lock_are_rejected(self):
        target = self.state.parent / "target"
        self.state.rename(target)
        self.state.symlink_to(target)
        with self.assertRaises(ValueError):
            control.read(self.state)
        self.state.unlink()
        target.rename(self.state)
        lock = self.state.with_name(self.state.name + ".lock")
        lock.unlink()
        lock.symlink_to(target)
        with self.assertRaises(OSError):
            control.update(self.state, 0, "resume-sync")

    def test_control_pass_never_claims_execution_or_deployment(self):
        control.update(self.state, 0, "resume-sync")
        result = control.check(self.state, "merge", "candidate-1", 1)
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["action_executed"])
        self.assertFalse(result["deployment_verified"])


if __name__ == "__main__":
    unittest.main()
