#!/usr/bin/env python3
"""Stage the built companion and a supplied CPython 3.12 Windows runtime.

No downloads, dependency resolution, model calls, or changes to a user's game.
Inputs are an SDK-only environment installed from requirements.lock, a complete
Windows CPython installation, and the exact wheel being delivered.
"""
from __future__ import annotations

import argparse
from email.parser import BytesParser
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import tempfile
import zipfile

_wheel_spec = importlib.util.spec_from_file_location("cph_companion_wheel_payload", Path(__file__).with_name("wheel_payload.py"))
_wheel = importlib.util.module_from_spec(_wheel_spec)
_wheel_spec.loader.exec_module(_wheel)


class BundleError(ValueError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _windows_amd64(path: Path) -> None:
    with path.open('rb') as stream:
        head = stream.read(64)
        if len(head) != 64 or head[:2] != b'MZ':
            raise BundleError('windows_amd64_runtime_required')
        stream.seek(struct.unpack_from('<I', head, 60)[0])
        header = stream.read(6)
        if header != b'PE\0\0\x64\x86':
            raise BundleError('windows_amd64_runtime_required')


def _locked_distributions(site: Path, requirements: Path) -> dict[str, str]:
    normalize = lambda name: re.sub(r'[-_.]+', '-', name).lower()
    locked = {}
    for line in requirements.read_text().splitlines():
        match = re.match(r'^([A-Za-z0-9_.-]+)==([^\s;\\]+)(?:\s*;\s*(.*?))?\s*\\?$', line)
        if not match:
            continue
        name, version, marker = match.groups()
        if marker:
            # The checked lock currently uses only these platform markers.
            # Fail closed if its format grows rather than guess at PEP 508.
            condition = re.fullmatch(r"sys_platform\s*(==|!=)\s*['\"]([^'\"]+)['\"]", marker.strip())
            if not condition:
                raise BundleError('unsupported_lock_marker')
            operator, platform = condition.groups()
            active = (platform == 'win32') if operator == '==' else (platform != 'win32')
            if not active:
                continue
        locked[normalize(name)] = version
    installed = {}
    for directory in site.glob('*.dist-info'):
        metadata = BytesParser().parsebytes((directory / 'METADATA').read_bytes())
        name, version = normalize(metadata['Name'] or ''), metadata['Version']
        if not name or name in installed or locked.get(name) != version:
            raise BundleError('sdk_environment_not_locked')
        installed[name] = version
    if installed.get('openai') != '3.22.1':
        raise BundleError('matching_sdk_required')
    if installed != locked:
        raise BundleError('complete_locked_sdk_required')
    return installed


def _reject_reparse(path: Path) -> None:
    for candidate in (path.absolute(), *path.absolute().parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise BundleError('runtime_reparse_not_supported')


def _copy_tree(source: Path, target: Path, *, skip_site_packages: bool = False) -> None:
    _reject_reparse(source)
    for path in source.rglob('*'):
        _reject_reparse(path)
    ignored = ['__pycache__', '*.pyc', '*.pyo', '_virtualenv*']
    if skip_site_packages:
        ignored.append('site-packages')
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(*ignored), dirs_exist_ok=True)


def bundle(python_root: Path, site_packages: Path, wheel: Path, game_root: Path,
           requirements: Path) -> dict:
    for path in (python_root, site_packages, wheel, game_root, requirements):
        _reject_reparse(path)
    python_root, site_packages, wheel, game_root = (
        path.resolve() for path in (python_root, site_packages, wheel, game_root))
    _windows_amd64(python_root / 'python.exe')
    _windows_amd64(python_root / 'python312.dll')
    distributions = _locked_distributions(site_packages, requirements)
    try:
        payloads, protocol_digest = _wheel.mod_payloads(wheel)
    except _wheel.ReleaseError as error:
        raise BundleError(str(error)) from None
    target = game_root / 'companion-runtime'
    mod_target = game_root / 'data/mods/cph_ai_companion'
    if target.exists() or mod_target.exists():
        raise BundleError('fresh_game_stage_required')
    game_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.companion-stage-', dir=game_root) as temporary:
        staged = Path(temporary)
        runtime = staged / 'companion-runtime'
        python = runtime / 'python'
        python.mkdir(parents=True)
        for name in ('python.exe', 'pythonw.exe', 'python3.dll', 'python312.dll',
                     'vcruntime140.dll', 'vcruntime140_1.dll', 'LICENSE.txt'):
            path = python_root / name
            if path.is_file():
                shutil.copy2(path, python / name)
        _copy_tree(python_root / 'DLLs', python / 'DLLs')
        _copy_tree(python_root / 'Lib', python / 'Lib', skip_site_packages=True)
        # A base interpreter is not the dependency authority. Replace its site
        # packages with the supplied locked SDK environment before adding wheel.
        bundled_site = python / 'Lib/site-packages'
        _copy_tree(site_packages, bundled_site)
        mod = staged / 'mod'
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            for name in names:
                relative = PurePosixPath(name)
                if (relative.is_absolute() or '..' in relative.parts or '\\' in name
                        or '\0' in name or ':' in name or relative.as_posix() != name.rstrip('/')):
                    raise BundleError('invalid_wheel_path')
                if name.endswith('/'):
                    continue
                if '.data/' in name:
                    raise BundleError('unsupported_wheel_layout')
                destination = bundled_site / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(name))
        for name, data in payloads.items():
            destination = mod / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        resources = bundled_site / 'cph_ai_companion/resources'
        shutil.copy2(resources / 'templates/config.json', runtime / 'config.default.json')
        shutil.copy2(resources / 'templates/background.md', runtime / 'background.default.md')
        files = {path.relative_to(runtime).as_posix(): digest(path)
                 for path in sorted(runtime.rglob('*')) if path.is_file()}
        file_data = (json.dumps(files, sort_keys=True, indent=2) + '\n').encode()
        (runtime / 'files.json').write_bytes(file_data)
        record = {'schema_version': 1, 'package_version': _wheel.VERSION,
                  'platform': 'windows-x86_64', 'python_abi': 'cp312-win_amd64',
                  'protocol_version': _wheel.PROTOCOL_VERSION, 'protocol_digest': protocol_digest,
                  'wheel_sha256': digest(wheel), 'requirements_sha256': digest(requirements),
                  'sdk_distributions': distributions, 'payload_files': len(files),
                  'files_sha256': hashlib.sha256(file_data).hexdigest(),
                  'mod_files': {path.relative_to(mod).as_posix(): digest(path)
                                for path in sorted(mod.rglob('*')) if path.is_file()},
                  'acceptance': 'UNVALIDATED_WINDOWS_BUNDLE', 'model_calls': 0}
        (runtime / 'manifest.json').write_text(json.dumps(record, sort_keys=True, indent=2) + '\n')
        mod_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(mod), mod_target)
        shutil.move(str(runtime), target)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('python-root', 'site-packages', 'wheel', 'game-root'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--requirements', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'requirements.lock')
    args = parser.parse_args()
    try:
        result = bundle(args.python_root, args.site_packages, args.wheel, args.game_root, args.requirements)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        parser.exit(1, 'Windows companion bundle assembly failed\n')
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
