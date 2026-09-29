"""Validate candidate meaning before a transaction writes project files.

Manifest hashes detect accidental byte changes, not a self-consistent edit to
the manifest itself. Bind destinations to the guarded project configuration,
and independently check the PO/state/snapshot relationships as well.
"""

import json
import os
from pathlib import Path
import re

from .catalog import (entry_id, entry_problem, gettext_check, identity, index,
                      json_bytes, parse_po, translation_digest, values)
from .config import KeeperError, load_config, plural_rule
from .transaction import _read, digest


_SHA = re.compile(r"^[0-9a-f]{64}$")


def _require(condition, message):
    if not condition:
        raise KeeperError("invalid candidate: " + message)


def _object(raw, label):
    try:
        value = json.loads(raw)
    except (ValueError, TypeError, UnicodeError):
        raise KeeperError(f"invalid candidate: malformed {label}") from None
    _require(isinstance(value, dict), label + " must be an object")
    return value


def _sha(value):
    return isinstance(value, str) and bool(_SHA.fullmatch(value))


def validate_candidate(manifest, files):
    """Read-only validation, called under the transaction's project lock."""
    config_path = manifest.get("config")
    _require(isinstance(config_path, str) and os.path.isabs(config_path)
             and os.path.abspath(config_path) == config_path,
             "configuration path must be absolute and normalized")
    inputs = manifest["inputs"]
    report = _object(files["report.json"], "report")
    proposal_inputs = report.get("proposal_inputs", {})
    _require(isinstance(proposal_inputs, dict)
             and all(isinstance(p, str) and (_sha(h) or h is None) and p in inputs and inputs[p] == h
                     for p, h in proposal_inputs.items()), "proposal inputs are not guarded")
    _require(config_path in inputs and _sha(inputs[config_path]),
             "configuration must be a guarded input")
    cfg = load_config(config_path)
    config_raw = _read(cfg.path)
    _require(config_raw is not None and digest(config_raw) == inputs[config_path],
             "configuration changed")
    expected_targets = {
        "po": str(cfg.resolve("catalog")),
        "state": str(cfg.resolve("state")),
        "snapshots": str(cfg.snapshots),
    }
    _require(manifest["targets"] == expected_targets,
             "destinations differ from the guarded configuration")
    required = {config_path, str(cfg.resolve("template")),
                str(cfg.resolve("catalog")), str(cfg.resolve("state")),
                *(str(source["path"]) for source in cfg.sources)}
    _require(required <= inputs.keys(), "required project input is not guarded")
    for name in inputs.keys() - required:
        if name in proposal_inputs:
            continue
        path = Path(name)
        _require(path.parent == cfg.snapshots and path.suffix == ".po"
                 and _sha(path.stem) and inputs[name] == path.stem,
                 "unexpected or damaged historical snapshot input")

    po_raw = files["candidate.po"]
    po = parse_po(po_raw, "candidate")
    state = _object(files["state.json"], "state")
    _require(set(state) == {"version", "project", "language", "plural_forms", "baseline", "entries", "references"},
             "state schema differs from version 1")
    _require(state["version"] == 1 and state["project"] == cfg.data["project"]
             and state["language"] == cfg.data["language"], "state project/language/version mismatch")
    _require(plural_rule(state["plural_forms"])[1] == plural_rule(cfg.data["plural_forms"])[1],
             "state plural rule differs from configured rule")
    _require(state["baseline"] == digest(po_raw), "state baseline differs from candidate PO")
    _require(isinstance(state["entries"], dict) and isinstance(state["references"], dict),
             "state entries/references must be objects")
    records = state["entries"]
    references = state["references"]
    entries = {}
    for entry in po:
        key = entry_id(entry)
        _require(key not in entries, "one identity appears as both active and obsolete")
        entries[key] = entry
    _require(set(entries) == set(records), "state entry set differs from candidate PO")
    used = set()
    for key, entry in entries.items():
        record = records[key]
        _require(isinstance(record, dict)
                 and set(record) == {"identity", "translation", "protected", "source"},
                 "malformed entry state")
        _require(record["identity"] == identity(entry)
                 and record["translation"] == translation_digest(entry),
                 "entry baseline differs from candidate translation")
        _require(isinstance(record["protected"], bool), "protection must be boolean")
        source = record["source"]
        _require(source is None or isinstance(source, str) and source in references,
                 "entry has an unknown source reference")
        if source is not None:
            used.add(source)
        elif entry.msgstr or any(entry.msgstr_plural.values()):
            raise KeeperError("invalid candidate: nonempty translation has no provenance")
    _require(used == set(references), "unreferenced source state")

    snapshot_cache = {}

    def snapshot(checksum):
        _require(_sha(checksum), "invalid snapshot digest")
        if checksum not in snapshot_cache:
            name = f"snapshots/{checksum}.po"
            if name in files:
                raw = files[name]
            else:
                path = cfg.snapshots / (checksum + ".po")
                _require(inputs.get(str(path)) == checksum,
                         "historical source snapshot is not guarded")
                raw = _read(path)
            _require(raw is not None and digest(raw) == checksum,
                     "missing or damaged source snapshot")
            parsed = parse_po(raw, "source snapshot")
            snapshot_cache[checksum] = (raw, {**index(parsed, True), **index(parsed)})
        return snapshot_cache[checksum]

    baseline_name = f"snapshots/{state['baseline']}.po"
    _require(files.get(baseline_name) == po_raw, "candidate baseline snapshot is missing or different")
    for key, ref in references.items():
        _require(isinstance(ref, dict) and {"kind", "name", "sha256"} <= ref.keys()
                 and not ref.keys() - {"kind", "name", "sha256", "revision", "request"},
                 "malformed source reference")
        _require(ref["kind"] in ("upstream", "existing", "human", "gemini", "external")
                 and isinstance(ref["name"], str) and bool(ref["name"]),
                 "invalid source kind/name")
        _require(all(isinstance(ref[field], str) for field in ("revision", "request") if field in ref),
                 "invalid source revision/request")
        _require(key == digest(json_bytes(ref)), "source reference ID differs from metadata")
        snapshot(ref["sha256"])
    expected_snapshots = {state["baseline"], *(ref["sha256"] for ref in references.values())}
    _require(all(Path(name).stem in expected_snapshots for name in files if name.startswith("snapshots/")),
             "candidate includes an unrelated snapshot")
    for key, entry in entries.items():
        source = records[key]["source"]
        if source is None:
            continue
        ref = references[source]
        _, source_entries = snapshot(ref["sha256"])
        origin = source_entries.get(key)
        deletion = (ref["kind"] == "human" and ref["name"] == "catalog deletion"
                    and (origin is None or origin.obsolete)
                    and not entry.msgstr and not any(entry.msgstr_plural.values()))
        _require(deletion or origin is not None and values(origin) == values(entry),
                 "translation does not match its historical source snapshot")

    template_raw = _read(cfg.resolve("template"))
    _require(template_raw is not None
             and digest(template_raw) == inputs[str(cfg.resolve("template"))], "template changed")
    template_entries = index(parse_po(template_raw, "template"))
    active = index(po)
    _require(set(active) == set(template_entries), "candidate does not contain the complete POT identity set")
    _require(po.metadata.get("Language") == cfg.data["language"], "candidate Language mismatch")
    _require(plural_rule(po.metadata.get("Plural-Forms", ""))[1]
             == plural_rule(cfg.data["plural_forms"])[1], "candidate plural rule mismatch")
    for key, entry in active.items():
        template_entry = template_entries[key]
        _require(set(entry.flags) - {"fuzzy"} == set(template_entry.flags) - {"fuzzy"},
                 "candidate changed source format flags")
        issue = entry_problem(entry, po.metadata.get("Plural-Forms", ""),
                              cfg.data["plural_forms"], cfg.data.get("rules", {}), template_entry)
        _require(issue in (None, "empty", "fuzzy"), f"invalid translation ({issue})")
    _require(report.get("version") == 1 and report.get("project") == cfg.data["project"],
             "report version/project mismatch")
    for field in ("updates", "conflicts", "gaps", "human_changes", "ignored", "removed", "unprotected"):
        _require(isinstance(report.get(field), list), "malformed report category")
    gettext_check(po_raw)
