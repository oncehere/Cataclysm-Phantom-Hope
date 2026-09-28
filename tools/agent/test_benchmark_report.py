import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import benchmark_context_pack as benchmark


class BenchmarkReportTest(unittest.TestCase):
    def setUp(self):
        self.report = {"case_count": 1, "cases": [{"passed": True}]}

    def invoke(self, arguments):
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(
                benchmark, "benchmark", return_value=self.report,
            ),
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err),
        ):
            code = benchmark.main(arguments)
        return code, out.getvalue(), err.getvalue()

    def test_default_prints_parseable_json_without_writing(self):
        with mock.patch.object(
            Path, "write_text", side_effect=AssertionError("write"),
        ):
            code, output, summary = self.invoke([])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output), self.report)
        self.assertIn("1/1", summary)

    def test_check_needs_no_export_and_does_not_write(self):
        with mock.patch.object(
            Path, "write_text", side_effect=AssertionError("write"),
        ):
            code, output, summary = self.invoke(["--check"])
        self.assertEqual((code, output), (0, ""))
        self.assertIn("1/1", summary)

    def test_explicit_export_and_check_detect_staleness(self):
        with tempfile.TemporaryDirectory(
            prefix="cph-ai-doc-benchmark-",
        ) as folder:
            path = Path(folder) / "nested" / "report.json"
            args = ["--output", str(path)]
            code, _, _ = self.invoke(args)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(path.read_text()), self.report)
            before = path.read_bytes()
            code, _, _ = self.invoke(["--check", *args])
            self.assertEqual(code, 0)
            self.assertEqual(path.read_bytes(), before)
            path.write_text("stale\n")
            code, _, error = self.invoke(["--check", *args])
            self.assertEqual(code, 1)
            self.assertIn(str(path), error)
            self.assertEqual(path.read_text(), "stale\n")
            path.unlink()
            code, _, _ = self.invoke(["--check", *args])
            self.assertEqual(code, 1)
            self.assertFalse(path.exists())

    def test_failed_cases_still_fail_without_a_snapshot(self):
        self.report["cases"][0]["passed"] = False
        code, _, _ = self.invoke(["--check"])
        self.assertEqual(code, 1)

    def test_invalid_input_is_an_error(self):
        with mock.patch.object(
            benchmark, "benchmark", side_effect=ValueError("bad input"),
        ), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(benchmark.main(["--check"]), 2)

    def test_expected_document_ids_must_resolve_before_benchmarking(self):
        original = benchmark.load_yaml
        definition_path = benchmark.ROOT / "ai/agent-benchmark.yml"
        for identifier in (
            "repo.missing-document",
            "repo.doc-frequently-made-suggestions-md",
            "repo.data-lua-reference-ccb-platform-api-v1-json",
        ):
            definition = copy.deepcopy(original(definition_path))
            definition["cases"][0]["expected_documentation_ids"] = [
                identifier,
            ]

            def modified(path):
                if path == definition_path:
                    return definition
                return original(path)

            with self.subTest(identifier=identifier), mock.patch.object(
                benchmark, "load_yaml", side_effect=modified,
            ), self.assertRaisesRegex(ValueError, "documentation ID"):
                benchmark.benchmark()


if __name__ == "__main__":
    unittest.main()
