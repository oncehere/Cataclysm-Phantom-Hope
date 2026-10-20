"""Exercise the same file/lock interface used by profiles and budget ledgers."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from cph_ai_companion import platform_io as local


class PlatformIOTests(unittest.TestCase):
    def test_private_file_and_atomic_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = local.private_directory(Path(temporary) / "私有 profile", create=True)
            target = root / "ledger"
            fd = local.open_file(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            try:
                self.assertTrue(local.private_file(fd))
                os.write(fd, b"before")
                os.fsync(fd)
            finally:
                os.close(fd)
            replacement = root / "next"
            fd = local.open_file(replacement, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            with os.fdopen(fd, "wb") as output:
                output.write(b"after")
                output.flush()
                os.fsync(output.fileno())
            local.replace_file(replacement, target)
            self.assertEqual(target.read_bytes(), b"after")
            self.assertFalse(replacement.exists())
            with self.assertRaises(FileExistsError):
                local.open_file(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL)

    def test_writer_lock_rejects_second_process_and_releases(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = local.private_directory(temporary, create=True)
            path = root / "writer.lock"
            fd = local.open_file(path, os.O_CREAT | os.O_RDWR)
            local.lock_file(fd, blocking=False)
            script = (
                "from cph_ai_companion import platform_io as p; import os,sys; "
                "f=p.open_file(sys.argv[1],os.O_RDWR); p.lock_file(f,blocking=False); os.close(f)"
            )
            try:
                result = subprocess.run([sys.executable, "-c", script, str(path)],
                                        capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
            finally:
                os.close(fd)
            result = subprocess.run([sys.executable, "-c", script, str(path)],
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    def test_process_identity_is_stable_and_missing_pid_is_rejected(self):
        first = local.process_start(os.getpid())
        self.assertTrue(first)
        self.assertEqual(first, local.process_start(os.getpid()))
        self.assertIsNone(local.process_start(0x7fffffff))

    @unittest.skipUnless(local.WINDOWS, "Windows Win32 path aliases")
    def test_aliases_and_hardlinks_cannot_access_private_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = local.private_directory(temporary, create=True)
            target = root / "state.json"
            local.atomic_write(target, b"preserve")
            alias = root / "hardlink.json"
            os.link(target, alias)
            with self.assertRaisesRegex(OSError, "use_atomic_write"):
                local.open_file(alias, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
            self.assertEqual(target.read_bytes(), b"preserve")
            with self.assertRaisesRegex(OSError, "unsafe_file"):
                local.open_file(alias, os.O_RDONLY)
            alias.unlink()
            for name in ("state.json:stream", "state.json.", "state.json ", "CON.json", "NUL", "COM1"):
                with self.subTest(name=name), self.assertRaisesRegex(OSError, "unsafe_path"):
                    local.open_file(root / name, os.O_CREAT | os.O_WRONLY)
            self.assertEqual(target.read_bytes(), b"preserve")

    @unittest.skipUnless(local.WINDOWS, "Windows named stop event")
    def test_stop_event_is_private_and_never_signals_a_reused_pid(self):
        nonce = os.urandom(16).hex()
        event = local.StopEvent(nonce)
        try:
            identity = local.process_start(os.getpid())
            self.assertFalse(local.request_stop_event(os.getpid(), "older-creation", nonce))
            self.assertFalse(event.is_set())
            self.assertTrue(local.request_stop_event(os.getpid(), identity, nonce))
            self.assertTrue(event.is_set())
            with self.assertRaises(OSError):
                local.StopEvent(nonce)
        finally:
            event.close()

    @unittest.skipUnless(local.WINDOWS, "Windows junctions")
    def test_junction_is_rejected_before_open_or_permission_change(self):
        import _winapi
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "destination"
            destination.mkdir()
            (destination / "keep").write_bytes(b"preserve")
            alias = root / "alias"
            _winapi.CreateJunction(str(destination), str(alias))
            try:
                with self.assertRaisesRegex(OSError, "unsafe_link"):
                    local.private_directory(alias, create=True)
                with self.assertRaisesRegex(OSError, "unsafe_link"):
                    local.open_file(alias / "keep", os.O_RDONLY)
                self.assertEqual((destination / "keep").read_bytes(), b"preserve")
            finally:
                alias.rmdir()


if __name__ == "__main__":
    unittest.main()
