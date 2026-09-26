"""Exercise the real documentation install rules without building the game."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.name == "posix", "DESTDIR staging requires POSIX")
class DocumentInstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cmake = shutil.which("cmake")
        if not cls.cmake:
            raise unittest.SkipTest("cmake is required")
        if shutil.which("ninja"):
            cls.generator = "Ninja"
        elif shutil.which("make"):
            cls.generator = "Unix Makefiles"
        else:
            raise unittest.SkipTest("ninja or make is required")
        # Run the project's actual path setup and installation commands. The
        # other blocks require game dependencies unrelated to this gate.
        source = (ROOT / "CMakeLists.txt").read_text()
        cls.path_setup = source.split(
            "# Set build types and display info\n", 1
        )[1].split('message(STATUS "GIT_BINARY', 1)[0]
        cls.install_rules = source.split(
            "# The source-tree symlink points into data/json, "
            "which moves on installation.\n", 1
        )[1].split("\nif (RELEASE)", 1)[0]

    def check_install(self, doc_directory, *options):
        with tempfile.TemporaryDirectory(
            prefix="cph-doc-install-"
        ) as temporary:
            root = Path(temporary)
            source = root / "source"
            build = root / "build"
            prefix = root / "prefix with spaces"
            stage = root / "stage"
            (source / "doc/JSON").mkdir(parents=True)
            (source / "data/json").mkdir(parents=True)
            (source / "src").mkdir()
            content = "Loading order documentation fixture\n"
            (source / "data/json/LOADING_ORDER.md").write_text(content)
            (source / "doc/JSON/JSON_LOADING_ORDER.md").symlink_to(
                "../../data/json/LOADING_ORDER.md"
            )
            (source / "doc/README.md").write_text("Existing documentation\n")
            shutil.copyfile(
                ROOT / "src/prefix.h.in", source / "src/prefix.h.in"
            )
            (source / "CMakeLists.txt").write_text(
                "cmake_minimum_required(VERSION 3.20)\n"
                "project(CPHDocumentInstall NONE)\n" +
                self.path_setup + self.install_rules
            )
            command = [
                self.cmake, "-S", str(source), "-B", str(build),
                "-G", self.generator,
                "-DCMAKE_INSTALL_PREFIX=" + str(prefix),
                "-DCMAKE_BUILD_TYPE=Release",
                "-DUSE_PREFIX_DATA_DIR=ON",
                "-DCPH_TEST_IDENTITY=OFF",
                *options,
            ]
            configured = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
            self.assertEqual(
                configured.returncode, 0, configured.stdout + configured.stderr
            )
            installed = subprocess.run(
                [self.cmake, "--install", str(build)],
                env={**os.environ, "DESTDIR": str(stage)},
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(
                installed.returncode, 0, installed.stdout + installed.stderr
            )
            expected = {
                prefix / doc_directory / "README.md",
                prefix / doc_directory / "JSON/JSON_LOADING_ORDER.md",
            }
            manifest = set(
                Path(line) for line in
                (build / "install_manifest.txt").read_text().splitlines()
            )
            self.assertEqual(manifest, expected)
            staged_files = {
                stage / path.relative_to(path.anchor) for path in expected
            }
            self.assertEqual(
                {path for path in stage.rglob("*") if path.is_file()},
                staged_files,
            )
            for path in staged_files:
                self.assertFalse(path.is_symlink())
                if path.name == "JSON_LOADING_ORDER.md":
                    self.assertEqual(path.read_text(), content)

    def test_default_prefix_install(self):
        self.check_install("share/cataclysm-dda/doc/doc")

    def test_debug_defaults(self):
        self.check_install("share/doc/doc", "-DCMAKE_BUILD_TYPE=Debug")

    def test_test_identity_prefix(self):
        self.check_install(
            "share/doc/cph-isolation-test/doc", "-DCPH_TEST_IDENTITY=ON"
        )

    def test_portable_install(self):
        self.check_install("doc", "-DUSE_PREFIX_DATA_DIR=OFF")

    def test_explicit_document_directory(self):
        self.check_install(
            "custom docs/doc", "-DCMAKE_INSTALL_DOCDIR=custom docs"
        )

    def test_empty_document_directory_uses_type_default(self):
        self.check_install(
            "share/cataclysm-dda/doc/doc", "-DCMAKE_INSTALL_DOCDIR="
        )

    def test_debug_dataroot_override(self):
        self.check_install(
            "assets/doc/doc", "-DCMAKE_BUILD_TYPE=Debug",
            "-DCMAKE_INSTALL_DATAROOTDIR=assets",
        )


if __name__ == "__main__":
    unittest.main()
