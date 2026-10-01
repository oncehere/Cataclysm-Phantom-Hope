from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch

from cph_ai_companion.cli import (CliError, doctor, initialize_profile, install_mod,
                                  main, remove_mod, stop_session, INSTALL_MANIFEST)
from cph_ai_companion.config import load_config
from cph_ai_companion.protocol import PROTOCOL_VERSION, schema_digest
from cph_ai_companion.transport import SessionDescriptor


class FakeClient:
    safe = True

    def __init__(self, descriptor):
        pass

    def connect(self):
        return {}

    def request(self, method, params):
        return {"safe_to_remove": self.safe, "world_dependencies": []}

    def close(self):
        pass


class CliTests(unittest.TestCase):
    def test_init_is_offline_preserves_background_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "profile"
            with patch("cph_ai_companion.provider._call_openai", side_effect=AssertionError("must remain offline")):
                self.assertFalse(initialize_profile(profile)["model_started"])
                config = load_config(profile)
                self.assertTrue(Path(config["paths"]["background"]).is_absolute())
                result = doctor(profile)
                self.assertIs(result["checks"]["model_called"], False)
            (profile / "background.md").write_text("User's own background")
            with self.assertRaisesRegex(CliError, "profile_already_initialized"):
                initialize_profile(profile)
            self.assertEqual((profile / "background.md").read_text(), "User's own background")
            self.assertFalse((profile / ".writer.lock").exists())

    def test_mod_installed_from_package_resources_and_no_silent_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            user = Path(directory) / "game"
            target = install_mod(user)
            self.assertTrue((target / "mod.lua").is_file())
            self.assertTrue((target / "main.lua").is_file())
            self.assertTrue((target / INSTALL_MANIFEST).is_file())
            self.assertEqual(install_mod(user), target)
            (target / "mod.lua").write_text("User edit")
            with self.assertRaises(CliError):
                install_mod(user)

    def test_install_metadata_cannot_be_scanned_as_gameplay_json(self):
        with tempfile.TemporaryDirectory() as directory:
            target = install_mod(directory)
            # CPH's MOD loader scans *.json as game data and requires a type.
            # Ownership metadata is valid JSON but must not enter that scan.
            game_json = [path.relative_to(target).as_posix() for path in target.rglob("*.json")]
            self.assertEqual([name for name in game_json if name != "modinfo.json"], [])
            manifest = json.loads((target / INSTALL_MANIFEST).read_text())
            self.assertEqual(set(manifest["files"]), {"mod.lua", "main.lua"})
            self.assertNotIn("type", manifest)

    def test_remove_requires_game_confirmation_and_preserves_unknown_files(self):
        with tempfile.TemporaryDirectory() as directory:
            user = Path(directory) / "game"
            target = install_mod(user)
            (target / "user-notes.txt").write_text("keep")
            descriptor = SessionDescriptor(Path(directory) / "session.json", "s", "127.0.0.1", 1,
                                           Path(directory) / "credential", PROTOCOL_VERSION, schema_digest(), user_dir=str(user))
            with patch("cph_ai_companion.cli.JsonRpcClient", FakeClient):
                FakeClient.safe = False
                with self.assertRaisesRegex(CliError, "mod_removal_not_confirmed_safe"):
                    remove_mod(user, descriptor)
                self.assertTrue((target / "mod.lua").exists())
                FakeClient.safe = True
                remove_mod(user, descriptor)
                self.assertFalse((target / "mod.lua").exists())
                self.assertEqual((target / "user-notes.txt").read_text(), "keep")

    def test_install_cannot_claim_existing_unowned_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "mods/cph_ai_companion"
            target.mkdir(parents=True)
            (target / "user-data.txt").write_text("keep")
            with self.assertRaisesRegex(CliError, "unowned_mod_destination"):
                install_mod(directory)

    def test_errors_are_codes_without_private_paths(self):
        with tempfile.TemporaryDirectory(prefix="private-profile-") as directory:
            output = io.StringIO()
            with redirect_stderr(output):
                self.assertEqual(main(["doctor", "--offline", "--profile", directory]), 2)
            self.assertEqual(json.loads(output.getvalue())["error"]["code"], "invalid_configuration")
            self.assertNotIn(directory, output.getvalue())

    def test_installer_refuses_manifest_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            target = install_mod(directory)
            manifest = target / INSTALL_MANIFEST
            value = json.loads(manifest.read_text())
            value["files"]["../../secret"] = "a" * 64
            manifest.write_text(json.dumps(value))
            with self.assertRaisesRegex(CliError, "invalid_install_manifest"):
                install_mod(directory)

    def test_stop_without_runtime_requests_native_detach_after_cancelling_queue(self):
        calls = []

        class StopClient(FakeClient):
            def request(self, method, params):
                calls.append(method)
                return {"detach_state": "detach_pending" if method == "stop" else "attached"}

        with tempfile.TemporaryDirectory() as directory:
            descriptor = SessionDescriptor(Path(directory) / "session.json", "s", "127.0.0.1", 1,
                                           Path(directory) / "credential", PROTOCOL_VERSION, schema_digest())
            with patch("cph_ai_companion.cli.JsonRpcClient", StopClient):
                result = stop_session(descriptor)
        self.assertEqual(calls, ["cancel", "stop"])
        self.assertEqual(result, {"state": "stop_requested", "detach": {"detach_state": "detach_pending"}})

    def test_stop_signals_verified_process_handle_instead_of_reusable_pid(self):
        descriptor = SessionDescriptor(Path("/tmp/session.json"), "s", "127.0.0.1", 1,
                                       Path("/tmp/credential"), PROTOCOL_VERSION, schema_digest())
        record = {"pid": 424242, "process_start": "original-start"}
        with patch("cph_ai_companion.cli._runtime_record", return_value=record), \
             patch("cph_ai_companion.cli.os.pidfd_open", return_value=17) as opened, \
             patch("cph_ai_companion.cli.process_start", return_value="original-start"), \
             patch("cph_ai_companion.cli.signal.pidfd_send_signal") as signalled, \
             patch("cph_ai_companion.cli.os.kill") as unsafe_signal, \
             patch("cph_ai_companion.cli.os.close") as closed, \
             patch("cph_ai_companion.cli.JsonRpcClient") as client:
            result = stop_session(descriptor)
        opened.assert_called_once_with(424242, 0)
        signalled.assert_called_once_with(17, signal.SIGTERM)
        closed.assert_called_once_with(17)
        unsafe_signal.assert_not_called()
        client.assert_not_called()
        self.assertEqual(result, {"state": "stop_requested", "safe_detach_complete": False})

    def test_reused_runtime_pid_is_never_signalled_and_native_control_is_released(self):
        calls = []

        class StopClient(FakeClient):
            def request(self, method, params):
                calls.append(method)
                return {"detach_state": "detached"}

        descriptor = SessionDescriptor(Path("/tmp/session.json"), "s", "127.0.0.1", 1,
                                       Path("/tmp/credential"), PROTOCOL_VERSION, schema_digest())
        with patch("cph_ai_companion.cli._runtime_record", return_value={"pid": 424242, "process_start": "old"}), \
             patch("cph_ai_companion.cli.os.pidfd_open", return_value=17), \
             patch("cph_ai_companion.cli.process_start", return_value="replacement"), \
             patch("cph_ai_companion.cli.signal.pidfd_send_signal") as signalled, \
             patch("cph_ai_companion.cli.os.kill") as unsafe_signal, \
             patch("cph_ai_companion.cli.os.close") as closed, \
             patch("cph_ai_companion.cli.JsonRpcClient", StopClient):
            result = stop_session(descriptor)
        signalled.assert_not_called()
        unsafe_signal.assert_not_called()
        closed.assert_called_once_with(17)
        self.assertEqual(calls, ["cancel", "stop"])
        self.assertEqual(result["detach"]["detach_state"], "detached")


if __name__ == "__main__":
    unittest.main()
