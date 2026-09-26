# E0 read-only preflight

Run from a clean, isolated CPH checkout after reviewing its instructions:

```sh
python3 tools/project/preflight.py --repo "$PWD"
python3 tools/project/preflight.py --repo "$PWD" --github
python3 -m unittest discover -s tests/project -p 'test_preflight.py' -v
```

JSON goes to stdout; redirect it to an evidence directory outside the checkout.
Exit 0 means the **local history/workspace checks** passed. Exit 1 rejects an
untrusted or dirty local workspace; missing/invalid CLI arguments exit 2.
Missing tools, unexecuted platform builds and remote conditions are separate
report fields. They do not become successful builds when local preflight passes.

The default `project/upstreams.lock.json` fixes B/U and both tree IDs from the
execution specification. B must be an ancestor of U, and HEAD must retain U.
The lock is a reviewed control input, not an authenticity claim by itself.
`--lock PATH` permits reproducible testing of a separately reviewed lock;
the test suite uses explicitly synthetic temporary Git histories and never
claims game, platform, GitHub protection or fork acceptance.

The supplied directory must be the actual Git working-tree root. Shallow history,
replacement refs, legacy grafts, dirty tracked/staged/untracked paths and unsafe
Git environment overrides cause rejection. Git reads use
`GIT_OPTIONAL_LOCKS=0`, `GIT_NO_LAZY_FETCH=1` and `--no-replace-objects`.
Global/system Git configuration is disabled for the probe; no lazy fetch, Git
index refresh, hooks or fsmonitor is requested. The prohibited `obj-lua/` cache
is excluded by explicit Git pathspecs and is not inventoried. Other ignored
build caches are not enumerated. This probe does not claim that every historical
blob in a promisor repository is locally present.

Fetch sources must be the declared GitHub CDDA/CCB repositories, under
`upstream` and `ccb`. Optional `source-cache` is a local absolute path used only
as a cache, never as upstream provenance. Every configured remote must have
exactly `DISABLED` as its push URL for this initialization probe. Unknown remotes
fail. An `origin` remote is accepted only when `--target OWNER/REPO` explicitly
names its matching project. Credential-bearing URLs are rejected and redacted
in output. Environment values and tokens are never reported.

No target is inferred: omitting `--target` records `target_fork: BLOCKED`, while
valid local work can pass. `--github` performs anonymous HTTPS GET requests for
the pinned source commit/tree metadata and, if supplied, the target's real fork
parent and personal-account owner type. API failures stay visible as remote
failures; they never become an
assumed empty/new repository. These reads neither inspect nor grant write
authorization, so `remote_operations` remains `BLOCKED` even after a correct
fork-parent read. This script cannot deploy rules, enable Actions, push or fork.

Recovery: inspect failing checks without changing user work; use another clean
isolated checkout for dirty or redirected repositories, and obtain missing
history through an explicitly authorized operation outside this read-only tool.
Record the unique target and authorized scope before remote initialization.
Compiler/SDK discovery is limited to tools available on PATH and configured SDK
directories; an absent tool is `NOT_RUN`, and build/runner validation remains a
separate E1 task. No toolchain is installed by this probe.
