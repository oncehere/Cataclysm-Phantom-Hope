"""Read-only deterministic QA for CPH Gemini and offline agent proposals."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import tomllib

import polib

from pokeeper.catalog import entry_id, index
from audit_translations import review_pair


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("candidate", type=Path, help="complete PO Keeper candidate directory")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    root = Path(__file__).resolve().parent
    config = tomllib.loads((root / "project.toml").read_text())
    patterns = [re.compile(s) for s in config.get("rules", {}).get("token_patterns", [])]
    source_index = json.loads((root / "qa-source-index.json").read_text())
    report = json.loads((args.candidate / "report.json").read_text())
    state = json.loads((args.candidate / "state.json").read_text())
    po = polib.pofile(str(args.candidate / "candidate.po"), check_for_duplicates=False)
    entries = index(po)
    ai = []
    models = Counter()
    for key, record in state["entries"].items():
        ref = state["references"].get(record.get("source"))
        if ref and ref.get("kind") in ("gemini", "external"):
            ai.append({"id": key})
            models[ref["kind"] + ": " + ref.get("name", "unknown")] += 1
    checks = Counter()
    flags = []
    for row in ai:
        source = source_index.get(row["id"])
        entry = entries.get(row["id"])
        if source is None or entry is None:
            flags.append({"id": row["id"], "issue": "identity_not_found"})
            continue
        checks["completed_entries"] += 1
        originals = [s for s in source["identity"][1:3] if s is not None]
        translations = list(entry.msgstr_plural.values()) if entry.msgid_plural else [entry.msgstr]
        for variant, target in enumerate(translations):
            alternatives = [review_pair(src, target, source.get("flags", []), patterns) for src in originals]
            findings = min(alternatives, key=lambda items: (sum(f["level"] == "difference" for f in items), len(items)))
            if target.count("\n") not in [src.count("\n") for src in originals]:
                findings.append({"kind": "newline_count_review", "level": "difference"})
            if findings:
                flags.append({"id": row["id"], "variant": variant, "findings": findings})
    result = {"version": 2, "candidate": str(args.candidate.resolve()), "checks": dict(checks),
              "proposal_sources": dict(models),
              "review_flags": flags,
              "remaining_gaps": len(report.get("gaps", [])),
              "provider_results": dict(Counter(r["status"] for r in report.get("gemini", []))),
              "external_batches": dict(Counter(r["status"] for r in report.get("external", []))),
              "limitation": "Review flags require contextual judgment. This is not full semantic or human acceptance."}
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
