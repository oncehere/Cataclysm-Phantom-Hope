# CPH repository settings / 仓库设置

Target repository: [`oncehere/Cataclysm-Phantom-Hope`](https://github.com/oncehere/Cataclysm-Phantom-Hope), a native CDDA fork whose development branch is `main`. GitHub's live configuration is authoritative. A workflow, this page, or `ai/repository-settings.target.yml` cannot activate a setting. The CPH target is `ai/repository-settings.target.yml`; the inherited CCB settings are retained as history in `ai/history/ccb-repository-settings-2026-08-02.yml` and must not be applied to CPH.

At the 2026-09-27 07:40 UTC public readback, `main=39859e1b253e28e2c34b6a19935b7edcce51b9b6`, ruleset `24056126` was active and the branch reported `protected=true`. The `codex/sync-state` branch at revision 3 separately recorded `sync_paused=false`, `merge_paused=false`, `auto_merge_enabled=true`; rule activation alone does not establish these switches or approve a particular PR. Documentation PR #3 remains blocked by protected-path rejection under the active rule; do not disable the rule to merge it.

Read the dated [project status](docs/project/status.md), [remote sync evidence](docs/project/remote-sync.md) and actual GitHub settings/Actions for the current Issues, Discussions, private vulnerability reporting, ruleset, sync, merge and release state. The status document is a snapshot, so verify the remote again before a privileged action. Template files do not enable Issues or private reporting.

## Verification and operation order

1. Read back the exact repository, branch, Actions permissions, workflow runs, settings and candidate check names. Keep tokens and private membership out of evidence.
2. Classify the operation using execution-spec section 6.1. Explicitly authorized personal maintenance uses applicable local evidence and records unverified platforms; it need not wait for Actions. Unattended sync/automatic merge still requires remote Windows/Linux results and trusted publication for the exact base/head/merge tree. Local evidence and a previous PR cannot satisfy that remote gate.
3. Read back the active `main` rule, bypass-actor lock and operator controls; retain the required `cph/trusted-gate` check. Record the rule ID, update time and candidate-specific positive or negative result. Do not turn off the rule for an ordinary or bootstrap PR.
4. Read the sync-state branch immediately before any automatic merge. A true switch is not a check result, and a protected PR with a failing or missing required status remains blocked. Issues and private vulnerability reporting are separate setting decisions; after either is enabled and read back, update [ISSUES.md](ISSUES.md), [SUPPORT.md](SUPPORT.md), [SECURITY.md](SECURITY.md) and the dated status as needed.
5. A public development release requires four current platform packages, checks, identity/signing decisions and release acceptance. Stable release remains an explicit user decision.

An ordinary source PR does not apply administrator settings. Do not weaken required checks, force linear history across inherited merges, fabricate human review, or use an untested bypass to claim success. A bot review does not count as the required human review.

## Personal maintenance under the existing rule

The rule currently requires `cph/trusted-gate` for every PR. GitHub does not infer the owner's task authorization from a conversation or PR label. The minimum setting procedure is a separately confirmed, short-lived **Repository admin / For pull requests only** exception to ruleset `24056126`; this document does not apply or pre-authorize it. It needs no change to the unattended collector, sync validator, required status or release policy.

Explain the actual scope before confirmation: this role exception covers every repository administrator and the rules in that ruleset for PR operations during the window; GitHub cannot restrict it to one PR or infer local-test sufficiency. Only the fixed, reviewed PR/head may be merged by the operator. Existing rules remain configured, but their requirements may be bypassed by that role in the window. The user has stated that only they currently hold the administrator role; refresh this fact if contrary evidence appears.

After the candidate's local evidence is complete and the user confirms the exact setting change: save current rule/state; use a fresh CAS to pause sync and automatic merge; check in-flight operations; add the PR-only exception; merge the fixed head using a merge commit; immediately remove the exception even if the merge fails. Read back the resulting parents/tree, empty bypass list and unchanged required checks. Refresh the affected administrator-verified rule lock and restore the original controls through CAS. Preserve unrelated state fields and historical acceptance records.

Do not retain a permanent administrator exception as part of this minimum procedure. Both `remote_gate.active_rules` and `remote_sync.validate_state` currently require an empty bypass lock; a permanent exception would require a distinct reviewed controller/settings change. Personal maintenance readiness does not imply the new unattended tooling gate or any release is deployed and accepted.

## Read-only verification examples

```sh
gh api repos/oncehere/Cataclysm-Phantom-Hope
gh api repos/oncehere/Cataclysm-Phantom-Hope/rulesets
gh api repos/oncehere/Cataclysm-Phantom-Hope/actions/workflows
```

These examples only inspect live state under the caller's read permissions. The previous CCB audit and organization 2FA notes are historical CCB evidence, not CPH administrator instructions.
