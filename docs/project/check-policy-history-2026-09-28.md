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

The v2 policy adds tool regression evidence before the native builds. This is a
local candidate until the reviewed controller is deployed and tested on a real
protected PR. Existing artifacts bind the previous whole-file policy digest and
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

## Deployment and bootstrap boundary

Status: **IMPLEMENTED_NOT_DEPLOYED**. The maintenance PR introducing this
controller cannot obtain the new tooling evidence from its old base: that base
does not yet contain `ci_tooling.py` or the new policy contract. A PR-triggered
candidate workflow therefore cannot establish acceptance of its own new gate.
Use a `project-ci.yml` dispatch on the currently deployed main to obtain the
existing Windows/Linux evidence for the fixed maintenance candidate, together
with the local tool and collector regressions. Apply the separately authorized
protected maintenance procedure; retain its actual gate rejection and never
publish a fabricated success or run candidate code with a status-write token.

After that reviewed controller is merged, create a controlled ordinary PR on
the new main and verify the deployed path. Its plan and tooling jobs must bind
the same base/head/merge tree/policy/run/attempt as both native platforms. A
tooling failure stops the native dependency chain, and the trusted collector
rejects a missing, skipped, failed, empty or stale tooling report. Read back the
actual status and active no-bypass rule before calling this path deployed.
Keep local model tests distinct from those future GitHub acceptance results.
The repository Actions allowlist must also add the exact reviewed
`actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065` reference. Updating
the tracked `remote-actions-policy.json` does not change that GitHub setting;
record its actual readback before the deployment probe.
