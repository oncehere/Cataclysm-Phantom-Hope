# Compatibility record

The local review-fix candidate is package `0.1.2.dev0`, Python `>=3.12,<3.13`,
Linux x86_64, OpenAI SDK `3.22.1`, and wire protocol `1.1`. It is not published.
Configuration, memory, checkpoint and native extension formats remain separately versioned.

`compatibility.json` records the current tested inputs and actual scope. Changed
sources do not inherit historical PASS results. The published 0.1.1 combination
is preserved in [its historical manifest](evidence/v0.1.1-compatibility.json);
0.1.0 evidence and assets also remain unchanged. The native source is developed
in the isolated actor-control branch associated with
[draft PR #25](https://github.com/oncehere/Cataclysm-Phantom-Hope/pull/25), separately
from ordinary mainline and the installed game.

Handshake requires both protocol version and exact schema digest. Protocol 1.1
adds explicit player requirement identities and persisted rejection decisions.
Old protocol 1.0 clients and native builds are rejected before control; a
matching version alone is insufficient. CPH builds consume a fixed exported
snapshot with source revision and hashes, without fetching a moving contract.

Only combinations backed by fresh joint tests enter `validated_combinations`.
Compiler checks, focused native tests, installed-package integration, GUI,
real-provider quality, full official native suite, hosted CI, publication and
actual-user save/runtime tests are separate results. Windows, macOS and Android
support is not inferred from the portable Python wheel tag. Package assembly
preserves this manifest rather than upgrading unrun checks to PASS.

The freshly verified local pair is standalone code `df138cbbb24e` and CPH
`e01386a1eba1`, with 149 source and installed Python tests, 72 focused native
cases, a final installed/native checkpoint/gather/handoff case and actual MOD
loading. Exact artifact and binary hashes are recorded in
[the dated evidence](evidence/review-fixes-20261001/verified.json). The later
documentation-only commit does not replace the frozen package code identity.
