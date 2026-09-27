# CPH repository settings / 仓库设置

Target repository: [`oncehere/Cataclysm-Phantom-Hope`](https://github.com/oncehere/Cataclysm-Phantom-Hope), a native CDDA fork whose development branch is `main`. GitHub's live configuration is authoritative. A workflow, this page, or `ai/repository-settings.target.yml` cannot activate a setting. The CPH target is `ai/repository-settings.target.yml`; the inherited CCB settings are retained as history in `ai/history/ccb-repository-settings-2026-08-02.yml` and must not be applied to CPH.

At the 2026-09-27 07:40 UTC public readback, `main=39859e1b253e28e2c34b6a19935b7edcce51b9b6`, ruleset `24056126` was active and the branch reported `protected=true`. The `codex/sync-state` branch at revision 3 separately recorded `sync_paused=false`, `merge_paused=false`, `auto_merge_enabled=true`; rule activation alone does not establish these switches or approve a particular PR. Documentation PR #3 remains blocked by protected-path rejection under the active rule; do not disable the rule to merge it.

Read the dated [project status](docs/project/status.md), [remote sync evidence](docs/project/remote-sync.md) and actual GitHub settings/Actions for the current Issues, Discussions, private vulnerability reporting, ruleset, sync, merge and release state. The status document is a snapshot, so verify the remote again before a privileged action. Template files do not enable Issues or private reporting.

## Verification and operation order

1. Read back the exact repository, branch, Actions permissions, workflow runs, settings and candidate check names. Keep tokens and private membership out of evidence.
2. For each candidate, verify native Windows/Linux results and trusted check publication for its fixed base/head/merge tree. A previous PR or `workflow_dispatch` result cannot satisfy the current PR's required checks.
3. Read back the active `main` rule, bypass-actor lock and operator controls; retain the required `cph/trusted-gate` check. Record the rule ID, update time and candidate-specific positive or negative result. Do not turn off the rule for an ordinary or bootstrap PR.
4. Read the sync-state branch immediately before any automatic merge. A true switch is not a check result, and a protected PR with a failing or missing required status remains blocked. Issues and private vulnerability reporting are separate setting decisions; after either is enabled and read back, update [ISSUES.md](ISSUES.md), [SUPPORT.md](SUPPORT.md), [SECURITY.md](SECURITY.md) and the dated status as needed.
5. A public development release requires four current platform packages, checks, identity/signing decisions and release acceptance. Stable release remains an explicit user decision.

An ordinary source PR does not apply administrator settings. Do not weaken required checks, force linear history across inherited merges, fabricate human review, or use an untested bypass to claim success. A bot review does not count as the required human review.

## Read-only verification examples

```sh
gh api repos/oncehere/Cataclysm-Phantom-Hope
gh api repos/oncehere/Cataclysm-Phantom-Hope/rulesets
gh api repos/oncehere/Cataclysm-Phantom-Hope/actions/workflows
```

These examples only inspect live state under the caller's read permissions. The previous CCB audit and organization 2FA notes are historical CCB evidence, not CPH administrator instructions.
