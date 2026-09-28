import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/project"))
import remote_gate as gate  # noqa: E402
import remote_sync as sync  # noqa: E402


BASE, HEAD, MERGE, TREE, UPSTREAM = (char * 40 for char in "abcde")
XML = (
    b'<testsuite tests="1" failures="0"><testcase name="actual"/></testsuite>'
)


def packed(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as bundle:
        for name, data in files.items():
            bundle.writestr(name, data)
    return output.getvalue()


def job(name, steps):
    return {
        "name": name,
        "status": "completed",
        "conclusion": "success",
        "steps": [{"name": step, "conclusion": "success"} for step in steps],
    }


def tooling_files(identity, policy, requirements):
    files, commands, suites = {}, [], []
    names = ["dependencies", *policy["suites"], *policy["checks"]]
    for name in names:
        log = name + ".log"
        files[log] = b"executed tooling command\n"
        argv = ["python", "-m", "pip", "install"]
        if name in policy["suites"]:
            config = policy["suites"][name]
            filename = name + ".json"
            files[filename] = json.dumps(
                {
                    "directory": config["directory"],
                    "pattern": "test_*.py",
                    "excluded_prefixes": config["excluded_prefixes"],
                    "excluded_tests": [],
                "selected_tests": ["test_fixture.Case.test_ok"],
                "selected_count": 1,
                "excluded_count": 0,
                    "status": "PASS",
                    "tests": 1,
                    "failures": 0,
                    "errors": 0,
                    "skipped": 0,
                    "expected_failures": 0,
                    "unexpected_successes": 0,
                }
            ).encode()
            suites.append(
                {
                    "name": name,
                    "report": filename,
                    "sha256": gate.digest(files[filename]),
                }
            )
            argv = [
                "python",
                "/control/tools/project/ci_tooling.py",
                "suite",
                "--directory",
                config["directory"],
                "--excluded",
                json.dumps(config["excluded_prefixes"]),
                "--output",
                "/evidence/" + filename,
            ]
        if name in policy["checks"]:
            argv = ["python", *policy["checks"][name]]
        commands.append(
            {
                "argv": argv,
                "exit_code": 0,
                "status": "PASS",
                "log": log,
                "log_sha256": gate.digest(files[log]),
            }
        )
    files["commands.jsonl"] = b"\n".join(
        json.dumps(item).encode() for item in commands
    )
    files["tooling-report.json"] = json.dumps(
        {
            "schema_version": 1,
            "kind": "cph-tooling-ci",
            "status": "PASS",
            "identity": identity,
            "python_version": policy["python_version"],
            "requirements_sha256": gate.digest(requirements),
            "suites": suites,
            "checks": list(policy["checks"]),
        }
    ).encode()
    return files


class Fixture:
    def __init__(self, directory):
        self.root = Path(directory)
        (self.root / "project").mkdir()
        self.surfaces = {
            "schema_version": 1,
            "prefixes": [".github", "tools/project"],
            "paths": ["CMakeLists.txt"],
            "basenames": ["AGENTS.md"],
        }
        raw = json.dumps(self.surfaces).encode()
        (self.root / "project/protected-surfaces.json").write_bytes(raw)
        target = {
            "target_id": "native-x64",
            "preset": "native",
            "generator": "Ninja",
            "configuration": "RelWithDebInfo",
            "options": {"TESTS": True},
            "binaries": ["game", "tests"],
            "tests": {"translations": "[translations]"},
        }
        self.policy = {
            "protected_surfaces": {"sha256": gate.digest(raw)},
            "targets": {"linux": target, "windows": target},
            "tooling": {
                "python_version": "3.12.10",
                "requirements": "requirements.txt",
                "suites": {
                    "project": {
                        "directory": "tests/project",
                        "excluded_prefixes": [],
                    }
                },
                "checks": {"generated": ["tools/check.py", "--check"]},
            },
        }
        self.requirements = b"jsonschema==4.26.0\n"
        (self.root / "requirements.txt").write_bytes(self.requirements)
        policy_raw = json.dumps(self.policy).encode()
        (self.root / "project/check-policy.json").write_bytes(policy_raw)
        self.expected = {
            "repository": gate.REPOSITORY,
            "repository_id": str(gate.REPOSITORY_ID),
            "pr_number": 3,
            "base_sha": BASE,
            "head_sha": HEAD,
            "merge_sha": MERGE,
            "merge_tree": TREE,
            "control_sha": BASE,
            "event": "workflow_dispatch",
            "run_id": "12",
            "run_attempt": "1",
            "policy_sha": gate.digest(policy_raw),
            "workflow_ref": gate.REPOSITORY +
            "/" +
            gate.WORKFLOW +
            "@refs/heads/main",
        }
        self.raw = {}
        self.reports = {}
        artifacts = []
        for number, platform in enumerate(("linux", "windows"), 1):
            files = {"translations.xml": XML}
            commands = []
            for name in ("configure", "build", "game-version", "translations"):
                files[name + ".log"] = b"actual execution evidence\n"
                commands.append(
                    {
                        "log": name + ".log",
                        "log_sha256": gate.digest(files[name + ".log"]),
                        "argv": [
                            "test",
                            "[translations]",
                            "--reporter",
                            "junit",
                        ],
                        "exit_code": 0,
                        "status": "PASS",
                    }
                )
            files["commands.jsonl"] = b"\n".join(
                json.dumps(item).encode() for item in commands
            )
            report = {
                "schema_version": 1,
                "kind": "cph-native-ci",
                "status": "PASS",
                "platform": platform,
                "identity": self.expected,
                "configuration": target,
                "checks": dict.fromkeys(
                    ("configure", "build", "version", "isolation"), "PASS"
                ),
                "isolation_scope": "explicit-userdir-sentinels",
                "binaries": [
                    {"path": name, "bytes": 20, "sha256": "a" * 64}
                    for name in target["binaries"]
                ],
                "tests": [
                    {
                        "check": "translations",
                        "selection": "[translations]",
                        "status": "PASS",
                        "report": "translations.xml",
                        "report_sha256": gate.digest(XML),
                        "test_cases": 1,
                        "assertions": 1,
                    }
                ],
            }
            files["report.json"] = json.dumps(report).encode()
            self.reports[platform] = files
            raw = packed(files)
            self.raw[number] = raw
            artifacts.append(
                {
                    "id": number,
                    "name": f"cph-ci-{platform}-12-1",
                    "expired": False,
                    "size_in_bytes": len(raw),
                    "digest": "sha256:" + gate.digest(raw),
                    "workflow_run": {"id": 12},
                }
            )
        self.tool_files = tooling_files(
            self.expected, self.policy["tooling"], self.requirements
        )
        self.raw[3] = packed(self.tool_files)
        artifacts.append(
            {
                "id": 3,
                "name": "cph-ci-tooling-12-1",
                "expired": False,
                "size_in_bytes": len(self.raw[3]),
                "workflow_run": {"id": 12},
                "digest": "sha256:" + gate.digest(self.raw[3]),
            }
        )
        run = {
            "id": 12,
            "repository": {
                "id": gate.REPOSITORY_ID,
                "full_name": gate.REPOSITORY,
            },
            "workflow_id": 55,
            "path": gate.WORKFLOW,
            "run_attempt": 1,
            "status": "completed",
            "conclusion": "success",
            "event": "workflow_dispatch",
            "head_sha": BASE,
            "head_branch": "main",
            "display_title": f"CPH CI PR 3 base {BASE} head {HEAD}",
        }
        self.pr = {
            "state": "open",
            "draft": False,
            "base": {
                "ref": "main",
                "sha": BASE,
                "repo": {"id": gate.REPOSITORY_ID},
            },
            "head": {
                "sha": HEAD,
                "ref": "codex/sync",
                "repo": {"id": gate.REPOSITORY_ID},
            },
            "user": {"login": "github-actions[bot]"},
            "changed_files": 1,
            "mergeable": True,
            "mergeable_state": "clean",
            "merge_commit_sha": MERGE,
        }
        self.values = {
            "actions/runs/12": run,
            "actions/workflows/project-ci.yml": {
                "id": 55,
                "path": gate.WORKFLOW,
            },
            "actions/workflows/project-ci.yml/runs": {"workflow_runs": [run]},
            "pulls/3": self.pr,
            "pulls/3/files": [{"filename": "src/ordinary.cpp"}],
            "git/commits/" + MERGE: {
                "tree": {"sha": TREE},
                "parents": [{"sha": BASE}, {"sha": HEAD}],
            },
            "git/commits/" + HEAD: {
                "parents": [{"sha": BASE}, {"sha": UPSTREAM}]
            },
            "actions/runs/12/attempts/1/jobs": {
                "total_count": 4,
                "jobs": [
                    job(
                        "CPH Plan",
                        (
                            "Checkout trusted control revision",
                            "Bind current PR and merge tree",
                        ),
                    ),
                    job("CPH Linux", gate.BUILD_STEPS),
                    job("CPH Windows", gate.BUILD_STEPS),
                    job("CPH Tooling", gate.TOOLING_STEPS),
                ],
            },
            "actions/runs/12/artifacts": {
                "total_count": 3,
                "artifacts": artifacts,
            },
        }
        self.writes = []

    def repo(self, path, method="GET", data=None, missing=False):
        if method != "GET":
            self.writes.append((method, path, copy.deepcopy(data)))
            if path == "pulls/3/merge":
                return {"merged": True, "sha": MERGE}
            return {}
        return copy.deepcopy(self.values[path.split("?")[0]])

    def collect(self):
        return gate.collect(
            self, 12, 1, BASE, self.root, lambda api, number: self.raw[number]
        )

    def report(self, mutation):
        files = copy.deepcopy(self.reports["linux"])
        report = json.loads(files["report.json"])
        mutation(report, files)
        files["report.json"] = json.dumps(report).encode()
        return gate.validate_report(files, "linux", self.expected, self.policy)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = Fixture(self.temp.name)

    def validate_tools(self, mutate=None):
        files = copy.deepcopy(self.fixture.tool_files)
        report = json.loads(files["tooling-report.json"])
        suite = json.loads(files["project.json"])
        if mutate:
            mutate(report, suite, files)
        files["project.json"] = json.dumps(suite).encode()
        report["suites"][0]["sha256"] = gate.digest(files["project.json"])
        files["tooling-report.json"] = json.dumps(report).encode()
        return gate.validate_tooling(
            files,
            self.fixture.expected,
            self.fixture.policy["tooling"],
            gate.digest(self.fixture.requirements),
        )

    def test_tooling_requires_nonzero_executed_tests_without_skips(self):
        self.validate_tools()
        for field, value in (
            ("tests", 0),
            ("tests", True),
            ("skipped", 1),
            ("errors", 1),
            ("failures", 1),
            ("expected_failures", 1),
            ("unexpected_successes", 1),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.validate_tools(
                    lambda report, suite, files: suite.update({field: value})
                )

    def test_tooling_cannot_reuse_another_candidate_policy_or_attempt(self):
        for field in self.fixture.expected:
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(ValueError, "identity"),
            ):
                self.validate_tools(
                    lambda report, suite, files: report["identity"].update(
                        {field: "stale"}
                    )
                )

    def test_tooling_reports_and_check_commands_are_required(self):
        mutations = [
            lambda report, suite, files: report.update(status="SKIPPED"),
            lambda report, suite, files: report.update(checks=[]),
            lambda report, suite, files: report.update(
                requirements_sha256="changed"
            ),
            lambda report, suite, files: report.update(
                python_version="3.13.0"
            ),
            lambda report, suite, files: suite.update(selected_tests=[]),
            lambda report, suite, files: suite.update(
                excluded_tests=["test_mandatory"]
            ),
            lambda report, suite, files: files.pop("commands.jsonl"),
            lambda report, suite, files: files.update(
                {"generated.log": b"changed"}
            ),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                self.validate_tools(mutate)

    def test_absent_failed_skipped_tooling_job_rejects_native_success(self):
        jobs = self.fixture.values["actions/runs/12/attempts/1/jobs"]
        for conclusion in (
            "failure",
            "skipped",
            "cancelled",
            "timed_out",
            "neutral",
        ):
            jobs["jobs"][-1]["conclusion"] = conclusion
            with (
                self.subTest(conclusion=conclusion),
                self.assertRaisesRegex(ValueError, "CPH Tooling"),
            ):
                self.fixture.collect()
        jobs["jobs"].pop()
        jobs["total_count"] -= 1
        with self.assertRaisesRegex(ValueError, "CPH Tooling"):
            self.fixture.collect()

    def test_missing_expired_or_old_tooling_artifact_rejected(self):
        artifacts = self.fixture.values["actions/runs/12/artifacts"]
        tooling = artifacts["artifacts"][-1]
        for field, value in (
            ("expired", True),
            ("name", "cph-ci-tooling-12-2"),
            ("digest", "sha256:" + "0" * 64),
        ):
            old = tooling[field]
            tooling[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.fixture.collect()
            tooling[field] = old
        artifacts["artifacts"].pop()
        artifacts["total_count"] -= 1
        with self.assertRaisesRegex(ValueError, "artifact"):
            self.fixture.collect()

    def test_complete_native_evidence_is_accepted_without_publishing_early(
        self,
    ):
        result = self.fixture.collect()
        self.assertEqual(result["merge_tree"], TREE)
        self.assertEqual(self.fixture.writes, [])

    def test_non_success_workflows_fail_closed(self):
        for conclusion in (
            "failure",
            "cancelled",
            "timed_out",
            "neutral",
            "skipped",
            None,
        ):
            with self.subTest(conclusion=conclusion):
                self.fixture.values["actions/runs/12"]["conclusion"] = (
                    conclusion
                )
                with self.assertRaises(ValueError):
                    self.fixture.collect()
                self.assertEqual(
                    self.fixture.writes[-1][2]["state"], "failure"
                )

    def test_skipped_native_job_and_step_fail_closed(self):
        jobs = self.fixture.values["actions/runs/12/attempts/1/jobs"]["jobs"]
        jobs[1]["conclusion"] = "skipped"
        with self.assertRaises(ValueError):
            self.fixture.collect()
        jobs[1]["conclusion"] = "success"
        jobs[1]["steps"][-2]["conclusion"] = "skipped"
        with self.assertRaises(ValueError):
            self.fixture.collect()

    def test_other_workflow_or_stale_attempt_rejected(self):
        for key, value in (
            ("path", ".github/workflows/forged.yml"),
            ("run_attempt", 2),
            ("head_sha", HEAD),
            ("event", "schedule"),
        ):
            with self.subTest(key=key):
                original = self.fixture.values["actions/runs/12"][key]
                self.fixture.values["actions/runs/12"][key] = value
                with self.assertRaises(ValueError):
                    self.fixture.collect()
                self.fixture.values["actions/runs/12"][key] = original

    def test_superseded_run_rejected(self):
        other = copy.deepcopy(self.fixture.values["actions/runs/12"])
        other["id"] = 13
        self.fixture.values["actions/workflows/project-ci.yml/runs"][
            "workflow_runs"
        ].insert(0, other)
        with self.assertRaisesRegex(ValueError, "newer"):
            self.fixture.collect()

    def test_protected_paths_and_renames_rejected(self):
        self.fixture.values["pulls/3/files"] = [
            {
                "filename": "src/new.cpp",
                "previous_filename": ".github/workflows/evil.yml",
            }
        ]
        with self.assertRaisesRegex(ValueError, "protected"):
            self.fixture.collect()

    def test_changed_head_or_parent_rejected(self):
        self.fixture.pr["head"]["sha"] = MERGE
        with self.assertRaises(ValueError):
            self.fixture.collect()
        self.fixture.pr["head"]["sha"] = HEAD
        self.fixture.values["git/commits/" + MERGE]["parents"].reverse()
        with self.assertRaises(ValueError):
            self.fixture.collect()

    def test_artifact_provenance_and_digest_rejected(self):
        item = self.fixture.values["actions/runs/12/artifacts"]["artifacts"][0]
        item["workflow_run"]["id"] = 8
        with self.assertRaises(ValueError):
            self.fixture.collect()
        item["workflow_run"]["id"] = 12
        item["digest"] = "sha256:" + "0" * 64
        with self.assertRaises(ValueError):
            self.fixture.collect()

    def test_report_cannot_claim_other_head_or_empty_tests(self):
        for mutation in (
            lambda report, _: report["identity"].update(head_sha=BASE),
            lambda report, _: report.update(tests=[]),
            lambda report, _: report["tests"][0].update(test_cases=0),
            lambda report, _: report["checks"].update(build="SKIPPED"),
        ):
            with self.assertRaises(ValueError):
                self.fixture.report(mutation)

    def test_xml_failure_cannot_be_hidden_by_pass_report(self):
        def mutate(report, files):
            files["translations.xml"] = (
                b'<testsuite tests="1"><testcase name="failed">'
                b'<failure/></testcase></testsuite>'
            )
            report["tests"][0]["report_sha256"] = gate.digest(
                files["translations.xml"]
            )

        with self.assertRaises(ValueError):
            self.fixture.report(mutate)

    def test_command_exit_or_modified_log_rejected(self):
        def mutate(report, files):
            commands = files["commands.jsonl"].decode().splitlines()
            item = json.loads(commands[0])
            item["exit_code"] = 1
            commands[0] = json.dumps(item)
            files["commands.jsonl"] = "\n".join(commands).encode()

        with self.assertRaises(ValueError):
            self.fixture.report(mutate)
        with self.assertRaises(ValueError):
            self.fixture.report(
                lambda report, files: files.update({"build.log": b"forged"})
            )

    def test_unsafe_archive_paths_symlinks_and_duplicates_rejected(self):
        for name in ("../escape", "/absolute", "C:/file", "a\\b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                gate.archive(packed({name: b"data"}))
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as bundle:
            item = zipfile.ZipInfo("link")
            item.external_attr = 0o120777 << 16
            bundle.writestr(item, "target")
        with self.assertRaises(ValueError):
            gate.archive(output.getvalue())

    def test_missing_strict_or_app_protection_rejected(self):
        for value in (
            {},
            {
                "required_status_checks": {
                    "strict": True,
                    "checks": [{"context": gate.CONTEXT, "app_id": -1}],
                }
            },
        ):
            with self.assertRaises(ValueError):
                gate.validate_protection(value)

    def verified_rules(self, hidden=False):
        rules = [
            {"type": kind, "ruleset_id": 91}
            for kind in ("deletion", "non_fast_forward", "pull_request")
        ]
        rules.append(
            {
                "type": "required_status_checks",
                "ruleset_id": 91,
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "required_status_checks": [
                        {"context": gate.CONTEXT, "integration_id": 15368}
                    ],
                },
            }
        )
        self.fixture.values["rules/branches/main"] = rules
        ruleset = {
            "id": 91,
            "target": "branch",
            "source_type": "Repository",
            "source": gate.REPOSITORY,
            "enforcement": "active",
            "conditions": {"ref_name": {
                "include": ["refs/heads/main"], "exclude": [],
            }},
            "rules": [{key: value for key, value in item.items()
                       if key != "ruleset_id"} for item in rules],
            "updated_at": "2026-09-26T23:47:44.831Z",
            "bypass_actors": [],
        }
        self.fixture.values["rulesets/91"] = ruleset
        state = {"verified_rulesets": [{
            "id": 91, "updated_at": ruleset["updated_at"],
            "visible_sha256": gate.ruleset_digest(ruleset),
            "bypass_actors": [],
        }]}
        if hidden:
            del ruleset["bypass_actors"]
        return state

    def test_active_rules_require_no_bypass_and_preserved_history(self):
        state = self.verified_rules()
        self.assertEqual(gate.active_rules(self.fixture, state), 15368)
        self.fixture.values["rulesets/91"]["bypass_actors"] = [
            {"actor_type": "Integration", "actor_id": 15368}
        ]
        with self.assertRaises(ValueError):
            gate.active_rules(self.fixture, state)
        self.fixture.values["rulesets/91"]["bypass_actors"] = []
        self.fixture.values["rules/branches/main"].append(
            {"type": "required_linear_history", "ruleset_id": 91}
        )
        with self.assertRaises(ValueError):
            gate.active_rules(self.fixture, state)

    def test_hidden_bypass_metadata_uses_admin_verified_lock(self):
        state = self.verified_rules(hidden=True)
        self.assertNotIn("bypass_actors", self.fixture.values["rulesets/91"])
        self.assertEqual(gate.active_rules(self.fixture, state), 15368)

    def test_equivalent_ruleset_timezones_match_admin_lock(self):
        state = self.verified_rules(hidden=True)
        self.fixture.values["rulesets/91"]["updated_at"] = (
            "2026-09-26T16:47:44.831-07:00"
        )
        self.assertEqual(gate.active_rules(self.fixture, state), 15368)

    def test_invalid_or_naive_ruleset_timestamp_is_rejected(self):
        for value in (None, "invalid", "2026-09-26T23:47:44.831"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                gate.ruleset_timestamp(value)

    def test_missing_admin_lock_cannot_be_treated_as_empty_bypass(self):
        self.verified_rules(hidden=True)
        for state in ({}, {"verified_rulesets": []}):
            with self.assertRaisesRegex(ValueError, "locks are missing"):
                gate.active_rules(self.fixture, state)
        state = self.verified_rules(hidden=True)
        state["verified_rulesets"][0]["id"] = 92
        with self.assertRaisesRegex(ValueError, "lacks administrator"):
            gate.active_rules(self.fixture, state)
        state = self.verified_rules(hidden=True)
        del state["verified_rulesets"][0]["bypass_actors"]
        with self.assertRaisesRegex(ValueError, "invalid administrator"):
            gate.active_rules(self.fixture, state)

    def test_changed_rules_invalidate_admin_lock(self):
        state = self.verified_rules(hidden=True)
        self.fixture.values["rulesets/91"]["rules"].pop()
        with self.assertRaisesRegex(ValueError, "lock is stale"):
            gate.active_rules(self.fixture, state)

    def test_updated_timestamp_alone_invalidates_admin_lock(self):
        state = self.verified_rules(hidden=True)
        self.fixture.values["rulesets/91"]["updated_at"] = (
            "2026-09-27T01:00:00.000Z"
        )
        with self.assertRaisesRegex(ValueError, "lock is stale"):
            gate.active_rules(self.fixture, state)

    def test_ruleset_source_must_remain_the_authorized_repository(self):
        state = self.verified_rules(hidden=True)
        self.fixture.values["rulesets/91"]["source"] = "other/repository"
        with self.assertRaisesRegex(ValueError, "source or enforcement"):
            gate.active_rules(self.fixture, state)

    def state(self):
        state = sync.initial_state()
        state.update(
            sync_paused=False, merge_paused=False, auto_merge_enabled=True
        )
        state["tasks"][UPSTREAM] = {
            "task_key": "ccb-" + UPSTREAM,
            "pr_number": 3,
            "head": HEAD,
            "base": BASE,
            "tree": TREE,
            "status": "PR_OPEN",
            "branch": "codex/sync",
        }
        return state

    def test_ordinary_pr_only_publishes_status(self):
        result = self.fixture.collect()
        state = sync.initial_state()
        with (
            patch.object(sync, "verify_target"),
            patch.object(sync, "load_state", return_value=(state, BASE)),
        ):
            gate.finish(self.fixture, result)
        self.assertFalse(result["merged"])
        self.assertEqual(
            [item[1] for item in self.fixture.writes], ["statuses/" + HEAD]
        )

    def test_automatic_merge_is_normal_protected_merge(self):
        result, state = self.fixture.collect(), self.state()
        with (
            patch.object(sync, "verify_target"),
            patch.object(sync, "load_state", return_value=(state, BASE)),
            patch.object(gate, "active_rules", return_value=15368),
            patch.object(sync, "record_merged") as record,
        ):
            gate.finish(self.fixture, result)
        self.assertTrue(result["merged"])
        self.assertEqual(
            self.fixture.writes[-1],
            ("PUT", "pulls/3/merge", {"sha": HEAD, "merge_method": "merge"}),
        )
        record.assert_called_once_with(self.fixture, UPSTREAM, HEAD)

    def test_pause_wins_over_inflight_success(self):
        result, state = self.fixture.collect(), self.state()
        paused = copy.deepcopy(state)
        paused["merge_paused"] = True
        with (
            patch.object(sync, "verify_target"),
            patch.object(
                sync, "load_state", side_effect=[(state, BASE), (paused, HEAD)]
            ),
            patch.object(gate, "active_rules", return_value=15368),
        ):
            with self.assertRaisesRegex(ValueError, "paused"):
                gate.finish(self.fixture, result)
        self.assertFalse(
            any(item[1].endswith("/merge") for item in self.fixture.writes)
        )

    def test_status_evaluation_delay_is_retried_without_real_sleep(self):
        result, state = self.fixture.collect(), self.state()
        self.fixture.pr["mergeable_state"] = "blocked"
        waits = []

        def sleep(seconds):
            waits.append(seconds)
            self.fixture.pr["mergeable_state"] = (
                "unstable" if len(waits) == 1 else "clean"
            )

        with (
            patch.object(sync, "verify_target"),
            patch.object(sync, "load_state", return_value=(state, BASE)),
            patch.object(gate, "active_rules", return_value=15368) as rules,
            patch.object(sync, "record_merged"),
        ):
            gate.finish(self.fixture, result, sleep=sleep)
        self.assertEqual(waits, [5, 5])
        rules.assert_called_once_with(self.fixture, state)
        self.assertTrue(result["merged"])

    def test_status_wait_is_bounded(self):
        result, state = self.fixture.collect(), self.state()
        self.fixture.pr["mergeable_state"] = "blocked"
        waits = []
        with (
            patch.object(sync, "verify_target"),
            patch.object(sync, "load_state", return_value=(state, BASE)),
        ):
            with self.assertRaisesRegex(ValueError, "six checks"):
                gate.finish(self.fixture, result, sleep=waits.append)
        self.assertEqual(waits, [5] * 5)
        self.assertFalse(
            any(item[1].endswith("/merge") for item in self.fixture.writes)
        )

    def test_pause_during_status_wait_stops_before_another_sleep(self):
        result, state = self.fixture.collect(), self.state()
        fresh = copy.deepcopy(state)
        self.fixture.pr["mergeable_state"] = "blocked"
        waits = []

        def sleep(seconds):
            waits.append(seconds)
            fresh["merge_paused"] = True

        with (
            patch.object(sync, "verify_target"),
            patch.object(sync, "load_state", side_effect=[
                (state, BASE), (fresh, BASE), (fresh, BASE),
            ]),
        ):
            with self.assertRaisesRegex(ValueError, "paused"):
                gate.finish(self.fixture, result, sleep=sleep)
        self.assertEqual(waits, [5])
        self.assertFalse(
            any(item[1].endswith("/merge") for item in self.fixture.writes)
        )

    def test_head_moving_during_status_wait_stops_immediately(self):
        result, state = self.fixture.collect(), self.state()
        self.fixture.pr["mergeable_state"] = "blocked"
        waits = []

        def sleep(seconds):
            waits.append(seconds)
            self.fixture.pr["head"]["sha"] = MERGE

        with (
            patch.object(sync, "verify_target"),
            patch.object(sync, "load_state", return_value=(state, BASE)),
        ):
            with self.assertRaisesRegex(ValueError, "base/head changed"):
                gate.finish(self.fixture, result, sleep=sleep)
        self.assertEqual(waits, [5])
        self.assertFalse(
            any(item[1].endswith("/merge") for item in self.fixture.writes)
        )

    def test_unrecorded_or_changed_controller_candidate_cannot_merge(self):
        result, state = self.fixture.collect(), self.state()
        state["tasks"][UPSTREAM]["head"] = BASE
        with (
            patch.object(sync, "verify_target"),
            patch.object(sync, "load_state", return_value=(state, BASE)),
        ):
            with self.assertRaises(ValueError):
                gate.finish(self.fixture, result)
        self.assertEqual(self.fixture.writes, [])


if __name__ == "__main__":
    unittest.main()
