"""Checker policy tests; fixtures are not game or installation acceptance."""

import importlib.util
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "linux_identity_probe",
    Path(__file__).resolve().parents[2] /
    "tools/project/linux_identity_probe.py",
)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class IdentityProbePolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.cwd = self.root / "portable"
        self.stage = self.root / "stage"
        self.stage.mkdir()

    def test_home_and_portable_paths_are_not_ccb_paths(self):
        home = probe.expected_paths("home", self.home, None, None, self.cwd)
        self.assertEqual(home["user"], self.home / ".cph-isolation-test")
        self.assertEqual(home["config"], home["user"] / "config")
        portable = probe.expected_paths(
            "portable", self.home, None, None, self.cwd
        )
        self.assertEqual(
            portable["save"], self.cwd / "cph-isolation-test/save"
        )

    def test_xdg_set_empty_and_unset(self):
        xdg = probe.expected_paths(
            "xdg",
            self.home,
            self.root / "data",
            self.root / "config",
            self.cwd,
        )
        self.assertEqual(xdg["user"], self.root / "data/cph-isolation-test")
        self.assertEqual(
            xdg["config"], self.root / "config/cph-isolation-test"
        )
        for empty in [None, ""]:
            paths = probe.expected_paths(
                "xdg", self.home, empty, empty, self.cwd
            )
            self.assertEqual(
                paths["user"], self.home / ".local/share/cph-isolation-test"
            )
            self.assertEqual(
                paths["config"], self.home / ".config/cph-isolation-test"
            )

    def test_explicit_user_does_not_silently_replace_xdg_config(self):
        paths = probe.expected_paths(
            "xdg",
            self.home,
            self.root / "data",
            self.root / "config",
            self.cwd,
            user=self.root / "explicit user",
        )
        self.assertEqual(paths["user"], self.root / "explicit user")
        self.assertEqual(
            paths["config"], self.root / "config/cph-isolation-test"
        )

    def test_explicit_config_and_save_override_defaults(self):
        for mode in ["home", "xdg", "portable"]:
            paths = probe.expected_paths(
                mode,
                self.home,
                None,
                None,
                self.cwd,
                user=self.root / "u",
                config=self.root / "c",
                save=self.root / "s",
            )
            self.assertEqual(
                paths,
                {
                    "user": self.root / "u",
                    "config": self.root / "c",
                    "save": self.root / "s",
                },
            )

    def test_invalid_mode_is_not_assumed_home(self):
        with self.assertRaises(ValueError):
            probe.expected_paths("unknown", self.home, None, None, self.cwd)

    def test_manifest_is_confined_to_destination_prefix(self):
        (self.root / "install_manifest.txt").write_text(
            "/usr/bin/cph-isolation-test\n"
        )
        self.assertEqual(
            probe.validate_manifest(self.root, self.stage, "/usr"),
            [self.stage / "usr/bin/cph-isolation-test"],
        )

    def test_manifest_rejects_empty_relative_and_escaped_paths(self):
        for value in [
            "",
            "relative/file\n",
            "/etc/something\n",
            "/usr/../etc/something\n",
        ]:
            with self.subTest(value=value):
                (self.root / "install_manifest.txt").write_text(value)
                with self.assertRaises(ValueError):
                    probe.validate_manifest(self.root, self.stage, "/usr")

    def test_manifest_rejects_symlink_escape(self):
        (self.stage / "usr").mkdir()
        (self.stage / "usr/bin").symlink_to(
            self.root, target_is_directory=True
        )
        (self.root / "install_manifest.txt").write_text("/usr/bin/escape\n")
        with self.assertRaises(ValueError):
            probe.validate_manifest(self.root, self.stage, "/usr")

    def test_snapshot_detects_new_and_changed_ccb_files(self):
        self.home.mkdir()
        path = self.home / "save"
        path.write_bytes(b"CCB sentinel")
        before = probe.snapshot([self.home])
        path.write_bytes(b"changed")
        self.assertNotEqual(before, probe.snapshot([self.home]))
        path.write_bytes(b"CCB sentinel")
        (self.home / "cph-isolation-test-unexpected").write_bytes(b"new")
        self.assertNotEqual(before, probe.snapshot([self.home]))

    def test_file_sentinel_allows_unrelated_sibling_names(self):
        path = self.root / "ccb"
        path.write_bytes(b"CCB sentinel")
        before = probe.snapshot([path])
        (self.root / "cph-isolation-test").write_bytes(b"separate")
        self.assertEqual(before, probe.snapshot([path]))

    def test_snapshot_rejects_symlink_root(self):
        link = self.root / "link"
        link.symlink_to(self.stage, target_is_directory=True)
        with self.assertRaises(ValueError):
            probe.snapshot([link])

    def test_cache_requires_explicit_test_identity(self):
        path = self.root / "CMakeCache.txt"
        for contents in ["", "CPH_TEST_IDENTITY:BOOL=OFF\n"]:
            path.write_text(contents)
            with self.assertRaises(ValueError):
                probe.read_cache(self.root)
        path.write_text("CPH_TEST_IDENTITY:BOOL=ON\n")
        self.assertEqual(
            probe.read_cache(self.root)["CPH_TEST_IDENTITY"], "ON"
        )

    def test_cmake_boolean_spellings(self):
        for value in ["ON", "True", "YES", "1", "Y"]:
            self.assertTrue(probe.enabled(value))
        for value in ["OFF", "False", "NO", "0", None, ""]:
            self.assertFalse(probe.enabled(value))


if __name__ == "__main__":
    unittest.main()
