import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile


SPEC = importlib.util.spec_from_file_location('windows_bundle', Path(__file__).resolve().parents[1] / 'tools/build_windows_bundle.py')
bundler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundler)


class WindowsBundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.python = self.root / 'python-input'
        (self.python / 'DLLs').mkdir(parents=True)
        (self.python / 'Lib/site-packages').mkdir(parents=True)
        (self.python / 'Lib/site-packages/unrelated.py').write_text('must not ship')
        image = bytearray(70)
        image[:2] = b'MZ'
        struct.pack_into('<I', image, 60, 64)
        image[64:] = b'PE\0\0\x64\x86'
        for name in ('python.exe', 'python312.dll'):
            (self.python / name).write_bytes(image)
        (self.python / 'Lib/stdlib.py').write_text('stdlib fixture')
        self.site = self.root / 'sdk'
        metadata = self.site / 'openai-3.22.1.dist-info'
        metadata.mkdir(parents=True)
        (metadata / 'METADATA').write_text('Name: openai\nVersion: 3.22.1\n')
        (self.site / 'openai').mkdir()
        (self.site / 'openai/__init__.py').write_text('SDK fixture')
        self.lock = self.root / 'requirements.lock'
        self.lock.write_text('openai==3.22.1 \\\n    --hash=sha256:fixture\n')
        self.game = self.root / 'game'
        self.wheel = self.root / 'companion.whl'
        self.write_wheel()

    def write_wheel(self, extra=None):
        prefix = 'cph_ai_companion/resources/'
        with zipfile.ZipFile(self.wheel, 'w') as archive:
            archive.writestr('cph_ai_companion-0.1.2.dev0.dist-info/METADATA',
                             'Name: cph-ai-companion\nVersion: 0.1.2.dev0\nRequires-Python: <3.13,>=3.12\n')
            archive.writestr(prefix + 'mod/main.lua', 'canonical main')
            archive.writestr(prefix + 'mod/mod.lua', 'canonical metadata')
            archive.writestr(prefix + 'templates/config.json', '{"schema_version":1}')
            archive.writestr(prefix + 'templates/background.md', 'background')
            archive.writestr(prefix + 'protocol/protocol.json', '{"protocol_version":"1.2"}')
            if extra:
                archive.writestr(*extra)

    def build(self):
        return bundler.bundle(self.python, self.site, self.wheel, self.game, self.lock)

    def test_bundle_ships_same_mod_and_records_exact_wheel_protocol_and_dependency_inputs(self):
        result = self.build()
        runtime = self.game / 'companion-runtime'
        site = runtime / 'python/Lib/site-packages'
        self.assertEqual((self.game / 'data/mods/cph_ai_companion/main.lua').read_text(), 'canonical main')
        self.assertEqual((site / 'cph_ai_companion/resources/mod/main.lua').read_text(), 'canonical main')
        self.assertFalse((site / 'unrelated.py').exists())
        self.assertEqual(result['wheel_sha256'], bundler.digest(self.wheel))
        self.assertEqual(result['requirements_sha256'], bundler.digest(self.lock))
        self.assertEqual(result['sdk_distributions'], {'openai': '3.22.1'})
        self.assertEqual(result['model_calls'], 0)
        self.assertEqual(result['acceptance'], 'UNVALIDATED_WINDOWS_BUNDLE')
        files = json.loads((runtime / 'files.json').read_text())
        for name, expected in files.items():
            self.assertEqual(bundler.digest(runtime / name), expected)
        self.assertEqual(bundler.digest(runtime / 'files.json'), result['files_sha256'])

    def test_existing_game_payload_is_preserved(self):
        self.build()
        sentinel = self.game / 'data/mods/cph_ai_companion/main.lua'
        sentinel.write_text('user edit')
        with self.assertRaisesRegex(bundler.BundleError, 'fresh_game_stage_required'):
            self.build()
        self.assertEqual(sentinel.read_text(), 'user edit')

    def test_multiple_wheel_metadata_records_are_rejected_before_staging(self):
        self.write_wheel(('extra.dist-info/METADATA',
                          'Name: cph-ai-companion\nVersion: 0.1.2.dev0\nRequires-Python: <3.13,>=3.12\n'))
        with self.assertRaisesRegex(bundler.BundleError, 'invalid_wheel_metadata'):
            self.build()
        self.assertFalse(self.game.exists())

    def test_wrong_interpreter_and_unlocked_sdk_are_rejected_before_staging(self):
        (self.python / 'python312.dll').write_bytes(b'not a Windows CPython image')
        with self.assertRaisesRegex(bundler.BundleError, 'windows_amd64_runtime_required'):
            self.build()
        self.assertFalse(self.game.exists())
        (self.python / 'python312.dll').write_bytes((self.python / 'python.exe').read_bytes())
        (self.site / 'openai-3.22.1.dist-info/METADATA').write_text('Name: openai\nVersion: 1.0\n')
        with self.assertRaisesRegex(bundler.BundleError, 'sdk_environment_not_locked'):
            self.build()

    def test_missing_active_dependency_is_rejected_but_other_platform_dependency_is_not_required(self):
        self.lock.write_text("openai==3.22.1\nhttpx2-jsfetch==1.0 ; sys_platform == 'emscripten'\n")
        self.assertEqual(self.build()['sdk_distributions'], {'openai': '3.22.1'})
        self.game = self.root / 'second-game'
        self.lock.write_text("openai==3.22.1\nidna==3.20 ; sys_platform != 'emscripten'\n")
        with self.assertRaisesRegex(bundler.BundleError, 'complete_locked_sdk_required'):
            self.build()
        self.assertFalse(self.game.exists())

    def test_reparse_is_rejected_before_resolving_input(self):
        from unittest.mock import patch
        class Reparse:
            st_mode = 0
            st_file_attributes = 0x400
        original = Path.lstat
        def lstat(path, *args, **kwargs):
            return Reparse() if path == self.python else original(path, *args, **kwargs)
        with patch.object(Path, 'lstat', lstat):
            with self.assertRaisesRegex(bundler.BundleError, 'runtime_reparse_not_supported'):
                self.build()
        self.assertFalse(self.game.exists())

    def test_unsafe_wheel_path_does_not_escape_or_publish_partial_payload(self):
        self.write_wheel(('../outside.txt', 'not written'))
        with self.assertRaisesRegex(bundler.BundleError, 'invalid_wheel_path'):
            self.build()
        self.assertFalse((self.root / 'outside.txt').exists())
        self.assertFalse((self.game / 'companion-runtime').exists())
        self.assertFalse((self.game / 'data/mods/cph_ai_companion').exists())


if __name__ == '__main__':
    unittest.main()
