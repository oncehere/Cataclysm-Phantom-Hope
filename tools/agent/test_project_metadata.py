import copy
import unittest
from unittest import mock

import yaml

from check_project_metadata import (
    ROOT,
    load_yaml as load_project_yaml,
    tracked_paths,
    validate_context,
    validate_documentation_registry,
    validate_inventory,
    validate_lua_first_roadmap,
    validate_repository_settings,
)
from check_lua_first_replacement_ledger import check as check_lua_first_replacement_ledger


class ProjectMetadataTest(unittest.TestCase):
    @mock.patch("check_project_metadata.subprocess.run")
    def test_path_discovery_reads_only_the_git_index(self, run):
        run.return_value.stdout = b"AGENTS.md\0tools/AGENTS.md\0"

        self.assertEqual(tracked_paths(), ["AGENTS.md", "tools/AGENTS.md"])
        command = run.call_args.args[0]
        self.assertIn("--cached", command)
        self.assertNotIn("--others", command)

    def test_context_is_valid(self):
        validate_context()

    def test_required_documentation_rejects_historical_page(self):
        original = load_project_yaml
        impact_path = ROOT / "ai/docs-impact.yml"
        impact = copy.deepcopy(original(impact_path))
        lua = next(item for item in impact["entries"]
                   if item["id"] == "lua-public-contract")
        lua["documentation_readiness"]["documents"][0]["path"] = (
            "doc/FREQUENTLY_MADE_SUGGESTIONS.md"
        )

        def modified(path):
            return impact if path == impact_path else original(path)

        with mock.patch("check_project_metadata.check_lua_first_replacement_ledger"), \
             mock.patch("check_project_metadata.load_yaml", side_effect=modified):
            with self.assertRaisesRegex(ValueError, "not current"):
                validate_context()

    def test_required_documentation_rejects_wrong_stable_id(self):
        original = load_project_yaml
        impact_path = ROOT / "ai/docs-impact.yml"
        impact = copy.deepcopy(original(impact_path))
        lua = next(item for item in impact["entries"]
                   if item["id"] == "lua-public-contract")
        lua["documentation_readiness"]["documents"][0]["id"] = "wrong.id"

        def modified(path):
            return impact if path == impact_path else original(path)

        with mock.patch("check_project_metadata.check_lua_first_replacement_ledger"), \
             mock.patch("check_project_metadata.load_yaml", side_effect=modified):
            with self.assertRaisesRegex(ValueError, "not current"):
                validate_context()

    def test_repository_records_cph_main_as_active(self):
        path = ROOT / "ai/repository-settings.target.yml"
        settings = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(settings["audit"]["repository"]["default_branch"], "main")
        self.assertTrue(settings["audit"]["repository"]["main_protected"])
        self.assertEqual(settings["entries"][0]["observed_enforcement"], "active")
        self.assertTrue(settings["entries"][0]["operational"])
        validate_repository_settings(settings)

    def test_repository_target_rejects_unproved_operation(self):
        path = ROOT / "ai/repository-settings.target.yml"
        settings = yaml.safe_load(path.read_text(encoding="utf-8"))
        settings = copy.deepcopy(settings)
        settings["entries"][0]["post_activation_probe_verified"] = False
        settings["entries"][0]["operational"] = True

        with self.assertRaisesRegex(ValueError, "operational"):
            validate_repository_settings(settings)

    def test_inventory_is_valid(self):
        validate_inventory()

    def test_lua_first_roadmap_is_valid(self):
        validate_lua_first_roadmap()

    def test_lua_first_replacement_ledger_is_exact(self):
        result = check_lua_first_replacement_ledger()
        self.assertEqual(result["total"], 776)

    def test_lua_first_roadmap_rejects_dependency_cycles(self):
        path = ROOT / "ai/lua-first-roadmap.yml"
        roadmap = yaml.safe_load(path.read_text(encoding="utf-8"))
        roadmap = copy.deepcopy(roadmap)
        roadmap["milestones"][0]["depends_on"] = [
            roadmap["milestones"][-1]["id"]
        ]

        with self.assertRaisesRegex(ValueError, "cycle"):
            validate_lua_first_roadmap(roadmap)

    def test_implemented_lua_first_capability_cannot_require_public_legacy(self):
        path = ROOT / "ai/lua-first-roadmap.yml"
        roadmap = yaml.safe_load(path.read_text(encoding="utf-8"))
        roadmap = copy.deepcopy(roadmap)
        roadmap["capabilities"][0]["status"] = "source_complete_unverified"
        roadmap["capabilities"][0]["legacy_dependency"] = "public_legacy"

        with self.assertRaisesRegex(ValueError, "public legacy"):
            validate_lua_first_roadmap(roadmap)

    def test_documentation_registry_is_valid(self):
        validate_documentation_registry()


if __name__ == "__main__":
    unittest.main()
