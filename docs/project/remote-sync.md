# CCB remote synchronization

This controller follows only `CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb`
`master`. Its only write target is `oncehere/Cataclysm-Phantom-Hope` (repository
ID `1389460908`), verified as a native `CleverRaven/Cataclysm-DDA` fork.
Deployment and actual GitHub acceptance are recorded with dates in the
[project status report](status.md). At the 2026-09-27 07:40 UTC readback,
`main=39859e1b253e28e2c34b6a19935b7edcce51b9b6` and ruleset
`24056126` is active; the branch reports `protected=true`. PR #1 was merged
under this rule. The public `codex/sync-state` branch, revision 3, records
`sync_paused=false`, `merge_paused=false`, `auto_merge_enabled=true` and
positive/negative protected-merge acceptance. It also records that a new CCB
integration has not been live tested and public release is not enabled.
These controls must be read again before acting; ruleset activation alone
does not establish the sync or merge switch state. Documentation PR #3 is
blocked by the protected-path collector rejection and cannot use a disabled
rule as a bootstrap exception.

At the earlier 2026-09-27 03:31 UTC review snapshot,
`main=d88815158ad31104ab4cde9fdd7537c7180cf7ff`; the three controlled
workflows remain active and the main ruleset remains disabled. PR #1 has a
new Windows/Linux attempt running at that snapshot; no successful native gate
or protected merge is established by an in-progress run. The following is the
earlier `main=5dc53160e6e877ef0526d686a2c3b9a9c2bfb3ec` deployment receipt:
CI `368009607`, gate `368019205`, sync `368019206`. Actions allows exactly five
pinned actions; inherited `master` remains frozen at its original SHA.
Pause run `36281825809` and no-update run `36281948613` passed. State revision 1
has `sync_paused=false`, `merge_paused=true`, `auto_merge_enabled=false`.
Native CI run `36281829866` for PR #1 failed on Windows because the shallow
vcpkg checkout lacked a historical tree; Linux was cancelled and is not a pass.
Collector run `36282037172` published `cph/trusted-gate=failure`. Main ruleset
`24056126` was created but disabled, so protected-PR acceptance remained
**PENDING**. Subsequent facts belong in
Actions and the external evidence ledger rather than a source commit per run.
Local tests do not prove that the remote gate is active.

`project-sync.yml` checks every six hours at minute 23 and supports manual
dispatch on `main`. Scheduling may be delayed; GitHub can disable a public
repository's scheduled workflows after prolonged inactivity. Use the manual
entry to recover and inspect the Actions result. There is no automatic AI call,
public release, signing, force push, or rewrite of upstream history.

## Execution and credentials

1. The preparation job checks out the controller at the event's trusted commit.
   Public API reads pin project H, CCB U1, and the last integrated source SHA.
   No change creates no candidate or PR. A paused or blocked candidate performs
   no synchronization action.
2. Public Git fetches run with an environment allowlist and no credentials.
   Partial-clone blobs needed by checkout/merge and the new upstream history
   are fetched explicitly. The existing `sync_dry_run.py` checks ancestry,
   active design differences, protected surfaces and real merge conflicts.
   It creates a local candidate, never builds or executes candidate code.
3. A new runner downloads only the plan and optional Git bundle from the same
   workflow run. It runs the same trusted controller, independently checks
   exact H/U1 parents, tree, ancestry and protected paths, and recomputes the
   Git merge tree. It never checks out or executes candidate files.
4. Only this publishing job has repository write permission. It checks fresh
   operator state and H/U1 before writes, pushes a fixed candidate to a new
   branch without force, creates or reuses the PR, then dispatches
   `project-ci.yml` on `main` with `pr_number`, `base_sha`, and `head_sha`.
   Ordinary dispatch job success is not a required PR check. The separate
   trusted collector must validate native Windows/Linux results and publish
   `cph/trusted-gate`; only its verified protected merge path can merge.

The synchronization workflow does not enable GitHub auto-merge or call the
merge API. The collector must reload state immediately before its final merge
action and call `record_merged` after verifying actual remote completion.

