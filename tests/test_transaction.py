import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from pokeeper import transaction as tx


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.po = self.root / "project.po"
        self.state = self.root / "project.state.json"
        self.source = self.root / "source.po"
        self.po.write_bytes(b"old po")
        self.state.write_bytes(b"old state")
        self.source.write_bytes(b"source")
        self.targets = {"po": str(self.po), "state": str(self.state), "snapshots": str(self.root / "snapshots")}
        self.files = {"candidate.po": b"new po", "state.json": b"new state", "report.json": b"{}",
                      "snapshots/" + tx.digest(b"source") + ".po": b"source"}

    def publish(self, extra_inputs=()):
        self.inputs = {str(path): tx.file_digest(path) for path in (self.po, self.state, self.source, *extra_inputs)}
        return tx.publish_candidate(self.root / "candidate", self.files, self.inputs, self.targets)

    def interrupt(self, candidate):
        original = tx.atomic_write

        def failing(path, data):
            if path == self.state:
                raise OSError("simulated interruption before state replacement")
            return original(path, data)

        with patch.object(tx, "atomic_write", side_effect=failing):
            with self.assertRaisesRegex(OSError, "interruption"):
                tx.apply_candidate(candidate, require_config=False)
        self.assertEqual(self.po.read_bytes(), b"new po")
        self.assertEqual(self.state.read_bytes(), b"old state")

    def test_apply_and_snapshot(self):
        candidate = self.publish()
        tx.apply_candidate(candidate, require_config=False)
        self.assertEqual(self.po.read_bytes(), b"new po")
        self.assertEqual(self.state.read_bytes(), b"new state")
        self.assertEqual((self.root / "snapshots" / (tx.digest(b"source") + ".po")).read_bytes(), b"source")
        tx.assert_no_pending(self.state)

    def test_default_application_requires_bound_project_config(self):
        candidate = self.publish()
        with self.assertRaisesRegex(tx.TransactionError, "bound to its project config"):
            tx.apply_candidate(candidate)
        self.assertEqual(self.po.read_bytes(), b"old po")

    def test_changed_inputs_rejected(self):
        candidate = self.publish()
        self.source.write_bytes(b"concurrent source update")
        with self.assertRaisesRegex(tx.TransactionError, "input changed"):
            tx.apply_candidate(candidate, require_config=False)
        self.assertEqual(self.po.read_bytes(), b"old po")

    def test_current_po_and_state_are_guarded(self):
        candidate = self.publish()
        self.po.write_bytes(b"new human edit")
        with self.assertRaisesRegex(tx.TransactionError, "input changed"):
            tx.apply_candidate(candidate, require_config=False)
        self.assertEqual(self.po.read_bytes(), b"new human edit")

    def test_missing_target_input_is_rejected(self):
        with self.assertRaisesRegex(tx.TransactionError, "inputs must include"):
            tx.publish_candidate(self.root / "candidate", self.files, {}, self.targets)

    def test_candidate_corruption_is_rejected(self):
        candidate = self.publish()
        (candidate / "candidate.po").write_bytes(b"tampered")
        with self.assertRaisesRegex(tx.TransactionError, "hash check"):
            tx.apply_candidate(candidate, require_config=False)
        self.assertEqual(self.po.read_bytes(), b"old po")

    def test_finish_survives_candidate_removal(self):
        candidate = self.publish()
        self.interrupt(candidate)
        shutil.rmtree(candidate)
        with self.assertRaisesRegex(tx.TransactionError, "unfinished"):
            tx.assert_no_pending(self.state)
        tx.recover(self.state, "finish")
        self.assertEqual(self.po.read_bytes(), b"new po")
        self.assertEqual(self.state.read_bytes(), b"new state")
        tx.assert_no_pending(self.state)

    def test_finish_checks_previously_persisted_snapshots(self):
        historical = self.root / "snapshots" / (tx.digest(b"historical source") + ".po")
        historical.parent.mkdir()
        historical.write_bytes(b"historical source")
        candidate = self.publish(extra_inputs=[historical])
        self.interrupt(candidate)
        historical.unlink()
        with self.assertRaisesRegex(tx.TransactionError, "input changed"):
            tx.recover(self.state, "finish")
        self.assertEqual(self.state.read_bytes(), b"old state")

    def test_rollback_restores_both_files(self):
        candidate = self.publish()
        self.interrupt(candidate)
        tx.recover(self.state, "rollback")
        self.assertEqual(self.po.read_bytes(), b"old po")
        self.assertEqual(self.state.read_bytes(), b"old state")
        tx.assert_no_pending(self.state)

    def test_rollback_restores_missing_files(self):
        self.po.unlink()
        self.state.unlink()
        candidate = self.publish()
        original = tx.atomic_write

        def failing(path, data):
            if path == self.state:
                raise OSError("simulated interruption")
            return original(path, data)

        with patch.object(tx, "atomic_write", side_effect=failing):
            with self.assertRaises(OSError):
                tx.apply_candidate(candidate, require_config=False)
        tx.recover(self.state, "rollback")
        self.assertFalse(self.po.exists())
        self.assertFalse(self.state.exists())

    def test_unknown_concurrent_edit_blocks_recovery(self):
        candidate = self.publish()
        self.interrupt(candidate)
        self.po.write_bytes(b"user edited during outage")
        for action in ("finish", "rollback"):
            with self.subTest(action=action), self.assertRaisesRegex(tx.TransactionError, "refusing overwrite"):
                tx.recover(self.state, action)
        self.assertEqual(self.po.read_bytes(), b"user edited during outage")
        self.assertEqual(self.state.read_bytes(), b"old state")

    def test_pending_blocks_new_apply(self):
        candidate = self.publish()
        self.interrupt(candidate)
        with self.assertRaisesRegex(tx.TransactionError, "unfinished"):
            tx.apply_candidate(candidate, require_config=False)

    def test_journal_payload_hash_mismatch_blocks_recovery(self):
        candidate = self.publish()
        self.interrupt(candidate)
        path = Path(str(self.state) + ".pending")
        journal = json.loads(path.read_text())
        journal["versions"]["po"]["new"]["sha256"] = "0" * 64
        path.write_text(json.dumps(journal))
        with self.assertRaisesRegex(tx.TransactionError, "payload hash mismatch"):
            tx.recover(self.state, "rollback")
        self.assertEqual(self.po.read_bytes(), b"new po")

    def test_journal_wrong_state_is_rejected(self):
        candidate = self.publish()
        self.interrupt(candidate)
        other = self.root / "other.json"
        shutil.copyfile(Path(str(self.state) + ".pending"), Path(str(other) + ".pending"))
        with self.assertRaisesRegex(tx.TransactionError, "another state"):
            tx.recover(other, "finish")

    def test_existing_candidate_not_replaced(self):
        self.publish()
        with self.assertRaisesRegex(tx.TransactionError, "already exists"):
            self.publish()

    def test_symlink_and_hardlink_targets_are_rejected(self):
        self.state.unlink()
        self.state.symlink_to(self.po)
        with self.assertRaisesRegex(tx.TransactionError, "symlink"):
            self.publish()
        self.state.unlink()
        self.state.hardlink_to(self.po)
        with self.assertRaisesRegex(tx.TransactionError, "alias"):
            self.publish()

    def test_candidate_traversal_and_snapshot_hash_are_rejected(self):
        self.files["../outside"] = b"not allowed"
        with self.assertRaisesRegex(tx.TransactionError, "unexpected candidate"):
            self.publish()
        del self.files["../outside"]
        self.files["snapshots/" + "0" * 64 + ".po"] = b"wrong"
        with self.assertRaisesRegex(tx.TransactionError, "content hash"):
            self.publish()

    def test_change_during_candidate_creation_is_rejected(self):
        original = tx.atomic_write

        def changing(path, data):
            original(path, data)
            if path.name == "manifest.json":
                self.source.write_bytes(b"concurrent")

        with patch.object(tx, "atomic_write", side_effect=changing):
            with self.assertRaisesRegex(tx.TransactionError, "input changed"):
                self.publish()
        self.assertFalse((self.root / "candidate").exists())

    def test_change_after_journal_is_not_overwritten(self):
        candidate = self.publish()
        original = tx.atomic_write

        def changing(path, data):
            original(path, data)
            if path.name.endswith(".pending"):
                self.po.write_bytes(b"human raced apply")

        with patch.object(tx, "atomic_write", side_effect=changing):
            with self.assertRaisesRegex(tx.TransactionError, "input changed"):
                tx.apply_candidate(candidate, require_config=False)
        self.assertEqual(self.po.read_bytes(), b"human raced apply")
        with self.assertRaisesRegex(tx.TransactionError, "unfinished"):
            tx.assert_no_pending(self.state)


if __name__ == "__main__":
    unittest.main()
