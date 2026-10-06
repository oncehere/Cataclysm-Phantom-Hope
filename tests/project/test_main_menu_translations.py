"""Check Chinese main-menu labels and hotkeys through compiled gettext."""

import gettext
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MSGFMT = shutil.which("msgfmt")
MENU_MESSAGES = {
    "Main Menu": (
        "<N|n>ew Game",
        "Co-<O|o>p",
        "Lo<a|A>d",
        "<W|w>orld",
        "Se<t|T>tings",
        "Oth<e|E>r",
        "<Q|q>uit",
        "<T|t>utorial",
        "<M|m>OTD",
        "H<e|E|?>lp",
        "<C|c>redits",
    ),
    "Main Menu|New Game": (
        "C<u|U>stom Character",
        "<P|p>reset Character",
        "<R|r>andom Character",
        "Play Now!  (<D|d>efault Scenario)",
        "Play N<o|O>w!",
    ),
    "Main Menu|Co-op": (
        "<H|h>ost a session",
        "<J|j>oin a session",
    ),
    "Main Menu|World": (
        "Sh<o|O>w World Mods",
        "Copy World Sett<i|I>ngs",
        "Character to Tem<p|P>late",
        "Toggle World <C|c>ompression",
        "S<n|N>apshots",
        "<D|d>elete World",
        "<R|r>eset World",
        "Cop<y|Y> Personal Zones",
        "Past<e|E> Personal Zones",
    ),
    "Main Menu|Settings": (
        "<O|o>ptions",
        "Ke<y|Y>bindings",
        "A<u|U>topickup",
        "Sa<f|F>emode",
        "Colo<r|R>s",
        "ImGui <S|s>tyles",
        "<I|i>mGui Demo Screen",
    ),
}


class MainMenuTranslationCoverageTests(unittest.TestCase):
    def test_all_main_menu_source_messages_are_covered(self):
        source = (ROOT / "src/main_menu.cpp").read_text(encoding="utf-8")
        messages = re.findall(
            r'pgettext\(\s*"(Main Menu(?:\|[^"\n]+)?)"\s*,\s*'
            r'"([^"\n]+)"\s*\)', source)
        expected = [(context, message)
                    for context, messages in MENU_MESSAGES.items()
                    for message in messages]
        self.assertCountEqual(messages, expected)


@unittest.skipUnless(MSGFMT, "gettext msgfmt is required")
class MainMenuTranslationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="cph-main-menu-translation-")
        cls.addClassCleanup(cls.temporary.cleanup)
        output = Path(cls.temporary.name) / "cataclysm-dda.mo"
        result = subprocess.run(
            [MSGFMT, "-c", "-o", str(output),
             str(ROOT / "lang/cph/zh_CN.po")],
            check=False, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        if result.returncode:
            raise AssertionError(result.stdout)
        with output.open("rb") as stream:
            cls.catalog = gettext.GNUTranslations(stream)

    def test_every_hotkey_alternative_is_preserved(self):
        # Case variants and the help alias "?" are part of the input contract.
        for context, messages in MENU_MESSAGES.items():
            for message in messages:
                with self.subTest(context=context, message=message):
                    translated = self.catalog.pgettext(context, message)
                    hotkeys = re.findall(r"<[^<>]+>", message)
                    self.assertEqual(len(hotkeys), 1)
                    self.assertEqual(
                        re.findall(r"<[^<>]+>", translated), hotkeys)

    def test_hotkey_hint_precedes_the_complete_chinese_label(self):
        for context, messages in MENU_MESSAGES.items():
            for message in messages:
                with self.subTest(context=context, message=message):
                    translated = self.catalog.pgettext(context, message)
                    # A separate prefix cannot insert the Latin hint into a
                    # Chinese word, as "选<O|o>项" previously did.
                    match = re.fullmatch(
                        r"\(<[^<>]+>\) (?P<label>[^<>]+)", translated)
                    self.assertIsNotNone(match, translated)
                    self.assertRegex(match.group("label"), "[\u3400-\u9fff]")

    def test_imgui_name_is_complete_after_the_hint(self):
        for message in ("ImGui <S|s>tyles", "<I|i>mGui Demo Screen"):
            with self.subTest(message=message):
                translated = self.catalog.pgettext(
                    "Main Menu|Settings", message)
                self.assertRegex(translated, r"^\(<[^<>]+>\) ImGui")


if __name__ == "__main__":
    unittest.main()
