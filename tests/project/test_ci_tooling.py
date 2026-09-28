"""Tool suite selection must distinguish excluded scope from skipped checks."""

import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tools/project/ci_tooling.py"
sys.path.insert(0, str(RUNNER.parent))
import ci_tooling  # noqa: E402
import ci_build  # noqa: E402
import remote_gate  # noqa: E402


class ToolingRunnerTests(unittest.TestCase):
    def test_real_suite_and_generator_reports_are_accepted_by_collector(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, control, evidence = (
                root / name for name in ("source", "control", "evidence")
            )
            source.mkdir()
            (control / "project").mkdir(parents=True)
            (source / "test_fixture.py").write_text(
                "import unittest\nclass Case(unittest.TestCase):\n"
                "    def test_ok(self): self.assertEqual(2 + 2, 4)\n"
            )
            (source / "check.py").write_text("raise SystemExit(0)\n")
            requirements = control / "requirements.txt"
            requirements.write_text("")
            policy = {
                "python_version": platform.python_version(),
                "requirements": "requirements.txt",
                "suites": {
                    "fixture": {"directory": ".", "excluded_prefixes": []}
                },
                "checks": {"generated": ["check.py", "--check"]},
            }
            policy_file = control / "project/check-policy.json"
            policy_file.write_text(json.dumps({"tooling": policy}))
            identity = {
                "control_sha": "a" * 40,
                "policy_sha": ci_build.digest(policy_file),
            }
            real_run = subprocess.run

            def without_package_install(argv, **kwargs):
                # Keep this test independent of pip/network availability while
                # exercising the real test and generated-check subprocesses.
                if argv[1:4] == ["-m", "pip", "install"]:
                    return subprocess.CompletedProcess(argv, 0)
                return real_run(argv, **kwargs)

            with (
                patch.object(ci_build, "CONTROL", control),
                patch.object(ci_build, "verify_checkout"),
                patch.object(ci_build, "git", return_value="a" * 40),
                patch.dict(os.environ, {"CPH_CI_PLAN": json.dumps(identity)}),
                patch.object(
                    subprocess, "run", side_effect=without_package_install
                ),
            ):
                self.assertEqual(ci_tooling.build(source, evidence), 0)
            files = {
                path.name: path.read_bytes()
                for path in evidence.iterdir()
                if path.is_file()
            }
            report = remote_gate.validate_tooling(
                files, identity, policy, remote_gate.digest(b"")
            )
            self.assertEqual(report["status"], "PASS")

    def run_fixture(self, tests, excluded=(), files=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "test_fixture.py").write_text("import unittest\n" + tests)
            for name, contents in (files or {}).items():
                (root / name).write_text(contents)
            output = root / "report.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "suite",
                    "--directory",
                    str(root),
                    "--excluded",
                    json.dumps(excluded),
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode, json.loads(output.read_text())

    def test_suite_imports_candidate_ci_build_not_preloaded_controller(self):
        code, report = self.run_fixture(
            "import ci_build\n"
            "class Case(unittest.TestCase):\n"
            "    def test_candidate(self):\n"
            "        self.assertEqual(ci_build.SENTINEL, 'candidate')\n",
            files={"ci_build.py": "SENTINEL = 'candidate'\n"},
        )
        self.assertEqual(code, 0, report)
        self.assertEqual(report["tests"], 1)
        self.assertEqual(report["errors"], 0)

    def test_nonzero_actual_tests_pass(self):
        code, report = self.run_fixture(
            "class Case(unittest.TestCase):\n"
            "    def test_ok(self): self.assertEqual(2+2, 4)\n"
        )
        self.assertEqual(code, 0)
        self.assertEqual(report["tests"], 1)
        self.assertEqual(
            report["selected_tests"], ["test_fixture.Case.test_ok"]
        )

    def test_nested_suite_imports_packages_from_candidate_workdir(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            package = source / "tools/project"
            suite = source / "tests/project"
            package.mkdir(parents=True)
            suite.mkdir(parents=True)
            (package / "candidate_fixture.py").write_text(
                "ORIGIN = 'candidate'\n"
            )
            (suite / "test_candidate.py").write_text(
                "import unittest\n"
                "from tools.project import candidate_fixture\n"
                "class Case(unittest.TestCase):\n"
                "    def test_origin(self):\n"
                "        self.assertEqual(\n"
                "            candidate_fixture.ORIGIN, 'candidate')\n"
            )
            output = source / "report.json"
            result = subprocess.run(
                [sys.executable, str(RUNNER), "suite", "--directory",
                 "tests/project", "--output", str(output)],
                cwd=source, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text())
            self.assertEqual(report["tests"], 1)
            self.assertEqual(report["errors"], 0)

    def test_failure_skip_and_empty_suite_are_not_pass(self):
        cases = (
            "",
            "class Case(unittest.TestCase):\n"
            "    def test_fail(self): self.fail('failure')\n",
            "class Case(unittest.TestCase):\n"
            "    @unittest.skip('unavailable')\n"
            "    def test_skip(self): pass\n",
        )
        for tests in cases:
            with self.subTest(tests=tests):
                code, report = self.run_fixture(tests)
                self.assertEqual(code, 1)
                self.assertEqual(report["status"], "FAIL")

    def test_explicit_optional_scope_is_recorded_and_not_claimed_passed(self):
        code, report = self.run_fixture(
            "class Case(unittest.TestCase):\n    def test_ok(self): pass\n"
            "class Optional(unittest.TestCase):\n"
            "    @unittest.skip('not configured')\n"
            "    def test_editor(self): pass\n",
            ["test_fixture.Optional."],
        )
        self.assertEqual(code, 0)
        self.assertEqual(report["tests"], 1)
        self.assertEqual(report["skipped"], 0)
        self.assertEqual(
            report["excluded_tests"], ["test_fixture.Optional.test_editor"]
        )

    def test_native_jobs_wait_for_tooling(self):
        import yaml

        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/project-ci.yml").read_text()
        )
        self.assertEqual(
            workflow["jobs"]["native"]["needs"], ["plan", "tooling"]
        )
        tooling = workflow["jobs"]["tooling"]
        self.assertEqual(tooling["permissions"], {"contents": "read"})
        self.assertEqual(tooling["needs"], "plan")
        steps = tooling["steps"]
        for job, depth in (("tooling", 0), ("native", 2)):
            candidate = [
                step
                for step in workflow["jobs"][job]["steps"]
                if step["name"] == "Checkout exact merge candidate"
            ]
            self.assertEqual(len(candidate), 1)
            self.assertEqual(candidate[0]["with"]["fetch-depth"], depth)
        self.assertTrue(
            all(
                step["with"].get("persist-credentials") is False
                for step in steps
                if step["name"].startswith("Checkout")
            )
        )

    def test_active_policy_contains_contract_not_historical_readiness(self):
        policy = json.loads((ROOT / "project/check-policy.json").read_text())
        self.assertFalse(
            {
                "scope",
                "deployment_blockers",
                "merge_ready",
                "public_release_ready",
            } & policy.keys()
        )
        self.assertTrue(
            all(
                "baseline_status" not in target
                for target in policy["targets"].values()
            )
        )


if __name__ == "__main__":
    unittest.main()
