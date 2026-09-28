"""Build the supplementary catalog without changing locked base catalogs."""

import gettext
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MSGFMT = shutil.which("msgfmt")


def translated_literals(path):
    """Read adjacent C++ literals used by the new rules' translation calls."""
    for match in re.finditer(
        r'\b(?:_|to_translation)\(\s*((?:"(?:[^"\\]|\\.)*"\s*)+)',
        path.read_text(encoding="utf-8"),
    ):
        yield "".join(json.loads(part) for part in
                      re.findall(r'"(?:[^"\\]|\\.)*"', match[1]))


@unittest.skipUnless(MSGFMT, "gettext msgfmt is required")
class CphTranslationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cph-translation-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.lang = self.root / "lang"
        (self.lang / "po").mkdir(parents=True)
        shutil.copytree(ROOT / "lang/cph", self.lang / "cph")
        for filename in ("Makefile", "CMakeLists.txt", "compile_mo.sh",
                         "CPHTranslations.cmake"):
            shutil.copyfile(ROOT / "lang" / filename, self.lang / filename)
        self.baseline = self.lang / "mo/de/LC_MESSAGES/cataclysm-dda.mo"
        self.baseline.parent.mkdir(parents=True)
        self.baseline.write_bytes(b"locked upstream catalog fixture\n")
        self.supplement = (self.lang /
                           "mo/cph/zh_CN/LC_MESSAGES/cataclysm-dda.mo")

    def run_command(self, *command):
        result = subprocess.run(
            command, cwd=self.root, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(result.returncode, 0, result.stdout)
        return result

    def catalog(self):
        self.assertEqual(self.baseline.read_bytes(),
                         b"locked upstream catalog fixture\n")
        with self.supplement.open("rb") as stream:
            return gettext.GNUTranslations(stream)

    def assert_chinese(self):
        self.assertEqual(self.catalog().gettext("Follow core / mods"),
                         "跟随本体／MOD")

    def test_catalog_covers_every_new_rule_and_dialog_message(self):
        self.supplement.parent.mkdir(parents=True)
        self.run_command(MSGFMT, "-c", "-o", str(self.supplement),
                         str(self.lang / "cph/zh_CN.po"))
        catalog = self.catalog()
        for filename in ("world_advanced_definitions.cpp",
                         "world_advanced_options.cpp",
                         "world_advanced_runtime.cpp",
                         "world_advanced_ui.cpp"):
            messages = list(translated_literals(ROOT / "src" / filename))
            self.assertTrue(messages, filename)
            for message in messages:
                with self.subTest(file=filename, message=message):
                    self.assertNotEqual(catalog.gettext(message), message)

    @unittest.skipUnless(shutil.which("make"), "GNU Make is required")
    def test_make_builds_supplement_with_and_without_language_selection(self):
        self.run_command("make", "-C", str(self.lang), "LANGUAGES=zh_CN de")
        self.assert_chinese()
        # Removing only the output must be recoverable on the next build.
        self.supplement.unlink()
        self.run_command("make", "-C", str(self.lang))
        self.assert_chinese()

    @unittest.skipUnless(shutil.which("bash"), "Bash is required")
    def test_shell_compiler_supports_supplement_only_source_tree(self):
        self.run_command("bash", "lang/compile_mo.sh", "all")
        self.assert_chinese()
        self.supplement.unlink()
        self.run_command("bash", "lang/compile_mo.sh", "zh_CN", "de")
        self.assert_chinese()

    @unittest.skipUnless(shutil.which("cmake"), "CMake is required")
    def test_cmake_direct_nonrelease_target_builds_the_supplement(self):
        (self.root / "CMakeLists.txt").write_text(
            'cmake_minimum_required(VERSION 3.20)\n'
            'project(cph_translation_fixture NONE)\n'
            f'set(GETTEXT_MSGFMT_EXECUTABLE "{Path(MSGFMT).as_posix()}")\n'
            'set(RELEASE OFF)\n'
            'include(lang/CPHTranslations.cmake)\n'
            'add_custom_target(game_fixture)\n'
            'add_dependencies(game_fixture cph_translations)\n',
            encoding="utf-8")
        self.run_command("cmake", "-S", ".", "-B", "build")
        self.run_command("cmake", "--build", "build",
                         "--target", "game_fixture")
        self.assert_chinese()

    @unittest.skipUnless(shutil.which("cmake"), "CMake is required")
    def test_cmake_installs_portable_prefix_and_test_identity_catalogs(self):
        for profile, prefix_data, identity, destination in (
            ("portable", "OFF", "OFF", "lang/mo/cph"),
            ("prefix", "ON", "OFF", "share/locale/cph"),
            ("identity", "ON", "ON", "share/cph-isolation-test/lang/mo/cph"),
        ):
            with self.subTest(profile=profile):
                msgfmt_path = Path(MSGFMT).as_posix()
                (self.root / "CMakeLists.txt").write_text(
                    'cmake_minimum_required(VERSION 3.20)\n'
                    'project(cph_translation_fixture NONE)\n'
                    'set(CMAKE_INSTALL_DATADIR "share/cph-isolation-test")\n'
                    'set(CMAKE_INSTALL_LOCALEDIR "share/locale")\n'
                    f'set(GETTEXT_MSGFMT_EXECUTABLE "{msgfmt_path}")\n'
                    'set(RELEASE ON)\n'
                    f'set(USE_PREFIX_DATA_DIR {prefix_data})\n'
                    f'set(CPH_TEST_IDENTITY {identity})\n'
                    'set(LANGUAGES "zh_CN;de")\n'
                    'include(lang/CPHTranslations.cmake)\n'
                    'if(NOT CPH_TEST_IDENTITY)\n'
                    '  add_subdirectory(lang)\n'
                    'endif()\n', encoding="utf-8")
                build = f"build-{profile}"
                install = self.root / f"install-{profile}"
                self.run_command("cmake", "-S", ".", "-B", build)
                self.run_command("cmake", "--build", build)
                self.run_command("cmake", "--install", build,
                                 "--prefix", str(install))
                installed = (install / destination /
                             "zh_CN/LC_MESSAGES/cataclysm-dda.mo")
                self.assertEqual(installed.read_bytes(),
                                 self.supplement.read_bytes())
                if identity == "OFF":
                    base = ((install / destination).parent /
                            "de/LC_MESSAGES/cataclysm-dda.mo")
                    self.assertEqual(base.read_bytes(),
                                     self.baseline.read_bytes())
                self.assert_chinese()


if __name__ == "__main__":
    unittest.main()
