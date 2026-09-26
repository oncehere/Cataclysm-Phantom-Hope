"""Synthetic evidence checks, never game, platform or release acceptance."""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "tools/project/linux_probe.py"
)
SPEC = importlib.util.spec_from_file_location("linux_probe", MODULE_PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)
VALID_REPORT = '<testsuite tests="3"><testcase name="one"/></testsuite>'


class ReportValidation(unittest.TestCase):
    def validate(self, content):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.xml"
            path.write_text(content)
            return probe.check_junit(path)

    def test_cases_and_positive_assertions_required(self):
        self.assertEqual(
            self.validate("<testsuites>" + VALID_REPORT + "</testsuites>"),
            {"test_cases": 1, "assertions": 3},
        )
        for tests in ('tests="0"', 'tests="-1"', 'tests="nan"', ''):
            with self.subTest(tests=tests), self.assertRaises(ValueError):
                self.validate(
                    f'<testsuite {tests}><testcase name="empty"/></testsuite>'
                )
        with self.assertRaises(ValueError):
            self.validate('<testsuite tests="1"/>')

    def test_claimed_success_does_not_hide_failure(self):
        for tag in ("failure", "error", "skipped"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                self.validate(
                    f'<testsuite tests="1" failures="0"><testcase><{tag}/>'
                    "</testcase></testsuite>"
                )

    def test_summary_failure_and_malformed_reports_rejected(self):
        for field in ("failures", "errors", "skipped", "disabled"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.validate(
                    f'<testsuite tests="1" {field}="1"><testcase/></testsuite>'
                )
        with self.assertRaises(ET.ParseError):
            self.validate("<testsuite><testcase>")
        with self.assertRaises(ValueError):
            self.validate("<unrelated>" + VALID_REPORT + "</unrelated>")

    def test_aggregate_count_and_orphan_cases_rejected(self):
        with self.assertRaises(ValueError):
            self.validate(
                '<testsuites tests="0">' + VALID_REPORT + '</testsuites>'
            )
        with self.assertRaises(ValueError):
            self.validate(
                '<testsuites>' + VALID_REPORT + '<testcase/></testsuites>'
            )

    def test_multiple_suites_do_not_double_count_assertions(self):
        self.assertEqual(
            self.validate(
                '<testsuites tests="6">' + VALID_REPORT * 2 + '</testsuites>'
            ),
            {"test_cases": 2, "assertions": 6},
        )

    def test_selections_include_explicit_hidden_chinese_probe(self):
        self.assertEqual(
            probe.TESTS[0], ("translations", "[translations]~[.]"),
        )
        self.assertEqual(
            probe.TESTS[1],
            ("chinese-runtime", "TranslationPluralRulesEvaluatorPerformance"),
        )


class SyntheticProbe(unittest.TestCase):
    """A tiny Git repository and Python executables, not a game build."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.build = self.root / "build"
        self.build.mkdir()
        self.evidence = self.root / "evidence"
        self.git_env = {
            key: value for key, value in os.environ.items()
            if not key.startswith("GIT_")
        }
        self.git_env.update(
            GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
            GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@invalid",
            GIT_COMMITTER_NAME="Fixture",
            GIT_COMMITTER_EMAIL="fixture@invalid",
        )
        self.git("init", "--quiet")
        (self.source / "CMakePresets.json").write_text("{}\n")
        (self.source / ".gitignore").write_text("lang/mo/\n")
        (self.source / "project").mkdir()
        self.mo = self.source / "lang/mo/zh_CN/LC_MESSAGES/cataclysm-dda.mo"
        self.mo.parent.mkdir(parents=True)
        self.mo.write_bytes(b"synthetic MO hash fixture; not gettext data")
        self.lock = {
            "required_locales": ["zh_CN"],
            "files": [{
                "kind": "gettext-mo", "locale": "zh_CN",
                "path": self.mo.relative_to(self.source).as_posix(),
                "bytes": self.mo.stat().st_size,
                "sha256": hashlib.sha256(self.mo.read_bytes()).hexdigest(),
            }],
        }
        self.write_lock()
        self.commit()
        self.write_cache()
        for name in probe.BINARIES:
            path = self.build / name
            path.parent.mkdir(parents=True)
            self.script(path, "print('synthetic executable')\n")
        self.script(
            self.build / probe.BINARIES[1],
            "import os, pathlib, sys\n"
            "if '--out' in sys.argv:\n"
            "    p = pathlib.Path(sys.argv[sys.argv.index('--out') + 1])\n"
            f"    p.write_text({VALID_REPORT!r})\n"
            "    print('fixture selection:', sys.argv[1])\n"
            "    print('fixture xdg:', os.environ['XDG_CONFIG_HOME'])\n",
        )
        self.tool_dir = self.root / "tools"
        self.tool_dir.mkdir()
        self.script(self.tool_dir / "cmake", "print('synthetic cmake')\n")
        self.base_env = {
            key: value for key, value in os.environ.items()
            if not key.startswith("GIT_")
        }
        self.base_env["PATH"] = str(self.tool_dir) + os.pathsep + os.environ[
            "PATH"
        ]
        self.patch = mock.patch.dict(os.environ, self.base_env, clear=True)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def script(self, path, body):
        path.write_text("#!" + sys.executable + "\n" + body)
        path.chmod(0o755)

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.source), *args], env=self.git_env,
            capture_output=True, check=True,
        ).stdout.decode().strip()

    def commit(self):
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "Synthetic fixture")

    def write_lock(self):
        (self.source / "project/assets.lock.json").write_text(
            json.dumps(self.lock)
        )

    def write_cache(self, overrides=None, source=None):
        options = {
            name: "True" if enabled else "False"
            for name, enabled in probe.OPTIONS.items()
        }
        options.update(overrides or {})
        content = "CMAKE_HOME_DIRECTORY:INTERNAL=" + str(
            source or self.source
        ) + "\n"
        content += "".join(
            name + ":BOOL=" + value + "\n" for name, value in options.items()
        )
        content += "".join(
            name + ":STRING=" + value + "\n"
            for name, value in probe.BUILD_SETTINGS.items()
        )
        content += "".join(
            name + ":FILEPATH=" + sys.executable + "\n"
            for name in ("CMAKE_C_COMPILER", "CMAKE_CXX_COMPILER")
        )
        (self.build / "CMakeCache.txt").write_text(content)

    def run_phase(self, phase, evidence=None, source=None):
        evidence = evidence or self.evidence
        with contextlib.redirect_stdout(io.StringIO()):
            code = probe.main([
                "--source", str(source or self.source),
                "--build", str(self.build), "--evidence", str(evidence),
                "--phase", phase,
            ])
        summary = json.loads((evidence / "result.json").read_text())
        self.assertEqual(code, 0 if summary["status"] == "PASS" else 1)
        return code, summary

    def successful_build(self):
        code, summary = self.run_phase("build", self.root / "build-evidence")
        self.assertEqual(code, 0, summary)

    def test_clean_build_binds_source_cache_mo_and_binaries(self):
        self.successful_build()
        manifest = json.loads(
            (self.build / probe.BUILD_MANIFEST).read_text()
        )
        self.assertEqual(manifest["source_state"]["head"], self.git(
            "rev-parse", "HEAD"
        ))
        self.assertEqual(len(manifest["source_state"]["mo_inputs"]), 1)
        self.assertEqual(len(manifest["binaries"]), 2)
        self.assertEqual(manifest["build_command"]["exit_code"], 0)
        code, result = self.run_phase("test")
        self.assertEqual(code, 0, result)
        self.assertEqual(len(result["checks"]), 3)
        self.assertTrue(
            all(row["assertions"] == 3 for row in result["checks"])
        )
        self.assertEqual(
            (self.evidence / "source-before.json").read_bytes(),
            (self.evidence / "source-after.json").read_bytes(),
        )
        self.assertIn(
            str(self.evidence / "xdg-config"),
            (self.evidence / "translations.log").read_text(),
        )

    def test_test_only_requires_successful_build_evidence(self):
        code, result = self.run_phase("test")
        self.assertEqual(code, 1)
        self.assertIn(probe.BUILD_MANIFEST, result["error"])
        self.assertFalse((self.evidence / "commands.jsonl").exists())

    def test_dirty_and_untracked_source_cannot_build(self):
        for name in ("CMakePresets.json", "untracked.txt"):
            with self.subTest(name=name):
                path = self.source / name
                previous = path.read_bytes() if path.exists() else None
                path.write_text("changed")
                code, result = self.run_phase("build", self.root / name)
                self.assertEqual(code, 1)
                self.assertIn("clean", result["error"])
                if previous is None:
                    path.unlink()
                else:
                    path.write_bytes(previous)

    def test_source_commit_change_invalidates_build(self):
        self.successful_build()
        (self.source / "tracked.txt").write_text("new source")
        self.commit()
        code, result = self.run_phase("test")
        self.assertEqual(code, 1)
        self.assertIn("mismatched", result["error"])

    def test_binary_change_invalidates_build(self):
        self.successful_build()
        self.script(self.build / probe.BINARIES[0], "print('different')\n")
        code, result = self.run_phase("test")
        self.assertEqual(code, 1)
        self.assertIn("mismatched", result["error"])

    def test_modified_missing_and_additional_mo_are_rejected(self):
        original = self.mo.read_bytes()
        extra = self.mo.with_name("extra.mo")
        for mode in ("changed", "missing", "extra"):
            with self.subTest(mode=mode):
                if mode == "changed":
                    self.mo.write_bytes(b"changed")
                elif mode == "missing":
                    self.mo.unlink()
                else:
                    extra.write_bytes(b"unlocked")
                code, result = self.run_phase("build", self.root / mode)
                self.assertEqual(code, 1)
                self.assertIn("error", result)
                self.mo.write_bytes(original)
                extra.unlink(missing_ok=True)

    def test_cache_wrong_source_and_each_wrong_option_are_rejected(self):
        self.write_cache(source=self.root)
        with self.assertRaisesRegex(ValueError, "different source"):
            probe.check_cache(self.source, self.build)
        for name, expected in probe.OPTIONS.items():
            with self.subTest(name=name):
                self.write_cache({name: "OFF" if expected else "ON"})
                with self.assertRaisesRegex(ValueError, name):
                    probe.check_cache(self.source, self.build)
        self.write_cache()
        cache = self.build / "CMakeCache.txt"
        cache.write_text(cache.read_text().replace("TESTS:BOOL=True\n", ""))
        with self.assertRaisesRegex(ValueError, "TESTS"):
            probe.check_cache(self.source, self.build)

    def test_source_alias_is_accepted_but_another_source_is_not(self):
        alias = self.root / "ascii-alias"
        alias.symlink_to(self.source, target_is_directory=True)
        code, result = self.run_phase("build", source=alias)
        self.assertEqual(code, 0, result)
        self.write_cache(source=self.root / "different")
        code, result = self.run_phase("test", self.root / "different-evidence")
        self.assertEqual(code, 1)
        self.assertIn("different source", result["error"])

    def test_build_failure_invalidates_old_proof_and_records_nonzero(self):
        self.successful_build()
        old = (self.build / probe.BUILD_MANIFEST).read_bytes()
        self.script(self.tool_dir / "cmake", "import sys\nsys.exit(23)\n")
        code, result = self.run_phase("build")
        self.assertEqual(code, 1)
        self.assertIn("build failed", result["error"])
        self.assertEqual(
            (self.evidence / "previous-build-manifest.json").read_bytes(), old
        )
        self.assertFalse((self.build / probe.BUILD_MANIFEST).exists())
        record = json.loads((self.evidence / "commands.jsonl").read_text())
        self.assertEqual(record["exit_code"], 23)
        self.assertEqual(record["status"], "FAIL")

    def test_spawn_failure_records_log_and_null_exit_code(self):
        self.evidence.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):
                probe.run_command(
                    [str(self.root / "missing-command")], self.source,
                    self.evidence, "missing", os.environ.copy(),
                )
        record = json.loads((self.evidence / "commands.jsonl").read_text())
        self.assertEqual(record["status"], "FAIL")
        self.assertIsNone(record["exit_code"])
        self.assertIn("FileNotFoundError", record["error"])

    def test_existing_evidence_is_preserved(self):
        self.evidence.mkdir()
        sentinel = self.evidence / "result.json"
        sentinel.write_text("previous evidence")
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                self.run_phase("test")
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(sentinel.read_text(), "previous evidence")

    def test_existing_command_log_is_preserved(self):
        self.evidence.mkdir()
        log = self.evidence / "unchanged.log"
        log.write_text("previous log")
        with self.assertRaises(FileExistsError):
            probe.run_command(
                [sys.executable, "-c", "raise SystemExit(0)"], self.source,
                self.evidence, "unchanged", os.environ.copy(),
            )
        self.assertEqual(log.read_text(), "previous log")

    def test_git_environment_redirect_is_rejected_without_value_leak(self):
        with mock.patch.dict(os.environ, {"GIT_DIR": "private-secret-path"}):
            code, result = self.run_phase("build")
        self.assertEqual(code, 1)
        self.assertIn("GIT_DIR", result["error"])
        self.assertNotIn("private-secret-path", json.dumps(result))

    def test_git_failure_still_writes_failed_result(self):
        self.script(self.tool_dir / "git", "import sys\nsys.exit(19)\n")
        code, result = self.run_phase("build")
        self.assertEqual(code, 1)
        self.assertIn("exit code 19", result["error"])
        self.assertFalse((self.build / probe.BUILD_MANIFEST).exists())

    def test_credentials_stripped_xdg_isolated_home_preserved(self):
        self.evidence.mkdir()
        with mock.patch.dict(os.environ, {
            "GH_TOKEN": "hidden", "SIGNING_CERT": "hidden",
            "AWS_ACCESS_KEY_ID": "hidden",
        }):
            env = probe.environment(self.evidence)
        for key in ("GH_TOKEN", "SIGNING_CERT", "AWS_ACCESS_KEY_ID"):
            self.assertNotIn(key, env)
        self.assertEqual(env.get("HOME"), os.environ.get("HOME"))
        self.assertEqual(env["GIT_NO_LAZY_FETCH"], "1")
        self.assertEqual(env["GIT_CONFIG_GLOBAL"], os.devnull)
        for key in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
            self.assertTrue(Path(env[key]).is_relative_to(self.evidence))

    def test_source_change_during_build_never_writes_success_marker(self):
        self.script(
            self.tool_dir / "cmake", "from pathlib import Path\n"
            "Path('CMakePresets.json').write_text('changed during build')\n",
        )
        code, result = self.run_phase("build")
        self.assertEqual(code, 1)
        self.assertIn("source_after_error", result)
        self.assertFalse((self.build / probe.BUILD_MANIFEST).exists())

    def test_source_change_during_tests_cannot_pass(self):
        self.script(
            self.build / probe.BINARIES[0], "from pathlib import Path\n"
            "Path('CMakePresets.json').write_text('changed during test')\n",
        )
        self.successful_build()
        code, result = self.run_phase("test")
        self.assertEqual(code, 1)
        self.assertIn("source_after_error", result)

    def test_nonzero_test_process_cannot_pass_with_valid_junit(self):
        path = self.build / probe.BINARIES[1]
        path.write_text(path.read_text() + "sys.exit(7)\n")
        self.successful_build()
        code, result = self.run_phase("test")
        self.assertEqual(code, 1)
        self.assertEqual(result["checks"], [])
        self.assertTrue((self.evidence / "translations.xml").exists())
        records = [
            json.loads(line) for line in
            (self.evidence / "commands.jsonl").read_text().splitlines()
        ]
        self.assertEqual(records[-1]["exit_code"], 7)

    def test_zero_assertion_report_fails_after_real_process_success(self):
        path = self.build / probe.BINARIES[1]
        path.write_text(path.read_text().replace('tests="3"', 'tests="0"'))
        self.successful_build()
        code, result = self.run_phase("test")
        self.assertEqual(code, 1)
        self.assertIn("assertions", result["error"])
        self.assertEqual(result["checks"], [])

    def test_git_replace_and_graft_overrides_are_rejected(self):
        head = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/replace/" + head, head)
        code, result = self.run_phase("build", self.root / "replace-evidence")
        self.assertEqual(code, 1)
        self.assertIn("replacement", result["error"])
        self.git("update-ref", "-d", "refs/replace/" + head)
        (self.source / ".git/info/grafts").write_text(head + "\n")
        code, result = self.run_phase("build")
        self.assertEqual(code, 1)
        self.assertIn("graft", result["error"])

    def test_cache_or_build_log_mutation_invalidates_build(self):
        self.successful_build()
        cache = self.build / "CMakeCache.txt"
        old = cache.read_text()
        cache.write_text(old + "UNRELATED:STRING=changed\n")
        code, result = self.run_phase("test", self.root / "cache-evidence")
        self.assertEqual(code, 1)
        self.assertIn("mismatched", result["error"])
        cache.write_text(old)
        (self.root / "build-evidence/build.log").write_text("changed")
        code, result = self.run_phase("test")
        self.assertEqual(code, 1)
        self.assertIn("command evidence", result["error"])

    def test_index_flags_cannot_hide_source_changes(self):
        for flag in ("assume-unchanged", "skip-worktree"):
            with self.subTest(flag=flag):
                self.git("update-index", "--" + flag, "CMakePresets.json")
                code, result = self.run_phase("build", self.root / flag)
                self.assertEqual(code, 1)
                self.assertIn(flag, result["error"])
                self.git(
                    "update-index", "--no-" + flag, "CMakePresets.json"
                )

    def test_malformed_lock_result_is_fail_not_an_unhandled_exception(self):
        self.lock["files"][0]["path"] = {"not": "a string"}
        self.write_lock()
        self.commit()
        code, result = self.run_phase("build")
        self.assertEqual(code, 1)
        self.assertIn("invalid MO path", result["error"])

    def test_source_local_evidence_is_rejected_without_creating_it(self):
        evidence = self.source / "forbidden-evidence"
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                self.run_phase("build", evidence)
        self.assertFalse(evidence.exists())

    def test_wrong_build_type_or_flags_cannot_match_expected_profile(self):
        for name, value in probe.BUILD_SETTINGS.items():
            with self.subTest(name=name):
                self.write_cache()
                cache = self.build / "CMakeCache.txt"
                cache.write_text(cache.read_text().replace(
                    name + ":STRING=" + value, name + ":STRING=changed"
                ))
                with self.assertRaisesRegex(ValueError, name):
                    probe.check_cache(self.source, self.build)


if __name__ == "__main__":
    unittest.main()
