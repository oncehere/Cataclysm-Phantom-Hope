#!/usr/bin/env python3
"""Validate context routing in memory or export an on-demand JSON report.

The default prints JSON; --output exports it. --check validates the current
cases without writing, and --check --output also rejects a stale export.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema

from build_context_pack import (
    ROOT, build_pack, documentation_paths, load_yaml, pattern_exists,
    tracked_paths,
)


def benchmark() -> dict:
    definition = load_yaml(ROOT / "ai/agent-benchmark.yml")
    schema = json.loads(
        (ROOT / "ai/agent-benchmark.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(definition)
    known = tracked_paths()
    registry = load_yaml(ROOT / "ai/documentation-registry.yml")
    test_matrix = load_yaml(ROOT / "ai/test-matrix.yml")
    known_commands = {entry["command"] for entry in test_matrix["entries"]}
    cases = []
    expected_path_count = 0
    path_hit_count = 0
    hallucinated_paths = 0
    hallucinated_commands = 0
    upstream_divergence_regressions = 0
    unrelated_changes = 0

    for case in definition["cases"]:
        documentation_paths(
            case["expected_documentation_ids"], registry, known,
        )
        # Exercise automatic routing; a case ID must not force its own answer.
        pack = build_pack(case["task"], [], case["files"], 8000)
        routes = set(pack["selected_routes"])
        paths = set(pack["source_paths"])
        docs = set(pack["documentation_ids"])
        validations = {entry["id"] for entry in pack["tests"]}
        agents = {entry["path"] for entry in pack["agents"]}
        path_hits = sorted(set(case["expected_paths"]) & paths)
        expected_path_count += len(case["expected_paths"])
        path_hit_count += len(path_hits)
        hallucinated_paths += sum(
            1 for pattern in paths if not pattern_exists(pattern, known)
        )
        hallucinated_commands += sum(
            1 for entry in pack["tests"]
            if entry["command"] not in known_commands
        )
        if case["id"] == "upstream-port" and not pack["upstream_differences"]:
            upstream_divergence_regressions += 1
        errors = []
        for label, expected, actual in (
            ("routes", set(case["expected_routes"]), routes),
            ("paths", set(case["expected_paths"]), paths),
            ("documentation", set(case["expected_documentation_ids"]), docs),
            ("validation", set(case["expected_validation_ids"]), validations),
            ("agents", set(case.get("expected_agents", [])), agents),
        ):
            missing = sorted(expected - actual)
            if missing:
                errors.append(f"missing {label}: {', '.join(missing)}")
        for label, forbidden, actual in (
            ("routes", set(case.get("forbidden_routes", [])), routes),
            ("validation", set(case.get("forbidden_validation_ids", [])),
             validations),
            ("agents", set(case.get("forbidden_agents", [])), agents),
        ):
            unexpected = sorted(forbidden & actual)
            unrelated_changes += len(unexpected)
            if unexpected:
                errors.append(f"unexpected {label}: {', '.join(unexpected)}")
        cases.append(
            {
                "id": case["id"],
                "passed": not errors,
                "errors": errors,
                "selected_routes": pack["selected_routes"],
                "estimated_tokens": pack["estimated_tokens"],
            }
        )

    passed = sum(1 for case in cases if case["passed"])
    return {
        "schema_version": 1,
        "generated_by": "python3 tools/agent/benchmark_context_pack.py",
        "case_count": len(cases),
        "metrics": {
            "correct_path_hit_rate": (
                path_hit_count / expected_path_count
                if expected_path_count else 1.0
            ),
            "hallucinated_paths": hallucinated_paths,
            "hallucinated_commands": hallucinated_commands,
            "unrelated_changes": unrelated_changes,
            "first_pass_validation": passed / len(cases) if cases else 1.0,
            "upstream_divergence_regressions": upstream_divergence_regressions,
        },
        "cases": cases,
    }


def serialized(report: dict) -> str:
    return (json.dumps(report, ensure_ascii=False,
                       indent=2, sort_keys=True) + "\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true",
        help="validate without writing; compare --output if given",
    )
    parser.add_argument("--output", type=Path,
                        help="explicit JSON export path (default: stdout)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = benchmark()
        output = serialized(report)
        if args.check:
            if args.output is not None and (
                not args.output.is_file() or
                args.output.read_text(encoding="utf-8") != output
            ):
                print(
                    f"stale benchmark report: {args.output}", file=sys.stderr,
                )
                return 1
        elif args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output, encoding="utf-8")
        else:
            sys.stdout.write(output)
    except (OSError, ValueError, jsonschema.ValidationError) as error:
        print(error, file=sys.stderr)
        return 2
    print(
        f"agent benchmark: {sum(case['passed'] for case in report['cases'])}/"
        f"{report['case_count']} cases", file=sys.stderr,
    )
    return 0 if all(case["passed"] for case in report["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
