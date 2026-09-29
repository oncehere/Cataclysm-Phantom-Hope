"""PO parsing is entirely polib; GNU gettext is the final format authority."""

from collections import Counter
import copy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import shutil
import string
import subprocess
import tempfile

import polib

from .config import KeeperError, plural_rule


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def identity(entry):
    return [entry.msgctxt, entry.msgid, entry.msgid_plural or None]


def entry_id(entry):
    return hashlib.sha256(json_bytes(identity(entry))).hexdigest()


def values(entry):
    if entry.msgid_plural:
        return {str(k): v for k, v in sorted(entry.msgstr_plural.items())}
    return entry.msgstr


def translation_digest(entry):
    return hashlib.sha256(json_bytes(values(entry))).hexdigest()


def set_values(entry, translations):
    entry.msgstr = ""
    entry.msgstr_plural = {}
    if entry.msgid_plural:
        entry.msgstr_plural = dict(enumerate(translations))
    else:
        entry.msgstr = translations[0]


def blank(entry, count):
    set_values(entry, [""] * (count if entry.msgid_plural else 1))


def parse_po(raw, label="PO"):
    try:
        # polib handles charset declarations, escaped strings and contexts.
        with tempfile.NamedTemporaryFile(suffix=".po") as f:
            f.write(raw)
            f.flush()
            po = polib.pofile(f.name, check_for_duplicates=False)
        seen = set()
        for entry in po:
            # polib cannot serialize an explicitly empty msgid_plural faithfully.
            # Refuse this representation instead of changing a plural identity
            # into a singular one (or silently repairing malformed plural input).
            if entry.msgstr_plural and not entry.msgid_plural:
                raise KeeperError(f"empty or missing msgid_plural with plural forms in {label} is not supported by polib roundtrip")
            key = (entry.obsolete, entry_id(entry))
            if key in seen:
                raise KeeperError(f"duplicate identity in {label}: {identity(entry)!r}")
            seen.add(key)
        return po
    except (OSError, UnicodeError, ValueError) as exc:
        raise KeeperError(f"cannot parse {label}: {exc}") from None


def serialize(po):
    po = copy.deepcopy(po)
    po.encoding = "utf-8"
    po.metadata["Content-Type"] = "text/plain; charset=UTF-8"
    po.wrapwidth = 78
    return str(po).encode("utf-8")


def index(po, obsolete=False):
    return {entry_id(e): e for e in po if bool(e.obsolete) == obsolete}


# Conservative pre-screen. msgfmt additionally checks the format flags in final PO.
PRINTF = re.compile(r"%(?:\([^)]+\)|\d+\$)?[-+#0 ']*(?:\d+|\*(?:\d+\$)?)?(?:\.(?:\d+|\*(?:\d+\$)?))?(?:hh|ll|[hlLjzt])?[diouxXeEfFgGaAcspn%]")


def token_signature(text, entry, rules):
    result = []
    # GNU gettext understands positional argument equivalence (%s -> %1$s),
    # widths and argument types. Exact token spelling is too strict for valid
    # c-format translations; entry_problem checks these with msgfmt below.
    if "c-format" not in entry.flags and any("format" in flag and "no-" not in flag for flag in entry.flags):
        result.append(Counter(m.group() for m in PRINTF.finditer(text) if m.group() != "%%"))
    if "python-brace-format" in entry.flags:
        try:
            result.append(Counter((field, spec, conv) for _, field, spec, conv
                                  in string.Formatter().parse(text) if field is not None))
        except ValueError:
            return None
    for pattern in rules.get("token_patterns", []):
        result.append(Counter(m.group() for m in re.finditer(pattern, text)))
    return result


def validate_values(entry, translations, count, rules):
    expected = count if entry.msgid_plural else 1
    if not isinstance(translations, list) or len(translations) != expected:
        return "plural_count"
    if any(not isinstance(t, str) or not t for t in translations):
        return "empty"
    originals = [entry.msgid] + ([entry.msgid_plural] if entry.msgid_plural else [])
    signatures = [token_signature(s, entry, rules) for s in originals]
    for translated in translations:
        if "\x00" in translated:
            return "nul_character"
        sig = token_signature(translated, entry, rules)
        if sig is None or sig not in signatures:
            return "placeholders_or_tokens"
        if rules.get("preserve_newlines", True):
            shape = lambda s: (s.count("\n"), s.startswith("\n"), s.endswith("\n"))
            if shape(translated) not in [shape(s) for s in originals]:
                return "newlines"
    return None


def entry_problem(entry, donor_rule, target_rule, rules, template=None):
    if entry.obsolete:
        return "obsolete"
    if "fuzzy" in entry.flags:
        return "fuzzy"
    count = plural_rule(target_rule)[0]
    if entry.msgid_plural:
        try:
            if plural_rule(donor_rule)[1] != plural_rule(target_rule)[1]:
                return "plural_rule_conflict"
        except KeeperError:
            return "plural_rule_conflict"
        if set(entry.msgstr_plural) != set(range(count)):
            return "plural_count"
        translations = [entry.msgstr_plural[i] for i in range(count)]
    else:
        translations = [entry.msgstr]
    source = template or entry
    issue = validate_values(source, translations, count, rules)
    if issue:
        return issue
    if any(flag.endswith("-format") and not flag.startswith("no-") for flag in source.flags):
        return _gettext_format_problem(source.msgid, source.msgid_plural,
                                       tuple(sorted(source.flags)), tuple(translations), target_rule)
    return None


@lru_cache(maxsize=8192)
def _gettext_format_problem(msgid, plural, flags, translations, rule):
    """GNU gettext checks flagged entries, cached across donors and output.

    Unflagged ordinary text never spawns a per-entry subprocess. A broken donor
    is reported and skipped here instead of breaking the final candidate.
    """
    po = polib.POFile()
    po.metadata = {"Project-Id-Version": "pokeeper validation", "Language": "und",
                   "Plural-Forms": rule, "Content-Type": "text/plain; charset=UTF-8",
                   "MIME-Version": "1.0", "Content-Transfer-Encoding": "8bit",
                   "PO-Revision-Date": "1970-01-01 00:00+0000",
                   "Last-Translator": "Project maintainers", "Language-Team": "und"}
    candidate = polib.POEntry(msgid=msgid, msgid_plural=plural,
                             flags=[flag for flag in flags if flag != "fuzzy"])
    set_values(candidate, list(translations))
    po.append(candidate)
    try:
        gettext_check(serialize(po))
    except KeeperError as exc:
        if str(exc).startswith("msgfmt rejected"):
            return "gettext_format"
        raise
    return None


def gettext_check(raw, output=None):
    executable = shutil.which("msgfmt")
    if not executable:
        raise KeeperError("GNU gettext msgfmt is required on PATH")
    with tempfile.TemporaryDirectory(prefix="pokeeper-check-") as tmp:
        source = Path(tmp) / "candidate.po"
        source.write_bytes(raw)
        compiled = Path(tmp) / "candidate.mo"
        result = subprocess.run([executable, "--check", "--check-format", "-o", str(compiled), str(source)],
                                capture_output=True, text=True)
        if result.returncode:
            raise KeeperError("msgfmt rejected PO:\n" + result.stderr.replace(str(source), "candidate.po"))
        if output is not None:
            from .transaction import atomic_write
            atomic_write(Path(output), compiled.read_bytes())
        return compiled.read_bytes()
