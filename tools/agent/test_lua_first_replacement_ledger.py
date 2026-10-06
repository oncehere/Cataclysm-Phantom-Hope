import copy
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator, ValidationError

from tools.agent import check_lua_first_replacement_ledger as checker
from tools.agent import generate_lua_first_replacement_ledger as generator
from tools.agent.generate_lua_first_replacement_ledger import (
    IMPLEMENTED_VERIFIED,
    INVENTORIES,
    BOUNDED_IMPLEMENTED_VERIFIED,
    TODO_CLASSIFICATIONS,
    build_ledger,
    classify_migration_todo,
    disposition,
    legacy_evidence,
    normalize_evidence,
)


class LuaFirstReplacementLedgerTest(unittest.TestCase):
    def test_coordinate_reflection_without_native_acceptance_claim(
        self,
    ):
        entry = disposition("eoc-effects", "mirror_coordinates", {})
        self.assertEqual(entry["target"], "services.coords")
        self.assertEqual(entry["status"], "bounded_implemented_unverified")
        for path in (
            "src/point.cpp",
            "src/lua_platform_bindings_coords.cpp",
            "tests/point_test.cpp",
            ("tests/lua_platform_variable_native_key_test.cpp"),
        ):
            self.assertIn(path, entry["evidence"])

    def test_location_copy_world_service_without_native_claim(
        self,
    ):
        entry = disposition("eoc-effects", "copy_location", {})
        self.assertEqual(entry["target"], "services.world")
        self.assertEqual(entry["status"], "bounded_implemented_unverified")
        self.assertIn("src/lua_platform_variables.cpp", entry["evidence"])
        self.assertIn(
            ("tests/lua_platform_variable_native_key_test.cpp"),
            entry["evidence"],
        )

    def test_location_adjust_services_without_acceptance_claim(
        self,
    ):
        entry = disposition("eoc-effects", "location_variable_adjust", {})
        self.assertEqual(entry["target"], "services.coords-and-variables")
        self.assertEqual(entry["status"], "bounded_implemented_unverified")
        self.assertIn("src/lua_platform_variables.cpp", entry["evidence"])
        self.assertIn(
            ("tests/lua_platform_variable_native_key_test.cpp"),
            entry["evidence"],
        )

    def test_engine_backed_control_flow_is_not_exempt_from_acceptance(self):
        entries = {
            (entry["inventory"], entry["selector"]): entry
            for entry in build_ledger()["entries"]
        }
        for selector in (
            "foreach",
            "run_eocs",
            "run_eoc_selector",
            "weighted_list_eocs",
        ):
            with self.subTest(selector=selector):
                entry = entries[("eoc-effects", selector)]
                self.assertEqual(
                    entry["status"], "primitive_available_unverified"
                )
                self.assertEqual(entry["verification"], "source_only")
                self.assertEqual(entry["target_kind"], "shared_service")
                self.assertIn(
                    "data/reference/json/ccb_eoc_effects.json",
                    entry["evidence"],
                )
                self.assertIn("tools/migrate_lua_first.py", entry["evidence"])
        for selector in ("and", "or", "not"):
            self.assertEqual(
                entries[("eoc-conditions", selector)]["status"],
                "reviewed_not_applicable",
            )

    def test_named_predicates_require_semantic_acceptance(self):
        entries = {
            (entry["inventory"], entry["selector"]): entry
            for entry in build_ledger()["entries"]
        }
        for inventory, selector in (
            ("eoc-effects", "set_condition"),
            ("eoc-conditions", "get_condition"),
            ("eoc-conditions", "test_eoc"),
        ):
            with self.subTest(selector=selector):
                entry = entries[(inventory, selector)]
                self.assertEqual(
                    entry["status"], "bounded_implemented_unverified"
                )
                self.assertEqual(entry["verification"], "source_only")
                self.assertEqual(
                    entry["target"], "native-lua-predicate-context"
                )
                self.assertIn("tools/migrate_lua_first.py", entry["evidence"])

    def test_mutation_actions_remain_source_only_bounded(self):
        entries = {
            (entry["inventory"], entry["selector"]): entry
            for entry in build_ledger()["entries"]
        }
        for prefix in ("u_", "npc_"):
            for operation, method in (
                ("add_trait", "replace"),
                ("lose_trait", "erase"),
                ("activate_trait", "invoke_activation"),
                ("deactivate_trait", "invoke_activation"),
            ):
                entry = entries[("eoc-effects", prefix + operation)]
                self.assertEqual(
                    entry["target"], "services.mutations." + method
                )
                self.assertEqual(
                    entry["status"], "bounded_implemented_unverified"
                )
                self.assertEqual(entry["verification"], "source_only")
                self.assertIn(
                    "tests/lua_platform_mutations_test.cpp", entry["evidence"]
                )
                self.assertIn(
                    "tools/test_lua_mutation_migration.py", entry["evidence"]
                )

    def test_schema_requires_each_todo_category_and_core_input_contract(self):
        schema_root = Path(__file__).resolve().parents[2] / "ai"
        schema_path = schema_root / "lua-first-replacement-ledger.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        generated = build_ledger()
        validator = Draft202012Validator(schema)

        self.assertEqual(list(validator.iter_errors(generated)), [])

        for category in TODO_CLASSIFICATIONS:
            duplicate = copy.deepcopy(generated)
            classifications = duplicate["migration_todo_policy"][
                "classifications"
            ]
            duplicate_index = next(
                index
                for index, entry in enumerate(classifications)
                if entry["id"] != category
            )
            classifications[duplicate_index]["id"] = category
            self.assertTrue(
                list(validator.iter_errors(duplicate)),
                category,
            )

        for category, expected in (
            ("platform_gap", False),
            ("auto_fix", True),
        ):
            mismatch = copy.deepcopy(generated)
            entry = next(
                item
                for item in mismatch["migration_todo_policy"][
                    "classifications"
                ]
                if item["id"] == category
            )
            entry["platform_core_input"] = expected
            self.assertTrue(
                list(validator.iter_errors(mismatch)),
                category,
            )

    def test_migration_todo_policy_is_orthogonal_and_conservative(self):
        policy = build_ledger()["migration_todo_policy"]
        self.assertEqual(policy["scope"], "individual_migration_todo")
        self.assertEqual(
            policy["orthogonal_to"],
            "selector_disposition_and_verification_status",
        )
        self.assertEqual(policy["unclassified"], "error")
        self.assertEqual(policy["platform_core_input"], "platform_gap")
        self.assertEqual(
            [entry["id"] for entry in policy["classifications"]],
            list(TODO_CLASSIFICATIONS),
        )
        self.assertEqual(
            [
                entry["id"]
                for entry in policy["classifications"]
                if entry["platform_core_input"]
            ],
            ["platform_gap"],
        )

    def test_migration_todo_classification_validates_all_categories(self):
        for category in TODO_CLASSIFICATIONS:
            self.assertEqual(classify_migration_todo(category), category)
        with self.assertRaisesRegex(
            ValueError, "unknown migration TODO classification"
        ):
            classify_migration_todo(None)
        with self.assertRaisesRegex(
            ValueError, "unknown migration TODO classification"
        ):
            classify_migration_todo("selector_todo")

    def test_json_promotions_remain_disabled_until_their_final_gate(self):
        self.assertEqual(IMPLEMENTED_VERIFIED, frozenset())
        self.assertEqual(BOUNDED_IMPLEMENTED_VERIFIED, frozenset())

    def test_verified_entries_require_final_gate_and_native_test_evidence(
        self,
    ):
        verified = [
            entry
            for entry in build_ledger()["entries"]
            if entry["status"]
            in ("implemented_verified", "bounded_implemented_verified")
        ]
        for entry in verified:
            self.assertEqual(entry["verification"], "final_semantic_gate")
            self.assertTrue(
                any(
                    Path(evidence).parts[0] == "tests" and
                    Path(evidence).suffix == ".cpp"
                    for evidence in entry["evidence"]
                ),
                entry,
            )

    def test_generator_uses_the_three_real_inventories(self):
        generated = build_ledger()
        self.assertEqual(
            {source["id"] for source in generated["sources"]},
            set(INVENTORIES),
        )
        self.assertTrue(
            all(source["entry_count"] > 0 for source in generated["sources"])
        )

    def test_entries_have_honest_source_only_evidence(self):
        generated = build_ledger()
        for entry in generated["entries"]:
            self.assertIn("verification", entry)
            self.assertNotIn(
                "cata" + "lua", " ".join(entry["evidence"]).lower()
            )
            self.assertNotIn(
                "ccb_" + "native_inventory", " ".join(entry["evidence"])
            )
            if entry["status"] in {
                "implemented_verified",
                "bounded_implemented_verified",
            }:
                self.assertEqual(entry["verification"], "final_semantic_gate")
            elif entry["status"] in {
                "implemented_unverified",
                "bounded_implemented_unverified",
                "primitive_available_unverified",
            }:
                self.assertEqual(entry["verification"], "source_only")

    def test_bounded_shapes_are_not_promoted_to_verified(self):
        generated = {
            (entry["inventory"], entry["selector"]): entry
            for entry in build_ledger()["entries"]
        }
        for identity in {
            ("json-object-types", "wound"),
            ("eoc-conditions", "u_has_item"),
            ("eoc-effects", "u_add_effect"),
        }:
            self.assertEqual(
                generated[identity]["status"],
                "bounded_implemented_unverified",
            )
            self.assertEqual(
                generated[identity]["verification"], "source_only"
            )

    def test_evidence_normalization_rejects_legacy_paths(self):
        evidence = normalize_evidence(
            "json-object-types",
            [
                "src/" + "cata" + "lua_runtime.cpp",
                "data/lua/types/ccb_platform_v1.d.lua",
                "tests/lua_platform_test.cpp",
                "tools/migrate_lua_first.py",
            ],
        )
        self.assertNotIn("src/" + "cata" + "lua_runtime.cpp", evidence)
        self.assertIn(
            "src/lua_platform_runtime.cpp",
            normalize_evidence(
                "json-object-types", ["src/lua_platform_runtime.cpp"]
            ),
        )
        self.assertIn(
            "data/reference/json/ccb_json_object_types.json",
            evidence,
        )

    def test_legacy_evidence_points_to_the_real_inventory(self):
        self.assertEqual(
            legacy_evidence("eoc-effects", {}),
            ["data/reference/json/ccb_eoc_effects.json"],
        )


class OnDemandReplacementLedgerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = build_ledger()

    def test_check_validates_current_inputs_without_writing(self):
        with (
            mock.patch.object(Path, "write_text", side_effect=AssertionError),
            mock.patch.object(
                checker, "build_ledger", wraps=build_ledger,
            ) as build,
        ):
            self.assertEqual(checker.check(), self.ledger["summary"])
        build.assert_called_once_with()

    def test_missing_extra_and_duplicate_selectors_fail(self):
        for mutation in ("missing", "extra", "duplicate"):
            with self.subTest(mutation=mutation):
                ledger = copy.deepcopy(self.ledger)
                if mutation == "missing":
                    ledger["entries"].pop()
                else:
                    entry = copy.deepcopy(ledger["entries"][0])
                    if mutation == "extra":
                        entry["selector"] = "unregistered_selector_fixture"
                    ledger["entries"].append(entry)
                with self.assertRaisesRegex(
                    RuntimeError, "coverage differs|duplicate selectors"
                ):
                    checker.validate_ledger(ledger)

    def test_source_identity_fingerprint_and_count_are_checked(self):
        for field, value, error in (
            ("path", "data/reference/json/ccb_eoc_effects.json",
             "source contract"),
            ("selector", "key", "source contract"),
            ("source_fingerprint", "sha256:" + "0" * 64, "fingerprint"),
            ("entry_count", 1, "count changed"),
        ):
            with self.subTest(field=field):
                ledger = copy.deepcopy(self.ledger)
                source = next(source for source in ledger["sources"]
                              if source["id"] == "json-object-types")
                source[field] = value
                with self.assertRaisesRegex(RuntimeError, error):
                    checker.validate_ledger(ledger)

    def test_missing_inventory_and_invalid_verification_fail_schema(self):
        ledger = copy.deepcopy(self.ledger)
        ledger["sources"].pop()
        with self.assertRaises(ValidationError):
            checker.validate_ledger(ledger)
        ledger = copy.deepcopy(self.ledger)
        entry = next(entry for entry in ledger["entries"]
                     if entry["status"] == "implemented_verified")
        entry["verification"] = "source_only"
        with self.assertRaises(ValidationError):
            checker.validate_ledger(ledger)

    def test_all_required_evidence_kinds_remain_required(self):
        for prefix in (
            "src/lua_platform", "data/lua/types/", "tests/",
            "tools/migrate_lua_first.py",
        ):
            with self.subTest(prefix=prefix):
                ledger = copy.deepcopy(self.ledger)
                entry = next(entry for entry in ledger["entries"]
                             if entry["status"] == "implemented_verified")
                entry["evidence"] = [path for path in entry["evidence"]
                                     if not path.startswith(prefix)]
                with self.assertRaisesRegex(
                    RuntimeError, "lacks Platform source"
                ):
                    checker.validate_ledger(ledger)

    def test_missing_evidence_file_is_not_accepted_by_prefix(self):
        ledger = copy.deepcopy(self.ledger)
        entry = next(entry for entry in ledger["entries"]
                     if entry["status"] == "implemented_verified")
        entry["evidence"].append(
            "src/lua_platform_missing_evidence_fixture.cpp"
        )
        with self.assertRaisesRegex(
            RuntimeError, "evidence path does not exist"
        ):
            checker.validate_ledger(ledger)

    def test_legacy_dependency_and_stale_summary_fail(self):
        ledger = copy.deepcopy(self.ledger)
        entry = next(entry for entry in ledger["entries"]
                     if entry["status"] == "implemented_verified")
        entry["legacy_dependency"] = "public_legacy"
        with self.assertRaisesRegex(RuntimeError, "unresolved public legacy"):
            checker.validate_ledger(ledger)
        ledger = copy.deepcopy(self.ledger)
        ledger["summary"]["total"] += 1
        with self.assertRaisesRegex(RuntimeError, "summary is stale"):
            checker.validate_ledger(ledger)

    def test_default_export_goes_to_stdout_without_writing(self):
        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            mock.patch.object(Path, "write_text", side_effect=AssertionError),
        ):
            self.assertEqual(generator.main([]), 0)
        self.assertEqual(output.getvalue(), generator.render(self.ledger))

    def test_check_rejects_invalid_generated_coverage_without_an_export(self):
        ledger = copy.deepcopy(self.ledger)
        ledger["entries"].pop()
        with (
            mock.patch.object(generator, "build_ledger", return_value=ledger),
            mock.patch.object(Path, "write_text", side_effect=AssertionError),
        ):
            with self.assertRaisesRegex(RuntimeError, "coverage differs"):
                generator.main(["--check"])

    def test_explicit_export_and_staleness_check_do_not_repair_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "ledger.yml"
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(
                    generator.main(["--check", "--output", str(output)]), 1
                )
            self.assertFalse(output.exists())
            self.assertEqual(generator.main(["--output", str(output)]), 0)
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                generator.render(self.ledger),
            )
            self.assertEqual(
                generator.main(["--check", "--output", str(output)]), 0
            )
            output.write_text("stale export\n", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(
                    generator.main(["--check", "--output", str(output)]), 1
                )
            self.assertEqual(
                output.read_text(encoding="utf-8"), "stale export\n"
            )

    def test_script_check_works_outside_repository_without_an_export(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(Path(generator.__file__).resolve()),
                 "--check"],
                cwd=directory, capture_output=True, text=True, check=False,
            )
            self.assertEqual(
                result.returncode, 0, result.stdout + result.stderr
            )
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
