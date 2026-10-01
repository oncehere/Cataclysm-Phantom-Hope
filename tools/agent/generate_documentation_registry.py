#!/usr/bin/env python3
"""Generate the CPH documentation registry from tracked repository paths."""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "ai/documentation-registry.yml"
ORIGINS = ROOT / "ai/history/ccb-document-origins.yml"
GENERATED_FILES = ROOT / "ai/generated-files.yml"
ROOT_GOVERNANCE = {
    "AGENTS.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "GOVERNANCE.md",
    "ISSUES.md",
    "LABELS.md",
    "OWNERSHIP.md",
    "README.md",
    "REPOSITORY_SETTINGS.md",
    "SECURITY.md",
    "SUPPORT.md",
    "SYNC_EXCLUDED_PRS.md",
}
AGENT_METADATA = {
    "ai/agent-benchmark.schema.json",
    "ai/agent-benchmark.yml",
    "ai/context.schema.json",
    "ai/context-pack.schema.json",
    "ai/documentation-registry.schema.json",
    "ai/documentation-registry.yml",
    "ai/docs-impact.yml",
    "ai/generated-files.yml",
    "ai/lua-first-replacement-ledger.schema.json",
    "ai/lua-first-roadmap.schema.json",
    "ai/lua-first-roadmap.yml",
    "ai/project-map.yml",
    "ai/repository-settings.target.schema.json",
    "ai/repository-settings.target.yml",
    "ai/test-matrix.yml",
    "ai/task-router.schema.json",
    "ai/task-router.yml",
}
API_CONTRACTS = {
    "data/lua/types/ccb_platform_v1.d.lua",
    "data/lua/reference/ccb_platform_native_inventory.schema.json",
    "data/lua/reference/ccb_platform_api_v1.schema.json",
    "data/lua/reference/ccb_platform_api_v1_coverage.schema.json",
    "tools/json_api/contract-inventory.schema.json",
}
ARCHITECTURE_CONTRACTS = {
    "data/lua/LUA_FIRST_EOC_WORKFLOW.md",
    "data/lua/LUA_FIRST_PLATFORM.md",
}
CCB_DOCS_IDS = {
    "data/lua/LUA_FIRST_PLATFORM.md": [
        "architecture.lua-first-platform",
        "architecture.lua-first-glossary",
    ],
    "data/lua/LUA_FIRST_EOC_WORKFLOW.md": [
        "architecture.lua-first-eoc-workflow",
    ],
    "ai/lua-first-roadmap.yml": ["architecture.lua-first-roadmap"],
    "ai/lua-first-roadmap.schema.json": ["architecture.lua-first-roadmap"],
}
CURRENT_PLATFORM_DOCUMENTS = {
    "data/lua/README.md": "lua.platform.overview",
    "tools/lua_api/README.md": "tool-lua-platform-contract",
    "src/lua/README.md": "lua.vendoring",
    "data/mods/Lua_First_Example/README.md": "lua.platform.example",
    "data/mods/TEST_DATA/README.md": "test-data.overview",
    ".github/pull_request_template.md": "cph.contributing.pull-request",
    "tools/json_api/README.md": "tool-json-contract",
    "tools/lua_api/fixtures/native_probe/README.md": (
        "lua.platform.native-probe-fixture"
    ),
    "data/json/LOADING_ORDER.md": "json.loading-order",
}
CURRENT_CPH_DOCUMENTS = {
    "companion/README.md": "cph.companion",
    "companion/THIRD_PARTY.md": "cph.companion-provenance",
    "companion/docs/architecture.md": "cph.companion-architecture",
    "companion/docs/install.md": "cph.companion-install",
    "companion/docs/compatibility.md": "cph.companion-compatibility",
    "companion/docs/acceptance.md": "cph.companion-acceptance",
    "docs/project/ai-companion-monorepo.md": "cph.companion-monorepo",
    "docs/project/actor-control.md": "cph.actor-control",
    "docs/README.md": "cph.documentation-index",
    "tools/agent/README.md": "cph.agent-tools",
    "doc/JSON/JSON_INFO.md": "json.object-types",
    "doc/JSON/JSON_INHERITANCE.md": "json.inheritance",
    "doc/JSON/EFFECT_ON_CONDITION.md": "eoc.reference",
}
HISTORICAL_DOC_PATHS = {
    "doc/development_process.md",
    "doc/HOWTO_MASSAGE_MA_GUN_DATA.md",
    "doc/c++/COMPILING-CYGWIN.md",
    "doc/c++/COMPILING-FLATPAK.md",
    "doc/FREQUENTLY_MADE_SUGGESTIONS.md",
    "doc/GUN_NAMING_AND_INCLUSION.md",
    "tools/llama/README.md",
}
RETIRED_PLATFORM_MARKERS = (
    "cata" + "lua",
    "ccb_" + "native_inventory",
    "public_" + "api_" + "v" + "5",
    "c" + "b" + "n" + "_",
    "api_" + "v" + "5",
)


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout


