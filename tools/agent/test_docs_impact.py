from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import check_docs_impact as checker

from check_docs_impact import (
    documentation_field_warnings,
    impacts,
    load_rules,
    report,
    validate_pr_body,
)


def complete_body(document_id: str = "lua.platform.overview",
                  document_path: str = "data/lua/README.md") -> str:
    return f"""#### Responsible human
@maintainer
#### Documentation impact
Refresh the Lua-first Platform contract reference after the source change.
#### Repository documentation impact
Update `{document_path}` in the same repository change.
#### Affected documentation IDs
{document_id}
#### Generated reference impact
Regenerate and verify the checked-in Lua contract inventory.
"""


class DocsImpactTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = [
            {
                "id": "governance",
                "enforcement": "advisory",
                "patterns": ["CONTRIBUTING.md"],
                "documentation_ids": ["contributing.overview"],
                "generated_reference_impact": False,
                "required_check_ids": [],
            },
            {
                "id": "lua",
                "enforcement": "required",
                "patterns": ["data/lua/*", "src/lua_platform_*"],
                "documentation_ids": ["lua.platform.overview"],
                "generated_reference_impact": True,
                "required_check_ids": ["agent-context", "lua-contract"],
                "documentation_readiness": {
                    "documents": [{"id": "lua.platform.overview",
                                   "path": "data/lua/README.md"}],
                },
            },
        ]

    def test_matches_only_relevant_paths(self) -> None:
        result = impacts(
            [
                "src/game.cpp",
                "data/lua/types/ccb_platform_v1.d.lua",
            ],
            self.rules,
        )
        self.assertEqual(
            ["data/lua/types/ccb_platform_v1.d.lua"],
            result[0]["matched_files"],
        )
        self.assertEqual(result[0]["enforcement"], "required")

    def test_unrelated_path_has_no_impact(self) -> None:
        result = impacts(["src/game.cpp"], self.rules)
        self.assertEqual(result, [])
        self.assertEqual(validate_pr_body(complete_body(), result), [])

    def test_advisory_mapping_does_not_block_fields(self) -> None:
        result = impacts(["CONTRIBUTING.md"], self.rules)
        body = "#### Responsible human\n@maintainer\n"
        self.assertEqual(validate_pr_body(body, result), [])
        self.assertEqual(len(documentation_field_warnings(body, result)), 4)

    def test_required_mapping_blocks_missing_fields(self) -> None:
        result = impacts(["data/lua/types/ccb_platform_v1.d.lua"], self.rules)
        body = "#### Responsible human\n@maintainer\n"
        errors = validate_pr_body(body, result)
        self.assertEqual(len(errors), 4)
        self.assertTrue(
            all("missing required PR field" in error for error in errors)
        )
        self.assertEqual(documentation_field_warnings(body, result), [])

    def test_required_mapping_blocks_template_placeholders(self) -> None:
        result = impacts(["data/lua/types/ccb_platform_v1.d.lua"], self.rules)
        body = """#### Responsible human
@maintainer
#### Documentation impact
None
#### Repository documentation impact
N/A
#### Affected documentation IDs
TBD
#### Generated reference impact
无
"""
        errors = validate_pr_body(body, result)
        self.assertEqual(len(errors), 4)
        self.assertTrue(all("placeholder" in error for error in errors))

    def test_required_mapping_accepts_complete_fields(self) -> None:
        result = impacts([
            "data/lua/types/ccb_platform_v1.d.lua", "data/lua/README.md"
        ], self.rules)
        self.assertEqual(validate_pr_body(complete_body(), result), [])

    def test_diff_statuses_preserve_add_modify_and_delete(self) -> None:
        output = (b"M\0data/lua/types/ccb_platform_v1.d.lua\0"
                  b"A\0data/lua/README.md\0"
                  b"D\0doc/JSON/JSON_INFO.md\0")
        with mock.patch.object(checker.subprocess, "run") as run:
            run.return_value.stdout = output
            self.assertEqual(checker.changed_file_statuses("base", "head"), {
                "data/lua/types/ccb_platform_v1.d.lua": "M",
                "data/lua/README.md": "A",
                "doc/JSON/JSON_INFO.md": "D",
            })
        self.assertEqual(run.call_args.args[0], [
            "git", "diff", "--name-status", "--no-renames", "-z",
            "base", "head", "--",
        ])

    def test_cli_diff_rejects_deleted_document_and_accepts_added_or_modified(self) -> None:
        source = "data/lua/types/ccb_platform_v1.d.lua"
        document = "data/lua/README.md"
        for status, expected in (("D", 1), ("A", 0), ("M", 0)):
            with self.subTest(document_status=status), \
                 mock.patch.object(checker, "changed_file_statuses",
                                   return_value={source: "M", document: status}), \
                 mock.patch.object(checker, "load_rules", return_value=self.rules), \
                 mock.patch("sys.argv", ["check_docs_impact.py", "--base",
                                         "base", "--head", "head",
                                         "--check-pr-body"]), \
                 mock.patch.dict(os.environ, {"PR_BODY": complete_body()},
                                 clear=True), \
                 redirect_stdout(io.StringIO()), \
                 redirect_stderr(io.StringIO()):
                self.assertEqual(checker.main(), expected)

    def test_cli_changed_file_requires_document_to_remain(self) -> None:
        document = "data/lua/README.md"
        argv = ["check_docs_impact.py", "--changed-file",
                "data/lua/types/ccb_platform_v1.d.lua", "--changed-file",
                document, "--check-pr-body"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / document
            candidate.parent.mkdir(parents=True)
            candidate.write_text("Updated reference\n", encoding="utf-8")
            with mock.patch.object(checker, "ROOT", root), \
                 mock.patch.object(checker, "load_rules", return_value=self.rules), \
                 mock.patch("sys.argv", argv), \
                 mock.patch.dict(os.environ, {"PR_BODY": complete_body()},
                                 clear=True), \
                 redirect_stdout(io.StringIO()), \
                 redirect_stderr(io.StringIO()):
                self.assertEqual(checker.main(), 0)
                candidate.unlink()
                self.assertEqual(checker.main(), 1)

    def test_cli_diff_deletion_overrides_changed_file_hint(self) -> None:
        document = "data/lua/README.md"
        source = "data/lua/types/ccb_platform_v1.d.lua"
        with mock.patch.object(checker, "changed_file_statuses",
                               return_value={source: "M", document: "D"}), \
             mock.patch.object(checker, "load_rules", return_value=self.rules), \
             mock.patch("sys.argv", ["check_docs_impact.py", "--base", "base",
                                     "--head", "head", "--changed-file",
                                     document, "--check-pr-body"]), \
             mock.patch.dict(os.environ, {"PR_BODY": complete_body()},
                             clear=True), \
             redirect_stdout(io.StringIO()), \
             redirect_stderr(io.StringIO()):
            self.assertEqual(checker.main(), 1)

    def test_required_mapping_needs_document_change_in_same_pr(self) -> None:
        result = impacts(["data/lua/types/ccb_platform_v1.d.lua"], self.rules)
        errors = validate_pr_body(complete_body(), result)
        self.assertTrue(any("same PR" in error for error in errors))

    def test_required_mapping_rejects_unmapped_repository_path(self) -> None:
        result = impacts(["data/lua/types/ccb_platform_v1.d.lua"], self.rules)
        body = complete_body(document_path="doc/JSON/JSON_INFO.md")
        errors = validate_pr_body(body, result)
        self.assertTrue(any("in-repository path" in error for error in errors))

    def test_required_mapping_rejects_unmapped_document_id(self) -> None:
        result = impacts(["data/lua/types/ccb_platform_v1.d.lua"], self.rules)
        errors = validate_pr_body(complete_body("unrelated.page"), result)
        self.assertTrue(any("mapped ID" in error for error in errors))

    def test_each_required_mapping_needs_an_affected_id(self) -> None:
        rules = self.rules + [
            {
                "id": "eoc",
                "enforcement": "required",
                "patterns": ["tools/contracts.py"],
                "documentation_ids": ["eoc.reference"],
                "generated_reference_impact": True,
                "required_check_ids": ["json-eoc-contract"],
                "documentation_readiness": {
                    "documents": [{"id": "eoc.reference",
                                   "path": "doc/JSON/EFFECT_ON_CONDITION.md"}],
                },
            }
        ]
        rules[1] = {**rules[1], "patterns": ["tools/contracts.py"]}
        result = impacts([
            "tools/contracts.py", "data/lua/README.md",
            "doc/JSON/EFFECT_ON_CONDITION.md",
        ], rules)
        errors = validate_pr_body(complete_body(), result)
        self.assertEqual(len(errors), 1)
        self.assertIn("eoc", errors[0])
        body = complete_body(
            "lua.platform.overview, eoc.reference",
            "data/lua/README.md, doc/JSON/EFFECT_ON_CONDITION.md",
        )
        self.assertEqual(validate_pr_body(body, result), [])

    def test_responsible_human_cannot_be_placeholder_or_bot(self) -> None:
        self.assertTrue(
            validate_pr_body("#### Responsible human\n@username\n")
        )
        self.assertTrue(
            validate_pr_body("#### Responsible human\n@automation[bot]\n")
        )
        self.assertTrue(validate_pr_body("#### Responsible human\nNone\n"))

    def test_report_names_enforcement_and_checks(self) -> None:
        result = impacts(["data/lua/types/ccb_platform_v1.d.lua"], self.rules)
        output = report(result)
        self.assertIn("[required] lua", output)
        self.assertIn("agent-context, lua-contract", output)

    def test_staged_map_requires_entry_enforcement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "docs-impact.yml"
            path.write_text(
                """schema_version: 1
kind: docs_impact
enforcement: staged
entries:
  - id: incomplete
    patterns: [README.md]
""",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError, "must declare enforcement"
            ):
                load_rules(path)

    def test_ordinary_json_repository_rules_are_advisory(self) -> None:
        rules = load_rules()
        result = impacts(
            ["data/mods/TEST_DATA/modinfo.json", "src/savegame_json.cpp"],
            rules,
        )
        self.assertTrue(result)
        self.assertEqual(
            {item["enforcement"] for item in result}, {"advisory"}
        )

    def test_repository_rules_require_json_eoc_contracts(self) -> None:
        result = impacts(
            ["tools/json_api/generate_contracts.py"], load_rules()
        )
        required = {
            item["id"]
            for item in result
            if item["enforcement"] == "required"
        }
        self.assertEqual(
            required, {"json-public-contract", "eoc-public-contract"}
        )


if __name__ == "__main__":
    unittest.main()
