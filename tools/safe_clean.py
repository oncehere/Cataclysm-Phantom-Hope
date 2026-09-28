#!/usr/bin/env python3
"""Clean only declared Make outputs, after validating the entire deletion plan.

Cleaning requires a Git checkout to identify tracked files. Never follows
symlinks or cleans obj-lua/user data; never scans an object directory.
Translation receipts are optional: an unsafe/unavailable receipt is skipped.
Use the Make clean-plan target to inspect the same checks without deleting.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys


PROTECTED = {
    '.git', '.agents', '.codex', 'obj-lua', 'save', 'saves', 'config',
    'memorial', 'graveyard', 'userdata', 'user_data', 'user-data',
    'userdir', 'user_dir', 'templates',
}
USER_FILES = {
    'options.txt', 'options.json', 'keymap.txt', 'keybindings.json',
    'auto_pickup.txt', 'auto_pickup.json', 'fontlist.txt',
}
RECEIPT_SUFFIX = '.cph-generated.json'


class UnsafePlan(ValueError):
    pass


def setting(name, default=''):
    return os.environ.get('CPH_CLEAN_' + name, default)


class Plan:
    def __init__(self, root):
        self.root = root.resolve()
        result = subprocess.run(
            ['git', '-C', str(self.root), 'ls-files', '-z'],
            check=True, capture_output=True,
        )
        self.tracked = {
            self.root / os.fsdecode(item)
            for item in result.stdout.split(b'\0') if item
        }
        self.tracked_dirs = {
            parent for file in self.tracked for parent in file.parents
            if self.root in parent.parents
        }
        self.files = {}
        self.directories = {}

    def path(self, value, base=None, allow_tracked=False, mapped_output=False):
        """Check lexical boundaries before any filesystem lookup."""
        if not value or '\n' in str(value) or '\r' in str(value):
            raise UnsafePlan('empty or multiline output path')
        candidate = Path(value)
        if '..' in candidate.parts:
            raise UnsafePlan(f'parent traversal in output: {value}')
        path = (candidate if candidate.is_absolute()
                else (base or self.root) / candidate)
        try:
            relative = path.relative_to(self.root)
        except ValueError:
            raise UnsafePlan(f'output outside checkout: {path}') from None
        if not relative.parts:
            raise UnsafePlan('cannot clean the checkout root')
        for part in relative.parts:
            always_protected = part in {'.git', '.agents', '.codex', 'obj-lua'}
            user_data = part in PROTECTED or part.startswith('test_user_dir_')
            if always_protected or (user_data and not mapped_output):
                raise UnsafePlan(f'protected path: {relative}')
        if relative.name in USER_FILES and not mapped_output:
            raise UnsafePlan(f'user configuration: {relative}')
        current = self.root
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise UnsafePlan(f'symlink in output path: {relative}')
        if not allow_tracked and path in self.tracked:
            raise UnsafePlan(f'tracked output: {relative}')
        return path

    def file(self, value, base=None, mapped_output=False):
        path = self.path(value, base, mapped_output=mapped_output)
        if path.exists() and not stat.S_ISREG(path.stat().st_mode):
            raise UnsafePlan(f'output is not a regular file: {path}')
        self.files[path] = mapped_output
        return path

    def tree(self, value, source=None):
        """Only a named distribution output may be removed as a whole tree."""
        # A distribution contains copies of tracked resources (for example
        # data/raw/keybindings.json and data/lua/templates). These are not the
        # user's root config/templates. Only exact source paths qualify.
        source_relative = (source.relative_to(self.root) if source else Path())
        mapped = (bool(source_relative.parts) and
                  source_relative.parts[0] in {'data', 'doc'} and
                  source in self.tracked_dirs)
        path = self.path(value, mapped_output=mapped)
        if not path.exists():
            return
        if not path.is_dir():
            raise UnsafePlan(f'distribution output is not a directory: {path}')
        for entry in path.iterdir():
            original = (source or self.root) / entry.name
            relative = original.relative_to(self.root)
            mapped_file = (relative.parts[0] in {'data', 'doc'} and
                           original in self.tracked)
            mapped_dir = (relative.parts[0] in {'data', 'doc'} and
                          original in self.tracked_dirs)
            checked = self.path(entry, mapped_output=mapped_file or mapped_dir)
            if checked.is_dir():
                self.tree(checked, original)
            else:
                self.file(checked, mapped_output=mapped_file)
        self.directories[path] = mapped

    def objects(self, directory, objects, base=None, pch=''):
        directory = self.path(directory, base)
        for obj in objects:
            if not obj.endswith('.o'):
                raise UnsafePlan(f'invalid declared object: {obj}')
            for suffix in ('.o', '.d', '.inc'):
                self.file(directory / (obj[:-2] + suffix))
        if pch:
            self.file(directory / pch)
            self.file(directory / (str(Path(pch).with_suffix('.d'))))
        return directory

    def execute(self, dry_run):
        existing = sorted(p for p in self.files if p.exists())
        # Recheck every planned path once more before the first unlink.
        for path in self.files:
            self.file(path, mapped_output=self.files[path])
        for path in self.directories:
            self.path(path, mapped_output=self.directories[path])
        for path in existing:
            print(('would remove ' if dry_run else 'remove ') +
                  str(path.relative_to(self.root)))
        if dry_run:
            return
        for path in existing:
            path.unlink()
        # Only distribution trees are removed. Empty object directories remain,
        # as do files outside the exact outputs of this configuration.
        for directory in sorted(self.directories, key=lambda p: len(p.parts),
                                reverse=True):
            directory.rmdir()


def test_outputs(plan):
    directory = setting('ODIR', 'obj')
    base = plan.root / 'tests'
    # Source names are looked up directly; no build/cache directory traversal.
    objects = [p.stem + '.o' for p in base.glob('*.cpp')]
    plan.objects(directory, objects, base, setting('TEST_PCH'))
    plan.file(setting('TEST_TARGET', setting('PREFIX') + 'cata_test'), base)


def root_outputs(plan):
    directory = plan.objects(setting('ODIR'), setting('OBJECTS').split())
    pch = setting('PCH')
    if pch:
        plan.file(pch)
        plan.file(str(Path(pch).with_suffix('.d')))
    for source in setting('ASTYLE').split():
        plan.file(directory / (source + '.astyle-check-stamp'),
                  mapped_output=True)
    for source in plan.tracked:
        relative = source.relative_to(plan.root)
        if (relative.parts[0] == 'data' and relative.suffix == '.json' and
                ' ' not in str(relative) and
                not str(relative).startswith(('data/lua/reference/',
                                              'data/reference/'))):
            plan.file(directory / relative.with_suffix('.jstyle-check-stamp'),
                      mapped_output=True)
    plan.file(directory / '.astyle-check-stamp')
    plan.file(directory / 'builtin_mods_generated.h')
    for value in (setting('TARGET'), setting('PREFIX') + 'cataclysm.a',
                  setting('PREFIX') + 'zstd.a', setting('LINK_STAMP'),
                  setting('CHKJSON'), setting('ZZIP'),
                  setting('ZZIP') + '.d', 'src/version.h', 'src/prefix.h'):
        plan.file(value)
    formats = set(setting('SHADER_FORMATS').split(','))
    if formats & {'dxil', 'msl'}:
        formats.add('spv')
    for source in setting('SHADERS').split():
        for extension in formats:
            if extension:
                plan.file(source + '.' + extension)
    if setting('SHADER_STAMP'):
        plan.file(setting('SHADER_STAMP'))
    test_outputs(plan)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def translation_outputs(plan):
    base = plan.root / 'lang'
    po_dir = plan.path(setting('PO_DIR', 'po'), base, allow_tracked=True)
    mo_dir = plan.path(setting('MO_DIR', 'mo'), base, allow_tracked=True)
    languages = setting('LANGUAGES').split()
    if not languages or languages == ['all']:
        languages = [p.stem for p in po_dir.glob('*.po')]
    for language in languages:
        source = plan.path(po_dir / (language + '.po'), allow_tracked=True)
        output = plan.path(mo_dir / language / 'LC_MESSAGES/cataclysm-dda.mo')
        receipt = plan.path(str(output) + RECEIPT_SUFFIX)
        if not all(path.is_file() for path in (source, output, receipt)):
            continue
        try:
            record = json.loads(receipt.read_text())
        except (ValueError, UnicodeError):
            continue
        expected = {
            'source': str(source.relative_to(plan.root)),
            'source_sha256': digest(source),
            'output_sha256': digest(output),
        }
        if record == expected:
            plan.file(output)
            plan.file(receipt)


def record_translation(plan, source, output):
    source = plan.path(source, Path.cwd(), allow_tracked=True)
    output = plan.path(output, Path.cwd())
    receipt = plan.path(str(output) + RECEIPT_SUFFIX)
    record = {
        'source': str(source.relative_to(plan.root)),
        'source_sha256': digest(source),
        'output_sha256': digest(output),
    }
    receipt.write_text(json.dumps(record, sort_keys=True) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=('root', 'tests', 'lang'),
                        required=True)
    parser.add_argument(
        '--goal', default='clean',
        choices=('clean', 'clean-tests', 'clean-lang', 'distclean'))
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--record-source')
    parser.add_argument('--record-output')
    args = parser.parse_args()
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            check=True, capture_output=True, text=True,
        )
        plan = Plan(Path(result.stdout.strip()))
        if args.record_source or args.record_output:
            if args.dry_run:
                raise UnsafePlan('cannot record translation during a dry run')
            if not args.record_source or not args.record_output:
                raise UnsafePlan(
                    'both translation source and output are required')
            record_translation(plan, args.record_source, args.record_output)
        else:
            if args.scope == 'tests':
                test_outputs(plan)
            elif args.scope == 'lang':
                translation_outputs(plan)
            else:
                goals = set(setting('GOALS').split()) | {args.goal}
                if goals & {'clean', 'clean-plan'}:
                    root_outputs(plan)
                elif 'clean-tests' in goals:
                    test_outputs(plan)
                if 'clean-lang' in goals:
                    translation_outputs(plan)
                if 'distclean' in goals:
                    plan.tree(setting('BINDIST'))
            plan.execute(args.dry_run)
    except (UnsafePlan, OSError, subprocess.CalledProcessError) as error:
        if (args.scope == 'lang' and args.record_source and
                args.record_output and not args.dry_run):
            # The MO was already compiled by msgfmt. A receipt enables safe
            # cleanup; its absence must not break an otherwise valid build.
            print(f'translation receipt not generated: {error}; '
                  'MO retained; clean preserves outputs without a receipt',
                  file=sys.stderr)
            return 0
        print(f'clean refused: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
