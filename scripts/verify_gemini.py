#!/usr/bin/env python3
"""Explicit, potentially billable two-entry Gemini acceptance probe.

Uses the production fill workflow and SDK transport, with zero automatic retries.
Credentials enter only through a hidden terminal prompt or GEMINI_API_KEY.
"""

import argparse
import getpass
import json
import os
from pathlib import Path
import sys

import polib

from pokeeper.catalog import serialize
from pokeeper.core import check
from pokeeper.gemini import fill, _google_transport
from pokeeper.transaction import apply_candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--workdir", required=True, type=Path)
    args = parser.parse_args()
    root = args.workdir.absolute()
    root.mkdir(parents=True, exist_ok=False)
    if not os.environ.get("GEMINI_API_KEY"):
        if not sys.stdin.isatty():
            parser.error("use a terminal for hidden key entry, or set GEMINI_API_KEY")
        os.environ["GEMINI_API_KEY"] = getpass.getpass("Gemini API key (hidden): ")
    po = polib.POFile()
    po.metadata = {"Content-Type": "text/plain; charset=UTF-8", "Project-Id-Version": "pokeeper-live-probe"}
    po.append(polib.POEntry(msgctxt="editor", msgid="Save", comment="Button to save the current document.",
                           occurrences=[("editor.c", "10")]))
    po.append(polib.POEntry(msgctxt="editor", msgid="%d file", msgid_plural="%d files",
                           msgstr_plural={0: "", 1: "", 2: ""}, flags=["c-format"],
                           comment="A count of open files. Preserve the printf argument.",
                           occurrences=[("editor.c", "20")]))
    (root / "messages.pot").write_bytes(serialize(po))
    config = root / "project.toml"
    config.write_text('''version = 1
project = "pokeeper-live-probe"
language = "pl"
plural_forms = "nplurals=3; plural=(n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<12 || n%100>14) ? 1 : 2);"
template = "messages.pot"
catalog = "output.po"
state = ".pokeeper/state.json"
[gemini]
model = ''' + json.dumps(args.model) + '''
batch_size = 2
retries = 0
timeout_seconds = 60
terms = { file = "plik" }
examples = [{source = "Open", translation = "Otwórz"}]
''', encoding="utf-8")
    attempts = 0
    result = {"status": "FAIL", "model": args.model, "entries_requested": 2,
              "automatic_retries": 0, "human_semantic_review": "NOT_RUN"}

    def counted_transport(model, prompt, timeout):
        nonlocal attempts
        attempts += 1
        return _google_transport(model, prompt, timeout)

    try:
        candidate = fill(config, root / "candidate", root / "cache.json", transport=counted_transport)
        report = json.loads((candidate / "report.json").read_bytes())
        result["gemini"] = report["gemini"]
        result["remaining_gaps"] = len(report["gaps"])
        if not report["gaps"] and len(report["gemini"]) == 2:
            apply_candidate(candidate)
            result["offline_check"] = check(config, root / "output.mo")
            result["status"] = "PASS"
    finally:
        os.environ.pop("GEMINI_API_KEY", None)
        result["transport_calls"] = attempts
        (root / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
