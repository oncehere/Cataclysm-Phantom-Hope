from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "agent"))

from benchmark_context_pack import benchmark  # noqa: E402
from build_context_pack import (  # noqa: E402
    build_pack, documentation_paths, load_yaml, matches, tracked_paths,
)


class ContextPackTests(unittest.TestCase):
    def test_lua_route_contains_contract_and_validation(self) -> None:
        pack = build_pack(
            "Change Lua-first Platform services",
            [],
            ["data/lua/types/ccb_platform_v1.d.lua"],
            4000,
        )
        self.assertIn("lua-api", pack["selected_routes"])
        self.assertIn("repo.data-lua-lua-first-platform-md", pack["documentation_ids"])
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

    def test_json_file_cli_rejects_impossible_budget_without_dropping_checks(self) -> None:
        path = "data/json/items/melee/misc.json"
        command = [
            sys.executable, "-B", "tools/agent/build_context_pack.py",
            "--file", path, "--token-limit",
        ]
        rejected = subprocess.run(
            [*command, "512"], cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(rejected.returncode, 2, rejected.stderr)
        self.assertEqual(rejected.stdout, "")
        self.assertIn("token limit 512 cannot fit", rejected.stderr)

        accepted = subprocess.run(
            [*command, "1024"], cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        pack = json.loads(accepted.stdout)
        full_pack = build_pack("", [], [path], 8000)
        self.assertLessEqual(pack["estimated_tokens"], 1024)
        self.assertEqual(pack["tests"], full_pack["tests"])
        self.assertEqual(pack["acceptance_commands"], full_pack["acceptance_commands"])
        self.assertLessEqual({"json-syntax", "json-load", "json-eoc-contract"}, {
            entry["id"] for entry in pack["tests"]
        })

    def test_current_document_ids_resolve_to_paths(self) -> None:
        registry = load_yaml(ROOT / "ai/documentation-registry.yml")
        known = tracked_paths()
        pack = build_pack("", ["eoc"], [], 8000)
        paths = documentation_paths(pack["documentation_ids"], registry, known)
        self.assertIn("doc/JSON/EFFECT_ON_CONDITION.md", paths)
        self.assertLessEqual(set(paths), set(pack["source_paths"]))

    def test_route_rejects_unknown_historical_and_nonindexed_documents(self) -> None:
        original = load_yaml
        route_path = ROOT / "ai/task-router.yml"
        registry_path = ROOT / "ai/documentation-registry.yml"
        registry = copy.deepcopy(original(registry_path))
        current = next(entry for entry in registry["entries"]
                       if entry["path"] == "doc/JSON/JSON_INFO.md")
        current["include_in_ai_index"] = False
        for identifier in (
            "repo.missing-document",
            "repo.doc-frequently-made-suggestions-md",
            current["id"],
        ):
            route = copy.deepcopy(original(route_path))
            next(entry for entry in route["entries"]
                 if entry["id"] == "repository-navigation")["documentation_ids"] = [identifier]

            def modified(path):
                if path == route_path:
                    return route
                if path == registry_path:
                    return registry
                return original(path)

            with self.subTest(identifier=identifier), patch(
                "build_context_pack.load_yaml", side_effect=modified,
            ), self.assertRaisesRegex(ValueError, "documentation ID"):
                build_pack("", ["repository-navigation"], [], 8000)

    def test_document_resolution_rejects_duplicate_ids_and_missing_paths(self) -> None:
        registry = load_yaml(ROOT / "ai/documentation-registry.yml")
        entry = next(item for item in registry["entries"]
                     if item["path"] == "doc/JSON/JSON_INFO.md")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            documentation_paths([entry["id"]], {"entries": [entry, entry]}, [])
        with self.assertRaisesRegex(ValueError, "not tracked/present"):
            documentation_paths([entry["id"]], {"entries": [entry]}, [])

    def test_explicit_files_add_contract_checks_even_with_a_task_id(self) -> None:
        for path in ("src/condition.cpp", "data/json/items/melee/misc.json",
                     "tools/json_api/generate_contracts.py"):
            for task_ids in ([], ["repository-navigation"]):
                with self.subTest(path=path, task_ids=task_ids):
                    pack = build_pack("", task_ids, [path], 8000)
                    self.assertIn("json-eoc-contract", {
                        entry["id"] for entry in pack["tests"]
                    })

    def test_no_file_route_keeps_its_checks_without_matching_broad_patterns(self) -> None:
        pack = build_pack("", ["repository-navigation"], [], 8000)
        checks = {entry["id"] for entry in pack["tests"]}
        self.assertIn("agent-context", checks)
        self.assertNotIn("json-eoc-contract", checks)
        self.assertNotIn("cpp-tests", checks)

    def test_routing_preserves_subsystem_validation_boundaries(self) -> None:
        cases = (
            ("Fix a workflow bug", ".github/workflows/project-ci.yml",
             {"project-python", "governance-audit"},
             {"cmake-configure", "cpp-tests", "json-syntax", "json-load"},
             {"AGENTS.md", ".github/AGENTS.md"}),
            ("修复 Python 测试 bug 和错误", "tests/project/test_remote_workflows.py",
             {"project-python", "python-tools"},
             {"cpp-tests", "cpp-format", "json-syntax", "json-load"},
             {"AGENTS.md", "tests/AGENTS.md"}),
            ("Fix C++ behaviour", "src/game.cpp",
             {"cpp-tests", "cpp-format"}, {"project-python", "json-syntax", "json-load"},
             {"AGENTS.md", "src/AGENTS.md"}),
            ("Fix pure Lua Mod bug", "data/mods/Lua_First_Example/main.lua",
             {"lua-contract", "lua-mod-load", "lua-playable-mvp"},
             {"json-syntax", "json-load", "json-eoc-contract", "cpp-tests"},
             {"AGENTS.md", "data/AGENTS.md", "data/mods/AGENTS.md"}),
            ("Fix JSON Mod bug", "data/mods/TEST_DATA/modinfo.json",
             {"json-syntax", "json-load", "json-eoc-contract"},
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
        self.assertLessEqual({"json-syntax", "json-load", "lua-contract", "lua-mod-load"}, {
            entry["id"] for entry in pack["tests"]
        })

    def test_python_bug_keywords_do_not_select_native_tests(self) -> None:
        pack = build_pack("修复项目测试 bug 和错误", [], [], 8000)
        self.assertIn("project-tooling", pack["selected_routes"])
        self.assertNotIn("cpp-bug", pack["selected_routes"])

    def test_cmake_inputs_select_configuration_and_behavioural_regressions(self) -> None:
        paths = [path for path in tracked_paths() if (
            Path(path).name == "CMakeLists.txt" or
            path.startswith("CMakeModules/") or
            path in {"CMakePresets.json", "src/version.cmake", "src/prefix.h.in"}
        )]
        matrix = load_yaml(ROOT / "ai/test-matrix.yml")["entries"]
        build = next(entry for entry in load_yaml(
            ROOT / "ai/project-map.yml"
        )["entries"] if entry["id"] == "build")
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(path=path):
                pack = build_pack("Repair build configuration", [], [path], 8000)
                self.assertIn("cmake-build", pack["selected_routes"])
                self.assertIn("repo.doc-c-compiling-cmake-md", pack["documentation_ids"])
                tests = {entry["id"] for entry in pack["tests"]}
                self.assertLessEqual({"cmake-configure", "cmake-regression"}, tests)
                self.assertNotIn("cpp-tests", tests)
                self.assertTrue(any(matches(pattern, path)
                                    for pattern in build["paths"]))
                selected = {entry["id"] for entry in matrix if any(
                    matches(pattern, path) for pattern in entry["paths"]
                )}
                self.assertLessEqual(
                    {"cmake-configure", "cmake-regression"}, selected,
                )
                self.assertNotIn("cpp-tests", selected)
                self.assertIn("build-scripts/AGENTS.md", {
                    item["path"] for item in pack["agents"]
                })

    def test_cmake_regression_files_select_the_cmake_test_command(self) -> None:
        paths = [path for path in tracked_paths()
                 if matches("tests/project/test_cmake*.py", path)]
        self.assertIn("tests/project/test_cmake_version.py", paths)
        for path in paths:
            with self.subTest(path=path):
                pack = build_pack("Repair test coverage", [], [path], 8000)
                self.assertIn("cmake-build", pack["selected_routes"])
                test = next(entry for entry in pack["tests"]
                            if entry["id"] == "cmake-regression")
                self.assertEqual(test["workdir"], ".")
                self.assertEqual(
                    test["command"],
                    "python3 -m unittest discover -s tests/project -p 'test_cmake*.py'",
                )
                self.assertNotIn("cpp-tests", {
                    entry["id"] for entry in pack["tests"]
                })

    def test_cmake_keyword_routes_without_a_file(self) -> None:
        pack = build_pack("修复 CMake 构建", [], [], 8000)
        self.assertEqual(pack["selected_routes"], ["cmake-build"])
        self.assertEqual({entry["id"] for entry in pack["tests"]}, {
            "cmake-configure", "cmake-regression",
        })

    def test_lua_migration_helper_selects_migration_regression(self) -> None:
        pack = build_pack("Repair generated output", [], [
            "tools/lua_migration_output.py",
        ], 8000)
        self.assertIn("lua-migration-tool", pack["selected_routes"])
        self.assertIn("lua-migration", {entry["id"] for entry in pack["tests"]})
        pack = build_pack("Repair Lua bindings", [], ["src/lua_platform_runtime.cpp"], 8000)
        self.assertNotIn("lua-migration", {entry["id"] for entry in pack["tests"]})

    def test_unrelated_changes_do_not_select_cmake_checks(self) -> None:
        for path in ("src/game.cpp", "tests/project/test_remote_workflows.py",
                     "data/mods/TEST_DATA/modinfo.json"):
            with self.subTest(path=path):
                pack = build_pack("Repair behaviour", [], [path], 8000)
                self.assertNotIn("cmake-build", pack["selected_routes"])
                self.assertFalse({"cmake-configure", "cmake-regression"} & {
                    entry["id"] for entry in pack["tests"]
                })

    def test_native_c_and_cpp_support_files_keep_native_validation(self) -> None:
        for path in ("src/lua/lapi.c", "src/sol/sol.hpp",
                     "src/third-party/fmt/format.cc", "src/lang_stats.inc",
                     "src/resource.rc"):
            with self.subTest(path=path):
                pack = build_pack("Repair native source", [], [path], 8000)
                self.assertIn("cpp-bug", pack["selected_routes"])
                self.assertIn("cpp-tests", {
                    entry["id"] for entry in pack["tests"]
                })

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
