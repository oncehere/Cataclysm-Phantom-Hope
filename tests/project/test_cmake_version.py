"""Run the version recipe in disposable Git checkouts, without compiling."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CMAKE = shutil.which("cmake")
GIT = shutil.which("git")


@unittest.skipUnless(CMAKE and GIT, "CMake and Git are required")
class CMakeVersionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "repository"
        (self.repo / "src").mkdir(parents=True)
        (self.repo / "CMakeModules").mkdir()
        for relative in (
            "src/version.cmake",
            "CMakeModules/GetGitRevisionDescription.cmake",
            "CMakeModules/GetGitRevisionDescription.cmake.in",
        ):
            shutil.copyfile(ROOT / relative, self.repo / relative)
        (self.repo / "tracked.txt").write_text("original\n")
        (self.repo / ".gitignore").write_text(
            "src/version.h\nVERSION.txt\nCMakeFiles/\n"
        )
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith("GIT_")}
        self.env.update(
            GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
            GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@invalid",
            GIT_COMMITTER_NAME="Fixture",
            GIT_COMMITTER_EMAIL="fixture@invalid",
        )
        self.git("init", "--quiet")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "Version fixture")

    def git(self, *args, source=None):
        return subprocess.run(
            [GIT, "-C", str(source or self.repo), *args], env=self.env,
            capture_output=True, text=True, check=True,
        ).stdout.strip()

    def version(self, source, *options):
        return subprocess.run(
            [CMAKE, *options, "-P", str(source / "src/version.cmake")],
            cwd=source, env=self.env, capture_output=True, text=True,
            check=False,
        )

    def test_checkout_and_absolute_gitdir_worktree_report_head_and_dirty(self):
        worktree = self.root / "worktree"
        self.git("worktree", "add", "--detach", str(worktree), "HEAD")
        gitdir = (worktree / ".git").read_text()
        gitdir = gitdir.removeprefix("gitdir: ").strip()
        self.assertTrue(Path(gitdir).is_absolute())
        expected = self.git("describe", "--tags", "--always",
                            "--match", "cdda-*")
        head = self.git("rev-parse", "HEAD")
        for source in (self.repo, worktree):
            for dirty in ("clean", "unstaged", "staged"):
                with self.subTest(source=source.name, dirty=dirty):
                    if dirty != "clean":
                        (source / "tracked.txt").write_text("changed\n")
                    if dirty == "staged":
                        self.git("add", "tracked.txt", source=source)
                    result = self.version(source, "-DGIT_BINARY=" + GIT)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    suffix = "-dirty" if dirty != "clean" else ""
                    self.assertIn(
                        '-' + expected + suffix + '"',
                        (source / "src/version.h").read_text(),
                    )
                    self.assertIn("commit sha: " + head,
                                  (source / "VERSION.txt").read_text())

    def test_without_git_preserves_release_header_or_writes_null(self):
        header = self.repo / "src/version.h"
        for existing in ('#define VERSION "archive-version"\n', "", None):
            with self.subTest(existing=existing):
                if existing is None:
                    header.unlink(missing_ok=True)
                else:
                    header.write_text(existing)
                result = self.version(
                    self.repo, "-DCMAKE_DISABLE_FIND_PACKAGE_Git=TRUE"
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                if existing:
                    self.assertEqual(header.read_text(), existing)
                else:
                    self.assertIn('#define VERSION "NULL"', header.read_text())

    def test_source_archive_does_not_use_enclosing_repository(self):
        archive = self.repo / "archive"
        (archive / "src").mkdir(parents=True)
        shutil.copyfile(ROOT / "src/version.cmake",
                        archive / "src/version.cmake")
        header = archive / "src/version.h"
        for existing in ('#define VERSION "archive-version"\n',
                         '// #define VERSION "comment-only"\n', ""):
            with self.subTest(existing=existing):
                header.write_text(existing)
                result = self.version(archive, "-DGIT_BINARY=" + GIT)
                self.assertEqual(result.returncode, 0, result.stderr)
                if existing.startswith("#define"):
                    self.assertEqual(header.read_text(), existing)
                else:
                    self.assertIn('#define VERSION "NULL"', header.read_text())
                self.assertFalse((archive / "VERSION.txt").exists())

    def test_invalid_git_fails_recipe_and_configure(self):
        invalid = "-DGIT_BINARY=" + str(self.root / "missing-git")
        result = self.version(self.repo, invalid)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Git", result.stderr)
        # Execute the real configure-time version block in isolation; failure
        # must propagate before any compiler or generator is needed.
        block = (ROOT / "CMakeLists.txt").read_text().split(
            "# Retrieve version", 1
        )[1].split("#OS Check Placeholders", 1)[0]
        configure = self.root / "configure-version.cmake"
        configure.write_text("# Retrieve version" + block)
        result = subprocess.run(
            [CMAKE, "-DGIT_EXECUTABLE=" + str(self.root / "missing-git"),
             "-P", str(configure)], cwd=self.repo,
            env=self.env, capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("version generation failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
