from copy import deepcopy
from importlib.resources import files
import json
import unittest

from cph_ai_companion.protocol import (
    PROTOCOL_VERSION, ProtocolError, action_catalog, contract, task_catalog,
    validate_request, validate_tasks,
)


class TaskProtocolTests(unittest.TestCase):
    def setUp(self):
        resources = files("cph_ai_companion").joinpath("resources/protocol")
        plans = json.loads(resources.joinpath("fixtures.json").read_text())
        self.candidate = {
            "context": deepcopy(plans[0]["plan"]["context"]),
            "tasks": [{"id": "follow-1", "kind": "follow", "args": {}}],
        }

    def test_version_and_catalog_preserve_shared_action_arguments(self):
        self.assertEqual(PROTOCOL_VERSION, "1.2")
        self.assertEqual(contract()["protocol_version"], PROTOCOL_VERSION)
        self.assertIn("offer_tasks", contract()["methods"])
        tasks = {entry["name"]: entry for entry in task_catalog()}
        actions = {entry["name"]: entry for entry in action_catalog()}
        self.assertEqual(set(tasks), {"follow", "guard", "move", "gather", "craft"})
        for kind in ("move", "craft"):
            self.assertEqual(tasks[kind]["args"], actions[kind]["args"])
        self.assertEqual(tasks["gather"]["args"]["properties"], actions["gather"]["args"]["properties"])
        self.assertEqual(tasks["gather"]["args"]["required"], ["item_type", "count"])
        self.assertEqual(contract()["schemas"]["tasks"]["properties"]["context"],
                         contract()["schemas"]["context"])

    def test_shared_native_task_fixtures_match_expected_validity(self):
        fixtures = json.loads(files("cph_ai_companion").joinpath(
            "resources/protocol/task_fixtures.json").read_text())
        for fixture in fixtures:
            with self.subTest(fixture=fixture["name"]):
                if fixture["valid"]:
                    self.assertEqual(validate_tasks(fixture["offer"]), fixture["offer"])
                else:
                    with self.assertRaises(ProtocolError) as raised:
                        validate_tasks(fixture["offer"])
                    self.assertEqual(raised.exception.code, fixture["error"])

    def test_defaults_are_optional_and_validation_preserves_payload(self):
        original = deepcopy(self.candidate)
        self.assertIs(validate_tasks(self.candidate), self.candidate)
        self.assertEqual(self.candidate, original)
        self.candidate["mode"] = "prioritize"
        self.candidate["tasks"][0]["constraints"] = {"max_distance": 60}
        validate_tasks(self.candidate)

    def test_rejections_locate_known_fields_without_disclosing_model_keys_or_values(self):
        cases = []
        missing = deepcopy(self.candidate)
        missing["tasks"][0].pop("args")
        cases.append((missing, "missing_field", "$.tasks[0].args"))
        unknown = deepcopy(self.candidate)
        unknown["tasks"][0]["args"]["private-model-key"] = "private-model-value"
        cases.append((unknown, "unknown_field", "$.tasks[0].args"))
        duplicate = deepcopy(self.candidate)
        duplicate["tasks"] *= 2
        cases.append((duplicate, "duplicate_task", "$.tasks[1].id"))
        dependency = deepcopy(self.candidate)
        dependency["tasks"][0]["depends_on"] = ["follow-1"]
        cases.append((dependency, "invalid_dependency", "$.tasks[0].depends_on"))
        for candidate, code, path in cases:
            with self.subTest(code=code):
                original = deepcopy(candidate)
                with self.assertRaises(ProtocolError) as raised:
                    validate_tasks(candidate)
                self.assertEqual(raised.exception.code, code)
                self.assertEqual(raised.exception.path, path)
                self.assertEqual(str(raised.exception), code)
                self.assertNotIn("private-model", raised.exception.path)
                self.assertEqual(candidate, original)

    def test_dependency_identity_is_resolved_by_native_admission(self):
        task = self.candidate["tasks"][0]
        task["depends_on"] = ["previous-candidate-task", "next-task"]
        self.candidate["tasks"].append({"id": "next-task", "kind": "guard", "args": {}})
        validate_tasks(self.candidate)
        for dependencies, code in ((["follow-1"], "invalid_dependency"),
                                   (["previous", "previous"], "duplicate_dependency")):
            with self.subTest(dependencies=dependencies):
                task["depends_on"] = dependencies
                with self.assertRaisesRegex(ProtocolError, code):
                    validate_tasks(self.candidate)

    def test_tasks_keep_step_identity_bounds_and_strict_fields(self):
        for identifier in ("", "x" * 257, "bad\x00id"):
            with self.subTest(identifier=identifier):
                self.candidate["tasks"][0]["id"] = identifier
                with self.assertRaises(ProtocolError):
                    validate_tasks(self.candidate)
        self.candidate["tasks"][0]["id"] = "同伴" * 128
        validate_tasks(self.candidate)
        for field, value in (("intent", "propose_own_goals"), ("python_code", "exec(...)")):
            with self.subTest(field=field):
                invalid = deepcopy(self.candidate)
                invalid["tasks"][0][field] = value
                with self.assertRaisesRegex(ProtocolError, "unknown_field"):
                    validate_tasks(invalid)
        self.candidate["tasks"][0]["id"] = "bad\ud800id"
        with self.assertRaisesRegex(ProtocolError, "invalid_json"):
            validate_tasks(self.candidate)

    def test_quantity_modes_are_only_available_for_gather(self):
        for kind in ("follow", "guard", "move", "craft"):
            with self.subTest(kind=kind):
                args = {"move": {"x": 1, "y": 2, "z": 0},
                        "craft": {"recipe": "bandages"}}.get(kind, {})
                self.candidate["tasks"] = [{"id": "work", "kind": kind, "args": args,
                                             "quantity_mode": "acquired"}]
                with self.assertRaisesRegex(ProtocolError, "invalid_quantity_mode"):
                    validate_tasks(self.candidate)

    def test_request_accepts_additive_task_summary_without_restricting_existing_extensions(self):
        request = {"context": self.candidate["context"], "observations": {},
                   "task_catalog": task_catalog(), "task_summary": [{"id": "work", "state": "running"}],
                   "future_extension": {"version": 1}}
        self.assertEqual(validate_request(request), request)
        request["task_catalog"] = {}
        with self.assertRaisesRegex(ProtocolError, "invalid_task_catalog"):
            validate_request(request)


if __name__ == "__main__":
    unittest.main()
