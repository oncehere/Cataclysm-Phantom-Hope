"""Behavioral maintenance tests: all fixtures travel through polib and msgfmt."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import polib

from pokeeper import core
from pokeeper.catalog import (entry_id, gettext_check, identity, index, json_bytes,
                              parse_po, serialize, translation_digest, values)
from pokeeper.config import KeeperError, load_config
from pokeeper.transaction import TransactionError, apply_candidate, digest


RU = "nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<12 || n%100>14) ? 1 : 2);"
TWO = "nplurals=2; plural=(n != 1);"


def entry(msgid="Save", text="", *, context=None, plural=None, texts=None, flags=(), obsolete=False):
    kwargs = {"msgid": msgid, "msgstr": text, "msgctxt": context,
              "flags": list(flags), "obsolete": obsolete}
    if plural is not None:
        kwargs.update(msgid_plural=plural, msgstr_plural=dict(enumerate(texts or ["", "", ""])))
    return polib.POEntry(**kwargs)


def po_bytes(entries, rule=RU, language="ru"):
    po = polib.POFile()
    po.metadata = {"Project-Id-Version": "tests", "Language": language,
                   "Plural-Forms": rule, "Content-Type": "text/plain; charset=UTF-8",
                   "MIME-Version": "1.0", "Content-Transfer-Encoding": "8bit",
                   "PO-Revision-Date": "2026-01-01 00:00+0000",
                   "Last-Translator": "Tester", "Language-Team": "Russian"}
    po.extend(copy.deepcopy(entries))
    return serialize(po)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "project.toml"
        self.catalog = self.root / "locale.po"
        self.template = self.root / "messages.pot"
        self.state = self.root / ".pokeeper" / "state.json"
        self.candidates = 0
        self.template.write_bytes(po_bytes([entry()]))
        self.source("first", [entry(text="Первый")])
        self.source("second", [entry(text="Второй")])
        self.configure()

    def configure(self, *, sources=("first", "second"), rule=RU, language="ru", extra=""):
        text = "\n".join([
            "version = 1", 'project = "test"', f"language = {json.dumps(language)}",
            f"plural_forms = {json.dumps(rule)}", 'template = "messages.pot"',
            'catalog = "locale.po"', 'state = ".pokeeper/state.json"',
        ]) + "\n"
        for name in sources:
            text += f"\n[[sources]]\nname = {json.dumps(name)}\npath = {json.dumps(name + '.po')}\nrevision = \"fixture-v1\"\n"
        self.config.write_text(text + extra)
        return load_config(self.config)

    def source(self, name, entries, **kwargs):
        (self.root / (name + ".po")).write_bytes(po_bytes(entries, **kwargs))

    def candidate(self, **kwargs):
        self.candidates += 1
        destination = self.root / f"candidate-{self.candidates}"
        if not self.state.exists():
            kwargs.setdefault("adopt_existing", "reuse")
        core.plan(self.config, destination, **kwargs)
        return destination

    def update(self, **kwargs):
        candidate = self.candidate(**kwargs)
        apply_candidate(candidate)
        return parse_po(self.catalog.read_bytes()), json.loads(self.state.read_bytes()), json.loads((candidate / "report.json").read_bytes())

    def edit(self, callback):
        po = parse_po(self.catalog.read_bytes())
        callback(po)
        self.catalog.write_bytes(serialize(po))

    def test_priority_context_none_empty_and_plural_roundtrip(self):
        entries = [entry(context=None), entry(context=""), entry(context="button"),
                   entry("%d file", plural="%d files", flags=["c-format"])]
        self.template.write_bytes(po_bytes(entries))
        translated = copy.deepcopy(entries)
        for e, text in zip(translated, ("Общий", "Пустой", "Кнопка")):
            e.msgstr = text
        translated[-1].msgstr_plural = {0: "%d файл", 1: "%d файла", 2: "%d файлов"}
        self.source("first", translated)
        output, state, _ = self.update()
        self.assertEqual([e.msgctxt for e in output[:3]], [None, "", "button"])
        self.assertEqual([e.msgstr for e in output[:3]], ["Общий", "Пустой", "Кнопка"])
        self.assertEqual(output[-1].msgstr_plural, translated[-1].msgstr_plural)
        self.assertEqual(len(state["entries"]), 4)
        self.assertGreater(len(gettext_check(self.catalog.read_bytes())), 0)

    def test_fuzzy_obsolete_empty_and_format_errors_are_distinct(self):
        originals = [entry("Fuzzy"), entry("Old"), entry("Empty"), entry("Number %d", flags=["c-format"])]
        self.template.write_bytes(po_bytes(originals))
        self.source("first", [entry("Fuzzy", "Нечётко", flags=["fuzzy"]), entry("Old", "Старый", obsolete=True),
                              entry("Empty"), entry("Number %d", "Число %s", flags=["c-format"])])
        self.source("second", [])
        output, _, report = self.update()
        self.assertTrue(all(not e.msgstr for e in output))
        reasons = {item["reason"] for key in ("ignored", "conflicts", "gaps") for item in report[key]}
        self.assertTrue({"fuzzy", "obsolete", "empty", "gettext_format"} <= reasons)

    def test_plural_rule_and_count_conflicts_are_not_repaired(self):
        original = entry("One", plural="Many")
        self.template.write_bytes(po_bytes([original]))
        self.source("first", [entry("One", plural="Many", texts=["one", "many"])], rule=TWO)
        self.source("second", [entry("One", plural="Many", texts=["one", "few"])])
        output, _, report = self.update()
        self.assertEqual(output[0].msgstr_plural, {0: "", 1: "", 2: ""})
        self.assertEqual({c["reason"] for c in report["conflicts"]}, {"plural_rule_conflict", "plural_count"})

    def test_human_edit_protected_and_explicit_unprotect(self):
        self.update()
        self.edit(lambda po: setattr(po[0], "msgstr", "Человек"))
        output, state, report = self.update()
        key = entry_id(output[0])
        self.assertEqual(output[0].msgstr, "Человек")
        self.assertTrue(state["entries"][key]["protected"])
        self.assertEqual(report["human_changes"][0]["kind"], "edited")
        output, state, _ = self.update(unprotect=[key])
        self.assertEqual(output[0].msgstr, "Первый")
        self.assertFalse(state["entries"][key]["protected"])

    def test_human_clear_remains_protected_blank(self):
        self.update()
        self.edit(lambda po: setattr(po[0], "msgstr", ""))
        output, state, report = self.update()
        key = entry_id(output[0])
        self.assertEqual(output[0].msgstr, "")
        self.assertTrue(state["entries"][key]["protected"])
        self.assertEqual(report["gaps"][0]["reason"], "empty")
        output, state, report = self.update()
        self.assertEqual(output[0].msgstr, "")
        self.assertTrue(state["entries"][key]["protected"])
        self.assertFalse(report["human_changes"])

    def test_human_delete_restored_protected_blank(self):
        self.update()
        self.edit(lambda po: po.clear())
        output, state, report = self.update()
        key = entry_id(output[0])
        self.assertEqual(output[0].msgstr, "")
        self.assertTrue(state["entries"][key]["protected"])
        self.assertEqual(report["human_changes"][0]["kind"], "deleted_restored_blank")
        self.update()  # Deletion provenance is a snapshot where the entry is absent.

    def test_human_obsoleting_active_entry_is_protected_deletion(self):
        self.update()
        self.edit(lambda po: setattr(po[0], "obsolete", True))
        output, state, report = self.update()
        self.assertEqual(output[0].msgstr, "")
        self.assertFalse(output[0].obsolete)
        self.assertTrue(state["entries"][entry_id(output[0])]["protected"])
        self.assertEqual(report["human_changes"][0]["kind"], "deleted_restored_blank")
        self.update()

    def test_same_as_upstream_does_not_unprotect(self):
        self.update()
        self.edit(lambda po: setattr(po[0], "msgstr", "Человек"))
        self.update()
        self.source("first", [entry(text="Человек")])
        output, state, _ = self.update()
        self.assertTrue(state["entries"][entry_id(output[0])]["protected"])

    def test_comments_fuzzy_and_rewrap_do_not_protect(self):
        self.update()

        def cosmetic(po):
            po[0].tcomment = "Reviewer note"
            po[0].comment = "Developer note changed"
            po[0].flags.append("fuzzy")
            po.wrapwidth = 12

        self.edit(cosmetic)
        output, state, report = self.update()
        self.assertEqual(output[0].msgstr, "Первый")
        self.assertEqual(output[0].tcomment, "Reviewer note")
        self.assertFalse(state["entries"][entry_id(output[0])]["protected"])
        self.assertFalse(report["human_changes"])

    def test_repeat_update_has_identical_po_state_and_no_human_change(self):
        self.update()
        first_po, first_state = self.catalog.read_bytes(), self.state.read_bytes()
        _, _, report = self.update()
        self.assertEqual(self.catalog.read_bytes(), first_po)
        self.assertEqual(self.state.read_bytes(), first_state)
        self.assertFalse(report["human_changes"])
        self.assertFalse(report["updates"])

    def test_source_change_is_new_identity_without_fuzzy_migration(self):
        self.update()
        self.template.write_bytes(po_bytes([entry("Save now")]))
        output, _, report = self.update()
        self.assertEqual(output[0].msgid, "Save now")
        self.assertEqual(output[0].msgstr, "")
        self.assertTrue(output[1].obsolete)
        self.assertEqual(output[1].msgstr, "Первый")
        self.assertEqual(len(report["removed"]), 1)

    def test_reintroduced_tool_obsolete_entry_not_human_deletion(self):
        self.update()
        self.template.write_bytes(po_bytes([entry("Save now")]))
        self.update()
        self.template.write_bytes(po_bytes([entry()]))
        output, state, report = self.update()
        self.assertEqual(output[0].msgstr, "Первый")
        self.assertFalse(state["entries"][entry_id(output[0])]["protected"])
        self.assertFalse(report["human_changes"])

    def test_protection_survives_removal_and_exact_reintroduction(self):
        self.update()
        self.edit(lambda po: setattr(po[0], "msgstr", "Человек"))
        self.update()
        self.template.write_bytes(po_bytes([entry("Other")]))
        self.update()
        self.template.write_bytes(po_bytes([entry()]))
        output, state, report = self.update()
        self.assertEqual(output[0].msgstr, "Человек")
        self.assertTrue(state["entries"][entry_id(output[0])]["protected"])
        self.assertFalse(report["human_changes"])

    def test_history_keeps_exact_prior_source_snapshot(self):
        output, state, _ = self.update()
        key = entry_id(output[0])
        original_ref = state["entries"][key]["source"]
        original = state["references"][original_ref]
        self.source("first", [])
        self.source("second", [])
        output, state, _ = self.update()
        self.assertEqual(output[0].msgstr, "Первый")
        self.assertEqual(state["entries"][key]["source"], original_ref)
        self.assertEqual(state["references"][original_ref], original)
        self.assertNotEqual(original["sha256"], digest((self.root / "first.po").read_bytes()))

    def test_upstream_replaces_ordinary_gemini(self):
        cfg = self.configure(sources=())
        output, state, report, snapshots, hashes = core.prepare(cfg)
        output[0].msgstr = "AI translation"
        raw = serialize(output)
        ref = {"kind": "gemini", "name": "fake-model", "sha256": digest(raw), "request": "offline-test"}
        refkey = digest(json_bytes(ref))
        state["references"][refkey] = ref
        state["entries"][entry_id(output[0])]["source"] = refkey
        snapshots[digest(raw)] = raw
        candidate = self.root / "ai-candidate"
        core.finalize(cfg, candidate, output, state, report, snapshots, hashes)
        apply_candidate(candidate)
        self.configure()
        output, state, _ = self.update()
        self.assertEqual(output[0].msgstr, "Первый")
        ref = state["references"][state["entries"][entry_id(output[0])]["source"]]
        self.assertEqual(ref["kind"], "upstream")

    def test_first_adoption_requires_choice_and_protect_preserves(self):
        self.catalog.write_bytes(po_bytes([entry(text="Initial")]))
        with self.assertRaisesRegex(KeeperError, "first adoption"):
            core.prepare(load_config(self.config))
        output, state, _ = self.update(adopt_existing="protect")
        self.assertEqual(output[0].msgstr, "Initial")
        self.assertTrue(state["entries"][entry_id(output[0])]["protected"])

    def test_initial_obsolete_content_has_existing_provenance(self):
        self.catalog.write_bytes(po_bytes([entry("Removed", "Old translation", obsolete=True)]))
        output, state, _ = self.update()
        old = next(e for e in output if e.obsolete)
        ref = state["references"][state["entries"][entry_id(old)]["source"]]
        self.assertEqual(ref["kind"], "existing")
        self.update()

    def test_invalid_human_edit_blocks_candidate(self):
        self.template.write_bytes(po_bytes([entry("Number %d", flags=["c-format"])]))
        self.source("first", [entry("Number %d", "Число %d", flags=["c-format"])])
        self.update()
        self.edit(lambda po: setattr(po[0], "msgstr", "Число %s"))
        with self.assertRaisesRegex(KeeperError, "protected translation.*invalid"):
            self.candidate()
        self.assertIn(b"%s", self.catalog.read_bytes())

    def test_state_and_snapshot_corruption_is_rejected(self):
        _, state, _ = self.update()
        state["entries"][next(iter(state["entries"]))]["translation"] = "0" * 64
        self.state.write_bytes(json_bytes(state))
        with self.assertRaisesRegex(KeeperError, "baseline mismatch"):
            self.candidate()

    def test_missing_historical_snapshot_is_rejected(self):
        source = self.root / "first.po"
        source.write_bytes(b"# Upstream source header\n" + source.read_bytes())
        _, state, _ = self.update()
        ref = next(iter(state["references"].values()))
        (self.state.parent / "snapshots" / (ref["sha256"] + ".po")).unlink()
        with self.assertRaisesRegex(KeeperError, "historical source"):
            self.candidate()

    def test_forged_source_reference_is_rejected(self):
        _, state, _ = self.update()
        raw = po_bytes([entry(text="Different actual translation")])
        checksum = digest(raw)
        (self.state.parent / "snapshots" / (checksum + ".po")).write_bytes(raw)
        ref = next(iter(state["references"].values()))
        ref["sha256"] = checksum
        self.state.write_bytes(json_bytes(state))
        with self.assertRaisesRegex(KeeperError, "does not contain"):
            self.candidate()

    def test_entire_catalog_missing_with_state_is_not_mass_deletion(self):
        self.update()
        self.catalog.unlink()
        with self.assertRaisesRegex(KeeperError, "entire catalog"):
            self.candidate()

    def test_wrong_source_or_catalog_language_is_rejected(self):
        self.source("first", [entry(text="wrong language")], language="de")
        with self.assertRaisesRegex(KeeperError, "Language.*differs"):
            self.candidate()
        self.configure(sources=())
        self.catalog.write_bytes(po_bytes([entry(text="wrong language")], language="de"))
        with self.assertRaisesRegex(KeeperError, "Language.*differs"):
            self.candidate()

    def test_config_only_supports_another_language_plural_rule(self):
        self.configure(rule=TWO, language="de")
        self.template.write_bytes(po_bytes([entry("One", plural="Many", texts=["", ""])], rule=TWO, language="de"))
        self.source("first", [entry("One", plural="Many", texts=["Einer", "Viele"])], rule=TWO, language="de")
        self.source("second", [], rule=TWO, language="de")
        output, _, _ = self.update()
        self.assertEqual(output[0].msgstr_plural, {0: "Einer", 1: "Viele"})

    def test_changed_plural_formula_does_not_reinterpret_protected_values(self):
        original = entry("One", plural="Many", texts=["one", "few", "many"])
        self.template.write_bytes(po_bytes([original]))
        self.catalog.write_bytes(po_bytes([original]))
        self.update(adopt_existing="protect")
        altered = "nplurals=3; plural=(n==1 ? 0 : n==2 ? 1 : 2);"
        self.configure(rule=altered, sources=())
        self.edit(lambda po: po.metadata.update({"Plural-Forms": altered}))
        with self.assertRaisesRegex(KeeperError, "plural_rule_conflict"):
            self.candidate()
        key = entry_id(original)
        output, state, report = self.update(unprotect=[key])
        self.assertEqual(output[0].msgstr_plural, {0: "", 1: "", 2: ""})
        self.assertFalse(state["entries"][key]["protected"])
        self.assertTrue(any(item["reason"] == "plural_rule_conflict" for item in report["ignored"]))

    def test_config_symlink_hardlink_and_reserved_path_collisions(self):
        self.catalog.symlink_to(self.root / "first.po")
        with self.assertRaisesRegex(KeeperError, "symlink"):
            load_config(self.config)
        self.catalog.unlink()
        self.catalog.hardlink_to(self.root / "first.po")
        with self.assertRaisesRegex(KeeperError, "alias"):
            load_config(self.config)
        self.catalog.unlink()
        text = self.config.read_text().replace('catalog = "locale.po"', 'catalog = ".pokeeper/state.json.pending"')
        self.config.write_text(text)
        with self.assertRaisesRegex(KeeperError, "reserved"):
            load_config(self.config)

    def test_mo_build_rechecks_inputs_after_compilation(self):
        self.update()
        original = core.gettext_check

        def changed(raw, output=None):
            result = original(raw, output)
            self.catalog.write_bytes(self.catalog.read_bytes() + b"\n# concurrent comment\n")
            return result

        output = self.root / "locale.mo"
        with patch.object(core, "gettext_check", side_effect=changed):
            with self.assertRaisesRegex(TransactionError, "input changed"):
                core.check(self.config, output)
        self.assertFalse(output.exists())

    def test_mo_build_rejects_normalized_and_reserved_aliases(self):
        self.update()
        original = self.catalog.read_bytes()
        outputs = [self.root / "nested" / ".." / "locale.po",
                   Path(str(self.state) + ".pending"), Path(str(self.state) + ".lock")]
        alias = self.root / "alias.mo"
        alias.hardlink_to(self.catalog)
        outputs.append(alias)
        for output in outputs:
            with self.subTest(output=output), self.assertRaisesRegex(KeeperError, "overwrite|alias"):
                core.check(self.config, output)
        self.assertEqual(self.catalog.read_bytes(), original)

    def test_other_gettext_format_donor_errors_are_reported(self):
        self.template.write_bytes(po_bytes([entry("Hello {0}", flags=["java-format"])]))
        self.source("first", [entry("Hello {0}", "Hallo {1}", flags=["java-format"])])
        self.source("second", [entry("Hello {0}", "Hallo {0}", flags=["java-format"])])
        output, _, report = self.update()
        self.assertEqual(output[0].msgstr, "Hallo {0}")
        self.assertTrue(any(item["reason"] == "gettext_format" for item in report["conflicts"]))

    def test_c_format_upstream_reordering_uses_gettext_argument_semantics(self):
        original = "%s shoots %s with %d rounds."
        translated = "%2$s получает от %1$s %3$d выстрелов."
        self.template.write_bytes(po_bytes([entry(original, flags=["c-format"])]))
        self.source("first", [entry(original, translated, flags=["c-format"])])
        output, _, report = self.update()
        self.assertEqual(output[0].msgstr, translated)
        self.assertFalse(report["gaps"])

    def test_c_format_missing_and_wrong_type_upstream_are_rejected(self):
        original = "%s shoots %s with %d rounds."
        translated = "%2$s получает от %1$s %3$d выстрелов."
        self.template.write_bytes(po_bytes([entry(original, flags=["c-format"])]))
        self.source("second", [entry(original, translated, flags=["c-format"])])
        for bad in ("%1$s стреляет.", "%2$s получает от %1$s %3$s выстрелов."):
            with self.subTest(bad=bad):
                self.source("first", [entry(original, bad, flags=["c-format"])])
                output, _, report = self.update()
                self.assertEqual(output[0].msgstr, translated)
                self.assertTrue(any(item["source"] == "first" and item["reason"] == "gettext_format"
                                    for item in report["conflicts"]))

    def test_project_token_and_newline_rules_are_configurable(self):
        self.configure(extra='\n[rules]\ntoken_patterns = ["<[^>]+>"]\npreserve_newlines = true\n')
        self.template.write_bytes(po_bytes([entry("<npc> Hello\n")]))
        self.source("first", [entry("<npc> Hello\n", "<user> Привет\n")])
        self.source("second", [entry("<npc> Hello\n", "<npc> Привет")])
        output, _, report = self.update()
        self.assertEqual(output[0].msgstr, "")
        self.assertEqual({item["reason"] for item in report["conflicts"]}, {"placeholders_or_tokens", "newlines"})


if __name__ == "__main__":
    unittest.main()