The 2026-09-28 maintenance candidate additionally requires a `CPH Tooling` job
before either native build, with independently verified tool suite counts,
generator checks, dependency digest and exact candidate/run identity. This
change is **IMPLEMENTED_NOT_DEPLOYED** until its reviewed controller and action
allowlist are deployed and a real ordinary PR verifies the new gate. The
[dated policy migration record](check-policy-history-2026-09-28.md) describes
the bootstrap boundary and the intentionally staged documentation-impact check.

## Persistent state and retries

`codex/sync-state` contains only `state.json`, outside game source history.
Updates create a child commit and fast-forward the ref with `force=false`.
Competing writes fail rather than overwrite each other. The workflow's fixed
concurrency group additionally serializes synchronization attempts.

The state stores `last_integrated_sha`, operator controls, and a task map keyed
by the full upstream SHA (`task_key=ccb-<U1>`). The initial locked B/U in
`project/upstreams.lock.json` never changes. Only a verified merged PR advances
the recorded integrated source; ancestry is checked again and cannot regress.
If merging succeeded but its state update was lost, the next publishing job
verifies the recorded PR's actual merged state and repairs this record before
attempting further synchronization. Open or failed PRs are never treated as merged.
Recovering an older merged task after a newer one marks the older task complete
without moving the integrated-source cursor backward; divergent histories fail.

The collector also requires `verified_rulesets`: administrator-verified rule
IDs, update timestamps, public-field digests, and an explicitly empty bypass
list. Runtime reads must match these locks. Older state without this field is
readable, but absent/empty locks do not authorize automatic merging. A public
API response omitting bypass information is not proof of an empty bypass list.

Conflicts, protected changes and unresolved design decisions update the same
task in state and appear in the Actions summary/failing run. They create no
Issue, comment or executable PR branch. Fix the design decision in a reviewed
change, then rerun. A history rewrite or missing object is a failure, never an
instruction to reset the source or silently accept another upstream.

The first candidate branch is `codex/ccb-<U1>`. A retry with the same H/U1/tree
reuses its actual branch commit and PR, even if a new local merge timestamp
would produce a different SHA. If H changes, a new branch
`codex/ccb-<U1>-<H>` retains the previous attempt's history; the replacement PR
supersedes the previous open PR within the same task. No branch is force pushed
or automatically deleted. A closed or unexpectedly modified attempt requires
explicit review rather than recreating duplicate PRs.

## Operator controls

The target's state branch was initialized; synchronization checks were resumed,
while merging remained paused at the deployment snapshot above. Read current
state from the target before using a control operation; do not reuse that old
revision as a current value.
Do not initialize it again. The following command documents the one-time
bootstrap operation, from a trusted checkout with a target-scoped credential
supplied only to the process environment:

```sh
python3 tools/project/remote_sync.py init-state
```

Initial controls were `sync_paused=true`, `merge_paused=true`, and
`auto_merge_enabled=false`. Initialization is not gate activation. Read the
current `codex/sync-state:state.json` revision before each edit; a stale
revision is rejected. The examples below are alternatives, not a sequence:

```sh
python3 tools/project/remote_sync.py controls --revision CURRENT_REVISION --sync pause
python3 tools/project/remote_sync.py controls --revision CURRENT_REVISION --block ccb-FULL_SHA
```

Replace `CURRENT_REVISION` with the freshly read integer and `FULL_SHA` with
the full lowercase source SHA. `--unblock` removes that
candidate from the list. `--merge pause` stops merging independently of source
checks/PR preparation. Only after real protected PR success/failure acceptance
may the authorized operator set `--merge resume --auto-merge enable`.
An in-flight publisher reloads controls before its final action; a changed
revision invalidates that attempt. The collector has the same obligation.
GitHub APIs do not provide a transaction spanning state and merge, so these
fresh checks narrow the race without claiming a cross-API atomic guarantee.

## Local verification

```sh
python3 -m unittest discover -s tests/project -p test_remote_sync.py -v
```

Tests use throwaway Git repositories and an explicit API state model. They
cover no-change behavior, history/tree forgery, protected workflow restoration,
credential stripping, paused/blocked controls, moved refs, state CAS, branch
reuse, conflict persistence and rejection of unverified merge completion.
Actual Actions, native platform tests, status binding and protected merges are
separate deployment acceptance scopes.
