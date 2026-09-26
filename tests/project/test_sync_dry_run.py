"""Real local Git fixtures; these are NOT GitHub/platform acceptance tests."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[2] / 'tools/project'
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location(
    'sync_dry_run', TOOLS / 'sync_dry_run.py')
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


class MergeFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cph-sync-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'source'
        self.repo.mkdir()
        self.counter = 0
        self.git('init', '--template=')
        self.git('config', 'user.name', 'Declared Git fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('remote', 'add', 'upstream',
                 'https://github.com/CleverRaven/Cataclysm-DDA.git')
        self.git('remote', 'add', 'ccb', 'https://github.com/'
                 'CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb.git')
        self.b = self.commit('base.txt', 'base\n')
        self.u = self.commit('game.txt', 'one\n')
        self.lock = {
            'schema_version': 1,
            'cdda': {'repository': 'CleverRaven/Cataclysm-DDA',
                     'remote': 'upstream', 'commit': self.b,
                     'tree': self.git('rev-parse', self.b + '^{tree}')},
            'ccb': {'repository':
                    'CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb',
                    'remote': 'ccb', 'ref': 'refs/heads/master',
                    'commit': self.u,
                    'tree': self.git('rev-parse', self.u + '^{tree}')},
        }
        self.h = self.ledger([])
        self.git('branch', 'project', self.h)

    def git(self, *args):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith('GIT_')}
        env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        result = subprocess.run(
            ['git', '-c', 'core.hooksPath=' + os.devnull,
             '-c', 'commit.gpgSign=false', '-C', str(self.repo), *args],
            env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def commit(self, path, content):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        self.git('add', '--', path)
        self.git('commit', '-m', 'fixture ' + path)
        return self.git('rev-parse', 'HEAD')

    def ledger(self, entries):
        return self.commit(sync.LEDGER, json.dumps({
            'schema_version': 1, 'baseline': self.u, 'entries': entries,
        }))

    def upstream(self, path='new.txt', content='new\n'):
        self.git('checkout', '--detach', self.u)
        newer = self.commit(path, content)
        self.git('update-ref', sync.TRACKING, newer)
        self.git('checkout', '--detach', self.h)
        return newer

    def probe(self, upstream=None, previous=None, cls=sync.Rehearsal):
        self.counter += 1
        return cls(self.repo, self.root / ('run-' + str(self.counter)),
                   self.h, upstream or self.u, previous or self.u, self.lock)

    def test_no_change_is_not_restoration_or_auto_merge(self):
        result = self.probe().run()
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['result'], 'no_new_upstream_commits')
        self.assertFalse(result['restoration_proven'])
        self.assertFalse(result['auto_merge_enabled'])
        self.assertNotIn('candidate_commit', result)

    def test_real_merge_retains_both_parents_and_source_unchanged(self):
        newer = self.upstream()
        refs = self.git('show-ref')
        result = self.probe(newer).run()
        self.assertEqual(result['status'], 'PASS', result['reason'])
        self.assertEqual(result['merge_parents'], [self.h, newer])
        self.assertEqual(self.git('show-ref'), refs)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.h)
        self.assertEqual(self.git('status', '--porcelain'), '')
        candidate = Path(result['candidate_directory'])
        self.assertEqual((candidate / 'new.txt').read_text(), 'new\n')
        self.assertTrue((candidate / sync.LEDGER).is_file())

    def test_text_conflict_preserves_real_index_and_source(self):
        self.h = self.commit('game.txt', 'project choice\n')
        newer = self.upstream('game.txt', 'upstream choice\n')
        result = self.probe(newer).run()
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['conflicts'], ['game.txt'])
        candidate = Path(result['candidate_directory'])
        self.assertTrue((candidate / '.git/MERGE_HEAD').is_file())
        self.assertIn('<<<<<<<', (candidate / 'game.txt').read_text())
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.h)

    def test_rewritten_upstream_rejected(self):
        self.git('checkout', '--detach', self.b)
        rewritten = self.commit('other.txt', 'rewritten\n')
        self.git('update-ref', sync.TRACKING, rewritten)
        self.git('checkout', '--detach', self.h)
        result = self.probe(rewritten).run()
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('rewrite', result['reason'])

    def test_protected_change_blocked_before_checkout(self):
        newer = self.upstream('.github/workflows/unsafe.yml', 'on: push\n')
        result = self.probe(newer).run()
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['protected_changes'],
                         ['.github/workflows/unsafe.yml'])
        self.assertNotIn('candidate_directory', result)

    def test_declared_build_and_identity_surfaces_block_before_checkout(self):
        for path in (
            'src/version.cpp', 'cmake_uninstall.cmake.in',
            'CMakeUserPresets.json', 'cmake/review-fixture.cmake',
            'msvc-full-features/vcpkg.json',
        ):
            with self.subTest(path=path):
                newer = self.upstream(path, 'changed protected input\n')
                result = self.probe(newer).run()
                self.assertEqual(result['status'], 'BLOCKED')
                self.assertEqual(result['protected_changes'], [path])
                self.assertNotIn('candidate_directory', result)

    def test_existing_sync_protections_are_preserved(self):
        for path in (
            '.gitattributes', 'build-data/windows/review-fixture.rc',
            'src/AGENTS.md', 'data/mods/example/AGENTS.override.md',
        ):
            with self.subTest(path=path):
                newer = self.upstream(path, 'changed protected input\n')
                result = self.probe(newer).run()
                self.assertEqual(result['status'], 'BLOCKED')
                self.assertEqual(result['protected_changes'], [path])
                self.assertNotIn('candidate_directory', result)

    def controller_policy(self, mutate=None):
        trusted = self.root / 'controller'
        trusted.mkdir()
        policy_path = trusted / 'check-policy.json'
        policy = json.loads(sync.PROTECTION_POLICY.read_text())
        surfaces = json.loads((sync.PROTECTION_POLICY.parent /
                               'protected-surfaces.json').read_text())
        if mutate:
            mutate(surfaces)
        raw = (json.dumps(surfaces, indent=2) + '\n').encode()
        (trusted / 'protected-surfaces.json').write_bytes(raw)
        policy['protected_surfaces']['sha256'] = (
            hashlib.sha256(raw).hexdigest())
        policy_path.write_text(json.dumps(policy))
        return policy_path

    def test_controller_policy_extension_is_enforced(self):
        path = 'custom-control/identity.json'
        policy_path = self.controller_policy(
            lambda surfaces: surfaces['paths'].append(path))
        newer = self.upstream(path, 'protected by the reviewed controller\n')
        with patch.object(sync, 'PROTECTION_POLICY', policy_path):
            result = self.probe(newer).run()
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['protected_changes'], [path])
        self.assertEqual(result['protected_surfaces_sha256'], json.loads(
            policy_path.read_text())['protected_surfaces']['sha256'])
        self.assertNotIn('candidate_directory', result)

    def test_source_policy_cannot_replace_controller_policy(self):
        self.h = self.commit('project/protected-surfaces.json', json.dumps({
            'schema_version': 1, 'paths': [], 'prefixes': [], 'basenames': [],
        }))
        newer = self.upstream('src/version.cpp', 'changed identity\n')
        result = self.probe(newer).run()
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['protected_changes'], ['src/version.cpp'])
        self.assertNotIn('candidate_directory', result)

    def test_unverified_or_missing_controller_policy_fails_closed(self):
        newer = self.upstream()
        policy_path = self.controller_policy()
        surfaces = policy_path.parent / 'protected-surfaces.json'
        surfaces.write_text('{}')
        with patch.object(sync, 'PROTECTION_POLICY', policy_path):
            for missing in (False, True):
                with self.subTest(missing=missing):
                    if missing:
                        surfaces.unlink()
                    result = self.probe(newer).run()
                    self.assertEqual(result['status'], 'FAIL')
                    self.assertNotIn('candidate_directory', result)

    def test_malformed_pinned_protection_policy_fails_closed(self):
        newer = self.upstream()
        policy_path = self.controller_policy(
            lambda surfaces: surfaces.pop('paths'))
        with patch.object(sync, 'PROTECTION_POLICY', policy_path):
            result = self.probe(newer).run()
        self.assertEqual(result['status'], 'FAIL')
        self.assertNotIn('candidate_directory', result)

    def test_protected_prefix_lookalike_can_still_merge(self):
        newer = self.upstream('msvc-full-features-other/content.txt')
        result = self.probe(newer).run()
        self.assertEqual(result['status'], 'PASS', result['reason'])
        self.assertEqual(result['protected_changes'], [])
        self.assertIn('candidate_commit', result)

    def test_dirty_untracked_and_tracked_rejected(self):
        for path in ('game.txt', 'personal.txt'):
            with self.subTest(path=path):
                target = self.repo / path
                previous = target.read_bytes() if target.exists() else None
                target.write_text('uncommitted user input\n')
                result = self.probe().run()
                self.assertEqual(result['status'], 'FAIL')
                self.assertIn('dirty', result['reason'])
                if previous is None:
                    target.unlink()
                else:
                    target.write_bytes(previous)

    def test_hidden_worktree_flags_rejected_without_source_changes(self):
        for flag in ('assume-unchanged', 'skip-worktree'):
            with self.subTest(flag=flag):
                self.git('update-index', '--' + flag, 'game.txt')
                target = self.repo / 'game.txt'
                target.write_text('hidden user edit\n')
                self.assertEqual(self.git('status', '--porcelain'), '')
                before = self.git('ls-files', '-v', '--', 'game.txt')
                result = self.probe().run()
                self.assertEqual(result['status'], 'FAIL')
                self.assertIn('assume-unchanged', result['reason'])
                self.assertNotIn('candidate_directory', result)
                self.assertEqual(target.read_text(), 'hidden user edit\n')
                self.assertEqual(self.git('ls-files', '-v', '--', 'game.txt'),
                                 before)
                self.git('update-index', '--no-' + flag, 'game.txt')
                target.write_text('one\n')

    def test_hidden_flags_added_during_merge_invalidate_result(self):
        newer = self.upstream()
        fixture = self
        for flag in ('assume-unchanged', 'skip-worktree'):
            with self.subTest(flag=flag):
                class HiddenEdit(sync.Rehearsal):
                    def merge(self):
                        super().merge()
                        fixture.git('update-index', '--' + flag, 'game.txt')
                        (fixture.repo / 'game.txt').write_text('hidden\n')

                result = self.probe(newer, cls=HiddenEdit).run()
                self.assertEqual(result['status'], 'FAIL')
                self.assertIn('assume-unchanged', result['reason'])
                self.assertIn('candidate_commit', result)
                self.assertEqual(self.git('status', '--porcelain'), '')
                self.assertEqual((self.repo / 'game.txt').read_text(),
                                 'hidden\n')
                self.git('update-index', '--no-' + flag, 'game.txt')
                (self.repo / 'game.txt').write_text('one\n')

    def test_source_change_rejected_without_credential_log(self):
        self.git('remote', 'set-url', 'ccb',
                 'https://secret:credential@github.com/other/repo.git')
        result = self.probe().run()
        self.assertEqual(result['status'], 'FAIL')
        self.assertNotIn('credential', json.dumps(result))

    def test_missing_object_rejected(self):
        result = self.probe('f' * 40).run()
        self.assertEqual(result['status'], 'FAIL')

    def test_shallow_replace_and_graft_rejected(self):
        gitdir = self.repo / '.git'
        (gitdir / 'shallow').write_text(self.b + '\n')
        self.assertIn('shallow', self.probe().run()['reason'])
        (gitdir / 'shallow').unlink()
        self.git('replace', self.u, self.b)
        self.assertIn('replace', self.probe().run()['reason'])
        self.git('replace', '-d', self.u)
        (gitdir / 'info').mkdir(exist_ok=True)
        (gitdir / 'info/grafts').write_text(self.u + '\n')
        self.assertIn('grafts', self.probe().run()['reason'])

    def test_dangling_graft_symlink_rejected(self):
        graft = self.repo / '.git/info/grafts'
        graft.parent.mkdir(exist_ok=True)
        graft.symlink_to('absent-graft-target')
        result = self.probe().run()
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('grafts', result['reason'])
        self.assertTrue(graft.is_symlink())
        self.assertFalse(graft.exists())

    def test_graft_symlink_added_during_merge_invalidate_result(self):
        newer = self.upstream()
        fixture = self

        class NewGraft(sync.Rehearsal):
            def merge(self):
                super().merge()
                graft = fixture.repo / '.git/info/grafts'
                graft.parent.mkdir(exist_ok=True)
                graft.symlink_to('absent-graft-target')

        result = self.probe(newer, cls=NewGraft).run()
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('grafts', result['reason'])
        self.assertIn('candidate_commit', result)

    def test_git_environment_override_rejected(self):
        with patch.dict(os.environ, {'GIT_CONFIG_COUNT': '0'}):
            result = self.probe().run()
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('GIT_CONFIG_COUNT', result['reason'])

    def test_base_moves_during_merge_requires_rebuild(self):
        newer = self.upstream()
        fixture = self

        class MovingBase(sync.Rehearsal):
            def merge(self):
                super().merge()
                fixture.commit('later.txt', 'base moved\n')

        result = self.probe(newer, cls=MovingBase).run()
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('base changed', result['reason'])

    def test_upstream_moves_during_merge_requires_rebuild(self):
        newer = self.upstream()
        fixture = self

        class MovingUpstream(sync.Rehearsal):
            def merge(self):
                super().merge()
                fixture.git('update-ref', sync.TRACKING, fixture.u)

        result = self.probe(newer, cls=MovingUpstream).run()
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('tracking head changed', result['reason'])

    def test_revert_merge_same_upstream_is_blocked_not_restored(self):
        newer = self.upstream()
        self.git('merge', '--no-ff', '-m', 'fixture merge', newer)
        merged = self.git('rev-parse', 'HEAD')
        self.git('revert', '-m', '1', '--no-edit', merged)
        reverted = self.git('rev-parse', 'HEAD')
        self.h = reverted
        result = self.probe(newer).run()
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['unrecorded_reverts'], [reverted])
        self.assertFalse((self.repo / 'new.txt').exists())
        self.h = self.ledger([{
            'kind': 'revert', 'upstream_sha': newer,
            'project_commit': reverted, 'decision': 'pending',
            'reason': 'Explicit local fixture rollback awaiting decision',
        }])
        result = self.probe(newer).run()
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertFalse(result['restoration_proven'])

    def test_pending_design_decision_blocks(self):
        self.h = self.ledger([{
            'kind': 'adaptation', 'upstream_sha': self.u,
            'project_commit': self.h, 'decision': 'pending',
            'reason': 'Fixture design choice has no authorization',
        }])
        self.assertEqual(self.probe().run()['status'], 'BLOCKED')

    def test_hooks_and_filters_never_execute(self):
        marker = self.root / 'EXECUTED'
        hook = self.repo / '.git/hooks/post-checkout'
        hook.parent.mkdir(exist_ok=True)
        hook.write_text('#!/bin/sh\ntouch ' + str(marker) + '\n')
        hook.chmod(0o755)
        self.git('config', 'filter.fixture.smudge', 'touch ' + str(marker))
        self.h = self.commit('.gitattributes', '*.txt filter=fixture\n')
        newer = self.upstream()
        self.assertEqual(self.probe(newer).run()['status'], 'PASS')
        self.assertFalse(marker.exists())

    def test_missing_ledger_never_defaults_to_empty(self):
        self.git('rm', sync.LEDGER)
        self.git('commit', '-m', 'fixture missing ledger')
        self.h = self.git('rev-parse', 'HEAD')
        self.assertEqual(self.probe().run()['status'], 'FAIL')

    def test_existing_workdir_and_source_subdir_rejected(self):
        probe = self.probe()
        probe.work.mkdir()
        with self.assertRaises(sync.Stop):
            probe.run()
        probe = self.probe()
        probe.work = self.repo / 'unsafe-output'
        with self.assertRaises(sync.Stop):
            probe.run()
        self.assertFalse(probe.work.exists())

    def test_wl_reports_cannot_enable_merge(self):
        # No report ingestion/remote writer exists in this local rehearsal.
        for verdict in ('FAIL', 'PASS', 'skipped', 'neutral'):
            self.h = self.commit('untrusted-windows-linux.json', verdict)
            result = self.probe().run()
            self.assertFalse(result['auto_merge_enabled'])
            self.assertEqual(result['windows_linux_gate'], 'NOT_RUN')

    def test_cli_missing_args_and_non_spec_lock_rejected(self):
        command = [sys.executable, str(TOOLS / 'sync_dry_run.py')]
        missing = subprocess.run(command, capture_output=True)
        self.assertEqual(missing.returncode, 2)
        self.commit('project/upstreams.lock.json', json.dumps(self.lock))
        wrong = subprocess.run(command + [
            '--repo', str(self.repo), '--work-dir', str(self.root / 'cli'),
            '--base', self.h, '--upstream', self.u, '--previous', self.u,
        ], capture_output=True)
        self.assertEqual(wrong.returncode, 1)
        self.assertIn(b'B/U identities are fixed', wrong.stderr)


if __name__ == '__main__':
    unittest.main()
