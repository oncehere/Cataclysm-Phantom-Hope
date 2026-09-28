# CCB remote synchronization

This controller follows only `CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb`
`master`. Its only write target is `oncehere/Cataclysm-Phantom-Hope` (repository
ID `1389460908`), verified as a native `CleverRaven/Cataclysm-DDA` fork.
Current deployment, pause controls and hosted acceptance are recorded once in
[project status](status.md). Read GitHub and `codex/sync-state` again before
acting. The user-requested pause must survive maintenance, policy deployment
and rule-lock refreshes. Earlier activation receipts remain in the
[historical version](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/abd9222e01b77ac9e187f53cd6cfe85275453a69/docs/project/remote-sync.md).

`project-sync.yml` is configured to check every six hours at minute 23 and
supports manual dispatch on `main`; it is currently disabled under the user's
pause. When enabled, scheduling may be delayed; GitHub can disable a public
repository's scheduled workflows after prolonged inactivity. Use the manual
entry only when the operation and current controls authorize it; inspect the Actions result. There is no automatic AI call,
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

The deployed source requires `CPH Tooling` before either native build, with
verified suite counts, generator checks, dependency digest and exact
candidate/run identity. Its new hosted acceptance remains **NOT_RUN** until a
real ordinary PR verifies both successful and rejected evidence. Keep automatic
merge paused through this acceptance; see the [deployment procedure](../../REPOSITORY_SETTINGS.md#controller-deployment).
Documentation impact remains an explicit local/review check.

## Persistent state and retries

This remote contract governs unattended synchronization and automatic merge.
Owner-authorized personal maintenance follows execution-spec section 6.1 using
applicable local evidence; it does not obtain a synthetic trusted status or alter
this controller's Windows/Linux requirements. Any temporary administrator
exception follows the separately confirmed [settings procedure](../../REPOSITORY_SETTINGS.md#personal-maintenance-under-the-existing-rule),
with automatic operations paused and the no-bypass rule lock restored afterward.

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
supersedes the previous open PR within the same task. No branch is force pushed. GitHub may delete a head branch after its PR is
merged; its commit and PR remain the recovery source. Active or failed candidate
branches are not retired by this controller. A closed or unexpectedly modified attempt requires
explicit review rather than recreating duplicate PRs.

## Operator controls

The state branch already exists. Do not run `init-state` as routine recovery.
Read the current `codex/sync-state:state.json` revision before each edit; stale
revisions are rejected. Workflow enablement and state controls are separate:
changing one does not authorize changing the other. The examples below are
alternatives, not a sequence:

```sh
python3 tools/project/remote_sync.py controls --revision CURRENT_REVISION --sync pause
python3 tools/project/remote_sync.py controls --revision CURRENT_REVISION --block ccb-FULL_SHA
```

Replace `CURRENT_REVISION` with the freshly read integer and `FULL_SHA` with
the full lowercase source SHA. `--unblock` removes that
candidate from the list. `--merge pause` stops merging independently of source
checks/PR preparation. Only after real protected PR success/failure acceptance
and a fresh user request to resume
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
