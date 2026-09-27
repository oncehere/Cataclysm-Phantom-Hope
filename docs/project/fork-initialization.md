# E2 read-only preparation and fork deployment

This page documents the read-only preparation tool and its 2026-09-26
initialization checklist. The named target now exists and has three controlled
workflows active on `main`; the original Actions-disabled condition is a
deployment snapshot, not the current operating instruction. See
[status.md](status.md) before acting on a checklist item.

The user explicitly authorized `oncehere/Cataclysm-Phantom-Hope` on 2026-09-26.
Its native CDDA fork, initial history upload and default-branch selection were
performed separately from this read-only tool. See [the actual deployment
receipt](fork-deployment.md). Actions were disabled during initialization;
controlled workflows were enabled later. Automatic merging and protected PR
acceptance have not been enabled or validated.

`prepare_fork.py` only reads local Git and, when explicitly requested, GitHub.
There is no remote-write code path and no execution flag. Its structured
checklist describes operations for a later authorized implementation; it does
not create a repository, upload a branch, change defaults/settings or enable
Actions. The native fork POST appears only as review metadata, never a request.

```sh
python3 tools/project/prepare_fork.py --repo "$PWD"
python3 tools/project/prepare_fork.py --repo "$PWD" --target oncehere/Cataclysm-Phantom-Hope --github
python3 -m unittest discover -s tests/project -p 'test_prepare_fork.py' -v
```

The target above is the user's unique explicit target, not an inferred account.
`--branch` selects a new remote branch; when
omitted, the report uses the current local branch without changing any ref.
Detached HEAD requires an explicit branch. Output JSON can be redirected to
the external evidence directory.

The tool reuses E0's clean-history/workspace, tree, environment and read-only
remote checks. Source-cache origin identity is also read without examining its
worktree: an existing personal CCB fork used as that cache is not a CPH target.
The two upstream repositories are rejected as targets before probing. Missing
target blocks remote operations while still reporting available local checks.

`--github` uses the already configured `gh` identity with GET-only commands. It
checks that the authenticated personal account matches the target owner,
inspects actual fork-parent metadata and administration permission, and checks
the proposed branch. It does not read or print token values, request a new
token, log raw API bodies or install a GitHub App. With no target, it does not
query the account to guess one. Without `--github`, remote facts stay unverified.

HTTP 404 is reported separately from 403, 429 and network/authentication errors.
A 404 still requires confirming visibility/name availability before a later
native fork operation. An existing correct fork requires an explicit reuse
scope; a wrong-parent fork, nonfork name collision, or occupied branch must not
be reset, deleted or silently repurposed. The report never turns these reads
into write authorization.

The ordered checklist requires native CDDA forking, Actions kept disabled and
no signing/AI secrets, read-back of the actual CDDA parent, quarantine of
inherited workflows, and upload of only a new unoccupied branch retaining B/U
history. Existing refs are preserved. Only afterward may the explicit target's
default branch change and reviewed low-permission checks be enabled. Linear
history enforcement is incompatible with this imported merge history. Real
Windows/Linux PR gates and four-platform release readiness remain later gates;
ordinary dispatch success is not a PR gate, and public/stable releases remain
disabled.

Exit 1 means local trust/preflight failed; exit 2 is invalid CLI usage; exit 3
means a review report was produced with specific blocked remote prerequisites.
The tool alone is `IMPLEMENTED_NOT_DEPLOYED`, not E2 completion. The tests use synthetic
Git histories and explicitly simulated API responses, not real fork creation,
branch protection or platform acceptance. It intentionally reports an existing
fork as requiring an explicit modification scope. That conservative diagnostic
does not revoke the user's recorded authorization or prove a deployment failed.
Use the receipt and current remote read-backs for the deployed target; never
rerun native fork creation or replace an existing branch to silence this check.
