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
from unittest import mock


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

    def test_tiles_build_uses_sdl3_without_a_backend_flag(self):
        if not shutil.which("ninja"):
            self.skipTest("ninja is required")
        # Only SDL3 targets are supplied. Selecting the former default SDL2
        # branch must fail configuration, even though these are tiny sources.
        (self.source / "data/shaders").mkdir()
        shutil.copyfile(ROOT / "tools/build_shaders.py",
                        self.source / "tools/build_shaders.py")
        cmake = """
cmake_minimum_required(VERSION 3.20)
project(tiles_backend_fixture LANGUAGES C CXX)
set(TILES ON)
set(CURSES OFF)
set(SOUND ON)
set(CATA_ENABLE_LUA_PLATFORM OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
foreach(component SDL3 SDL3_image SDL3_ttf SDL3_mixer)
    add_library(${component}::${component} INTERFACE IMPORTED)
    if(FIXTURE_STATIC_TARGETS)
        add_library(${component}::${component}-static INTERFACE IMPORTED)
    endif()
endforeach()
add_subdirectory(src)
"""
        self.write("CMakeLists.txt", cmake)
        # The empty shader fixture exercises the real build rule/stamp without
        # claiming to validate GPU artifacts or needing glslang in tooling CI.
        with mock.patch.dict(os.environ, {"GLSLANG": COMPILER}):
            for dynamic, static_targets in (("ON", "OFF"), ("OFF", "ON"),
                                            ("OFF", "OFF")):
                with self.subTest(dynamic=dynamic, static=static_targets):
                    build = self.root / f"tiles-{dynamic}-{static_targets}"
                    self.command(CMAKE, "-S", str(self.source), "-B", str(build),
                                 "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Debug",
                                 "-DCMAKE_CXX_COMPILER=" + COMPILER,
                                 "-DDYNAMIC_LINKING=" + dynamic,
                                 "-DFIXTURE_STATIC_TARGETS=" + static_targets)
                    self.command(CMAKE, "--build", str(build), "--target",
                                 "cataclysm-tiles", "--parallel", "15")
                    self.command(str(build / "src/cataclysm-tiles"))
                    stamp = self.source / "data/shaders/build-spv.stamp"
                    self.assertTrue(stamp.is_file())
                    stamp.unlink()

    def test_headless_build_does_not_require_sdl_targets(self):
        if not shutil.which("ninja"):
            self.skipTest("ninja is required")
        self.write("CMakeLists.txt", """
cmake_minimum_required(VERSION 3.20)
project(headless_backend_fixture LANGUAGES C CXX)
set(TILES OFF)
set(CURSES OFF)
set(HEADLESS ON)
set(CATA_ENABLE_LUA_PLATFORM OFF)
add_subdirectory(src)
""")
        self.command(CMAKE, "-S", str(self.source), "-B", str(self.build),
                     "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Debug",
                     "-DCMAKE_CXX_COMPILER=" + COMPILER)
        self.command(CMAKE, "--build", str(self.build), "--target", "cataclysm",
                     "--parallel", "15")
        self.command(str(self.build / "src/cataclysm"))

    def test_text_backends_link_sound_without_image_or_font_libraries(self):
        if not shutil.which("ninja"):
            self.skipTest("ninja is required")
        (self.source / "audio").mkdir()
        self.write("audio/fixture_audio.h", "int fixture_audio();\n")
        self.write("audio/fixture_audio.cpp",
                   "int fixture_audio() { return 42; }\n")
        self.write("src/main.cpp", """
#ifndef SDL_SOUND
#error Terminal sound was requested but was not enabled.
#endif
#include "fixture_audio.h"
int main() { return fixture_audio() == 42 ? 0 : 1; }
""")
        self.write("CMakeLists.txt", """
cmake_minimum_required(VERSION 3.20)
project(text_audio_fixture LANGUAGES C CXX)
set(TILES OFF)
set(SOUND ON)
set(CATA_ENABLE_LUA_PLATFORM OFF)
add_library(fixture_audio STATIC audio/fixture_audio.cpp)
target_include_directories(fixture_audio PUBLIC "${CMAKE_SOURCE_DIR}/audio")
add_library(SDL3::SDL3 INTERFACE IMPORTED)
add_library(SDL3_mixer::SDL3_mixer ALIAS fixture_audio)
if(NOT DYNAMIC_LINKING)
    add_library(SDL3::SDL3-static INTERFACE IMPORTED)
    add_library(SDL3_mixer::SDL3_mixer-static ALIAS fixture_audio)
endif()
add_subdirectory(src)
""")
        for backend in ("CURSES", "HEADLESS"):
            for dynamic in ("ON", "OFF"):
                with self.subTest(backend=backend, dynamic=dynamic):
                    build = self.root / f"audio-{backend}-{dynamic}"
                    self.command(CMAKE, "-S", str(self.source), "-B", str(build),
                                 "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Debug",
                                 "-DCMAKE_CXX_COMPILER=" + COMPILER,
                                 "-D" + backend + "=ON",
                                 "-DDYNAMIC_LINKING=" + dynamic)
                    self.command(CMAKE, "--build", str(build), "--target",
                                 "cataclysm", "--parallel", "15")
                    self.command(str(build / "src/cataclysm"))

    def test_cmake_rejects_legacy_off_for_sound_as_well_as_tiles(self):
        if not shutil.which("ninja"):
            self.skipTest("ninja is required")
        # Execute the actual project option normalization and diagnostic before
        # library discovery. HEADLESS has already disabled TILES at this point.
        option_setup = (ROOT / "CMakeLists.txt").read_text().split(
            "# Can't use both home and xdg directories", 1)[0]
        (self.source / "CMakeModules").mkdir()
        shutil.copyfile(ROOT / "CMakeModules/ListImportedTargets.cmake",
                        self.source / "CMakeModules/ListImportedTargets.cmake")
        self.write("CMakeLists.txt", option_setup)
        for tiles, sound, headless in (("ON", "OFF", "OFF"),
                                       ("OFF", "ON", "OFF"),
                                       ("OFF", "ON", "ON"),
                                       ("OFF", "OFF", "ON"),
                                       ("OFF", "OFF", "OFF")):
            with self.subTest(tiles=tiles, sound=sound, headless=headless):
                build = self.root / f"legacy-{tiles}-{sound}-{headless}"
                result = subprocess.run([
                    CMAKE, "-S", str(self.source), "-B", str(build),
                    "-G", "Ninja", "-DCMAKE_CXX_COMPILER=" + COMPILER,
                    "-DUSE_SDL3=OFF", "-DTILES=" + tiles,
                    "-DSOUND=" + sound, "-DHEADLESS=" + headless,
                ], capture_output=True, text=True, check=False)
                if tiles == "ON" or sound == "ON":
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("USE_SDL3=OFF is no longer supported",
                                  result.stderr)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_make_rejects_legacy_off_for_sound_as_well_as_tiles(self):
        make = shutil.which("make")
        if not make:
            self.skipTest("make is required")
        shutil.copyfile(ROOT / "Makefile", self.source / "Makefile")
        # Run a real, harmless prefix recipe in the disposable source fixture.
        # A rejected backend flag must fail before any build recipe executes.
        for tiles, sound in (("1", "0"), ("0", "1"), ("1", "1"),
                             ("0", "0")):
            with self.subTest(tiles=tiles, sound=sound):
                result = subprocess.run([
                    make, "--no-print-directory", "prefix", "SDL3=0",
                    "TILES=" + tiles, "SOUND=" + sound,
                    "ASTYLE=0", "LINTJSON=0", "LOCALIZE=0", "PREFIX=/fixture",
                ], cwd=self.source, capture_output=True, text=True, check=False)
                if tiles == "1" or sound == "1":
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("SDL3=0 is no longer supported", result.stderr)
                    self.assertFalse((self.source / "src/prefix.h").exists())
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertTrue((self.source / "src/prefix.h").is_file())


if __name__ == "__main__":
    unittest.main()
