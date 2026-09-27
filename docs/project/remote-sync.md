# CCB remote synchronization

This controller follows only `CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb`
`master`. Its only write target is `oncehere/Cataclysm-Phantom-Hope` (repository
ID `1389460908`), verified as a native `CleverRaven/Cataclysm-DDA` fork.
Deployment and actual GitHub acceptance are recorded separately in the
[project status report](status.md). As of this deployment checkpoint,
`project-ci.yml` is on the target, while `project-gate.yml` and
`project-sync.yml` are implemented and awaiting upload/readback. Actions is
enabled with exactly five pinned actions allowed; inherited `master` is frozen
at its original SHA. Native Windows/Linux CI uses GitHub-hosted runners.
Actual platform results and protected-PR acceptance remain **PENDING**.
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

The target's state branch has already been initialized and remains paused.
Do not initialize it again. The following command documents the one-time
bootstrap operation, from a trusted checkout with a target-scoped credential
supplied only to the process environment:

```sh
python3 tools/project/remote_sync.py init-state
```

Initial controls are `sync_paused=true`, `merge_paused=true`, and
`auto_merge_enabled=false`. Initialization is not gate activation. Read the
current state revision before each edit; a stale revision is rejected:

```sh
python3 tools/project/remote_sync.py controls --revision 0 --sync resume
python3 tools/project/remote_sync.py controls --revision 1 --sync pause
python3 tools/project/remote_sync.py controls --revision 2 --block ccb-FULL_SHA
```

Replace `FULL_SHA` with the full lowercase source SHA. `--unblock` removes that
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
