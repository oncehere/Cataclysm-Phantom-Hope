# Compatibility record

The experimental prerelease candidate is package `0.1.1`, Python `>=3.12,<3.13`, Linux x86_64,
OpenAI SDK `3.22.1`, wire protocol `1.0`, and schema version `1` for profile,
memory, checkpoint and native extension state.

`compatibility.json` is the machine-readable release record. Its
`validated_combinations` list contains only package/native combinations backed
by joint acceptance evidence. A candidate based on an adapted tree is recorded
separately under `candidate`; base HEAD alone is not a validated native revision.
The revised native candidate is
`a04e657dc009cc5dceacec20eb1acdc23068f248`, paired with the `0.1.1` wheel whose
SHA-256 begins `44c4082d6290`. The new installed wheel passed its actual joint
scenario and MOD scanner in the native Clang 21.1.8 build. A separate GCC 15.3.0
module syntax/diagnostic check passed; a full GCC game build is not claimed.
The previous `0.1.0` combination and assets remain historical in
[the prior manifest](evidence/v0.1.0-compatibility.json); they do not certify this
revision. Package assembly preserves the exact digests, tested scope and unrun
boundaries in `compatibility.json` and does not infer broader acceptance.
The adapted CPH source is reviewed separately in
[draft PR #25](https://github.com/oncehere/Cataclysm-Phantom-Hope/pull/25);
its ordinary mainline and the user's installed game are separate from this
tested source-build combination.

Handshake checks protocol version and exact protocol digest. CPH consumes a fixed
snapshot exported from this project's resources. A matching version string is
insufficient when the digest differs. Future native changes need joint tests
before addition to the validated list.

The Python platform tag describes packaging, not tested operating-system support.
Windows, macOS, Android and real-provider quality remain unclaimed unless
separately recorded. Import/diagnostic success does not establish game action,
save recovery or removal acceptance. The focused native runner is not the full
official test target; the two adjacent failures and their controlled source
comparison remain visible in the [acceptance report](acceptance.md).

Compatibility and acceptance fields are a snapshot as of package assembly.
The recorded implementation-commit CI result does not certify later source or
documentation commits. Final hosted CI, publication status and asset digests
belong to the corresponding GitHub run/release metadata and dated outer report;
assembly does not rewrite these fields to imply publication or complete testing.
