"""Offline launcher checks. No game, network, companion, or model is started."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import run


class ScenarioLauncherTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / "source"
        self.manifests = self.root / "manifests"
        self.manifests.mkdir()
        self.manifest_path = self.manifests / "story.json"
        original, self.manifest = run.manifests()["story-delivery"]
        self.manifest_path.write_bytes(original.read_bytes())
        for name in self.manifest["fixture_files"]:
            destination = self.source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(run.ROOT / name, destination)
        self.game = self.root / "game with spaces.exe"
        self.game.write_bytes(b"offline placeholder, never executed")
        self.run_dir = self.root / "isolated run"
        self.addCleanup(patch.stopall)
        patch.object(run, "MANIFESTS", self.manifests).start()

    def prepare(self):
        return run.prepare("story-delivery", self.run_dir, self.game, self.source, self.source)

    def test_bundled_manifests_have_three_distinct_workflows(self):
        with patch.object(run, "MANIFESTS", Path(run.__file__).parent / "manifests"):
            bundled = run.manifests()
            self.assertEqual(set(bundled), {"story-delivery", "companion-actions", "interruption-recovery"})
            self.assertEqual(bundled["story-delivery"][1]["mods"], ["ccb", "Scenario_Story_Smoke"])
            record = {"game": "not-executed", "base_path": str(self.source), "source_root": str(self.source)}
            for name in ("companion-actions", "interruption-recovery"):
                with self.subTest(scenario=name):
                    manifest = bundled[name][1]
                    self.assertEqual(manifest["mods"], ["ccb", "cph_ai_companion"])
                    argv = run.command(self.run_dir, record, manifest, True)
                    self.assertEqual(argv[argv.index("--check-mods"):], ["--check-mods", "ccb", "cph_ai_companion"])

    def test_manifest_rejects_escaped_fixtures_and_duplicate_checks(self):
        for update in ({"fixture_files": ["../real-save"]},
                       {"fixture_files": ["C:/userdata/key"]},
                       {"checks": [self.manifest["checks"][0]] * 2},
                       {"unexpected": "ignored"}):
            with self.subTest(update=update):
                self.manifest_path.write_text(json.dumps({**self.manifest, **update}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    run.load_manifest(self.manifest_path)

    def test_prepare_refuses_existing_directory_without_touching_it(self):
        self.run_dir.mkdir()
        sentinel = self.run_dir / "existing-user-file"
        sentinel.write_bytes(b"preserve")
        with self.assertRaisesRegex(ValueError, "must not exist"):
            self.prepare()
        self.assertEqual(list(self.run_dir.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b"preserve")

    def test_prepare_has_separate_user_and_config_and_not_run_checklist(self):
        self.prepare()
        self.assertEqual(list((self.run_dir / "userdata").iterdir()), [])
        self.assertEqual([path.name for path in (self.run_dir / "config").iterdir()], ["user-default-mods.json"])
        self.assertIn("NOT_RUN", (self.run_dir / "CHECKLIST.md").read_text(encoding="utf-8"))
        self.assertEqual(run.read_run(self.run_dir)[2], self.manifest)

    def test_default_mods_only_seed_new_isolated_config_and_old_runs_still_load(self):
        source_config = self.source / "config" / "user-default-mods.json"
        other_config = self.root / "existing-userdata" / "config" / "user-default-mods.json"
        for path in (source_config, other_config):
            path.parent.mkdir(parents=True)
            path.write_bytes(b"existing user configuration must remain identical")
        self.prepare()
        seeded = self.run_dir / "config" / "user-default-mods.json"
        self.assertEqual(json.loads(seeded.read_text(encoding="utf-8")), {
            "type": "MOD_INFO", "id": "user:default", "conflicts": [],
            "dependencies": self.manifest["mods"],
            "//": "Scenario defaults for newly created isolated test worlds only.", "obsolete": True,
        })
        for path in (source_config, other_config):
            self.assertEqual(path.read_bytes(), b"existing user configuration must remain identical")
        # An older prepared directory has no preset. Rerun must accept it and
        # leave its existing config alone, without migrating saves or identities.
        seeded.unlink()
        before = (self.run_dir / run.MARKER).read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run.launch(self.run_dir, dry_run=True), 0)
        self.assertFalse(seeded.exists())
        self.assertEqual((self.run_dir / run.MARKER).read_bytes(), before)

    def test_launch_arguments_are_explicit_and_check_mods_is_last(self):
        record = self.prepare()
        argv = run.command(self.run_dir, record, self.manifest, True)
        self.assertEqual(argv[0], str(self.game))
        self.assertEqual(argv[argv.index("--userdir") + 1], (self.run_dir / "userdata").as_posix() + "/")
        self.assertEqual(argv[argv.index("--configdir") + 1], (self.run_dir / "config").as_posix() + "/")
        self.assertEqual(argv[argv.index("--datadir") + 1], (self.source / "data").as_posix() + "/")
        self.assertEqual(argv[argv.index("--check-mods"):], ["--check-mods", "ccb", "Scenario_Story_Smoke"])
        self.assertNotIn("--shared", argv)
        self.assertNotIn("--datadir", run.command(self.run_dir, record, self.manifest, False))

    def test_check_mods_uses_the_installed_resources_seen_by_gui(self):
        with patch.object(run, "MANIFESTS", Path(run.__file__).parent / "manifests"):
            original, manifest = run.manifests()["companion-actions"]
        (self.manifests / "companion.json").write_bytes(original.read_bytes())
        app = self.root / "installed app"
        bundled_mod = app / "data/mods/cph_ai_companion/modinfo.json"
        bundled_mod.parent.mkdir(parents=True)
        bundled_mod.write_text('[{"type":"MOD_INFO","id":"cph_ai_companion"}]', encoding="utf-8")
        self.assertFalse((self.source / "data/mods/cph_ai_companion").exists())
        record = run.prepare("companion-actions", self.run_dir, self.game, self.source, app)
        binding = (self.run_dir / run.MARKER).read_bytes()
        defaults = (self.run_dir / "config/user-default-mods.json").read_bytes()

        def fake_game(argv, *, cwd):
            self.assertEqual(cwd, str(app))
            selected = Path(argv[argv.index("--datadir") + 1])
            code = 0 if (selected / "mods/cph_ai_companion/modinfo.json").is_file() else 1
            return Mock(wait=Mock(return_value=code), poll=Mock(return_value=code))

        with patch.object(run.subprocess, "Popen", side_effect=fake_game) as process:
            self.assertEqual(run.launch(self.run_dir, check_mods=True), 0)
        argv = process.call_args.args[0]
        gui = run.command(self.run_dir, record, manifest, False)
        self.assertEqual(argv[argv.index("--datadir") + 1],
                         run.directory_arg(Path(gui[gui.index("--basepath") + 1]) / "data"))
        self.assertEqual(argv[argv.index("--check-mods"):], ["--check-mods", *manifest["mods"]])
        self.assertEqual((self.run_dir / run.MARKER).read_bytes(), binding)
        self.assertEqual((self.run_dir / "config/user-default-mods.json").read_bytes(), defaults)

    def test_dry_run_starts_nothing_and_writes_no_attempt(self):
        self.prepare()
        with patch.object(run.subprocess, "Popen") as process, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(run.launch(self.run_dir, dry_run=True), 0)
        process.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["gameplay"], "NOT_RUN")
        self.assertEqual(list((self.run_dir / "attempts").iterdir()), [])

    def test_run_then_rerun_keeps_same_data_and_records_only_process_results(self):
        self.prepare()
        calls = []

        def fake_game(argv, *, cwd):
            calls.append(argv)
            self.assertEqual(cwd, str(self.source))
            save = Path(argv[argv.index("--userdir") + 1]) / "fake-save"
            if len(calls) == 1:
                save.write_bytes(b"same character")
            else:
                self.assertEqual(save.read_bytes(), b"same character")
            code = 0 if len(calls) == 1 else 7
            return Mock(wait=Mock(return_value=code), poll=Mock(return_value=code))

        with patch.object(run.subprocess, "Popen", side_effect=fake_game):
            self.assertEqual(run.main(["run", "--run-dir", str(self.run_dir)]), 0)
            self.assertEqual(run.main(["rerun", "--run-dir", str(self.run_dir)]), 7)
        self.assertEqual(calls[0], calls[1])
        attempts = [json.loads(p.read_text()) for p in sorted((self.run_dir / "attempts").glob("*.json"))]
        self.assertEqual([x["exit_code"] for x in attempts], [0, 7])
        self.assertEqual([x["gameplay"] for x in attempts], ["NOT_RUN", "NOT_RUN"])

    def test_changed_binary_blocks_before_launch(self):
        self.prepare()
        self.game.write_bytes(b"a different build")
        with patch.object(run.subprocess, "Popen") as process:
            with self.assertRaisesRegex(ValueError, "binary changed"):
                run.launch(self.run_dir)
        process.assert_not_called()

    def test_changed_fixture_or_snapshot_blocks_before_launch(self):
        self.prepare()
        fixture = self.source / self.manifest["fixture_files"][0]
        original = fixture.read_bytes()
        fixture.write_bytes(original + b"\n-- changed")
        with self.assertRaisesRegex(ValueError, "fixture changed"):
            run.read_run(self.run_dir)
        fixture.write_bytes(original)
        (self.run_dir / "scenario.json").write_bytes(self.manifest_path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "manifest changed"):
            run.read_run(self.run_dir)

    def test_copied_run_is_rejected_instead_of_retargeting_saves(self):
        self.prepare()
        copied = self.root / "copy"
        shutil.copytree(self.run_dir, copied)
        with self.assertRaisesRegex(ValueError, "original prepared"):
            run.read_run(copied)

    def test_lock_refuses_concurrent_launch_and_preserves_existing_lock(self):
        self.prepare()
        lock = self.run_dir / "launch.lock"
        lock.write_text("existing game", encoding="utf-8")
        with patch.object(run.subprocess, "Popen") as process:
            with self.assertRaisesRegex(ValueError, "launch lock"):
                run.launch(self.run_dir)
        process.assert_not_called()
        self.assertEqual(lock.read_text(), "existing game")

    def test_spawn_failure_keeps_not_run_record_and_releases_lock(self):
        self.prepare()
        with patch.object(run.subprocess, "Popen", side_effect=OSError("fake launch failure")):
            with self.assertRaises(OSError):
                run.launch(self.run_dir)
        self.assertFalse((self.run_dir / "launch.lock").exists())
        result = json.loads((self.run_dir / "attempts/0001.json").read_text())
        self.assertIsNone(result["exit_code"])
        self.assertEqual(result["gameplay"], "NOT_RUN")

    def test_ctrl_c_keeps_lock_if_child_game_is_still_alive(self):
        self.prepare()
        child = Mock(wait=Mock(side_effect=KeyboardInterrupt), poll=Mock(return_value=None))
        with patch.object(run.subprocess, "Popen", return_value=child):
            with self.assertRaises(KeyboardInterrupt):
                run.launch(self.run_dir)
        self.assertTrue((self.run_dir / "launch.lock").exists())
        result = json.loads((self.run_dir / "attempts/0001.json").read_text())
        self.assertTrue(result["game_still_running"])
        self.assertIsNone(result["exit_code"])
        with self.assertRaisesRegex(ValueError, "launch lock"):
            run.launch(self.run_dir)

    def test_prepare_rejects_stale_app_fixture_before_writing_userdata(self):
        assets = self.root / "test-app"
        shutil.copytree(self.source, assets)
        (assets / self.manifest["fixture_files"][0]).write_text("old app data", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "matching scenario fixture"):
            run.prepare("story-delivery", self.run_dir, self.game, self.source, assets)
        self.assertFalse(self.run_dir.exists())

    def test_output_symlink_to_other_userdata_is_rejected(self):
        self.prepare()
        other = self.root / "other-userdata"
        other.mkdir()
        original_resolve = Path.resolve

        def redirected(path, *args, **kwargs):
            if path == self.run_dir / "userdata":
                return other
            return original_resolve(path, *args, **kwargs)

        with patch.object(Path, "resolve", redirected):
            with self.assertRaisesRegex(ValueError, "output directories"):
                run.read_run(self.run_dir)


if __name__ == "__main__":
    unittest.main()
