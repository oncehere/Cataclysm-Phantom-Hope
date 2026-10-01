import copy
import unittest
from pathlib import Path
from unittest import mock

import generate_documentation_registry as registry


class DocumentationRegistryTest(unittest.TestCase):
    def test_companion_manuals_current_and_imported_evidence_historical(self):
        current = registry.classify("companion/README.md", {})
        self.assertEqual(current["stable_document_id"], "cph.companion")
        self.assertTrue(current["include_in_ai_index"])
        for path in ("companion/docs/architecture.md",
                     "companion/docs/install.md"):
            self.assertEqual(registry.classify(path, {})["status"], "active")
        historical = registry.classify(
            "companion/docs/evidence/v0.1.1/gcc-helper-fix-20261001.md", {},
        )
        self.assertEqual(historical["status"], "historical")
        self.assertFalse(historical["include_in_ai_index"])

    def test_origins_preserve_ids_and_attribution_without_git_history(self):
        with mock.patch.object(
            registry.subprocess, "run",
            side_effect=AssertionError("historical Git read"),
        ):
            origins = registry.load_origins()
        self.assertEqual(origins["CONTRIBUTING.md"]["stable_document_id"],
                         "governance.contributing")
        self.assertIn("David Seguin",
                      origins["CONTRIBUTING.md"]["contributors"])
        self.assertEqual(origins["src/lua/LICENSE.md"]["license"], "MIT")

    def test_origins_reject_duplicate_ids_and_cache_paths(self):
        data = {
            "schema_version": 1, "kind": "document_origins",
            "source_commit": "1" * 40,
            "source_inventory": (
                "https://github.com/owner/repo/blob/source/inventory.yml"
            ),
            "documents": [{"path": "doc/example.md",
                           "stable_document_id": "example",
                           "license": "MIT", "contributors": ["Author"]}],
        }
        cases = []
        duplicate = copy.deepcopy(data)
        duplicate["documents"].append(
            dict(duplicate["documents"][0], path="doc/other.md")
        )
        cases.append((duplicate, "duplicate"))
        forbidden = copy.deepcopy(data)
        forbidden["documents"][0]["path"] = "obj-lua/never-read.md"
        cases.append((forbidden, "invalid document origin path"))
        for content, message in cases:
            with self.subTest(message=message), mock.patch.object(
                registry.yaml, "safe_load", return_value=content,
            ):
                with self.assertRaisesRegex(ValueError, message):
                    registry.load_origins()

    def test_generated_declarations_match_paths_and_reject_ambiguity(self):
        declarations = [{"paths": ["data/reference/json/*.json"],
                         "generated_by": "python3 generator.py"}]
        path = "data/reference/json/test.json"
        self.assertEqual(registry.generated_by(path, declarations),
                         "python3 generator.py")
        self.assertIsNone(registry.generated_by("doc/manual.md", declarations))
        declarations.append({"paths": ["data/reference/json/test.json"],
                             "generated_by": "python3 another.py"})
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            registry.generated_by(path, declarations)

    @mock.patch.object(registry.subprocess, "run")
    def test_tracked_discovery_reads_only_the_git_index(self, run):
        run.return_value.stdout = b"AGENTS.md\0doc/example.md\0"

        self.assertEqual(
            registry.tracked_paths(),
            ["AGENTS.md", "doc/example.md"],
        )
        command = run.call_args.args[0]
        self.assertEqual(command[:3], ["git", "ls-files", "-z"])
        self.assertIn("--cached", command)
        self.assertNotIn("--others", command)

    def test_registry_covers_every_selected_tracked_path(self):
        data = registry.build_registry("0" * 40)
        expected = {
            path
            for path in registry.tracked_paths()
            if registry.is_documentation_path(path)
        }
        actual = {entry["path"] for entry in data["entries"]}

        self.assertEqual(expected, actual)
        self.assertEqual(data["entry_count"], len(actual))
        self.assertFalse(
            any("obj-lua" in Path(path).parts for path in actual)
        )

    def test_generated_and_third_party_boundaries_are_explicit(self):
        legacy = registry.load_origins()
        generated = registry.classify(
            "data/lua/reference/ccb_platform_native_inventory.json",
            legacy,
        )
        third_party = registry.classify(
            "src/third-party/zstd/README.md",
            legacy,
        )

        self.assertTrue(generated["generated"])
        self.assertTrue(generated["generated_by"])
        self.assertEqual(generated["status"], "generated")
        self.assertEqual(
            registry.classify(
                "ai/documentation-registry.yml", legacy,
            )["status"],
            "generated",
        )
        self.assertFalse(third_party["include_in_ai_index"])
        self.assertEqual(third_party["status"], "third_party")

    def test_current_platform_docs_override_stale_migration_metadata(self):
        legacy = registry.load_origins()
        current = registry.classify("data/lua/README.md", legacy)
        self.assertEqual(current["status"], "active")
        self.assertEqual(
            current["stable_document_id"],
            "lua.platform.overview",
        )
        self.assertIn(
            "architecture.lua-first-platform",
            current["ccb_docs_ids"],
        )

    def test_cph_project_and_technical_docs_are_current(self):
        legacy = registry.load_origins()
        spec = registry.classify("docs/project/execution-spec.md", legacy)
        technical = registry.classify("doc/JSON/JSON_INFO.md", legacy)
        self.assertEqual((spec["status"], spec["authority"]),
                         ("active", "governance_contract"))
        self.assertEqual(technical["status"], "active")
        self.assertEqual(technical["stable_document_id"], "json.object-types")
        self.assertTrue(technical["include_in_ai_index"])
        for path in ("docs/README.md", "tools/agent/README.md"):
            entry = registry.classify(path, legacy)
            self.assertEqual(entry["status"], "active")
            self.assertTrue(entry["include_in_ai_index"])
        for path in ("AGENTS.md", "tools/AGENTS.md", ".github/AGENTS.md"):
            self.assertEqual(registry.classify(path, legacy)["category"],
                             "agent_instruction")

    def test_inherited_design_and_ccb_audit_are_history(self):
        legacy = registry.load_origins()
        for path in (
            "doc/development_process.md",
            "doc/design-balance-lore/design-doc.md",
            "doc/migration/markdown-inventory.yml",
            "doc/FREQUENTLY_MADE_SUGGESTIONS.md",
            "doc/GUN_NAMING_AND_INCLUSION.md",
            "tools/llama/README.md",
            ".deepcode/plans/inherited.md",
            "ai/history/ccb-repository-settings-2026-08-02.yml",
        ):
            item = registry.classify(path, legacy)
            self.assertEqual(item["status"], "historical", path)
            self.assertFalse(item["include_in_ai_index"], path)

    def test_bundled_mod_and_lua_vendoring_boundaries(self):
        legacy = registry.load_origins()
        self.assertEqual(
            registry.classify("src/lua/README.md", legacy)["status"], "active"
        )
        self.assertEqual(
            registry.classify("src/lua/LICENSE.md", legacy)["status"],
            "third_party",
        )
        self.assertEqual(
            registry.classify("data/mods/Example/README.md", legacy)["status"],
            "third_party",
        )
        self.assertEqual(
            registry.classify(
                "data/mods/Migrated_Core/README.md", legacy,
            )["status"],
            "generated",
        )
        self.assertEqual(
            registry.classify(
                "data/mods/Lua_First_Example/README.md", legacy,
            )["status"],
            "active",
        )

    def test_retired_platform_docs_are_historical_and_not_indexed(self):
        legacy = registry.load_origins()
        retired = registry.classify(
            "data/lua/reference/ccb_public_api_" + "v" + "5.json",
            legacy,
        )
        self.assertEqual(retired["status"], "historical")
        self.assertFalse(retired["source_of_truth"])
        self.assertFalse(retired["include_in_ai_index"])

    def test_ccb_docs_ids_remain_historical_provenance(self):
        legacy = {
            "doc/merged.md": {
                "stable_document_id": "legacy.doc-merged",
                "ccb_docs_id": "maintenance.releases",
            },
            "doc/direct.md": {
                "stable_document_id": "cpp.activities",
                "ccb_docs_id": "cpp.activities",
            },
        }

        merged = registry.classify("doc/merged.md", legacy)
        direct = registry.classify("doc/direct.md", legacy)

        self.assertEqual(merged["ccb_docs_ids"], ["maintenance.releases"])
        self.assertEqual(direct["ccb_docs_ids"], ["cpp.activities"])
        self.assertEqual(merged["status"], "active")


if __name__ == "__main__":
    unittest.main()