def tracked_paths() -> list[str]:
    output = subprocess.run(
        ["git", "ls-files", "-z", "--cached"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout.decode("utf-8")
    paths = sorted(item for item in output.split("\0") if item)
    if any("obj-lua" in Path(path).parts for path in paths):
        raise RuntimeError("obj-lua must never enter documentation metadata")
    return paths


def is_documentation_path(path: str) -> bool:
    if path.lower().endswith(".md"):
        return True
    if (path.startswith("ai/history/") and
            path.endswith((".yml", ".yaml", ".json"))):
        return True
    if path in AGENT_METADATA or path in API_CONTRACTS:
        return True
    if path.startswith("data/lua/reference/") and path.endswith(".json"):
        return True
    if path.startswith("data/reference/json/") and path.endswith(".json"):
        return True
    if path.startswith("doc/migration/") and path.endswith((".json", ".yml")):
        return True
    return False


def registry_id(path: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")
    return "repo." + slug


def load_origins() -> dict[str, dict]:
    """Read retained IDs and attribution without historical Git objects."""
    data = yaml.safe_load(ORIGINS.read_text(encoding="utf-8"))
    if (data.get("schema_version") != 1 or
            data.get("kind") != "document_origins" or
            not re.fullmatch(r"[0-9a-f]{40}", data.get("source_commit", "")) or
            not data.get("source_inventory", "").startswith(
                "https://github.com/")):
        raise ValueError("invalid document origins source")
    origins = {}
    identifiers = set()
    for entry in data["documents"]:
        path = entry["path"]
        identifier = entry["stable_document_id"]
        if (not isinstance(path, str) or Path(path).is_absolute() or
                any(part in {"..", "obj-lua"}
                    for part in Path(path).parts)):
            raise ValueError("invalid document origin path")
        if (not isinstance(identifier, str) or not identifier or
                not isinstance(entry.get("license"), str) or
                not entry["license"] or
                not isinstance(entry.get("contributors"), list) or
                any(not isinstance(name, str) or not name.strip()
                    for name in entry["contributors"])):
            raise ValueError(f"missing document ID or attribution: {path}")
        if path in origins or identifier in identifiers:
            raise ValueError("duplicate document origin path or ID")
        target = entry.get("ccb_docs_id")
        if target is not None and (not isinstance(target, str) or not target):
            raise ValueError(f"invalid historical documentation ID: {path}")
        identifiers.add(identifier)
        origins[path] = entry
    return origins


def generated_by(
    path: str, declarations: list[dict] | None = None,
) -> str | None:
    if declarations is None:
        declarations = yaml.safe_load(
            GENERATED_FILES.read_text(encoding="utf-8")
        )["entries"]
    matches = [entry for entry in declarations if any(
        fnmatch.fnmatchcase(path, pattern) for pattern in entry["paths"]
    )]
    if len(matches) > 1:
        raise ValueError(f"ambiguous generated-file declarations: {path}")
    return matches[0]["generated_by"] if matches else None


def is_retired_platform_path(path: str) -> bool:
    lowered = path.lower()
    return path.startswith(("data/lua/", "tools/lua_api/", "doc/")) and any(
        marker in lowered for marker in RETIRED_PLATFORM_MARKERS
    )


def classify(path: str, legacy: dict[str, dict],
             declarations: list[dict] | None = None) -> dict:
    historical = legacy.get(path)
    retired = is_retired_platform_path(path) or path in HISTORICAL_DOC_PATHS
    current_platform = path in CURRENT_PLATFORM_DOCUMENTS
    generator = None if retired else generated_by(path, declarations)
    if (retired or path.startswith("ai/history/") or
            path.startswith("doc/migration/") or
            path.startswith("doc/design-balance-lore/") or
            path.startswith(".deepcode/plans/") or
            path.startswith("companion/docs/evidence/")):
        category = "historical_document"
        status = "historical"
        authority = "historical"
        source_of_truth = False
    elif current_platform:
        category = "maintained_document"
        status = "active"
        authority = "explanatory"
        source_of_truth = False
    elif path.endswith("AGENTS.md"):
        category = "agent_instruction"
        status = "active"
        authority = "governance_contract"
        source_of_truth = True
    elif generator:
        category = "generated_document"
        status = "generated"
        authority = "generated_contract"
        source_of_truth = True
    elif path in ROOT_GOVERNANCE or path in AGENT_METADATA:
        category = "authoritative_document"
        status = "active"
        authority = "governance_contract"
        source_of_truth = True
    elif path == "docs/project/execution-spec.md":
        category = "authoritative_document"
        status = "active"
        authority = "governance_contract"
        source_of_truth = True
    elif (path in CURRENT_CPH_DOCUMENTS or
          path.startswith("docs/project/") or path.startswith("doc/")):
        category = "maintained_document"
        status = "active"
        authority = "explanatory"
        source_of_truth = False
    elif path.startswith("data/json/") and path.endswith(".md"):
        category = "maintained_document"
        status = "active"
        authority = "explanatory"
        source_of_truth = False
    elif path in ARCHITECTURE_CONTRACTS:
        category = "authoritative_document"
        status = "active"
        authority = "architecture_contract"
        source_of_truth = True
    elif path in API_CONTRACTS:
        category = "api_contract"
        status = "active"
        authority = "api_contract"
        source_of_truth = True
    elif path.startswith("data/lua/templates/") and path.endswith(".md"):
        category = "maintained_document"
        status = "active"
        authority = "explanatory"
        source_of_truth = False
    elif path.startswith("src/third-party/") or path == "src/lua/LICENSE.md":
        category = "third_party_document"
        status = "third_party"
        authority = "third_party"
        source_of_truth = False
    elif path.startswith("data/mods/") and path.endswith(".md"):
        category = "third_party_document"
        status = "third_party"
        authority = "third_party"
        source_of_truth = False
    elif historical:
        category = "historical_document"
        status = "historical"
        authority = "historical"
        source_of_truth = False
    else:
        category = "historical_document"
        status = "historical"
        authority = "historical"
        source_of_truth = False

    stable_document_id = (
        CURRENT_PLATFORM_DOCUMENTS.get(path) or
        CURRENT_CPH_DOCUMENTS.get(path) or
        (historical.get("stable_document_id") if historical else None)
    )
    ccb_docs_ids = []
    if current_platform:
        ccb_docs_ids = (
            ["architecture.lua-first-platform"]
            if path == "data/lua/README.md"
            else []
        )
    elif not retired and historical and historical.get("ccb_docs_id"):
        ccb_docs_ids.append(historical["ccb_docs_id"])
    ccb_docs_ids.extend(CCB_DOCS_IDS.get(path, []))
    return {
        "id": registry_id(path),
        "path": path,
        "category": category,
        "status": status,
        "authority": authority,
        "source_of_truth": source_of_truth,
        "stable_document_id": stable_document_id,
        "ccb_docs_ids": ccb_docs_ids,
        "generated": generator is not None,
        "generated_by": generator,
        "include_in_ai_index": status == "active",
    }


def build_registry(source_commit: str) -> dict:
    legacy = load_origins()
    declarations = yaml.safe_load(
        GENERATED_FILES.read_text(encoding="utf-8")
    )["entries"]
    entries = [
        classify(path, legacy, declarations)
        for path in tracked_paths()
        if is_documentation_path(path)
    ]
    return {
        "schema_version": 1,
        "kind": "documentation_registry",
        "source_commit": source_commit,
        "scope": (
            "Tracked documentation and machine contracts from the Git index; "
            "untracked build caches are never traversed."
        ),
        "entry_count": len(entries),
        "entries": entries,
    }


def render(data: dict) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source-commit", default="HEAD")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    output = args.output if args.output.is_absolute() else ROOT / args.output
    if args.check:
        existing = yaml.safe_load(output.read_text(encoding="utf-8"))
        source_commit = git(
            "rev-parse", "--verify", f"{existing['source_commit']}^{{commit}}"
        ).strip()
    else:
        source_commit = git(
            "rev-parse", "--verify", f"{args.source_commit}^{{commit}}"
        ).strip()
    data = build_registry(source_commit)
    rendered = render(data)

    if args.check:
        if output.read_text(encoding="utf-8") != rendered:
            print(
                f"stale documentation registry: {output.relative_to(ROOT)}",
                file=sys.stderr,
            )
            return 1
        print(f"documentation registry is current ({source_commit})")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(f"wrote {output.relative_to(ROOT)} ({len(data['entries'])} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
