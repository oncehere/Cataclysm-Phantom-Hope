"""Check the maintained Chinese catalog's multiplayer additions through \
gettext."""

import gettext
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MSGFMT = shutil.which("msgfmt")


@unittest.skipUnless(MSGFMT, "gettext msgfmt is required")
class MultiplayerTranslationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="cph-mp-translation-")
        cls.addClassCleanup(cls.temporary.cleanup)
        output = Path(cls.temporary.name) / "cataclysm-dda.mo"
        result = subprocess.run(
            [MSGFMT, "-c", "-o", str(output),
             str(ROOT / "lang/cph/zh_CN.po")],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode:
            raise AssertionError(result.stdout)
        with output.open("rb") as stream:
            cls.catalog = gettext.GNUTranslations(stream)

    def test_each_recorded_multiplayer_addition_resolves_to_chinese(self):
        sources = json.loads(
            (ROOT / "lang/cph/zh_CN.sources.json").read_text(encoding="utf-8"))
        update = next(record for record in sources["updates"]
                      if record["id"] == "mp-update-20261001")
        messages = update["message_keys"]
        self.assertTrue(messages)
        for message in messages:
            singular = message["msgid"]
            context = message["msgctxt"]
            plural = message["msgid_plural"]
            with self.subTest(message=singular):
                if plural:
                    translate = (self.catalog.npgettext if context
                                 else self.catalog.ngettext)
                    args = (context, singular, plural) if context else (
                        singular, plural)
                    text = translate(*args, 2)
                else:
                    text = (self.catalog.pgettext(context, singular) if context
                            else self.catalog.gettext(singular))
                self.assertNotIn(text, ("", singular, plural))
                if singular == "%1$s: %2$d%%":
                    # The activity name is translated before it is substituted;
                    # this entry localizes only punctuation and preserves args.
                    self.assertEqual(text, "%1$s：%2$d%%")
                else:
                    self.assertRegex(text, "[\u3400-\u9fff]")

    def test_long_cast_warning_keeps_argument_order_and_chinese_plural(self):
        singular = ("%1$s has %2$d hostile nearby and %3$s takes about %4$d "
                    "turns.  Cast anyway?")
        plural = ("%1$s has %2$d hostiles nearby and %3$s takes about %4$d "
                  "turns.  Cast anyway?")
        expected = "%1$s附近有%2$d个敌对生物，而%3$s需要约%4$d回合。仍要施法吗？"
        self.assertEqual(self.catalog.ngettext(singular, plural, 1), expected)
        self.assertEqual(self.catalog.ngettext(singular, plural, 4), expected)

    def test_player_safety_text_describes_simulation_and_experimental_magic(
            self):
        edge = self.catalog.gettext(
            "Your partner is near the edge of the simulated zone (%d tiles)!  "
            "Brake or turn around.")
        self.assertIn("模拟区域", edge)
        self.assertIn("%d", edge)
        self.assertIn("刹车", edge)
        warning = self.catalog.gettext(
            "CO-OP: EXPERIMENTAL.  Spells cast by the joining player resolve "
            "in "
            "their own world: direct damage reaches shared monsters, but "
            "summons, spawned items, terrain changes and buffs may not.  "
            "Teleport spells can move you outside the host's simulated area "
            "and strand you.  Both players must run the same mod list.")
        self.assertIn("实验性", warning)
        self.assertIn("相同的模组列表", warning)
        self.assertIn("移出主机的模拟区域", warning)


if __name__ == "__main__":
    unittest.main()
