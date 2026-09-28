#!/usr/bin/env python3
"""Run policy-selected tool checks on an exact, disposable merge checkout.

The controller comes from main. Candidate tests run without credentials, and
their bounded JSON reports are data for the separate trusted collector.
"""

import argparse
import json
import os
from pathlib import Path
import platform
import sys
import unittest


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def run_suite(directory, excluded_prefixes, output):
    # build() launches this trusted script with the candidate as cwd. Nested
    # discovery adds only its test directory; package imports need that root.
    # Do not preload controller modules in this unprivileged subprocess.
    sys.path.insert(0, str(Path.cwd()))
    discovered = list(
        flatten(
            unittest.defaultTestLoader.discover(directory, pattern="test_*.py")
        )
    )
    excluded = sorted(
        test.id()
        for test in discovered
        if test.id().startswith(tuple(excluded_prefixes))
    )
    selected = [test for test in discovered if test.id() not in excluded]
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestSuite(selected)
    )
    counts = {
        "tests": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "expected_failures": len(result.expectedFailures),
        "unexpected_successes": len(result.unexpectedSuccesses),
    }
    passed = counts["tests"] > 0 and not any(
        value for key, value in counts.items() if key != "tests"
    )
    output.write_text(
        json.dumps(
            {
                "directory": directory,
                "pattern": "test_*.py",
                "excluded_prefixes": excluded_prefixes,
                "excluded_tests": excluded,
                "selected_tests": sorted(test.id() for test in selected),
                "selected_count": len(selected),
                "excluded_count": len(excluded),
                "status": "PASS" if passed else "FAIL",
                **counts,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return 0 if passed else 1


def build(source, evidence):
    # The suite subcommand must not preload project module names: candidate
    # tests need to import their own ci_build and its transitive dependencies.
    import ci_build

    source, evidence = source.resolve(), evidence.resolve()
    if evidence.exists() or evidence.is_relative_to(source):
        raise ValueError("tooling evidence must be fresh and outside source")
    evidence.mkdir(parents=True)
    report = {
        "schema_version": 1,
        "kind": "cph-tooling-ci",
        "status": "FAIL",
        "suites": [],
        "checks": [],
    }
    try:
        identity = json.loads(os.environ["CPH_CI_PLAN"])
        report["identity"] = identity
        policy_path = ci_build.CONTROL / "project/check-policy.json"
        if identity["policy_sha"] != ci_build.digest(policy_path):
            raise ValueError("control policy changed")
        policy = json.loads(policy_path.read_text())["tooling"]
        report["python_version"] = platform.python_version()
        if report["python_version"] != policy["python_version"]:
            raise ValueError("tooling Python version differs from policy")
        environment = ci_build.clean_environment()
        ci_build.verify_checkout(source, environment, identity)
        if (
            ci_build.git(ci_build.CONTROL, environment, "rev-parse", "HEAD") !=
            identity["control_sha"]
        ):
            raise ValueError("unexpected control checkout")
        runner = ci_build.Runner(evidence, environment)
        requirements = ci_build.CONTROL / policy["requirements"]
        report["requirements_sha256"] = ci_build.digest(requirements)
        # Install the trusted dependency set before any candidate code runs.
        runner.run(
            "dependencies",
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-r",
                requirements,
            ],
            evidence,
        )
        for name, config in policy["suites"].items():
            filename = name + ".json"
            runner.run(
                name,
                [
                    sys.executable,
                    Path(__file__).resolve(),
                    "suite",
                    "--directory",
                    config["directory"],
                    "--excluded",
                    json.dumps(config["excluded_prefixes"]),
                    "--output",
                    evidence / filename,
                ],
                source,
            )
            report["suites"].append(
                {
                    "name": name,
                    "report": filename,
                    "sha256": ci_build.digest(evidence / filename),
                }
            )
        for name, arguments in policy["checks"].items():
            runner.run(name, [sys.executable, *arguments], source)
            report["checks"].append(name)
        ci_build.verify_checkout(source, environment, identity)
        report["status"] = "PASS"
    except Exception as error:
        report["error"] = type(error).__name__ + ": " + str(error)
        print(report["error"], file=sys.stderr)
    finally:
        ci_build.write_json(evidence / "tooling-report.json", report)
    return 0 if report["status"] == "PASS" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    suite = sub.add_parser("suite")
    suite.add_argument("--directory", required=True)
    suite.add_argument("--excluded", default="[]")
    suite.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("build")
    run.add_argument("--source", type=Path, required=True)
    run.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "suite":
        return run_suite(
            args.directory, json.loads(args.excluded), args.output
        )
    return build(args.source, args.evidence)


if __name__ == "__main__":
    sys.exit(main())
