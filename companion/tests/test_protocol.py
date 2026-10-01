from copy import deepcopy
from importlib.resources import files
import json
import unittest

from cph_ai_companion.protocol import ProtocolError, action_catalog, contract, schema_digest, validate_plan, validate_request
from cph_ai_companion.personality import BEHAVIORS


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.fixtures = json.loads(files("cph_ai_companion").joinpath("resources/protocol/fixtures.json").read_text())
        self.plan = deepcopy(self.fixtures[0]["plan"])

    def test_shared_native_fixtures_match_expected_validity(self):
        for fixture in self.fixtures:
            with self.subTest(fixture=fixture["name"]):
                if fixture["valid"]:
                    self.assertEqual(validate_plan(fixture["plan"]), fixture["plan"])
                else:
                    with self.assertRaises(ProtocolError):
                        validate_plan(fixture["plan"])

    def test_catalog_and_policy_cover_same_fifteen_social_actions(self):
        self.assertEqual(set(contract()["behaviors"]), BEHAVIORS)
        self.assertTrue(BEHAVIORS.issubset({entry["name"] for entry in action_catalog()}))
        self.assertEqual(len(schema_digest()), 64)

    def test_unrecognized_fields_and_future_step_dependencies_fail_closed(self):
        self.plan["steps"][0]["from_step"] = "later-step"
        with self.assertRaisesRegex(ProtocolError, "invalid_dependency"):
            validate_plan(self.plan)
        self.plan["steps"][0].pop("from_step")
        self.plan["steps"][0]["python_code"] = "exec(...)"
        with self.assertRaisesRegex(ProtocolError, "unknown_field"):
            validate_plan(self.plan)

    def test_action_arguments_cannot_change_stats_and_counts_are_not_booleans(self):
        self.plan["steps"] = [{"id": "gather-1", "action": "gather", "args":
                              {"x": 1, "y": 2, "z": 0, "item_type": "bandages", "count": True}}]
        with self.assertRaisesRegex(ProtocolError, "integer_required"):
            validate_plan(self.plan)

    def test_request_bounds_and_context_are_validated(self):
        request = {"context": self.plan["context"], "observations": {}, "events": []}
        self.assertEqual(validate_request(request), request)
        for invalid in ({**request, "events": [{}] * 257}, {**request, "observations": []},
                        {**request, "context": {**request["context"], "actor_id": True}}):
            with self.assertRaises(ProtocolError):
                validate_request(invalid)


if __name__ == "__main__":
    unittest.main()
