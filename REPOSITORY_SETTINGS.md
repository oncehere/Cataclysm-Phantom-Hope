# CPH repository settings / 仓库设置

Target repository: [`oncehere/Cataclysm-Phantom-Hope`](https://github.com/oncehere/Cataclysm-Phantom-Hope), a native CDDA fork whose development branch is `main`. GitHub's live configuration is authoritative. A workflow, this page, or `ai/repository-settings.target.yml` cannot activate a setting. The CPH target is `ai/repository-settings.target.yml`; the inherited CCB settings are retained as history in `ai/history/ccb-repository-settings-2026-08-02.yml` and must not be applied to CPH.

Read the dated [project status](docs/project/status.md), [remote sync evidence](docs/project/remote-sync.md) and actual GitHub settings/Actions for the current Issues, Discussions, private vulnerability reporting, ruleset, sync, merge and release state. The status document is a snapshot, so verify the remote again before a privileged action. Template files do not enable Issues or private reporting, and a disabled ruleset is not protected-merge acceptance.

## Acceptance and activation order

1. Read back the exact repository, branch, Actions permissions, workflow runs, settings and candidate check names. Keep tokens and private membership out of evidence.
2. Fix Windows/Linux check failures and verify their results and trusted check publication on the required PR context. Test negative and positive protected-merge paths; ordinary `workflow_dispatch` job checks cannot be assumed to satisfy a PR's required checks.
3. Validate the intended `main` rule, bypass actor and operator controls. Activate it only after the criteria in the [execution specification](docs/project/execution-spec.md) pass. Record the real rule ID, operator, time and post-change readback.
4. Keep automatic merge paused until protected-PR and source/permission checks pass. Issues and private vulnerability reporting are separate setting decisions; after either is enabled and read back, update [ISSUES.md](ISSUES.md), [SUPPORT.md](SUPPORT.md), [SECURITY.md](SECURITY.md) and the dated status as needed.
5. A public development release requires four current platform packages, checks, identity/signing decisions and release acceptance. Stable release remains an explicit user decision.

An ordinary source PR does not apply administrator settings. Do not weaken required checks, force linear history across inherited merges, fabricate human review, or use an untested bypass to claim success. A bot review does not count as the required human review.

## Read-only verification examples

```sh
gh api repos/oncehere/Cataclysm-Phantom-Hope
gh api repos/oncehere/Cataclysm-Phantom-Hope/rulesets
gh api repos/oncehere/Cataclysm-Phantom-Hope/actions/workflows
```

These examples only inspect live state under the caller's read permissions. The previous CCB audit and organization 2FA notes are historical CCB evidence, not CPH administrator instructions.
