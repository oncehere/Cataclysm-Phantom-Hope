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


if __name__ == "__main__":
    unittest.main()
