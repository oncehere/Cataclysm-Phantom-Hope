import json
from pathlib import Path
import tempfile
import unittest

from cph_ai_companion.config import ConfigError, default_config, load_config, validate_config


class ConfigTests(unittest.TestCase):
    def test_default_template_is_offline_and_isolated_from_callers(self):
        config = default_config()
        self.assertEqual(config["llm"]["base_url"], "")
        self.assertEqual(config["llm"]["model"], "")
        config["personality"]["social_behavior"]["refuse"] = False
        self.assertTrue(default_config()["personality"]["social_behavior"]["refuse"])

    def test_partial_personality_is_normalized_before_native_configuration(self):
        value = default_config()
        value["personality"] = {"traits": {"honesty": 0.9},
                                "social_behavior": {"deception": {"enabled": False}}}
        validated = validate_config(value)
        self.assertEqual(validated["personality"]["traits"]["honesty"], 0.9)
        self.assertIn("caution", validated["personality"]["traits"])
        self.assertIn("false_promise", validated["personality"]["social_behavior"]["deception"])
        self.assertFalse(validated["personality"]["social_behavior"]["deception"]["enabled"])
        self.assertEqual(value["personality"]["traits"], {"honesty": 0.9})

    def test_paths_anchor_to_profile_instead_of_current_directory(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            config = default_config()
            config["paths"] = {"background": "people/person.md", "memory": "records"}
            (root / "config.json").write_text(json.dumps(config))
            result = load_config(root)
            self.assertEqual(result["paths"]["background"], str(root / "people/person.md"))
            self.assertEqual(result["paths"]["memory"], str(root / "records"))

    def test_credential_values_are_not_accepted_in_files_or_errors(self):
        config = default_config()
        config["llm"]["api_key"] = "private-secret-123"
        with self.assertRaises(ConfigError) as caught:
            validate_config(config)
        self.assertNotIn("private-secret-123", str(caught.exception))

    def test_invalid_limits_actor_and_schema_are_rejected(self):
        for field, value in (("max_steps", 6), ("max_calls", True), ("max_queries", 1.5),
                             ("request_timeout", float("nan")), ("session_max_calls", 0)):
            config = default_config()
            config["limits"][field] = value
            with self.assertRaises(ConfigError):
                validate_config(config)
        for value in (-1, True, "7"):
            config = default_config()
            config["actor_id"] = value
            with self.assertRaises(ConfigError):
                validate_config(config)
        config = default_config()
        config["schema_version"] = 2
        with self.assertRaises(ConfigError):
            validate_config(config)

    def test_optional_thinking_json_modes_and_duties_are_explicit(self):
        config = default_config()
        self.assertNotIn("thinking_mode", validate_config(config)["llm"])
        self.assertEqual(validate_config(config)["duties"], {
            "allowed_tasks": [], "max_distance": 12, "item_types": [], "recipes": []})
        config["llm"].update(thinking_mode="disabled", json_mode=True)
        config["duties"]["allowed_tasks"] = ["gather", "craft"]
        config["limits"]["budget_period"] = "explicit-next-period"
        self.assertEqual(validate_config(config)["llm"]["thinking_mode"], "disabled")
        for field, value in (("thinking_mode", None), ("thinking_mode", True), ("thinking_mode", "auto"), ("json_mode", "true")):
            invalid = default_config()
            invalid["llm"][field] = value
            with self.assertRaises(ConfigError):
                validate_config(invalid)

    def test_duties_scope_defaults_preserve_old_profiles_and_reject_invalid_scope(self):
        config = default_config()
        del config["duties"]
        self.assertEqual(validate_config(config)["duties"], {
            "allowed_tasks": [], "max_distance": 12, "item_types": [], "recipes": []})
        config["duties"] = {"allowed_tasks": ["gather"], "item_types": ["rock"]}
        self.assertEqual(validate_config(config)["duties"]["max_distance"], 12)
        for field, value in (("max_distance", 0), ("max_distance", 61), ("max_distance", True),
                             ("max_distance", 2.5), ("item_types", [""]), ("item_types", ["a", "a"]),
                             ("item_types", "rock"), ("recipes", [None]), ("recipes", ["a\0b"]),
                             ("recipes", ["x" * 129]), ("unknown", [])):
            invalid = default_config()
            invalid["duties"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ConfigError):
                validate_config(invalid)
        for kinds in (["drop"], ["move", "move"], [True], "gather"):
            invalid = default_config()
            invalid["duties"]["allowed_tasks"] = kinds
            with self.assertRaises(ConfigError):
                validate_config(invalid)


if __name__ == "__main__":
    unittest.main()
