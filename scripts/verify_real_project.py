#!/usr/bin/env python3
"""Verify the unchanged pokeeper CLI with fixed, real GNU Wget catalogs.

Only selected regular archive members are read. No upstream code is executed.
The downloaded catalogs and their license remain in the requested scratch dir.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import urllib.request

import polib


URL = "https://ftp.gnu.org/gnu/wget/wget-1.25.0.tar.gz"
ARCHIVE_SHA256 = "766e48423e79359ea31e41db9e5c289675947a7fcf2efdcedb726ac9d0da3784"
MEMBERS = {
    "po/wget.pot": "1eec698763439e0680995ac1a4ee3c8d404bc9e3a7c51e4d11801609d78f63f4",
    "po/pl.po": "9d8c07a9f974247a2f1b0001242b29567ec7b5db87cbaa27aca9e71d30b56143",
    "po/ru.po": "86748d0ec7b0b33298efb4c2fd2ce94c9cbea36610b097f066e75e2fc38f5621",
    "COPYING": "f7dc7522e7e1be9227f3dc8de8b39a4d1d2471968c893af15f00c1a2076a0eec",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def identity(entry: polib.POEntry) -> tuple[str | None, str, str]:
    return entry.msgctxt, entry.msgid, entry.msgid_plural


def core_sources() -> dict[str, str]:
    spec = importlib.util.find_spec("pokeeper")
    if spec is None or spec.origin is None:
        raise RuntimeError("pokeeper must be installed in this Python environment")
    root = Path(spec.origin).parent
    return {str(path.relative_to(root)): digest(path.read_bytes())
            for path in sorted(root.rglob("*.py"))}


def execute(command: list[str], evidence: dict) -> None:
    # These are offline commands; remove model credentials to demonstrate it.
    environment = os.environ.copy()
    environment.pop("GEMINI_API_KEY", None)
    environment.pop("GOOGLE_API_KEY", None)
    result = subprocess.run(command, text=True, capture_output=True, env=environment)
    evidence["commands"].append({
        "argv": command,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    })
    if result.returncode:
        raise RuntimeError(f"command failed with exit {result.returncode}: {command}")


def verify(workdir: Path, archive: Path | None, evidence: dict) -> None:
    evidence["core_source_sha256"] = core_sources()
    evidence["python_version"] = sys.version.split()[0]
    evidence["polib_version"] = polib.__version__
    if archive is None:
        # Bounded download and fixed hash; no 'latest' dependency or credentials.
        with urllib.request.urlopen(URL, timeout=60) as response:
            data = response.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise ValueError("archive exceeds 8 MiB")
        archive = workdir / "wget-1.25.0.tar.gz"
        archive.write_bytes(data)
    data = archive.read_bytes()
    if digest(data) != ARCHIVE_SHA256:
        raise ValueError("archive SHA256 mismatch")
    with tarfile.open(archive, "r:gz") as tar:
        for name, expected in MEMBERS.items():
            member = tar.getmember("wget-1.25.0/" + name)
            if not member.isfile() or member.size > 1024 * 1024:
                raise ValueError(f"unexpected archive member: {name}")
            stream = tar.extractfile(member)
            if stream is None:
                raise ValueError(f"cannot read archive member: {name}")
            extracted = stream.read()
            if digest(extracted) != expected:
                raise ValueError(f"member SHA256 mismatch: {name}")
            destination = workdir / "upstream" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(extracted)

    template = polib.pofile(str(workdir / "upstream/po/wget.pot"))
    expected_keys = {identity(entry) for entry in template if not entry.obsolete}
    for language in ("pl", "ru"):
        source = polib.pofile(str(workdir / f"upstream/po/{language}.po"))
        plural_forms = source.metadata["Plural-Forms"]
        if not plural_forms.startswith("nplurals=3;"):
            raise AssertionError("fixed real catalog must have three plural forms")
        config = workdir / f"{language}.toml"
        config.write_text(
            "version = 1\n"
            f"project = 'gnu-wget-1.25.0-{language}'\n"
            f"language = '{language}'\n"
            f"plural_forms = {json.dumps(plural_forms)}\n"
            "template = 'upstream/po/wget.pot'\n"
            f"catalog = 'output/{language}.po'\n"
            f"state = 'output/{language}.state.json'\n"
            "\n[[sources]]\n"
            "name = 'gnu-wget'\n"
            f"path = 'upstream/po/{language}.po'\n"
            "revision = 'wget-1.25.0'\n"
            # Wget translators intentionally reflow CLI help paragraphs.
            # GNU gettext still validates required leading/trailing newlines.
            "\n[rules]\npreserve_newlines = false\n",
            encoding="utf-8",
        )
        cli = [sys.executable, "-m", "pokeeper"]
        first = workdir / f"candidate-{language}-1"
        second = workdir / f"candidate-{language}-2"
        execute(cli + ["plan", "--config", str(config), "--candidate", str(first)], evidence)
        execute(cli + ["apply", str(first)], evidence)
        execute(cli + ["check", "--config", str(config)], evidence)
        execute(cli + ["compile", "--config", str(config), "--output",
                       str(workdir / f"output/{language}.mo")], evidence)
        output_path = workdir / f"output/{language}.po"
        original = output_path.read_bytes()
        output = polib.pofile(str(output_path))
        actual = {identity(entry): entry for entry in output if not entry.obsolete}
        if set(actual) != expected_keys:
            raise AssertionError(f"{language}: output does not contain complete POT identity set")
        for entry in source:
            if not entry.obsolete and identity(entry) in expected_keys:
                translated = actual[identity(entry)]
                if (translated.msgstr, translated.msgstr_plural) != (entry.msgstr, entry.msgstr_plural):
                    raise AssertionError(f"{language}: valid upstream translation was not reused exactly")
        plural_entries = [entry for entry in source if entry.msgid_plural
                          and not entry.obsolete and not entry.fuzzy
                          and identity(entry) in expected_keys]
        if len(plural_entries) != 2:
            raise AssertionError("unexpected real plural entry count")
        for entry in plural_entries:
            translated = actual[identity(entry)]
            if translated.msgstr_plural != entry.msgstr_plural:
                raise AssertionError(f"{language}: plural translation not copied exactly")
            if set(translated.msgstr_plural) != {0, 1, 2}:
                raise AssertionError(f"{language}: plural form count changed")
        execute(cli + ["plan", "--config", str(config), "--candidate", str(second)], evidence)
        execute(cli + ["apply", str(second)], evidence)
        if output_path.read_bytes() != original:
            raise AssertionError(f"{language}: second update changed catalog bytes")
        evidence["languages"][language] = {
            "status": "PASS", "template_entries": len(expected_keys),
            "output_entries": len(actual), "translated_entries": len(output.translated_entries()),
            "real_plural_entries": len(plural_entries), "plural_forms": plural_forms,
            "output_sha256": digest(original), "repeat_update_identical": True,
            "config_sha256": digest(config.read_bytes()),
            "report_counts": {
                key: len(value) for key, value in json.loads((first / "report.json").read_text()).items()
                if isinstance(value, list)
            },
        }
    if evidence["core_source_sha256"] != core_sources():
        raise AssertionError("core source changed during real-project validation")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, required=True, help="new scratch directory")
    parser.add_argument("--archive", type=Path, help="reuse the fixed archive without download")
    args = parser.parse_args()
    workdir = args.workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=False)
    evidence = {
        "project": "GNU Wget", "version": "1.25.0", "source_url": URL,
        "archive_sha256": ARCHIVE_SHA256, "member_sha256": MEMBERS,
        "core_changes": False, "commands": [], "languages": {}, "status": "FAIL",
        "limitations": ["No Gemini request", "No Wget build or runtime test",
                        "Archive signature not independently verified"],
    }
    try:
        verify(workdir, args.archive.resolve() if args.archive else None, evidence)
        evidence["status"] = "PASS"
    except Exception as error:
        evidence["error"] = str(error)
    (workdir / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    print(json.dumps({"status": evidence["status"], "evidence": str(workdir / "evidence.json"),
                      "languages": evidence["languages"], "error": evidence.get("error")},
                     ensure_ascii=False, indent=2))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
