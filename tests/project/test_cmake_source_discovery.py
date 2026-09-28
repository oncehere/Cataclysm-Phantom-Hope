"""Build real CMake targets with tiny sources after file additions/removals.

The disposable POSIX fixture replaces game/library implementations, but copies
the engine and test target definitions unchanged. No game checkout is built.
"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CMAKE = shutil.which("cmake")
COMPILER = (shutil.which("c++") or shutil.which("g++") or
            shutil.which("clang++"))


@unittest.skipUnless(os.name == "posix" and CMAKE and COMPILER,
                     "POSIX, CMake and a C++ compiler are required")
class CMakeSourceDiscoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cph-cmake-discovery-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source with spaces"
        self.build = self.root / "build"
        for directory in ("src/third-party", "tests", "tools", "data/mods"):
            (self.source / directory).mkdir(parents=True)
        for relative in (
            "src/CMakeLists.txt", "tests/CMakeLists.txt",
            "src/version.cmake", "tools/generate_builtin_mods.py",
        ):
            shutil.copyfile(ROOT / relative, self.source / relative)
        self.write("CMakeLists.txt", """
cmake_minimum_required(VERSION 3.20)
project(source_discovery_fixture LANGUAGES C CXX)
enable_testing()
set(CURSES ON)
set(TILES OFF)
set(BUILD_TESTING ON)
set(CATA_ENABLE_LUA_PLATFORM OFF)
add_subdirectory(src)
add_subdirectory(tests)
file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/engine-sources.txt"
     CONTENT "$<TARGET_PROPERTY:cataclysm-common,SOURCES>")
""")
        self.write("src/third-party/CMakeLists.txt",
                   "add_library(third-party INTERFACE)\n")
        self.write("src/version.h", '#define VERSION "fixture"\n')
        self.write("src/main.cpp", "int main() { return 0; }\n")
        self.write("src/messages.cpp", "void fixture_messages() {}\n")
        self.write("src/anchor.cpp", "int engine_count = 0;\n")
        self.write("src/anchor.h", "#pragma once\n")
        self.write("tests/main.cpp", """
#include <iostream>
extern int engine_count;
int test_count = 0;
int main() { std::cout << engine_count << ':' << test_count << '\\n'; }
""")

    def write(self, relative, content):
        (self.source / relative).write_text(content, encoding="utf-8")

    def command(self, *args):
        result = subprocess.run(args, cwd=self.source, capture_output=True,
                                text=True, check=False)
        self.assertEqual(result.returncode, 0,
                         f"{args}\n{result.stdout}\n{result.stderr}")
        return result.stdout.strip()

    def build_and_run(self, expected):
        self.command(CMAKE, "--build", str(self.build), "--config", "Debug",
                     "--target", "cataclysm", "cata_test", "--parallel", "2")
        directory = self.build / "tests"
        if self.generator == "Ninja Multi-Config":
            directory /= "Debug"
        self.assertEqual(self.command(str(directory / "cata_test")), expected)

    def exercise_generator(self, generator, program):
        if not shutil.which(program):
            self.skipTest(f"{program} is required for {generator}")
        self.generator = generator
        self.command(CMAKE, "-S", str(self.source), "-B", str(self.build),
                     "-G", generator, "-DCMAKE_BUILD_TYPE=Debug",
                     "-DCMAKE_CXX_COMPILER=" + COMPILER)
        self.build_and_run("0:0")

        # A header-only change must update the target inventory independently
        # of the C++ glob; adding both together would hide a stale header glob.
        self.write("src/added.h", "#pragma once\n")
        self.build_and_run("0:0")
        sources = self.build / "engine-sources.txt"
        self.assertIn("added.h", sources.read_text(encoding="utf-8"))

        # Only the file set changes: neither CMakeLists.txt nor an existing
        # compilation unit is touched. Ordinary build must discover both.
        self.write("src/added.cpp", """
extern int engine_count;
struct EngineRegistration { EngineRegistration() { ++engine_count; } };
EngineRegistration engine_registration;
""")
        self.build_and_run("1:0")
        self.write("tests/added_test.cpp", """
extern int test_count;
struct TestRegistration { TestRegistration() { ++test_count; } };
TestRegistration test_registration;
""")
        self.build_and_run("1:1")

        (self.source / "src/added.h").unlink()
        self.build_and_run("1:1")
        self.assertNotIn("added.h", sources.read_text(encoding="utf-8"))

        # Removed sources must stop participating without a manual configure.
        (self.source / "src/added.cpp").unlink()
        self.build_and_run("0:1")
        (self.source / "tests/added_test.cpp").unlink()
        self.build_and_run("0:0")
        self.assertNotIn("added.h", sources.read_text(encoding="utf-8"))

        # An unrelated file does not change the generated source inventory.
        before = sources.stat().st_mtime_ns
        self.write("src/notes.txt", "not a translation unit\n")
        self.build_and_run("0:0")
        self.assertEqual(sources.stat().st_mtime_ns, before)

    def test_ninja_discovers_source_changes(self):
        self.exercise_generator("Ninja", "ninja")

    def test_multi_config_discovers_source_changes(self):
        self.exercise_generator("Ninja Multi-Config", "ninja")

    def test_makefiles_discovers_source_changes(self):
        self.exercise_generator("Unix Makefiles", "make")


if __name__ == "__main__":
    unittest.main()
