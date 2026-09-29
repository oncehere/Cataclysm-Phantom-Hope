#!/usr/bin/env python3
"""Local-only, pinned CCB merge rehearsal. Never fetch, push, or auto-merge."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

from preflight import (
    PATHS, github_repository, read_lock, rejected_git_environment,
)
from check_merge_evidence import (
    decode, protected_changes, read_verified, regular, relative,
)

BASE = '221c786e7d61b3c9254f7cb1625bc69494b8181c'
UPSTREAM = 'bcb85682f3d28ab0f0123b05e45651bb9888b61b'
BASE_TREE = 'c7ad91e89ca75043106a74eb9c893130f378bd16'
UPSTREAM_TREE = '204b14a135ae307ad2180a348a6d6553374a07af'
LEDGER = 'project/design-differences.json'
TRACKING = 'refs/remotes/ccb/master'
PROTECTION_POLICY = (Path(__file__).resolve().parents[2] /
                     'project/check-policy.json')


class Stop(Exception):
    def __init__(self, status, reason):
        self.status = status
        super().__init__(reason)


def require(condition, reason, status='FAIL'):
    if not condition:
        raise Stop(status, reason)


def sha(value):
    require(isinstance(value, str) and
            re.fullmatch(r'[0-9a-f]{40}', value), 'full SHA-1 required')
    return value


def protection_policy():
    # Read the reviewed controller's policy, never a candidate's working copy.
    policy_path = regular(PROTECTION_POLICY)
    policy = decode(policy_path.read_bytes())
    binding = policy.get('protected_surfaces')
    require(isinstance(binding, dict) and
            set(binding) == {'path', 'sha256'}, 'invalid protection policy')
    surfaces = decode(read_verified(
        policy_path.parent / relative(binding['path']), binding['sha256']))
    return surfaces, binding['sha256']


class Rehearsal:
    def __init__(self, repo, work, base, upstream, previous, lock):
        self.repo = Path(repo).resolve()
        self.work = Path(work).absolute()
        self.base = sha(base)
        self.upstream = sha(upstream)
        self.previous = sha(previous)
        self.lock = lock
        self.report = {
            'schema_version': 1, 'scope': 'local_git_rehearsal',
            'platform': platform.platform(), 'base': base,
            'upstream': upstream, 'previous_integrated': previous,
            'commands': [], 'auto_merge_enabled': False,
            'remote_provenance': 'NOT_RUN',
            'windows_linux_gate': 'NOT_RUN',
            'semantic_acceptance': 'NOT_RUN',
            'restoration_proven': False,
            'task_key': 'ccb-' + upstream,
        }
        # Names only are inspected; secret values are never logged/passed.
        self.env = {k: os.environ[k] for k in (
            'PATH', 'HOME', 'TMPDIR', 'SYSTEMROOT', 'WINDIR'
        ) if k in os.environ}
        self.env.update({
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
            'GIT_OPTIONAL_LOCKS': '0', 'GIT_NO_LAZY_FETCH': '1',
            'GIT_TERMINAL_PROMPT': '0', 'GIT_PAGER': 'cat', 'LC_ALL': 'C',
        })

    def git(self, *args, cwd=None, allow=(0,)):
        argv = ['git', '--no-replace-objects']
        for value in (
            'core.hooksPath=' + os.devnull, 'core.fsmonitor=false',
            'core.untrackedCache=false', 'core.attributesFile=' + os.devnull,
            'protocol.allow=never', 'commit.gpgSign=false',
            'merge.verifySignatures=false', 'rerere.enabled=false',
            'gc.auto=0', 'maintenance.auto=false', 'submodule.recurse=false',
        ):
            argv.extend(('-c', value))
        argv.extend(('-C', str(cwd or self.repo), *args))
        result = subprocess.run(argv, env=self.env, capture_output=True,
                                timeout=120)
        out = result.stdout.decode('utf-8', errors='replace')
        err = result.stderr.decode('utf-8', errors='replace')
        self.report['commands'].append({
            'argv': argv, 'exit_code': result.returncode,
            'stdout': '' if args[0] == 'config' else out[:65536],
            'stderr': '' if args[0] == 'config' else err[:65536],
        })
        require(result.returncode in allow,
                'Git command failed: ' + args[0])
        return out.strip(), result.returncode

    def value(self, *args, cwd=None):
        return self.git(*args, cwd=cwd)[0]

    def ancestor(self, older, newer, cwd=None):
        return self.git('merge-base', '--is-ancestor', older, newer,
                        cwd=cwd, allow=(0, 1))[1] == 0

    def clean(self):
        entries = self.value('ls-files', '-v', '-z', *PATHS).split('\0')
        require(not any(entry and (entry[0].islower() or entry[0] == 'S')
                        for entry in entries),
                'assume-unchanged or skip-worktree source is rejected')
        require(not self.value('status', '--porcelain=v1', '-z',
                               '--untracked-files=all',
                               '--ignore-submodules=all', *PATHS),
                'dirty source working tree (obj-lua excluded)')

    def pins(self):
        require(self.value('rev-parse', 'HEAD') == self.base,
                'project base changed; rebuild and retest', 'BLOCKED')
        if self.upstream != self.lock['ccb']['commit']:
            require(self.value('rev-parse', TRACKING) == self.upstream,
                    'CCB tracking head changed; rebuild and retest', 'BLOCKED')

    def preflight(self):
        unexpected = rejected_git_environment(os.environ)
        require(not unexpected, 'unsupported Git environment names: ' +
                ', '.join(unexpected))
        require(Path(self.value('rev-parse', '--show-toplevel')).resolve() ==
                self.repo, '--repo must be the working-tree root')
        require(self.value('rev-parse', '--is-shallow-repository') == 'false',
                'shallow history rejected')
        require(not self.value('for-each-ref', '--format=%(refname)',
                               'refs/replace/'), 'replace refs rejected')
        common = (self.repo / self.value('rev-parse', '--git-common-dir'))
        graft = common / 'info/grafts'
        require(not graft.exists() and not graft.is_symlink(),
                'grafts rejected')
        for name in ('cdda', 'ccb'):
            source = self.lock[name]
            key = 'remote.' + source['remote'] + '.url'
            urls = self.value('config', '--get-all', key).splitlines()
            require(len(urls) == 1 and
                    github_repository(urls[0]) == source['repository'],
                    name + ' source differs from locked public GitHub source')
            self.value('cat-file', '-e', source['commit'] + '^{commit}')
            require(self.value('rev-parse', source['commit'] + '^{tree}') ==
                    source['tree'], name + ' baseline tree mismatch')
        for commit in (self.base, self.upstream, self.previous):
            self.value('cat-file', '-e', commit + '^{commit}')
        require(self.ancestor(self.lock['cdda']['commit'],
                              self.lock['ccb']['commit']), 'B is not under U')
        require(self.ancestor(self.lock['ccb']['commit'], self.previous),
                'previous integration predates or rewrites locked U')
        require(self.ancestor(self.previous, self.upstream),
                'upstream history rewrite or rollback rejected')
        require(self.ancestor(self.previous, self.base),
                'project history lost previously integrated upstream')
        self.pins()
        self.clean()

    def differences(self):
        raw = self.value('show', self.base + ':' + LEDGER)
        self.report['difference_ledger_sha256'] = hashlib.sha256(
            raw.encode()).hexdigest()
        ledger = json.loads(raw)
        require(isinstance(ledger, dict), 'ledger must be an object')
        require(ledger.get('schema_version') == 1 and
                ledger.get('baseline') == self.lock['ccb']['commit'] and
                isinstance(ledger.get('entries'), list),
                'invalid or missing design-difference ledger')
        recorded = set()
        pending = []
        for entry in ledger['entries']:
            require(isinstance(entry, dict), 'invalid difference entry')
            commit = sha(entry.get('project_commit'))
            upstream = sha(entry.get('upstream_sha'))
            require(self.ancestor(commit, self.base),
                    'difference record is not in fixed project history')
            require(self.ancestor(upstream, self.upstream),
                    'difference record refers outside upstream history')
            require(entry.get('kind') in ('adaptation', 'revert') and
                    isinstance(entry.get('reason'), str) and entry['reason'],
                    'difference entry requires kind and explanation')
            require(entry.get('decision') in ('retain', 'pending', 'restore'),
                    'invalid difference decision')
            recorded.add(commit)
            if entry['decision'] != 'retain' or entry['kind'] == 'revert':
                pending.append(entry)
        # Default git-revert messages provide a useful additional tripwire.
        # Custom semantic reversals still require explicit human ledger review.
        commits = self.value('rev-list', '--first-parent',
                             self.previous + '..' + self.base).splitlines()
        unrecorded = []
        for commit in commits:
            message = self.value('show', '-s', '--format=%B', commit)
            if re.search(r'This reverts commit [0-9a-f]{40}', message):
                if commit not in recorded:
                    unrecorded.append(commit)
        self.report['active_differences'] = ledger['entries']
        self.report['unrecorded_reverts'] = unrecorded
        require(not pending and not unrecorded,
                'explicit revert/restoration decision required; ancestry '
                'does not restore reverted behavior', 'BLOCKED')

    def changed_paths(self):
        out = self.value('diff', '--no-ext-diff', '--no-textconv',
                         '--name-only', '--no-renames', '-z',
                         self.previous, self.upstream)
        paths = out.rstrip('\0').split('\0') if out else []
        self.report['upstream_changed_paths'] = paths
        require(not any(p == 'obj-lua' or p.startswith('obj-lua/')
                        for p in paths), 'forbidden build-cache path')
        surfaces, surfaces_sha256 = protection_policy()
        protected_paths = protected_changes(paths, surfaces)
        self.report['protected_surfaces_sha256'] = surfaces_sha256
        self.report['protected_changes'] = protected_paths
        require(not protected_paths,
                'protected control/identity/design changes require explicit '
                'review; no executable remote candidate created', 'BLOCKED')

    def merge(self):
        candidate = self.work / 'candidate'
        empty = self.work / 'empty-template'
        candidate.mkdir()
        empty.mkdir()
        self.git('init', '--template=' + str(empty), cwd=candidate)
        objects = Path(self.value('rev-parse', '--git-path', 'objects'))
        if not objects.is_absolute():
            objects = self.repo / objects
        objects = objects.resolve(strict=True)
        require('\n' not in str(objects), 'unsafe object store path')
        info = candidate / '.git/objects/info'
        (info / 'alternates').write_text(str(objects) + '\n')
        # Borrow objects read-only; never copy hooks/config/remotes.
        for key in ('user.name', 'user.email'):
            value = self.value('config', '--local', '--get', key)
            require(value and '\n' not in value, 'local Git identity required')
            self.git('config', '--local', key, value, cwd=candidate)
        self.git('checkout', '--detach', self.base, cwd=candidate)
        out, code = self.git('merge', '--no-ff', '--no-commit', '--no-edit',
                             self.upstream, cwd=candidate, allow=(0, 1))
        self.report['candidate_directory'] = str(candidate)
        if code:
            self.report['conflicts'] = self.value(
                'diff', '--name-only', '--diff-filter=U', cwd=candidate
            ).splitlines()
            raise Stop('FAIL', 'merge conflict; candidate and index preserved')
        require(self.value('rev-parse', 'MERGE_HEAD', cwd=candidate) ==
                self.upstream, 'merge did not retain upstream parent')
        self.git('commit', '--no-verify', '-m',
                 'Local dry-run merge of CCB ' + self.upstream,
                 cwd=candidate)
        commit = self.value('rev-parse', 'HEAD', cwd=candidate)
        parents = self.value('show', '-s', '--format=%P', commit,
                             cwd=candidate).split()
        require(parents == [self.base, self.upstream],
                'candidate does not preserve exact merge parents')
        require(self.ancestor(self.lock['cdda']['commit'], commit,
                              cwd=candidate) and
                self.ancestor(self.upstream, commit, cwd=candidate),
                'candidate lost original history')
        self.report.update({
            'candidate_commit': commit,
            'candidate_tree': self.value('rev-parse', 'HEAD^{tree}',
                                         cwd=candidate),
            'merge_parents': parents,
        })

    def run(self):
        # Exclusive new evidence directory, outside source; never erase/reuse.
        require(not self.work.exists(), '--work-dir must not already exist')
        resolved = self.work.resolve()
        require(not resolved.is_relative_to(self.repo),
                '--work-dir must be outside source')
        common = (self.repo / self.value(
            'rev-parse', '--git-common-dir')).resolve()
        require(not resolved.is_relative_to(common),
                '--work-dir must be outside source Git metadata')
        self.work.mkdir(parents=True)
        try:
            self.preflight()
            self.differences()
            if self.ancestor(self.upstream, self.base):
                self.report['result'] = 'no_new_upstream_commits'
            else:
                self.changed_paths()
                self.merge()
                self.report['result'] = 'merge_candidate_only'
            self.preflight()
            self.report.update(status='PASS',
                               reason='local history/merge checks only')
        except Stop as exc:
            self.report.update(status=exc.status, reason=str(exc))
        except (OSError, ValueError, KeyError, TypeError,
                subprocess.TimeoutExpired) as exc:
            self.report.update(status='FAIL', reason=type(exc).__name__)
        report = self.work / 'report.json'
        report.write_text(json.dumps(self.report, indent=2) + '\n')
        return self.report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'work-dir', 'base', 'upstream', 'previous'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    try:
        repo = Path(args.repo).resolve()
        lock = read_lock(repo / 'project/upstreams.lock.json')
        require((lock['cdda']['commit'], lock['cdda']['tree'],
                 lock['ccb']['commit'], lock['ccb']['tree']) ==
                (BASE, BASE_TREE, UPSTREAM, UPSTREAM_TREE),
                'execution-spec B/U identities are fixed')
        probe = Rehearsal(repo, args.work_dir, args.base, args.upstream,
                          args.previous, lock)
        report = probe.run()
    except (Stop, OSError, ValueError) as exc:
        print('FAIL: ' + str(exc), file=sys.stderr)
        return 1
    print(json.dumps({k: report[k] for k in (
        'status', 'reason', 'task_key', 'auto_merge_enabled'
    )}))
    return {'PASS': 0, 'FAIL': 1, 'BLOCKED': 2}[report['status']]


if __name__ == '__main__':
    sys.exit(main())
