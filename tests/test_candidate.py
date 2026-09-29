"""Production apply must validate meaning, even if a manifest is rehashed."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from pokeeper.catalog import json_bytes
from pokeeper.cli import main
from pokeeper.config import KeeperError
from pokeeper.core import check, plan
from pokeeper.transaction import TransactionError, apply_candidate, digest


class CandidateValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        demo = Path(__file__).resolve().parents[1] / "examples/demo"
        for name in ("project.toml", "messages.pot", "upstream.po"):
            shutil.copyfile(demo / name, self.root / name)
        self.config = self.root / "project.toml"
        self.candidate = self.root / "candidate"
        plan(self.config, self.candidate)
        self.manifest = json.loads((self.candidate / "manifest.json").read_text())
        self.state = json.loads((self.candidate / "state.json").read_text())
        self.source_before = (self.root / "upstream.po").read_bytes()

    def rewrite(self, name, data):
        (self.candidate / name).parent.mkdir(parents=True, exist_ok=True)
        (self.candidate / name).write_bytes(data)
        self.manifest["files"][name] = digest(data)

    def save(self):
        self.rewrite("state.json", json_bytes(self.state))
        (self.candidate / "manifest.json").write_bytes(json_bytes(self.manifest))

    def rejected(self, pattern):
        self.save()
        with self.assertRaisesRegex((KeeperError, TransactionError), pattern):
            apply_candidate(self.candidate)
        self.assertFalse((self.root / "output.po").exists())
        self.assertFalse((self.root / ".pokeeper/state.json").exists())
        self.assertEqual((self.root / "upstream.po").read_bytes(), self.source_before)

    def test_valid_candidate_applies_and_checks(self):
        apply_candidate(self.candidate)
        self.assertEqual(check(self.config)["status"], "PASS")

    def test_rehashed_wrong_baseline_is_rejected(self):
        self.state["baseline"] = "0" * 64
        self.rejected("baseline differs")

    def test_rehashed_wrong_entry_digest_is_rejected(self):
        record = next(iter(self.state["entries"].values()))
        record["translation"] = "0" * 64
        self.rejected("entry baseline differs")

    def test_rehashed_wrong_project_is_rejected(self):
        self.state["project"] = "another-project"
        self.rejected("project/language/version mismatch")

    def test_retargeting_source_is_rejected(self):
        self.manifest["targets"]["po"] = str(self.root / "upstream.po")
        self.rejected("destinations differ")

    def test_retargeting_unrelated_file_is_rejected(self):
        other = self.root / "unrelated.txt"
        other.write_bytes(b"do not overwrite")
        self.manifest["targets"]["po"] = str(other)
        self.manifest["inputs"][str(other)] = digest(other.read_bytes())
        self.rejected("destinations differ")
        self.assertEqual(other.read_bytes(), b"do not overwrite")

    def test_unguarded_configuration_is_rejected(self):
        del self.manifest["inputs"][str(self.config)]
        self.rejected("configuration must be a guarded input")

    def test_unguarded_source_is_rejected(self):
        del self.manifest["inputs"][str(self.root / "upstream.po")]
        self.rejected("required project input is not guarded")

    def test_missing_baseline_snapshot_is_rejected(self):
        name = f"snapshots/{self.state['baseline']}.po"
        del self.manifest["files"][name]
        (self.candidate / name).unlink()
        self.rejected("baseline snapshot is missing")

    def test_missing_source_snapshot_is_rejected(self):
        ref = next(iter(self.state["references"].values()))
        name = f"snapshots/{ref['sha256']}.po"
        del self.manifest["files"][name]
        (self.candidate / name).unlink()
        self.rejected("historical source snapshot is not guarded")

    def test_source_must_contain_actual_adopted_translation(self):
        old_key, reference = next(iter(self.state["references"].items()))
        old_sha = reference["sha256"]
        raw = (self.root / "messages.pot").read_bytes()
        reference["sha256"] = digest(raw)
        new_key = digest(json_bytes(reference))
        self.state["references"] = {new_key: reference}
        for record in self.state["entries"].values():
            if record["source"] == old_key:
                record["source"] = new_key
        del self.manifest["files"][f"snapshots/{old_sha}.po"]
        (self.candidate / f"snapshots/{old_sha}.po").unlink()
        self.rewrite(f"snapshots/{reference['sha256']}.po", raw)
        self.rejected("translation does not match its historical source")

    def test_unrelated_snapshot_is_rejected(self):
        raw = b"unrelated bytes"
        self.rewrite(f"snapshots/{digest(raw)}.po", raw)
        self.rejected("unrelated snapshot")

    def test_production_apply_runs_final_gettext_check_before_writing(self):
        with patch("pokeeper.validation.gettext_check", side_effect=KeeperError("msgfmt rejected PO")):
            self.rejected("msgfmt rejected PO")

    def test_cli_cannot_apply_unbound_generic_transaction(self):
        self.manifest["config"] = None
        self.save()
        self.assertEqual(main(["apply", str(self.candidate)]), 2)
        self.assertFalse((self.root / "output.po").exists())


if __name__ == "__main__":
    unittest.main()
