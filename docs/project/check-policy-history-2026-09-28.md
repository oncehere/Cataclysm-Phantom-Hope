# Check policy maintenance snapshot — 2026-09-28

The fields below were removed from the active check policy because they describe
the historical E1 implementation, not a live deployment decision. They are
preserved verbatim as historical data; this snapshot does not assert that they
remain current. Gate operation must be established by dated remote evidence.

```json
{
  "scope": "Provisional E1 evidence contract; no GitHub gate or release authorization.",
  "deployment_blockers": [
    "Target repository and actual protected PR rule proof missing",
    "Native Windows E1 baseline not run",
    "E3 applicable Windows/Linux isolation acceptance incomplete",
    "No trusted GitHub collector/publisher deployed"
  ],
  "merge_ready": false,
  "public_release_ready": false,
  "baseline_status": {
    "linux": "native E1 selected tests exercised; not E3 or deployed CI",
    "windows": "NOT_RUN native Windows"
  }
}
```

The v2 policy adds tool regression evidence before the native builds and was
merged with the controller in PR #6. Its hosted gate acceptance remains NOT_RUN.
Existing artifacts bind the previous whole-file policy digest and
cannot validate the new policy. The platform target definitions and protection
surface digest are unchanged.

The required tool suites are agent, project, Lua API and JSON API regressions.
Every selected suite must execute nonzero tests with zero skips or failures.
The Lua language-server editor integration class remains outside this CI
profile because it requires a separately configured CCB_LUALS executable; its
excluded test IDs are recorded explicitly. It is not reported as passed.
The tooling candidate checkout fetches full history because agent metadata
validates frozen migration inputs, including paths deleted from the current
tree. Native compilation retains its two-parent checkout. Tool test subprocesses
load candidate modules without preloading same-named modules from the control
checkout; a candidate sentinel regression verifies that import boundary.

Documentation impact remains staged and is not part of the trusted CI status.
For each PR, run `tools/agent/check_docs_impact.py --base <base> --head <head>
--check-pr-body` from the candidate checkout with the current API-returned PR
body supplied as PR_BODY. The existing Git diff uses --no-renames, preserving
both the removed old path and added new path; deleted mapped docs cannot count
as updated documentation. Required and advisory mappings retain their existing
semantics. Record the exact refs, body snapshot and command result with the PR.

## Historical bootstrap boundary and remaining acceptance

The controller was merged by PR #6; the exact setup-python action below was
also added to the repository allowlist. Hosted positive/negative acceptance is
still **NOT_RUN**, and synchronization remains user-paused. See
[status.md](status.md) and [resume.md](resume.md) for the current state. The
following bootstrap limitation explains that maintenance merge; it is not an
instruction to repeat initialization or restore automatic merging.

The maintenance PR introducing this controller could not obtain the new
tooling evidence from its old base: that base
does not yet contain `ci_tooling.py` or the new policy contract. A PR-triggered
candidate workflow therefore cannot establish acceptance of its own new gate.
For owner-initiated, explicitly authorized personal maintenance, use applicable
local evidence under execution-spec section 6.1; remote Windows/Linux completion
is not a prerequisite for this maintenance merge. A main-dispatched native run
may remain supplemental evidence and must retain its actual result. Record
unverified Windows scope and evidence reuse against unchanged inputs. Apply the
separately confirmed protected maintenance procedure; retain any actual gate
rejection and never publish fabricated success or run candidate code with a
status-write token. This exception does not change unattended sync/merge policy.

When the user authorizes hosted acceptance, keep automatic merging paused,
create a controlled ordinary PR on current main and verify the deployed path.
Its plan and tooling jobs must bind
the same base/head/merge tree/policy/run/attempt as both native platforms. A
tooling failure stops the native dependency chain, and the trusted collector
rejects a missing, skipped, failed, empty or stale tooling report. Read back the
actual status and active no-bypass rule before calling this path deployed.
Keep local model tests distinct from those future GitHub acceptance results.
The repository Actions allowlist must retain the exact reviewed
`actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065` reference. Updating
the tracked `remote-actions-policy.json` does not change that GitHub setting;
recheck its actual value before the deployment probe.
