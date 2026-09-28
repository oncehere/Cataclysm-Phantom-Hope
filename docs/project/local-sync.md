# Local CCB integration rehearsal

This page specifies the local rehearsal command. That command remains local-only;
the separate remote controller has since been deployed on the authorized target.
Its current run and gate state is in [status.md](status.md) and
[remote-sync.md](remote-sync.md). This command performs local Git history and
merge checks only. It never fetches, pushes, updates the source branch, runs a
workflow, calls AI, or enables merging. The target is now named and verified;
the dated Windows/Linux protected-PR gate results are in [status.md](status.md).

Run from a clean committed project checkout. The CLI pins the specification's
exact B/U commits and trees. A newer upstream must already be available locally
and exactly match `refs/remotes/ccb/master`; this tool does not select a new
upstream head. `--previous` is the most recent deliberately recorded integrated
CCB source SHA, not an arbitrary common ancestor. For the initial fixed U:

```sh
python3 tools/project/sync_dry_run.py \
  --repo "$PWD" \
  --base "$(git rev-parse HEAD)" \
  --upstream bcb85682f3d28ab0f0123b05e45651bb9888b61b \
  --previous bcb85682f3d28ab0f0123b05e45651bb9888b61b \
  --work-dir /absolute/authorized/new-evidence-directory
```

The evidence directory must be new and outside both source and Git metadata.
It is never erased or reused. `report.json` contains commands, exits, pinned
heads, source/history checks, ledger digest, result tree/merge parents where
applicable, and separate unrun acceptance scopes. Exit 0 is `PASS` for this
local scope only, exit 1 is `FAIL`, and exit 2 is `BLOCKED`.

No new upstream commits yields no candidate. With updates, protected workflow,
policy, signing/build, identity and design paths stop before checkout. The
rehearsal uses E4's path matcher and the `project/protected-surfaces.json` beside
the reviewed controller checkout, pinned by that checkout's `check-policy.json`.
Run the reviewed tool from that checkout when inspecting another source repo;
the inspected repo or upstream candidate cannot supply its own protection list.
Missing, malformed or mismatched protection input fails closed, and the report
records the loaded protection digest. The shared list retains the rehearsal's
existing `.gitattributes` and full `build-data/` coverage. This local check is
not a substitute for E4's trusted policy/permission boundary. Ordinary
changes use a fresh empty-template Git repository. It borrows the source object
store read-only via an alternate, copies no hooks/remotes/filters/config, and
runs actual `git merge --no-ff --no-commit` followed by a local merge commit.
The identity comes from the source's explicit local Git identity; the tool does
not invent an author. The result must retain exact parents H/U1 and B/U ancestry.
The borrowed-object candidate depends on that source object store remaining
available; it is evidence, not a standalone transferable repository.

Only Git runs. The candidate is never built or executed. Git hooks, external
diff/text conversion, global/system Git configuration, lazy network fetch,
repository recursion and automatic maintenance are disabled. Git subprocesses
receive only a small environment allowlist, preserving HOME unchanged and
excluding tokens. Config query values (including credential-bearing bad URLs)
are omitted from logs. No speculative remote credential is needed. The source
is rechecked at completion; a moving H/U1, dirty state or source/history change
invalidates that run. Both passes reject assume-unchanged/skip-worktree index
flags, which could otherwise hide user edits, and any graft path including a
dangling symlink. The tool never clears those flags or edits user files.
Missing promisor objects fail explicitly instead of
fetching behind the caller's back.

A conflict retains the candidate working files, Git index, MERGE_HEAD and report
with `FAIL`; there is no `-X theirs`, source reset or automatic retry. Inspect
those retained files and the existing task record. The stable `task_key` is
`ccb-<U1>` across retries, with H recorded separately; a future remote controller
must reuse the corresponding task and rebuild/retest when H/U1 changes. This
local tool creates no Issue/PR and implements no remote deduplication store.

The [difference ledger](design-differences.md) is evaluated before an
already-ancestor result. Explicit reverts, unresolved choices and default
unrecorded revert commits are `BLOCKED`, never proof of restoration. Arbitrary
semantic conflicts remain outside this text/history check.

Tests use actual throwaway local Git repositories and declared fixture author
identities. They cover no change, preserved merge parents, text conflicts,
source changes, shallow/replace/graft history, missing objects, dirty files,
protected paths, changing H/U1, pending design choices, revert/retry, missing
ledger, unsafe output locations, config/hook isolation and fixed CLI baseline.
An untrusted Windows/Linux result file cannot enable this tool's nonexistent
merge action. This is not an E4 check-result validator: W/L actual failures,
skips and successes remain `NOT_RUN` here, and all reports retain
`auto_merge_enabled=false`.

```sh
python3 -m unittest discover -s tests/project -p test_sync_dry_run.py -v
```

Recovery prerequisites for remote E5: the authorized personal CDDA fork is
already present; verified E4 Windows/Linux required checks and base/head/tree
binding, active protection and pause/state/retry handling on an actual protected
PR are still required. The deployed controller uses scoped `GITHUB_TOKEN`, not
a configured App identity; that choice does not turn a dispatch job into a
required PR check. Do not deploy this local rehearsal directly as a
credential-bearing workflow.
