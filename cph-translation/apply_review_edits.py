"""Apply only the identity- and before-value-checked edits in review-edits.json."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "src"))
from pokeeper.catalog import entry_id, index, parse_po, serialize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the validated edits to po/zh_CN.po")
    args = parser.parse_args()
    data = json.loads((ROOT / "review-edits.json").read_text())
    path = ROOT / "po/zh_CN.po"
    original = path.read_bytes()
    po = parse_po(original, str(path))
    entries = index(po)
    changes = []
    for edit in data["edits"]:
        entry = entries.get(edit["id"])
        if entry is None or entry.msgstr != edit["expected"]:
            raise SystemExit(f"input mismatch for reviewed entry {edit['id']}")
        changes.append({"id": edit["id"], "before": entry.msgstr, "after": edit["translation"],
                        "reason": edit["reason"]})
    for edit in data["edits"]:
        entries[edit["id"]].msgstr = edit["translation"]
    if args.apply:
        path.write_bytes(serialize(po))
    print(json.dumps({"status": "PASS", "applied": args.apply, "edits": changes},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
