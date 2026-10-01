# Compatibility record

The local monorepo candidate is package `0.1.2.dev0`, Python `>=3.12,<3.13`,
Linux x86_64, OpenAI SDK `3.22.1`, and wire protocol `1.1`. It is not published.
Configuration, memory, checkpoint and native extension formats remain separately versioned.

`compatibility.json` records tested inputs and their actual scope. Changed
sources do not inherit historical PASS results. The published 0.1.1 combination
is preserved in [its historical manifest](evidence/v0.1.1-compatibility.json);
0.1.0 evidence and assets also remain unchanged. Source development now places
the Python project and MOD in CPH's `companion/` subtree alongside native control
code. The package and game remain separately built and distributed. The local
source migration does not imply mainline integration, publication or a change
to the installed game. The
[original 0.1.1 release](https://github.com/oncehere/cph-ai-companion/releases/tag/v0.1.1)
and original independent repository are preserved.

Handshake requires both protocol version and exact schema digest. Protocol 1.1
adds explicit player requirement identities and persisted rejection decisions.
Old protocol 1.0 clients and native builds are rejected before control; a
matching version alone is insufficient. Python resources under
`companion/src/cph_ai_companion/resources/protocol/` are the single source for
both runtimes. The native generator consumes that source directly, embeds the
contract and shared test fixtures, and checks the generated header. No protocol
export or second maintained snapshot is required.

Only combinations backed by fresh joint tests enter `validated_combinations`.
Compiler checks, focused native tests, installed-package integration, GUI,
real-provider quality, full official native suite, hosted CI, publication and
actual-user save/runtime tests are separate results. Windows, macOS and Android
support is not inferred from the portable Python wheel tag. Default package
assembly and `--candidate-only` emit a fresh unvalidated candidate manifest with
empty `validated_combinations` and `NOT_RUN` acceptance, rather than copying this
source record's historical PASS results. To retain separately tested evidence,
select its file explicitly with `--compatibility`. Every supported combination
must name the exact built wheel hash; missing or mismatched identities reject
assembly. An explicit file with no supported pairs also produces an unvalidated
candidate. Assembly never upgrades unrun checks to PASS.

The imported, pre-migration review-fix pair is standalone code `40d7c1442ad7`
and CPH `e01386a1eba1`, with 149 source and installed Python tests, 72 focused native
cases, a final installed/native checkpoint/gather/handoff case and actual MOD
loading. Exact artifact and binary hashes are recorded in
[the dated evidence](evidence/review-fixes-20261001/verified.json). The later
documentation-only commit does not replace the frozen package code identity.
Those results remain attached to that pair. The monorepo candidate requires
its own package/native verification and recorded source and artifact identities;
moving the source does not add a validated combination.
