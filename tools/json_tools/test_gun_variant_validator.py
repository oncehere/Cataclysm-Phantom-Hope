import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch


MODULE = pathlib.Path(__file__).with_name("gun_variant_validator.py")
with patch.object(sys, "argv", [str(MODULE), "."]):
    spec = importlib.util.spec_from_file_location("gun_variant_validator", MODULE)
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)


def gun(modes):
    return {
        "id": "test_gun",
        "modes": modes,
        "pocket_data": [{"pocket_type": "MAGAZINE", "ammo_restriction": {"9mm": 10}}],
    }


class GunModeValidationTest(unittest.TestCase):
    def test_mixed_mode_values_are_sorted_without_conflating_types(self):
        data = gun([["EXPLICIT", "auto-rpm", "750"], ["DEFAULT", "semi-auto", 1],
                    ["AUTO", "auto", 2], ["OTHER", "auto-rpm", "2"]])
        self.assertTrue(validator.simplify_gun_data(data))
        self.assertEqual(data["modes"], [1, 2, "2", "750"])

    def test_legacy_default_and_only_integer_modes_are_unchanged(self):
        data = gun([["BURST", "burst", 3], ["DEFAULT", "semi-auto", 1]])
        validator.simplify_gun_data(data)
        self.assertEqual(data["modes"], [1, 3])
        data = gun([])
        del data["modes"]
        validator.simplify_gun_data(data)
        self.assertEqual(data["modes"], [1])


if __name__ == "__main__":
    unittest.main()
