import unittest
from pathlib import Path
from unittest import mock

import generate_documentation_registry as registry


class DocumentationRegistryTest(unittest.TestCase):
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
        legacy = registry.load_inventory()
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
            registry.classify("ai/documentation-registry.yml", legacy)["status"],
            "generated",
        )
        self.assertFalse(third_party["include_in_ai_index"])
        self.assertEqual(third_party["status"], "third_party")

    def test_current_platform_docs_override_stale_migration_metadata(self):
        legacy = registry.load_inventory()
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
        legacy = registry.load_inventory()
        spec = registry.classify("docs/project/execution-spec.md", legacy)
        technical = registry.classify("doc/JSON/JSON_INFO.md", legacy)
        self.assertEqual((spec["status"], spec["authority"]),
                         ("active", "governance_contract"))
        self.assertEqual(technical["status"], "active")
        self.assertEqual(technical["stable_document_id"], "json.object-types")
        self.assertTrue(technical["include_in_ai_index"])
        for path in ("AGENTS.md", "tools/AGENTS.md", ".github/AGENTS.md"):
            self.assertEqual(registry.classify(path, legacy)["category"],
                             "agent_instruction")

    def test_inherited_design_and_ccb_audit_are_history(self):
        legacy = registry.load_inventory()
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
        legacy = registry.load_inventory()
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
            registry.classify("data/mods/Migrated_Core/README.md", legacy)["status"],
            "generated",
        )
        self.assertEqual(
            registry.classify("data/mods/Lua_First_Example/README.md", legacy)["status"],
            "active",
        )

    def test_retired_platform_docs_are_historical_and_not_indexed(self):
        legacy = registry.load_inventory()
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
                "action": "merge_into",
                "migration_status": "stubbed",
                "stable_document_id": "legacy.doc-merged",
                "merge_target": "maintenance.releases",
                "include_in_ai_index": True,
            },
            "doc/direct.md": {
                "action": "migrate_rewrite",
                "migration_status": "stubbed",
                "stable_document_id": "cpp.activities",
                "merge_target": None,
                "include_in_ai_index": True,
            },
        }

        merged = registry.classify("doc/merged.md", legacy)
        direct = registry.classify("doc/direct.md", legacy)

        self.assertEqual(merged["ccb_docs_ids"], ["maintenance.releases"])
        self.assertEqual(direct["ccb_docs_ids"], ["cpp.activities"])
        self.assertEqual(merged["status"], "active")


if __name__ == "__main__":
    unittest.main()
