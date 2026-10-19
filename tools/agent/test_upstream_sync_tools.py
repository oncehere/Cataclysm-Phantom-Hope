import csv
import importlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lang"))


class UpstreamTranslationExtractionTests(unittest.TestCase):
    def extract(self, module_name, function_name, payload):
        module = importlib.import_module(
            "string_extractor.parsers." + module_name)
        with patch.object(module, "write_text") as writer:
            getattr(module, function_name)(payload, "fixture.json")
        return [call.args[0] for call in writer.call_args_list]

    def test_extended_item_variants_are_translatable(self):
        payload = {"name": "coat", "extend": {"variants": [
            {"name": "striped coat", "description": "Bright stripes."}
        ]}}
        texts = self.extract("generic", "parse_subtypes", payload)
        self.assertIn("striped coat", texts)
        self.assertIn("Bright stripes.", texts)

    def test_spell_failure_messages_are_translatable(self):
        payload = {"name": "spell",
                   "caster_condition_fail_message": "Too tired.",
                   "target_condition_fail_message": "Target is immune."}
        texts = self.extract("spell", "parse_spell", payload)
        self.assertIn("Too tired.", texts)
        self.assertIn("Target is immune.", texts)

    def test_rejection_and_technique_effect_messages_are_translatable(self):
        texts = self.extract("shop_whitelist", "parse_shopkeeper_whitelist",
                             {"message": "No trading here.", "entries": []})
        self.assertIn("No trading here.", texts)
        payload = {"name": "jab",
                   "tech_effects": [{"message": "Off balance!"}]}
        texts = self.extract("technique", "parse_technique", payload)
        self.assertIn("Off balance!", texts)


class UpstreamReleaseToolsTests(unittest.TestCase):
    def test_macos_alias_columns_preserve_market_share(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            files = []
            for name, headers, values in [
                ("aliases", ["macOS Sequoia", "macOS Sequoia.0",
                             "macOS Catalina", "macOS 19"],
                 [20, 30, 10, 5]),
                ("canonical", ["macOS Sequoia", "macOS Catalina"], [50, 15]),
            ]:
                filename = directory / (name + ".csv")
                with filename.open("w") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(["Date", *headers])
                    writer.writerow(["2026-09", *values])
                command = [sys.executable,
                           str(ROOT / "tools/macos-market-share.py"),
                           str(filename)]
                result = subprocess.run(command, check=True,
                                        capture_output=True, text=True)
                files.append(result.stdout)
            self.assertEqual(files[0], files[1])



if __name__ == "__main__":
    unittest.main()
