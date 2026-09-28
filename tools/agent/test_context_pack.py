from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "agent"))

from benchmark_context_pack import benchmark  # noqa: E402
from build_context_pack import build_pack  # noqa: E402


class ContextPackTests(unittest.TestCase):
    def test_lua_route_contains_contract_and_validation(self) -> None:
        pack = build_pack(
            "Change Lua-first Platform services",
            [],
            ["data/lua/types/ccb_platform_v1.d.lua"],
            4000,
        )
        self.assertIn("lua-api", pack["selected_routes"])
        self.assertIn("architecture.lua-first-platform", pack["documentation_ids"])
        self.assertIn("lua-contract", {entry["id"] for entry in pack["tests"]})
        self.assertIn("src/lua_platform_loader.cpp", pack["source_paths"])
        self.assertIn("src/game_io.cpp", pack["source_paths"])
        self.assertLessEqual(pack["estimated_tokens"], 4000)

    def test_untracked_and_obj_lua_paths_are_rejected(self) -> None:
        for path in ("does-not-exist.cpp", "obj-lua/cache.o"):
            with self.subTest(path=path), self.assertRaisesRegex(
                ValueError, "not tracked"
            ):
                build_pack("navigate", [], [path], 2000)

    def test_small_pack_respects_token_limit(self) -> None:
        pack = build_pack("repository navigation", [], ["AGENTS.md"], 1000)
        self.assertLessEqual(pack["estimated_tokens"], 1000)
        self.assertTrue(pack["truncated"])

    def test_routing_preserves_subsystem_validation_boundaries(self) -> None:
        cases = (
            ("Fix a workflow bug", ".github/workflows/project-ci.yml",
             {"project-python", "governance-audit"},
             {"cmake-configure", "cpp-tests", "json-load"},
             {"AGENTS.md", ".github/AGENTS.md"}),
            ("修复 Python 测试 bug 和错误", "tests/project/test_remote_workflows.py",
             {"project-python", "python-tools"},
             {"cpp-tests", "cpp-format", "json-load"},
             {"AGENTS.md", "tests/AGENTS.md"}),
            ("Fix C++ behaviour", "src/game.cpp",
             {"cpp-tests", "cpp-format"}, {"project-python", "json-load"},
             {"AGENTS.md", "src/AGENTS.md"}),
            ("Fix pure Lua Mod bug", "data/mods/Lua_First_Example/main.lua",
             {"lua-contract", "lua-mod-load", "lua-playable-mvp"},
             {"json-load", "json-eoc-contract", "cpp-tests"},
             {"AGENTS.md", "data/AGENTS.md", "data/mods/AGENTS.md"}),
            ("Fix JSON Mod bug", "data/mods/TEST_DATA/modinfo.json",
             {"json-load", "json-eoc-contract"},
             {"lua-contract", "lua-mod-load", "cpp-tests"},
             {"AGENTS.md", "data/AGENTS.md", "data/mods/AGENTS.md"}),
        )
        for task, path, required, forbidden, agents in cases:
            with self.subTest(path=path):
                pack = build_pack(task, [], [path], 8000)
                tests = {entry["id"] for entry in pack["tests"]}
                self.assertLessEqual(required, tests)
                self.assertFalse(forbidden & tests)
                self.assertLessEqual(agents, {item["path"] for item in pack["agents"]})
                self.assertNotIn("build-scripts/AGENTS.md", {
                    item["path"] for item in pack["agents"]
                })

    def test_routed_instruction_includes_ancestors_without_requested_files(self) -> None:
        pack = build_pack("", ["lua-api"], [], 8000)
        agents = [item["path"] for item in pack["agents"]]
        self.assertLess(agents.index("AGENTS.md"), agents.index("data/AGENTS.md"))
        self.assertLess(agents.index("data/AGENTS.md"), agents.index("data/lua/AGENTS.md"))

    def test_mixed_mod_changes_keep_both_validation_routes(self) -> None:
        pack = build_pack("Fix mod behaviour", [], [
            "data/mods/Lua_First_Example/main.lua", "data/mods/TEST_DATA/modinfo.json",
        ], 8000)
        self.assertLessEqual({"json-load", "lua-contract", "lua-mod-load"}, {
            entry["id"] for entry in pack["tests"]
        })

    def test_python_bug_keywords_do_not_select_native_tests(self) -> None:
        pack = build_pack("修复项目测试 bug 和错误", [], [], 8000)
        self.assertIn("project-tooling", pack["selected_routes"])
        self.assertNotIn("cpp-bug", pack["selected_routes"])

    def test_generic_python_tests_do_not_select_project_tooling(self) -> None:
        pack = build_pack("Fix Python test bug", [], [
            "tools/agent/test_context_pack.py",
        ], 8000)
        self.assertNotIn("project-tooling", pack["selected_routes"])
        self.assertNotIn("project-python", {
            entry["id"] for entry in pack["tests"]
        })
        self.assertNotIn("tests/AGENTS.md", {
            item["path"] for item in pack["agents"]
        })

    def test_project_tool_and_test_files_select_project_validation(self) -> None:
        for path in ("tools/project/remote_gate.py",
                     "tests/project/test_remote_gate.py"):
            with self.subTest(path=path):
                pack = build_pack("Fix Python test bug", [], [path], 8000)
                self.assertIn("project-tooling", pack["selected_routes"])
                self.assertIn("project-python", {
                    entry["id"] for entry in pack["tests"]
                })

    def test_report_keyword_does_not_select_upstream_port(self) -> None:
        pack = build_pack("Repair the tooling report", [], [
            "tests/project/test_remote_workflows.py",
        ], 8000)
        self.assertNotIn("upstream-port", pack["selected_routes"])

    def test_benchmark_rejects_unrelated_route(self) -> None:
        def misroute(*args: object) -> dict:
            pack = build_pack(*args)
            pack["selected_routes"].append("cpp-bug")
            return pack

        with patch("benchmark_context_pack.build_pack", side_effect=misroute):
            report = benchmark()
        self.assertLess(report["metrics"]["first_pass_validation"], 1.0)
        self.assertGreater(report["metrics"]["unrelated_changes"], 0)

    def test_benchmark_has_no_hallucinated_paths_or_commands(self) -> None:
        report = benchmark()
        metrics = report["metrics"]
        self.assertEqual(metrics["hallucinated_paths"], 0)
        self.assertEqual(metrics["hallucinated_commands"], 0)
        self.assertEqual(metrics["upstream_divergence_regressions"], 0)
        self.assertEqual(metrics["unrelated_changes"], 0)
        self.assertEqual(metrics["correct_path_hit_rate"], 1.0)
        self.assertEqual(metrics["first_pass_validation"], 1.0)


if __name__ == "__main__":
    unittest.main()
