import copy
import unittest
from unittest import mock

import yaml

from check_project_metadata import (
    ROOT,
    load_yaml as load_project_yaml,
    tracked_paths,
    validate_context,
    validate_lua_first_roadmap,
)


class ProjectMetadataTest(unittest.TestCase):
    @mock.patch("check_project_metadata.subprocess.run")
    def test_path_discovery_reads_only_the_git_index(self, run):
        run.return_value.stdout = b"AGENTS.md\0tools/AGENTS.md\0"

        self.assertEqual(tracked_paths(), ["AGENTS.md", "tools/AGENTS.md"])
        command = run.call_args.args[0]
        self.assertIn("--cached", command)
        self.assertNotIn("--others", command)

    def test_routes_reject_unresolvable_document_ids(self):
        original = load_project_yaml
        path_to_change = ROOT / "ai/task-router.yml"
        for identifier in (
            "repo.missing-document",
            "repo.doc-frequently-made-suggestions-md",
            "repo.data-lua-reference-ccb-platform-api-v1-json",
        ):
            document = copy.deepcopy(original(path_to_change))
            document["entries"][0]["documentation_ids"] = [identifier]

            def modified(path):
                return document if path == path_to_change else original(path)

            with self.subTest(identifier=identifier), \
                 mock.patch("check_project_metadata.check_lua_first_replacement_ledger"), \
                 mock.patch("check_project_metadata.load_yaml", side_effect=modified):
                with self.assertRaisesRegex(ValueError, "documentation ID"):
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


if __name__ == "__main__":
    unittest.main()
