"""Execute the actual Make cleanup targets in disposable Git checkouts."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
MAKE = shutil.which('make')


class SafeCleanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not MAKE or not shutil.which('msgfmt'):
            raise RuntimeError('safe clean tests require GNU make and msgfmt')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cph clean test ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'checkout'
        self.root.mkdir()
        for name in ('Makefile', 'tests/Makefile', 'lang/Makefile',
                     'tools/safe_clean.py'):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        for name in ('src/main.cpp', 'src/example.cpp',
                     'tests/example_test.cpp', 'data/json/example.json',
                     'data/shaders/example.frag'):
            self.write(name, 'tracked source')
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        subprocess.run(['git', '-C', str(self.root), 'add', '.'], check=True)
        self.env = os.environ.copy()
        # Prevent the caller's recursive make/build state affecting fixtures.
        for name in tuple(self.env):
            inherited_build_vars = {
                'MAKEFLAGS', 'MFLAGS', 'MAKELEVEL', 'ODIR', 'BUILD_PREFIX',
                'CATA_ENABLE_LUA_PLATFORM', 'TARGETSYSTEM', 'PCH', 'CLANG'}
            if name.startswith('CPH_CLEAN_') or name in inherited_build_vars:
                self.env.pop(name, None)

    def write(self, name, contents='sentinel'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        return path

    def make(self, *args, directory='.', success=True):
        command = [MAKE, '--no-print-directory', '-C',
                   str(self.root / directory), *args]
        result = subprocess.run(command, env=self.env, text=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn('clean refused:', result.stdout)
        return result.stdout

    def assert_kept(self, *paths):
        for path in paths:
            self.assertTrue((self.root / path).exists(), path)

    def assert_removed(self, *paths):
        for path in paths:
            self.assertFalse((self.root / path).exists(), path)

    def test_default_non_lua_removes_exact_outputs_and_is_repeatable(self):
        outputs = ('cataclysm', 'cataclysm.a', 'obj/example.o',
                   'obj/example.d', 'obj/example.inc', 'obj/main.o',
                   'obj/pch/main-pch.hpp.gch', 'obj/pch/main-pch.hpp.d',
                   'obj/builtin_mods_generated.h',
                   'tests/cata_test', 'tests/obj/example_test.o')
        kept = ('other-cataclysm', 'other-obj/example.o', 'obj/notes.txt',
                'obj/orphan.o', 'save/world/sentinel', 'config/options.json',
                'lang/mo/fr/LC_MESSAGES/cataclysm-dda.mo',
                'lang/mo_built.stamp', 'data/options.txt')
        for name in outputs + kept:
            self.write(name)
        self.make('clean', 'CATA_ENABLE_LUA_PLATFORM=0')
        self.assert_removed(*outputs)
        self.assert_kept(*kept)
        self.make('clean', 'CATA_ENABLE_LUA_PLATFORM=0')

    def test_default_lua_is_protected_before_any_deletion(self):
        self.write('cataclysm')
        self.write('obj-lua/example.o')
        self.write('tests/cata_test')
        self.make('clean', success=False)
        self.assert_kept('cataclysm', 'obj-lua/example.o', 'tests/cata_test')

    def test_custom_prefix_with_spaces_and_shell_characters(self):
        prefix = "output space 'quote';-"
        outputs = (prefix + 'cataclysm', prefix + 'cataclysm.a',
                   prefix + 'obj-lua/example.o',
                   'tests/' + prefix + 'cata_test',
                   'tests/' + prefix + 'obj-lua/example_test.o')
        for name in outputs:
            self.write(name)
        self.write('cataclysm')
        self.make('clean', 'BUILD_PREFIX=' + prefix)
        self.assert_removed(*outputs)
        self.assert_kept('cataclysm')

    def test_custom_object_directory_with_spaces(self):
        for name in ('outputs with spaces/example.o',
                     'tests/outputs with spaces/example_test.o',
                     'obj/example.o'):
            self.write(name)
        self.make('clean', 'ODIR=outputs with spaces',
                  'CATA_ENABLE_LUA_PLATFORM=0')
        self.assert_removed('outputs with spaces/example.o',
                            'tests/outputs with spaces/example_test.o')
        self.assert_kept('obj/example.o')

    def test_current_tiles_config_does_not_clean_console(self):
        outputs = ('trial-cataclysm-tiles', 'trial-obj-lua/tiles/example.o',
                   'tests/trial-obj-lua/tiles/example_test.o',
                   'data/shaders/example.frag.spv',
                   'data/shaders/build-spv.stamp')
        for name in outputs + ('trial-cataclysm', 'trial-obj-lua/example.o'):
            self.write(name)
        self.make('clean', 'BUILD_PREFIX=trial-', 'TILES=1', 'SDL3=1')
        self.assert_removed(*outputs)
        self.assert_kept('trial-cataclysm', 'trial-obj-lua/example.o')

    def test_tests_subdirectory_current_target_including_windows(self):
        for target_system, filename in (('LINUX', 'cata_test'),
                                        ('WINDOWS', 'cata_test.exe')):
            with self.subTest(target_system=target_system):
                self.write('tests/my-' + filename)
                self.write('tests/custom obj/example_test.o')
                self.write('tests/other-cata_test')
                self.make('clean', 'BUILD_PREFIX=my-', 'ODIR=custom obj',
                          'TARGETSYSTEM=' + target_system, directory='tests')
                self.assert_removed('tests/my-' + filename,
                                    'tests/custom obj/example_test.o')
                self.assert_kept('tests/other-cata_test')

    def test_distclean_preserves_user_data_and_translations(self):
        self.write('trial-bindist/data/example.json')
        kept = ('bindist/keep', 'save/world/sentinel',
                'config/options.json', 'data/keymap.txt',
                'lang/mo/fr/LC_MESSAGES/cataclysm-dda.mo')
        for name in kept:
            self.write(name)
        self.make('distclean', 'BUILD_PREFIX=trial-')
        self.assert_removed('trial-bindist')
        self.assert_kept(*kept)
        self.make('distclean', 'BUILD_PREFIX=trial-')

    def test_distribution_resources_are_distinct_from_user_files(self):
        resources = ('data/raw/keybindings.json',
                     'data/lua/templates/minimal/main.lua')
        for name in resources:
            self.write(name, 'tracked resource')
            self.write('bindist/' + name, 'packaged resource')
        subprocess.run(['git', '-C', str(self.root), 'add', *resources],
                       check=True)
        self.make('distclean')
        self.assert_removed('bindist')
        self.assert_kept(*resources)
        # An unrecognized user file in the resource-shaped directory still
        # rejects the complete plan before an earlier valid file is removed.
        self.write('bindist/first')
        self.write('bindist/data/lua/templates/personal.template')
        self.make('distclean', success=False)
        self.assert_kept('bindist/first',
                         'bindist/data/lua/templates/personal.template')

    def test_distclean_refuses_nested_user_data_without_partial_deletion(self):
        self.write('bindist/first')
        self.write('bindist/save/world/sentinel')
        self.make('distclean', success=False)
        self.assert_kept('bindist/first', 'bindist/save/world/sentinel')

    def test_invalid_output_paths_refuse_before_deleting_other_outputs(self):
        for directory in ('', '../outside', str(self.root.parent / 'outside'),
                          'save', 'config', 'obj-lua', 'tests/obj-lua'):
            with self.subTest(directory=directory):
                self.write('cataclysm')
                self.write('tests/cata_test')
                self.make('clean', 'CATA_ENABLE_LUA_PLATFORM=0',
                          'ODIR=' + directory, success=False)
                self.assert_kept('cataclysm', 'tests/cata_test')

    def test_tracked_output_refuses_before_deleting_other_outputs(self):
        self.write('obj/example.o')
        self.write('tests/cata_test')
        self.make('clean', 'CATA_ENABLE_LUA_PLATFORM=0',
                  'TARGET=src/main.cpp', success=False)
        self.assert_kept('obj/example.o', 'tests/cata_test', 'src/main.cpp')

    def test_tracked_nested_distribution_file_is_protected(self):
        self.write('bindist/first')
        self.write('bindist/tracked')
        subprocess.run(['git', '-C', str(self.root), 'add',
                        'bindist/tracked'], check=True)
        self.make('distclean', success=False)
        self.assert_kept('bindist/first', 'bindist/tracked')

    def test_symlink_outputs_and_ancestors_refuse_entire_plan(self):
        sentinel = self.write('outside/sentinel')
        for symlink in ('obj/example.o', 'tests/cata_test', 'obj'):
            with self.subTest(symlink=symlink):
                path = self.root / symlink
                if path.is_dir():
                    shutil.rmtree(path)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.symlink_to(sentinel if path.suffix else sentinel.parent)
                self.write('cataclysm')
                self.make('clean', 'CATA_ENABLE_LUA_PLATFORM=0', success=False)
                self.assert_kept('cataclysm', 'outside/sentinel')
                self.assertTrue(path.is_symlink())
                path.unlink()

    def test_tests_subdirectory_symlink_refuses_without_partial_deletion(self):
        self.write('tests/obj/example_test.o')
        target = self.write('outside/sentinel')
        (self.root / 'tests/cata_test').symlink_to(target)
        self.make('clean', directory='tests', success=False)
        self.assert_kept('tests/obj/example_test.o', 'outside/sentinel')

    def test_test_protection_is_validated_before_root_deletion(self):
        self.write('cataclysm')
        self.write('obj/example.o')
        target = self.write('outside/sentinel')
        (self.root / 'tests/obj').symlink_to(target.parent)
        self.make('clean', 'CATA_ENABLE_LUA_PLATFORM=0', success=False)
        self.assert_kept('cataclysm', 'obj/example.o', 'outside/sentinel')

    def test_plan_and_make_dry_run_create_no_output_directories(self):
        for directory in ('.', 'tests'):
            with self.subTest(directory=directory):
                before = set(self.root.rglob('*'))
                self.make('-n', 'clean', 'BUILD_PREFIX=inspect-',
                          'ODIR=inspect obj', directory=directory)
                self.make('clean-plan', 'BUILD_PREFIX=inspect-',
                          'ODIR=inspect obj', directory=directory)
                self.assertEqual(before, set(self.root.rglob('*')))

    def test_clean_plan_preserves_files_and_rejects_unsafe_plan(self):
        self.write('cataclysm')
        output = self.make('clean-plan', 'CATA_ENABLE_LUA_PLATFORM=0')
        self.assertIn('would remove cataclysm', output)
        self.assert_kept('cataclysm')
        self.make('clean-plan', success=False)

    def test_language_cleanup_with_custom_directories_containing_spaces(self):
        source = self.write('lang/my po/fr.po', 'source')
        output = self.write('lang/my mo/fr/LC_MESSAGES/cataclysm-dda.mo',
                            'compiled')
        subprocess.run([
            sys.executable, '../tools/safe_clean.py', '--scope', 'lang',
            '--record-source', str(source), '--record-output', str(output),
        ], cwd=self.root / 'lang', env=self.env, check=True)
        self.make('clean-plan', 'PO_DIR=my po', 'MO_DIR=my mo',
                  directory='lang')
        self.assertTrue(output.exists())
        self.make('clean-lang', 'PO_DIR=my po', 'MO_DIR=my mo')
        self.assertFalse(output.exists())
        self.assertTrue(source.exists())

    def test_distribution_symlink_refuses_entire_plan(self):
        self.write('bindist/first')
        target = self.write('outside/sentinel')
        (self.root / 'bindist/link').symlink_to(target.parent)
        self.make('distclean', success=False)
        self.assert_kept('bindist/first', 'outside/sentinel')

    def test_build_recipes_create_their_directories(self):
        # Substitute only the compiler; execute the real Make recipe and mkdir.
        compiler = self.write('fixture-compiler',
                              '#!/bin/sh\n'
                              'while [ "$#" -gt 0 ]; do\n'
                              '  if [ "$1" = -o ]; then\n'
                              '    shift; touch "$1"; exit $?\n'
                              '  fi\n'
                              '  shift\n'
                              'done\n')
        compiler.chmod(0o755)
        for directory, target in (('.', 'compile-obj/example.o'),
                                  ('tests', 'compile-obj/example_test.o')):
            with self.subTest(directory=directory):
                self.make(target, 'ODIR=compile-obj', 'PCH=0', 'ASTYLE=0',
                          'LINTJSON=0', 'LOCALIZE=0',
                          'CATA_ENABLE_LUA_PLATFORM=0',
                          'CXX=' + ('./' if directory == '.' else '../') +
                          'fixture-compiler', directory=directory)
                self.assertTrue((self.root / directory / target).is_file())

    def translation_source(self):
        self.write('lang/po/fr.po',
                   'msgid ""\nmsgstr ""\n'
                   '"Content-Type: text/plain; charset=UTF-8\\n"\n'
                   '\nmsgid "hello"\nmsgstr "bonjour"\n')

    def test_translation_build_without_git_retains_unreceipted_mo(self):
        self.translation_source()
        (self.root / '.git').rename(self.root / 'fixture-git-backup')
        output = self.make('all', 'LANGUAGES=fr', directory='lang')
        self.assertIn('translation receipt not generated:', output)
        self.assertIn('clean preserves outputs without a receipt', output)
        mo = self.root / 'lang/mo/fr/LC_MESSAGES/cataclysm-dda.mo'
        compiled = mo.read_bytes()
        self.assertIn(compiled[:4],
                      (b'\xde\x12\x04\x95', b'\x95\x04\x12\xde'))
        self.assertFalse(Path(str(mo) + '.cph-generated.json').exists())
        self.make('clean', directory='lang', success=False)
        self.assertEqual(mo.read_bytes(), compiled)

    def test_translation_build_outside_checkout_retains_unreceipted_mo(self):
        self.translation_source()
        with tempfile.TemporaryDirectory(prefix='cph-mo-') as external:
            output = self.make('all', 'LANGUAGES=fr', 'MO_DIR=' + external,
                               directory='lang')
            self.assertIn('translation receipt not generated:', output)
            self.assertIn('clean preserves outputs without a receipt', output)
            mo = Path(external) / 'fr/LC_MESSAGES/cataclysm-dda.mo'
            compiled = mo.read_bytes()
            self.assertIn(compiled[:4],
                          (b'\xde\x12\x04\x95', b'\x95\x04\x12\xde'))
            self.assertFalse(Path(str(mo) + '.cph-generated.json').exists())
            self.make('clean', 'MO_DIR=' + external, directory='lang',
                      success=False)
            self.assertEqual(mo.read_bytes(), compiled)

    def record_translation(self, language='fr'):
        self.write('lang/po/' + language + '.po', 'source')
        output = 'mo/' + language + '/LC_MESSAGES/cataclysm-dda.mo'
        self.write('lang/' + output, 'compiled locally')
        subprocess.run([
            sys.executable, '../tools/safe_clean.py', '--scope', 'lang',
            '--record-source', 'po/' + language + '.po',
            '--record-output', output,
        ], cwd=self.root / 'lang', env=self.env, check=True)
        return 'lang/' + output

    def test_clean_lang_only_removes_unchanged_locally_generated_mo(self):
        generated = self.record_translation()
        foreign = 'lang/mo/de/LC_MESSAGES/cataclysm-dda.mo'
        self.write(foreign, 'locked input')
        self.write('lang/po/de.po', 'a PO alone does not prove ownership')
        self.make('clean-lang')
        self.assert_removed(generated, generated + '.cph-generated.json')
        self.assert_kept(foreign, 'lang/po/fr.po', 'lang/po/de.po')
        self.make('clean-lang')

    def test_changed_source_or_mo_and_missing_po_are_retained(self):
        for changed in ('source', 'output', 'missing'):
            with self.subTest(changed=changed):
                output = self.record_translation()
                source = self.root / 'lang/po/fr.po'
                if changed == 'source':
                    source.write_text('edited source')
                elif changed == 'output':
                    (self.root / output).write_text('replacement external MO')
                else:
                    source.unlink()
                self.make('clean', directory='lang')
                self.assert_kept(output, output + '.cph-generated.json')

    def test_combined_clean_goals_validate_all_before_deletion(self):
        self.write('cataclysm')
        output = self.record_translation()
        path = self.root / output
        path.unlink()
        path.symlink_to(self.root / 'src/main.cpp')
        self.make('clean', 'clean-lang', 'CATA_ENABLE_LUA_PLATFORM=0',
                  success=False)
        self.assert_kept('cataclysm', 'src/main.cpp')
        self.assertTrue(path.is_symlink())

    def record_package(self, kind):
        return subprocess.run(
            [sys.executable, 'tools/safe_clean.py', '--scope', 'root',
             '--record-package', kind], cwd=self.root, env=self.env,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=True).stdout

    def test_macos_package_clean_preserves_inputs_and_known_links(self):
        kept = ('data/options.txt', 'data/keymap.txt',
                'lang/mo/fr/LC_MESSAGES/cataclysm-dda.mo')
        for name in kept:
            self.write(name)
        # First build starts with no package or receipt.
        self.make('appclean', 'dmgdistclean', 'NATIVE=osx')
        app = 'Cataclysm.app/Contents/Resources'
        resources = ('data/lua/templates/minimal/main.lua',
                     'data/raw/keybindings.json')
        for resource in resources:
            self.write(resource, 'tracked resource')
            self.write(app + '/' + resource, 'packaged resource')
        subprocess.run(['git', '-C', str(self.root), 'add', *resources],
                       check=True)
        framework = self.write(app + '/SDL3.framework/Versions/A/SDL3')
        (framework.parent.parent / 'Current').symlink_to('A')
        self.record_package('app')
        shutil.copytree(self.root / 'Cataclysm.app',
                        self.root / 'Cataclysm/Cataclysm.app', symlinks=True)
        (self.root / 'Cataclysm/Applications').symlink_to('/Applications')
        self.write('Cataclysm.dmg', 'disk image')
        self.record_package('dmgdist')
        self.make('dmgdistclean', 'NATIVE=osx')
        self.assert_removed('Cataclysm', 'Cataclysm.dmg',
                            'Cataclysm.cph-generated.json',
                            'Cataclysm.dmg.cph-generated.json')
        self.assert_kept('Cataclysm.app', *kept)
        self.make('appclean', 'NATIVE=osx')
        self.assert_removed('Cataclysm.app',
                            'Cataclysm.app.cph-generated.json')
        self.assert_kept(*kept)

    def test_macos_package_clean_refuses_unowned_or_changed_content(self):
        self.write('Cataclysm.app/Contents/Info.plist', 'original')
        self.make('appclean', 'NATIVE=osx', success=False)
        self.assert_kept('Cataclysm.app/Contents/Info.plist')
        self.record_package('app')
        self.write('Cataclysm.app/Contents/Info.plist', 'signed change')
        self.make('appclean', 'NATIVE=osx', success=False)
        self.assert_kept('Cataclysm.app/Contents/Info.plist')
        # The native dmg recipe refreshes the receipt after signing.
        self.record_package('app')
        self.make('appclean', 'NATIVE=osx')
        self.assert_removed('Cataclysm.app')

        self.write('Cataclysm/Cataclysm.app/Contents/Info.plist', 'copied')
        self.write('Cataclysm.dmg', 'disk image')
        self.record_package('dmgdist')
        self.write('Cataclysm/extra', 'foreign file')
        self.make('dmgdistclean', 'NATIVE=osx', success=False)
        self.assert_kept('Cataclysm/extra', 'Cataclysm.dmg')

    def test_macos_package_receipt_refuses_external_links(self):
        target = self.write('outside/sentinel')
        app = self.root / 'Cataclysm.app'
        app.mkdir()
        (app / 'escape').symlink_to(target)
        output = self.record_package('app')
        self.assertIn('package receipt not generated:', output)
        self.make('appclean', 'NATIVE=osx', success=False)
        self.assertTrue((app / 'escape').is_symlink())
        self.assert_kept('outside/sentinel')

    def test_package_receipts_cannot_adopt_user_data(self):
        for relative in ('test_user_dir_1/options.txt', 'templates/keep',
                         'options.json', 'obj-lua/sentinel'):
            with self.subTest(relative=relative):
                path = self.write(
                    'Cataclysm.app/Contents/Resources/' + relative)
                output = self.record_package('app')
                self.assertIn('package receipt not generated:', output)
                self.make('appclean', 'NATIVE=osx', success=False)
                self.assertTrue(path.exists())
                shutil.rmtree(self.root / 'Cataclysm.app')

    def test_clean_only_skips_dependency_include_and_clang_probe(self):
        self.write('obj/example.d', '$(error poisoned dependency included)\n')
        compiler = self.write('fixture-compiler',
                              '#!/bin/sh\n'
                              'for arg in "$@"; do\n'
                              '  if [ "$arg" = _clang_ver.o ]; then\n'
                              '    touch _clang_ver.o clang-probe-called\n'
                              '  fi\n'
                              'done\n')
        compiler.chmod(0o755)
        for goal in ('clean-plan', 'appclean', 'dmgdistclean'):
            with self.subTest(goal=goal):
                self.make(goal, 'NATIVE=osx', 'CATA_ENABLE_LUA_PLATFORM=0',
                          'NOOPT=1', 'PCH=1', 'CLANG=1', 'CCACHE=1',
                          'CXX=./fixture-compiler')
                self.assertFalse((self.root / '_clang_ver.o').exists())
                self.assertFalse((self.root / 'clang-probe-called').exists())


if __name__ == '__main__':
    unittest.main()
