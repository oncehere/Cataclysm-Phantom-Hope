"""Exact reuse, translation-only human change detection, and provenance."""

import copy
import json
from pathlib import Path

import polib

from .catalog import (blank, entry_id, entry_problem, gettext_check, identity, index,
                      json_bytes, parse_po, serialize, translation_digest, values)
from .config import KeeperError, checked_output_path, load_config, plural_rule
from .transaction import (assert_no_pending, check_inputs, digest, file_digest,
                          publish_candidate)


def read_inputs(cfg):
    paths = [cfg.path, cfg.resolve("template"), cfg.resolve("catalog"), cfg.resolve("state")]
    paths += [s["path"] for s in cfg.sources]
    raw = {str(p): p.read_bytes() if p.exists() else None for p in paths}
    hashes = {p: digest(b) if b is not None else None for p, b in raw.items()}
    # Configuration itself must be the version loaded by the caller.
    if load_config(cfg.path).data != cfg.data:
        raise KeeperError("configuration changed while loading")
    for p in [cfg.resolve("template")] + [s["path"] for s in cfg.sources]:
        if raw[str(p)] is None:
            raise KeeperError(f"missing required input: {p}")
    return raw, hashes


def load_state(cfg, raw, hashes):
    state_raw = raw[str(cfg.resolve("state"))]
    if state_raw is None:
        return None
    try:
        state = json.loads(state_raw)
        if state["version"] != 1 or state["project"] != cfg.data["project"] or state["language"] != cfg.data["language"]:
            raise KeeperError("state version/project/language mismatch")
        baseline_sha = state["baseline"]
        if len(baseline_sha) != 64 or any(c not in "0123456789abcdef" for c in baseline_sha):
            raise KeeperError("invalid baseline digest")
        baseline_path = cfg.snapshots / (baseline_sha + ".po")
        baseline = baseline_path.read_bytes()
        hashes[str(baseline_path)] = digest(baseline)
        if digest(baseline) != baseline_sha:
            raise KeeperError("state baseline snapshot hash mismatch")
        po = parse_po(baseline, "baseline")
        state["_baseline_active"] = set(index(po))
        baseline_rule = po.metadata.get("Plural-Forms", "")
        if plural_rule(state.get("plural_forms", baseline_rule)) != plural_rule(baseline_rule):
            raise KeeperError("state plural rule differs from baseline")
        state["plural_forms"] = baseline_rule
        all_entries = {**index(po, True), **index(po)}
        if set(all_entries) != set(state["entries"]):
            raise KeeperError("state entry set differs from baseline")
        for key, rec in state["entries"].items():
            e = all_entries[key]
            if rec["identity"] != identity(e) or rec["translation"] != translation_digest(e):
                raise KeeperError("state translation baseline mismatch")
            if not isinstance(rec["protected"], bool):
                raise KeeperError("invalid state protection value")
            if rec["source"] is not None and rec["source"] not in state["references"]:
                raise KeeperError("unknown state source reference")
        # Historical references must still resolve to their original bytes.
        source_entries = {}
        snapshot_entries = {}
        snapshot_active = {}
        for refkey, ref in state["references"].items():
            sha = ref["sha256"]
            if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
                raise KeeperError("invalid source snapshot digest")
            p = cfg.snapshots / (sha + ".po")
            if sha not in snapshot_entries:
                actual = file_digest(p)
                hashes[str(p)] = actual
                if actual != sha:
                    raise KeeperError("missing or damaged historical source snapshot")
                source_po = parse_po(p.read_bytes(), "source snapshot")
                snapshot_active[sha] = set(index(source_po))
                snapshot_entries[sha] = {}
                for entry in source_po:
                    snapshot_entries[sha].setdefault(entry_id(entry), set()).add(translation_digest(entry))
            source_entries[refkey] = snapshot_entries[sha]
        for key, rec in state["entries"].items():
            if rec["source"] is None:
                continue
            ref = state["references"][rec["source"]]
            source = source_entries[rec["source"]]
            if rec["translation"] in source.get(key, ()):
                continue
            entry = all_entries[key]
            deletion = ref.get("kind") == "human" and ref.get("name") == "catalog deletion"
            empty = not entry.msgstr and not any(entry.msgstr_plural.values())
            if not (deletion and key not in snapshot_active[ref["sha256"]] and empty):
                raise KeeperError("state source snapshot does not contain the recorded translation")
        return state
    except (KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        raise KeeperError(f"state is incomplete or inconsistent ({type(exc).__name__}); restore matching state/snapshots") from None


def prepare(cfg, adopt_existing=None, unprotect=()):
    assert_no_pending(cfg.resolve("state"))
    raw, hashes = read_inputs(cfg)
    previous = load_state(cfg, raw, hashes)
    template = parse_po(raw[str(cfg.resolve("template"))], "template")
    current_raw = raw[str(cfg.resolve("catalog"))]
    if current_raw is None and previous:
        raise KeeperError("entire catalog is missing with existing state; restore it before planning")
    current = parse_po(current_raw, "catalog") if current_raw is not None else polib.POFile()
    if previous is None and any(e.msgstr or any(e.msgstr_plural.values()) for e in current) and adopt_existing not in ("protect", "reuse"):
        raise KeeperError("first adoption requires --adopt-existing protect or reuse")
    if previous is not None and adopt_existing is not None:
        raise KeeperError("--adopt-existing is only valid without a prior state")
    active = index(current)
    old_all = {**index(current, True), **active}
    records = copy.deepcopy(previous["entries"]) if previous else {}
    references = copy.deepcopy(previous["references"]) if previous else {}
    snapshots = {}
    report = {"version": 1, "project": cfg.data["project"], "updates": [], "conflicts": [],
              "gaps": [], "human_changes": [], "ignored": [], "removed": [], "unprotected": []}

    def check_language(po, name):
        language = po.metadata.get("Language", "").strip()
        if language and language.replace("-", "_") != cfg.data["language"].replace("-", "_"):
            raise KeeperError(f"{name} Language {language!r} differs from configured {cfg.data['language']!r}")
        if not language:
            report["ignored"].append({"source": name, "reason": "language_metadata_missing"})

    if current_raw is not None:
        check_language(current, "catalog")

    def ref_for(kind, name, data, revision=None):
        sha = digest(data)
        ref = {"kind": kind, "name": name, "sha256": sha}
        if revision is not None:
            ref["revision"] = revision
        key = digest(json_bytes(ref))
        references[key] = ref
        snapshots[sha] = data
        return key

    # Translation bytes only: wrapping, comments, fuzzy flags do not grant protection.
    for key, entry in old_all.items():
        before = records.get(key)
        changed = before is not None and translation_digest(entry) != before["translation"]
        new_human = previous is not None and before is None
        bootstrap = previous is None and adopt_existing == "protect"
        if changed or new_human or bootstrap:
            records[key] = {"identity": identity(entry), "translation": translation_digest(entry),
                            "protected": True, "source": ref_for("human", "catalog edit", current_raw)}
            report["human_changes"].append({"id": key, "kind": "edited" if before else "added"})
    target = index(template)
    for key in target:
        removed_active = previous and key in previous["_baseline_active"] and key not in active
        removed_any = previous and key in previous["entries"] and key not in old_all
        if removed_active or removed_any:
            entry = copy.deepcopy(target[key])
            blank(entry, cfg.nplurals)
            active[key] = entry
            records[key] = {"identity": identity(entry), "translation": translation_digest(entry),
                            "protected": True, "source": ref_for("human", "catalog deletion", current_raw)}
            report["human_changes"].append({"id": key, "kind": "deleted_restored_blank"})
    for key in unprotect:
        if key not in records:
            raise KeeperError(f"cannot unprotect unknown entry {key}")
        records[key]["protected"] = False
        report["unprotected"].append(key)

    donors = []
    for source in cfg.sources:
        data = raw[str(source["path"])]
        po = parse_po(data, source["name"])
        check_language(po, source["name"])
        ref = ref_for("upstream", source["name"], data, source.get("revision"))
        donors.append((source["name"], po, index(po), ref))
        for entry in po:
            if entry.obsolete:
                report["ignored"].append({"id": entry_id(entry), "source": source["name"], "reason": "obsolete"})
    output = polib.POFile()
    output.header = current.header or template.header
    output.metadata = dict(template.metadata)
    output.metadata.update(current.metadata)
    output.metadata.update({"Language": cfg.data["language"], "Plural-Forms": cfg.data["plural_forms"],
                            "Content-Type": "text/plain; charset=UTF-8", "Content-Transfer-Encoding": "8bit",
                            "MIME-Version": "1.0"})
    # Replace POT placeholders so msgfmt can perform its normal header checks.
    for field, fallback in (("Project-Id-Version", cfg.data["project"]), ("PO-Revision-Date", "1970-01-01 00:00+0000"),
                            ("Last-Translator", "Project maintainers"), ("Language-Team", cfg.data["language"])):
        if not output.metadata.get(field) or output.metadata[field] in ("PACKAGE VERSION", "YEAR-MO-DA HO:MI+ZONE", "FULL NAME <EMAIL@ADDRESS>", "LANGUAGE <LL@li.org>"):
            output.metadata[field] = fallback
    next_records = {}
    rules = cfg.data.get("rules", {})
    for key, original in target.items():
        out = copy.deepcopy(original)
        out.obsolete = False
        out.flags = [f for f in out.flags if f != "fuzzy"]
        blank(out, cfg.nplurals)
        existing = active.get(key)
        rec = records.get(key, {"protected": False, "source": None})
        if rec["protected"] and existing is None:
            # Protection survives a template temporarily removing this identity.
            existing = old_all.get(key)
        existing_rule = current.metadata.get("Plural-Forms", "")
        if previous and existing is not None and key in previous["entries"] and translation_digest(existing) == previous["entries"][key]["translation"]:
            existing_rule = previous["plural_forms"]
        selected = None
        source_ref = None
        if rec["protected"]:
            selected = existing
            source_ref = rec["source"]
            if existing is not None and existing.msgid_plural:
                try:
                    compatible = plural_rule(existing_rule) == plural_rule(cfg.data["plural_forms"])
                except KeeperError:
                    compatible = False
                if not compatible:
                    raise KeeperError(f"protected translation {key} has plural_rule_conflict; explicitly unprotect before changing plural rules")
            if existing and "fuzzy" in existing.flags:
                out.flags.append("fuzzy")
        else:
            for name, po, entries, ref in donors:
                if key not in entries:
                    continue
                donor = entries[key]
                issue = entry_problem(donor, po.metadata.get("Plural-Forms", ""), cfg.data["plural_forms"], rules, out)
                if issue:
                    category = "conflicts" if issue not in ("empty", "fuzzy") else "ignored"
                    report[category].append({"id": key, "source": name, "reason": issue})
                    continue
                if selected is None:
                    selected, source_ref = donor, ref
                elif values(donor) != values(selected):
                    report["conflicts"].append({"id": key, "source": name, "reason": "lower_priority_differs", "selected": source_ref})
            if selected is None and existing:
                issue = entry_problem(existing, existing_rule, cfg.data["plural_forms"], rules, out)
                if not issue:
                    selected = existing
                    source_ref = rec["source"] or ref_for("existing", "initial catalog", current_raw)
                else:
                    report["ignored"].append({"id": key, "source": "catalog", "reason": issue})
        if selected is not None:
            out.msgstr = selected.msgstr
            out.msgstr_plural = dict(selected.msgstr_plural)
        if existing:
            # Translator comments stay editable; source locations/developer notes follow POT.
            out.tcomment = existing.tcomment
        issue = entry_problem(out, cfg.data["plural_forms"], cfg.data["plural_forms"], rules)
        if issue:
            report["gaps"].append({"id": key, "identity": identity(out), "reason": issue, "protected": rec["protected"]})
            if rec["protected"] and issue not in ("empty", "fuzzy"):
                raise KeeperError(f"protected translation {key} is invalid: {issue}; correct the PO or explicitly unprotect it")
        if existing is None or values(existing) != values(out):
            report["updates"].append({"id": key, "identity": identity(out), "source": source_ref})
        next_records[key] = {"identity": identity(out), "translation": translation_digest(out),
                             "protected": rec["protected"], "source": source_ref}
        output.append(out)
    # Removed source identities remain visibly obsolete, never fuzzy-migrated.
    for key, entry in old_all.items():
        if key not in target:
            removed = copy.deepcopy(entry)
            removed.obsolete = True
            output.append(removed)
            rec = records.get(key, {})
            source = rec.get("source")
            if source is None and (removed.msgstr or any(removed.msgstr_plural.values())):
                source = ref_for("existing", "initial catalog", current_raw)
            next_records[key] = {"identity": identity(removed), "translation": translation_digest(removed),
                                 "protected": rec.get("protected", False), "source": source}
            if not entry.obsolete:
                report["removed"].append({"id": key, "identity": identity(entry)})
    state = {"version": 1, "project": cfg.data["project"], "language": cfg.data["language"], "plural_forms": cfg.data["plural_forms"],
             "baseline": None, "entries": next_records, "references": references}
    return output, state, report, snapshots, hashes


def finalize(cfg, candidate, output, state, report, snapshots, hashes):
    raw = serialize(output)
    # Serialize, reparse, validate before making the complete directory visible.
    parsed = parse_po(raw, "candidate")
    if [(identity(e), values(e)) for e in parsed] != [(identity(e), values(e)) for e in output]:
        raise KeeperError("PO roundtrip changed an identity or translation")
    gettext_check(raw)
    state["baseline"] = digest(raw)
    for entry in output:
        state["entries"][entry_id(entry)]["translation"] = translation_digest(entry)
    used = {r["source"] for r in state["entries"].values() if r["source"] is not None}
    state["references"] = {k: v for k, v in state["references"].items() if k in used}
    keep_snapshots = {r["sha256"] for r in state["references"].values()}
    snapshots = {k: v for k, v in snapshots.items() if k in keep_snapshots}
    snapshots[digest(raw)] = raw
    files = {"candidate.po": raw, "state.json": json_bytes(state), "report.json": json_bytes(report)}
    files.update({f"snapshots/{key}.po": val for key, val in snapshots.items()})
    check_inputs(hashes)
    return publish_candidate(Path(candidate).absolute(), files, hashes,
                             {"po": str(cfg.resolve("catalog")), "state": str(cfg.resolve("state")),
                              "snapshots": str(cfg.snapshots)}, config=str(cfg.path))


def plan(config, candidate, adopt_existing=None, unprotect=()):
    cfg = load_config(config)
    return finalize(cfg, candidate, *prepare(cfg, adopt_existing, unprotect))


def check(config, output=None):
    cfg = load_config(config)
    assert_no_pending(cfg.resolve("state"))
    raw, hashes = read_inputs(cfg)
    load_state(cfg, raw, hashes)
    data = raw[str(cfg.resolve("catalog"))]
    if data is None:
        raise KeeperError("catalog does not exist")
    po = parse_po(data)
    language = po.metadata.get("Language", "").strip()
    if language and language.replace("-", "_") != cfg.data["language"].replace("-", "_"):
        raise KeeperError("catalog Language differs from configured language")
    problems = []
    for entry in po:
        if not entry.obsolete:
            issue = entry_problem(entry, po.metadata.get("Plural-Forms", ""), cfg.data["plural_forms"], cfg.data.get("rules", {}))
            if issue not in (None, "empty", "fuzzy"):
                problems.append({"id": entry_id(entry), "reason": issue})
    if problems:
        raise KeeperError("invalid translations: " + json.dumps(problems))
    compiled = gettext_check(data)
    check_inputs(hashes)
    if output is not None:
        destination = checked_output_path(cfg, output, hashes)
        from .transaction import atomic_write
        # Compile into memory first so the last input check precedes publication.
        check_inputs(hashes)
        assert_no_pending(cfg.resolve("state"))
        atomic_write(destination, compiled)
    return {"status": "PASS", "entries": len(po), "translated": len(po.translated_entries()),
            "fuzzy": len(po.fuzzy_entries()), "obsolete": len(po.obsolete_entries())}
