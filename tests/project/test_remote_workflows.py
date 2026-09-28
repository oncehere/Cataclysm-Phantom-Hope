"""Successor workflow inventory rejects restored inherited entrypoints."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "remote_workflows", ROOT / "tools/project/check_remote_workflows.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class WorkflowPolicyTests(unittest.TestCase):
    def test_tooling_history_and_native_merge_depth_are_distinct(self):
        workflow = (ROOT / ".github/workflows/project-ci.yml").read_text()
        self.assertEqual(AUDIT.candidate_checkout_errors(workflow), [])
        shallow = workflow.replace("fetch-depth: 0", "fetch-depth: 2")
        self.assertIn(
            "tooling candidate checkout requires fetch-depth 0",
            AUDIT.candidate_checkout_errors(shallow),
        )
        changed = workflow.replace("fetch-depth: 2", "fetch-depth: 1")
        self.assertIn(
            "native candidate checkout requires fetch-depth 2",
            AUDIT.candidate_checkout_errors(changed),
        )

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        (self.repo / "project").mkdir()
        self.workflows = self.repo / ".github/workflows"
        self.workflows.mkdir(parents=True)
        self.action = "actions/checkout@" + "a" * 40
        policy = {"allowed_actions": [self.action], "workflows": ["ci.yml"]}
        (self.repo / "project/remote-actions-policy.json").write_text(
            json.dumps(policy)
        )
        self.ci = self.workflows / "ci.yml"
        self.ci.write_text("steps:\n  - uses: " + self.action + "\n")

    def test_exact_inventory_and_pins(self):
        self.assertEqual(AUDIT.inspect(self.repo)["status"], "PASS")

    def test_restored_release_entry_is_rejected(self):
        (self.workflows / "release.yml").write_text("on: push\n")
        self.assertEqual(AUDIT.inspect(self.repo)["status"], "FAIL")

    def test_old_checkout_or_moving_tag_is_rejected(self):
        for ref in ("actions/checkout@v5", "actions/checkout@" + "b" * 40):
            with self.subTest(ref=ref):
                self.ci.write_text("steps:\n  - uses: " + ref + "\n")
                self.assertEqual(AUDIT.inspect(self.repo)["status"], "FAIL")

    def test_missing_required_workflow_is_rejected(self):
        self.ci.unlink()
        self.assertEqual(AUDIT.inspect(self.repo)["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
