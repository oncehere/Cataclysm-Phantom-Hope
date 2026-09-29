#!/usr/bin/env python3
"""Read-only CPH review of completed Gemini cache records (Python 3.11+).

No model calls, PO changes or automatic corrections.  Differences are review
evidence, not a claim that a translation is linguistically wrong.  Run with
--self-test for the small regression suite, or no arguments to audit this folder.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import tomllib
import unicodedata


# Mask printf argument indexes/width/precision only for actual format entries.
# This is the same syntax recognized by POKeeper's existing format validator.
PRINTF = re.compile(r"%(?:\([^)]+\)|\d+\$)?[-+#0 ']*(?:\d+|\*(?:\d+\$)?)?(?:\.(?:\d+|\*(?:\d+\$)?))?(?:hh|ll|[hlLjzt])?[diouxXeEfFgGaAcspn%]")
NUMBER = re.compile(r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?")
COLOR = re.compile(r"<color_[A-Za-z0-9_%]+>|</color>")
WORD = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")
CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
NOTE = re.compile(r"(?:译者(?:注|按|吐槽)|翻译(?:说明|注释)|作为(?:一个|一名)?(?:AI|人工智能)|以下(?:是|为)(?:本句|该句|中文)?(?:翻译|译文)|(?:抱歉|对不起)[，,:：\s]*(?:我无法|无法翻译))", re.I)
SOURCE_NOTE = re.compile(r"\b(?:translator|translation|as an? (?:AI|language model)|cannot translate)\b", re.I)


def normalized_text(text: str, flags: list[str]) -> str:
    text = unicodedata.normalize("NFKC", text).replace("−", "-")
    if any(flag in flags for flag in ("c-format", "python-format")):
        text = PRINTF.sub(lambda m: "%" if m.group() == "%%" else " ", text)
    return text


def number_value(value: str) -> str:
    return format(Decimal(value.replace(",", "")).normalize(), "f")


def numbers(text: str) -> Counter:
    result = Counter()
    for match in NUMBER.finditer(text):
        value = match.group()
        start = match.start()
        # 5-10 is a range; -10 or (+10) is a signed quantity.  A hyphen
        # following a word (e.g. model-10) is not a negative sign either.
        if start and text[start - 1] in "+-":
            before_sign = text[start - 2] if start >= 2 else ""
            if not before_sign or not before_sign.isalnum():
                value = text[start - 1] + value
        result[number_value(value)] += 1
    return result


def percentages(text: str) -> Counter:
    result = Counter()
    occupied_percent = set()
    for match in NUMBER.finditer(text):
        following = re.match(r"\s*(%|percent\b|per\s+cent\b)", text[match.end():], re.I)
        preceding = re.search(r"百分之\s*$", text[:match.start()])
        if following or preceding:
            result[number_value(match.group())] += 1
            if following and following.group(1) == "%":
                occupied_percent.add(match.end() + following.end() - 1)
    # Detect an added/dropped literal percent sign even without a numeric
    # literal, such as a formatted value.  English "percentage points" is
    # deliberately not treated as a literal percent sign.
    result["unattached_%"] = sum(ch == "%" and i not in occupied_percent for i, ch in enumerate(text))
    return +result


def color_structure(text: str) -> dict:
    tags = COLOR.findall(text)
    depth = unmatched_closes = 0
    for tag in tags:
        if tag == "</color>":
            if depth:
                depth -= 1
            else:
                unmatched_closes += 1
        else:
            depth += 1
    return {"tags": tags, "opens": sum(t != "</color>" for t in tags),
            "closes": tags.count("</color>"), "unmatched_closes": unmatched_closes,
            "unclosed_opens": depth}


def review_pair(source: str, target: str, flags: list[str], patterns: list[re.Pattern]) -> list[dict]:
    findings = []

    def difference(kind: str, before, after) -> None:
        if before != after:
            findings.append({"kind": kind, "level": "difference", "source": before, "translation": after})

    original = normalized_text(source, flags)
    translated = normalized_text(target, flags)
    # Runtime tags can contain numeric arguments; compare them separately so
    # their digits are not counted as translated prose too.
    for index, pattern in enumerate(patterns):
        difference("runtime_tags", dict(Counter(m.group() for m in pattern.finditer(source))),
                   dict(Counter(m.group() for m in pattern.finditer(target))))
        if findings and findings[-1]["kind"] == "runtime_tags" and "pattern_index" not in findings[-1]:
            findings[-1]["pattern_index"] = index
        original = pattern.sub(" ", original)
        translated = pattern.sub(" ", translated)
    difference("arabic_numbers", dict(numbers(original)), dict(numbers(translated)))
    difference("percentages", dict(percentages(original)), dict(percentages(translated)))

    before_color, after_color = color_structure(source), color_structure(target)
    if before_color != after_color:
        findings.append({"kind": "color_structure", "level": "difference",
                         "source": before_color, "translation": after_color,
                         "source_already_unbalanced": bool(before_color["unmatched_closes"] or before_color["unclosed_opens"])})

    before_words, after_words = WORD.findall(original.lower()), WORD.findall(translated.lower())
    if len(before_words) >= 8 and len(after_words) >= 8 and not CJK.search(translated):
        findings.append({"kind": "possibly_untranslated_english", "level": "review",
                         "reason": "At least eight English words and no CJK characters; names, quotations or code may be intentional."})
    elif len(before_words) >= 10 and len(after_words) >= 10:
        source_phrases = {tuple(before_words[i:i + 10]) for i in range(len(before_words) - 9)}
        if any(tuple(after_words[i:i + 10]) in source_phrases for i in range(len(after_words) - 9)):
            findings.append({"kind": "possibly_untranslated_english", "level": "review",
                             "reason": "A sequence of ten source English words remains; an intentional quotation is possible."})
    if NOTE.search(target) and not (NOTE.search(source) or SOURCE_NOTE.search(source)):
        findings.append({"kind": "possible_translator_commentary", "level": "review",
                         "reason": "Translation/explanation or AI wording absent from the source; inspect in context."})
    if "```" in target and "```" not in source:
        findings.append({"kind": "possible_added_code_fence", "level": "review",
                         "reason": "Markdown code fencing was added; inspect whether the game actually expects it."})
    return findings


def audit(index: dict, cache: dict, config: dict, limit: int | None = None) -> dict:
    patterns = [re.compile(p) for p in config.get("rules", {}).get("token_patterns", [])]
    by_kind, by_level = Counter(), Counter()
    results = []
    complete = sorted((key, record) for key, record in cache["entries"].items() if record.get("status") == "complete")
    all_complete_count = len(complete)
    if limit is not None:
        complete = complete[:limit]
    matched = variants = unbalanced_sources = 0
    entry_ids = []
    for cache_key, record in complete:
        scope = record.get("scope", [])
        entry_id = scope[2] if isinstance(scope, list) and len(scope) == 3 else None
        entry_ids.append(entry_id)
        source = index.get(entry_id)
        values = record.get("values")
        if source is None or not isinstance(values, list) or not values or any(not isinstance(v, str) for v in values):
            results.append({"cache_key": cache_key, "entry_id": entry_id, "findings": [{"kind": "unmatched_or_malformed_complete_record", "level": "review"}]})
            by_kind["unmatched_or_malformed_complete_record"] += 1
            by_level["review"] += 1
            continue
        matched += 1
        identity = source["identity"]
        plural_sources = [identity[1]] + ([identity[2]] if identity[2] is not None else [])
        if any(color_structure(s)["unmatched_closes"] or color_structure(s)["unclosed_opens"] for s in plural_sources):
            unbalanced_sources += 1
        for variant, translation in enumerate(values):
            variants += 1
            # Chinese has a single plural form.  Where singular/plural source
            # invariants differ, accept a match with either and explicitly
            # record which comparison was selected.  Never assume variant 0
            # in every language corresponds to the English singular.
            alternatives = [review_pair(s, translation, source.get("flags", []), patterns) for s in plural_sources]
            chosen = min(range(len(alternatives)), key=lambda n: (sum(f["level"] == "difference" for f in alternatives[n]), len(alternatives[n])))
            findings = alternatives[chosen]
            if findings:
                results.append({"cache_key": cache_key, "entry_id": entry_id, "identity": identity,
                                "variant": variant, "source_variant_compared": "singular" if chosen == 0 else "plural",
                                "translation": translation, "locations": source.get("locations", []),
                                "findings": findings})
                by_kind.update(f["kind"] for f in findings)
                by_level.update(f["level"] for f in findings)
    return {"schema_version": 1, "status": "REVIEW_REQUIRED" if results else "NO_FLAGS_IN_COMPLETED_SNAPSHOT",
            "counts": {"source_index_entries": len(index), "cache_records": len(cache["entries"]),
                       "cache_statuses": dict(Counter(r.get("status", "missing") for r in cache["entries"].values())),
                       "complete_records_in_cache": all_complete_count,
                       "complete_records": len(complete), "matched_complete_records": matched,
                       "unique_complete_entry_ids": len(set(entry_ids)), "translation_variants_checked": variants,
                       "flagged_records_or_variants": len(results), "source_color_imbalance_records": unbalanced_sources,
                       "findings_by_kind": dict(by_kind), "findings_by_level": dict(by_level)},
            "selection": {"limit": limit, "order": "cache key sorted", "excluded_complete_records": all_complete_count - len(complete)},
            "runtime_tag_patterns": [p.pattern for p in patterns], "results": results,
            "limitations": ["Only complete cache records in this read snapshot are checked; failed/unknown/inflight records are not translations.",
                            "No PO or cache entries were modified. No numerical differences were corrected.",
                            "Differences require review: Chinese numerals, unit conversions, quotations and names may be intentional.",
                            "Unchanged pre-existing source color imbalance is accepted and counted, not treated as a new translation defect.",
                            "For plural entries, comparison with either source form may satisfy the checks; this is not plural-semantic validation.",
                            "These checks do not establish linguistic quality or full translation acceptance."]}


def self_test() -> None:
    tag = re.compile(r"</?\w+>")
    def kinds(source, target, flags=None):
        return {f["kind"] for f in review_pair(source, target, flags or [], [tag])}
    assert not kinds("%1$s: 1,000 at 25 percent", "%s：１０００，百分之２５", ["c-format"])
    assert not kinds("Range 5-10", "范围5～10")
    assert "arabic_numbers" in kinds("-5 damage", "5点伤害")
    assert "percentages" in kinds("50%", "50")
    assert not kinds("<color_red>danger", "<color_red>危险")
    assert "color_structure" in kinds("<color_red>danger", "<color_red>危险</color>")
    assert "color_structure" in kinds("<color_red>x</color>", "</color>x<color_red>")
    assert "runtime_tags" in kinds("<npc_name> waves", "<name>挥手")
    assert not kinds("M4A1 5.56 mm", "M4A1 5.56毫米")
    assert "possibly_untranslated_english" in kinds("This is a long example sentence that has been left untranslated.", "This is a long example sentence that has been left untranslated.")
    assert "possible_translator_commentary" in kinds("Hello", "你好。（译者注：这句很简单。）")
    assert "possible_translator_commentary" not in kinds("Translator note: hello", "译者注：你好")
    data = audit({"id": {"identity": [None, "1 item", "2 items"], "flags": []}},
                 {"entries": {"done": {"status": "complete", "scope": ["p", "zh_CN", "id"], "values": ["2个"]},
                              "pending": {"status": "inflight", "scope": ["p", "zh_CN", "id"]}}}, {})
    assert data["counts"]["complete_records"] == 1 and not data["results"]
    print("PASS: 13 QA regression checks; no model, PO or cache access")


def main() -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-index", type=Path, default=root / "qa-source-index.json")
    parser.add_argument("--cache", type=Path, default=root / ".pokeeper/gemini-cache.json")
    parser.add_argument("--config", type=Path, default=root / "project.toml")
    parser.add_argument("--output", type=Path, default=root / "qa-automatic.json")
    parser.add_argument("--limit", type=int, help="audit only this many completed records, sorted by cache key")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.limit is not None and args.limit < 1:
        parser.error("limit must be positive")
    paths = {"source_index": args.source_index, "cache": args.cache, "config": args.config}
    for path in paths.values():
        if args.output.resolve() == path.resolve() or (args.output.exists() and os.path.samefile(args.output, path)):
            parser.error("output must not alias an input")
    snapshots = {name: path.read_bytes() for name, path in paths.items()}
    report = audit(json.loads(snapshots["source_index"]), json.loads(snapshots["cache"]),
                   tomllib.loads(snapshots["config"].decode("utf-8")), args.limit)
    report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["command"] = [sys.executable, *sys.argv]
    report["inputs"] = {name: {"path": str(paths[name].resolve()), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)} for name, data in snapshots.items()}
    report["inputs_changed_during_audit"] = [name for name, path in paths.items() if path.read_bytes() != snapshots[name]]
    report["checks_execution"] = "PASS"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=args.output.parent, prefix=".qa-", suffix=".json", delete=False, encoding="utf-8") as handle:
        temporary = Path(handle.name)
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temporary, args.output)
    print(json.dumps({"output": str(args.output), "status": report["status"], "counts": report["counts"],
                      "inputs_changed_during_audit": report["inputs_changed_during_audit"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
