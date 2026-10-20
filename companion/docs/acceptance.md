# Acceptance and release evidence

Current checkout: **0.1.2.dev0 local monorepo candidate / protocol 1.2**.
The Python project and MOD now live in CPH's `companion/` subtree and retain
their independent package and control lifecycle. Migration verification must
bind the resulting CPH source tree and the actual installed package. Imported
results below do not certify this changed source layout. No new release,
mainline merge or actual-user installation is implied.

The imported, pre-migration review-fix verification binds source `40d7c1442ad7`
/ package `0.1.2.dev0` to CPH `e01386a1eba1`, protocol `1.1`. See the
[exact evidence and hashes](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/71db54271124f072c330ef3da101c1480ef6aae8/companion/docs/evidence/review-fixes-20261001/verified.json).

| Pre-migration review-fix check | Outcome |
| --- | --- |
| Python source / installed wheel outside checkout | PASS, 149 tests each, Python 3.12.14 |
| Native focused regressions | PASS, 72 cases / 1,968 assertions |
| Installed wheel / native joint test | PASS, 1 case / 1,377 assertions; real ground pickup/AP/receipt, cognition checkpoint preparation and safe handoff |
| Adjacent mission checks | PASS, 3 cases / 63 assertions |
| Game build / actual installed MOD load | PASS, local Clang full game target and native MOD scanner |
| GNU regression / metadata / generators / style | PASS within their recorded scopes; GNU compiles the actual changed test translation unit, not the full game |
| Real provider / GUI / actual user saves / full official suite / hosted CI / publication | NOT_RUN; no new push, mainline merge or release |

That wheel and sdist were built from the frozen independent code commit before
its documentation-only evidence update. The external assembled compatibility
manifest records the tested wheel hash. Archive validation reads the real sdist
metadata and exact protocol/MOD payloads without extracting it; assembly does
not upgrade unrun acceptance. Historical 0.1.1 tables below remain historical.

This file describes required evidence. Actual outcomes belong in the dated
implementation evidence and the machine-readable compatibility record. Never
promote `NOT_RUN` to `PASS` solely because an implementation or test exists.

## Protocol 1.2 task candidate

The 2026-10-19 local implementation binds base CPH
`71db54271124f072c330ef3da101c1480ef6aae8` plus the uncommitted
`codex/companion-control-design` source snapshot to the final installed
`0.1.2.dev0` wheel identified in the dated implementation report. Protocol digest is
`93fffda84235f766229925dd9e77e56e6b5a2d6fc23d9d00b698f96ffdaf1b0e`;
wheel and sdist SHA256 identities are recorded with the actual build and
installed-package commands there. Artifacts precede the final documentation-only
evidence update; the 17 package files match source, wheel and installation.
Local review evidence remains outside the checkout and distributed packages in
the dated `companion-avatar-implementation-20261019/` evidence directory:
`implementation-report.md`, `native-verification-results.json`,
`native-input-manifest.json`, `python-verification-results.md`,
`docs-verification-results.md`, `provider-diagnostics-verification.md`,
`json-mode-verification-v6.md`, `task-prompt-verification-v7.md`, and
`deepseek-diagnosis/report.md`, plus `deepseek-followup-20261019/report.md`
for the separately authorized continuation. The final priority-mode repair,
v8 package and 2026-10-20 bounded acceptance are in
`mode-priority-20261020/report.md` and its Python/native result JSON files.
Historical imported PASS rows do not certify this implementation.

| Current local check | Outcome |
| --- | --- |
| Python source and installed wheel | PASS, final-v8 source/installed 202 tests each; 17 package files match source/wheel/installed bytes; init/doctor and old/new offline harness groups 5/7/9/11 pass |
| Native persistent tasks | PASS, 27 cases / 3,134 assertions; includes 520 real collection operations, save reconciliation, bounded retry, failure dependencies, prefetch identity/deduplication, priority/standing duties and visible-only progress |
| Old actor/NPC/selected MP regressions | PASS, 101 cases / 2,332 assertions |
| Installed wheel/native joint | PASS, v8 legacy steps 1 case / 1109 assertions and new tasks 1 case / 1188 assertions; exact binding/commands in the dated native report; real pickups, costs, memory receipts, checkpoint preparation and safe handoff |
| Three candidate scenarios in an isolated native world | PASS with synthetic offline fixtures, 1 case / 83 assertions; context/requirement IDs and fixture coordinates are rebound explicitly |
| Exact native inputs | PASS, 10,313 source/test/CMake/data inputs match; generated `prefix.h`/`version.h` excluded; native binary SHA256 `13219c708aeab2a612d3d3feb83952bd6ca9864b00b1a64014ab53d49f506daa` |
| DeepSeek compatibility | Priority semantics and bounded actionable feedback repaired in v8. New authorization used 3 of 4 calls, all chose prioritize; context mismatch and unknown-field replies were rejected, third change-goal candidate validates. Historical total 12 calls; no authentication/balance failure |
| Real-model candidate adoption | PASS in isolated replay: new change-goal 1 case / 31 assertions, then all three real candidates 1 case / 83 assertions. Gather/prefetch originated in v7, guard in v8; not three freshly generated v8 online cases, and not direct live GUI gameplay. No rejected/synthetic response substitutes for a real candidate |

Real tests use synthetic context only, thinking disabled, JSON mode, estimated
input bound 4,096 tokens, output limit 1,024, timeout 30 seconds and SDK retries
disabled. The original authorization allowed five inference attempts across
its first series of runs. A fixed durable ledger reserves each additional call before
sending; restarting or changing the result directory cannot renew the four
remaining attempts. Authentication or balance errors stop immediately. The
provider preserves only allowlisted diagnostics, never raw HTTP bodies or
messages. The original failed run remains historical in
`deepseek-online-v2/result.json`; later failures do not retroactively establish
its exact HTTP status. No model or endpoint substitution was made.

The user subsequently authorized a separate maximum of four additional model
requests. That grant has its own fixed durable ledger and execution lock,
with five previous attempts preserved and a combined cap of nine. Existing
gather bytes are revalidated against both recorded hashes and reused without
another model call. Corrections and authentication/balance halt state persist
across restart; fixed diagnostic codes/types also trigger the halt when the
HTTP status alone is ambiguous. The four added calls are exhausted; two
correction attempts did not produce the required `prioritize` mode. The
offline follow-up harness passes 9 tests; it does not turn rejected replies
into accepted game tasks.

On 2026-10-20 the user authorized a further maximum of four after offline
priority/feedback repair. A new fixed ledger preserves the prior nine and
caps the aggregate at thirteen; three requests were sufficient, leaving one
unused. No mode mismatch recurred. The explicit expected/actual-mode feedback
path passed offline; the live corrections were for context mismatch and an
unknown field, so the live run does not separately prove the new mode
correction path. These synthetic scenarios do not establish universal
natural-language intent compliance or direct live GUI gameplay.

| Area | Required scenario |
| --- | --- |
| Task protocol | Shared Python/native task fixtures; at most five tasks; unchanged old step dependencies; gather source coordinates all-or-none; duplicate/self dependencies rejected; durable references resolved natively |
| Local progress | Native follow/guard/move/gather/craft, real AP and inventory effects, acquired versus inventory quantity, bounded repair, blocked/dependent/independent tasks and no model critic for native completion |
| Delayed decisions | One in-flight request/one candidate, safe handoff, stale intent/configuration/dependency/resource rejection; model latency never advances game time or grants moves |
| Interruption | Conversation preserves existing work; accepted priority switches safely; danger reacts natively; cancel/stop revoke candidates and respect uninterruptible activities |
| Knowledge UI | Only `planning_state` and avatar-observed `player_progress` in normal UI; unseen progress remains unchanged; private queue/targets and insincere promises are not disclosed; self-report remains dialogue |
| Save and memory | Missing old task fields restore no speculative work; saved tasks and receipts resume idempotently; old requests/candidates discarded; world memory restored to confirmed checkpoint; background/preferences retained |
| Consumption and provider | Reserve calls/tokens before workers; failures/cancellation/restart/reload do not refund; explicit budget period renewal; optional thinking enabled/disabled/omitted forwarding; no real provider needed for these tests |

Windows native compilation, the Windows companion runtime, graphical review,
actual user saves, the complete native suite, dedicated hidden multi-process
MP acceptance, hosted CI and release are NOT_RUN. The current native evidence
uses Ubuntu 26.04.1/WSL2 with g++ 15.2, Lua enabled and a headless test target.
General transport/building/vehicle tasks remain outside this implementation.

| Area | Required scenario |
| --- | --- |
| Protocol | Shared valid/invalid fixtures; duplicate IDs, bounded messages, unknown fields, stale context, invalid dependencies |
| Runtime | Bounded calls and timeouts, explicit start, no import/scan/doctor model calls, stale memory rejection, one writer and explicit session |
| Memory | Manual edits win; deletion invalidates historical dependencies, checkpoint recovery and in-flight revisions; no audit relearning or cross-actor leak |
| Personality | All 15 permissions, parent/leaf precedence, real scene/effect for each, natural-language residual limitation recorded |
| Native actions | Real movement/AP, bandage crafting, gathering, combat, native NPC dialogue and inventories |
| Mission/reward | Antibiotics alternatives, deadline/failure/delivery, claimant ownership, stock-shortage balance and retry without duplicate payout |
| Lifecycle | Off-bubble pause, no offline work catch-up, disconnect continues accepted work, explicit detach respects native interruption |
| Recovery/removal | Successful save/checkpoint association; crashes between avatar, world, mission, map and native journal writes; prepared checkpoint or older queue never replays uncertain physical effects; NPC tasks/rewards remain usable after safe removal |
| Artifacts | Exact wheel/sdist/MOD resources, dependency hashes, checksums, fresh Python 3.12 install outside checkout and isolated user directory |
| Actual provider | Separately configured endpoint/credential/budget; real response and quality test, no paid CI call |

Offline Python tests use fakes and local loopback sockets. Package commands run
from `companion/`; their CI entry point belongs to the CPH-root
`.github/workflows/`. Package checks build the separate wheel/sdist/MOD artifacts
and run offline tests; they do not call a model, publish, modify game saves or
prove GUI/native gameplay acceptance. Native tests, real game scenarios,
GUI, real-provider work, hosted execution and actual release each require their
own command, platform, exact identity and result.

Package assembly defaults to an unvalidated candidate, also selected explicitly
by `--candidate-only`. Its output has empty `validated_combinations` and
`NOT_RUN` acceptance entries, regardless of historical source records. Retaining
separately tested results requires `--compatibility` with an explicit file whose
validated pairs all identify this exact built wheel hash. Mismatched identities
are rejected, and an empty pair list cannot carry PASS claims into the output.

## Historical 0.1.1 evidence

The historical candidate is an experimental prerelease. The recorded outcomes have bounded
scope; the compatibility manifest binds the release package to the tested native
commit `a04e657dc009cc5dceacec20eb1acdc23068f248` and the installed `0.1.1`
111-test wheel. Previous `0.1.0` evidence remains historical.

The revision fixes two internal native helpers rejected by the actual `0.1.0`
CPH Linux CI build's missing-declaration checks. The
[diagnosis and exact validation boundary](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/71db54271124f072c330ef3da101c1480ef6aae8/companion/docs/evidence/v0.1.1/gcc-helper-fix-20261001.md)
preserve that introduced failure; a local GNU module check does not convert it
into hosted success. Latest hosted CI and publication are recorded separately.

The first focused native execution failed 8 cases / 20 assertions. Its
[failure history and assertion excerpt](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/71db54271124f072c330ef3da101c1480ef6aae8/companion/docs/evidence/native-failure-history.json)
are retained alongside the passing rerun, including the observation fix and
fixture/JSON diagnostic corrections.

| Recorded check | Outcome and scope |
| --- | --- |
| Python source and installed package | **PASS**, 111 tests in each environment; installed non-editable wheel tested outside the source checkout |
| Installed MOD loading | **PASS**, actual nativea04 `--check-mods` for newly installed `0.1.1`; [revision report](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/71db54271124f072c330ef3da101c1480ef6aae8/companion/docs/evidence/v0.1.1/native-mod-load-v011-a04-20261001.json); original metadata failure remains historical |
| Focused native suite | **PASS**, 63 cases / 1,727 assertions from canonical engine objects and selected real test objects; [revision report and exact a04 identity mapping](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/71db54271124f072c330ef3da101c1480ef6aae8/companion/docs/evidence/v0.1.1/native-acceptance.json) |
| Multiplayer proxy exclusion | **PASS**, two native regression cases / 96 assertions after reproducing the prior gap; live multiplayer host/client session remains **NOT_RUN** |
| Native journal/recovery fixtures | **PASS** within that focused suite: rollback/commit, beforeimages, native writers, checkpoint markers and gameplay snapshot boundaries |
| Installed/native integration | **PASS**, nativea04 / installed `0.1.1`, one case / 1,538 assertions: real NPC ground-item gather, native action-point cost, receipt, local memory and safe handoff; [joint report](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/71db54271124f072c330ef3da101c1480ef6aae8/companion/docs/evidence/v0.1.1/native-installed-joint.json) |
| Full native game build | **PASS**, local Clang 21.1.8 nativea04 `cataclysm-tiles`; this is compilation, not GUI execution |
| GNU module diagnostics | **PASS**, GCC 15.3.0 checks `actor_control.cpp` with strict missing-declaration diagnostics; full GNU game and final hosted CPH result remain separate |
| Adjacent native regressions | **FAIL**, 15 of 17 cases pass; `crafting_with_a_companion` and `on_load-sane-values` fail three assertions; [raw log](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/71db54271124f072c330ef3da101c1480ef6aae8/companion/docs/evidence/native-adjacent-regressions.log) |
| Hosted independent-project CI | **PASS for historical `0.1.0` final commit `ce8b6a5`**, [run 36830812721](https://github.com/oncehere/cph-ai-companion/actions/runs/36830812721); `0.1.1` CI is recorded separately after its final commit |
| Full official native suite | **NOT_RUN**; the focused runner is not the full `cata_test-tiles` target |
| GUI, real provider and actual user environment | **NOT_RUN** |
| Complete physical crash campaign, graphical save/load, actual cross-dimension journey and death/replacement GUI | **NOT_RUN** |
| Other operating systems and publication | Recorded separately; not established by local package assembly |

The two adjacent failures also reproduce in a
[controlled base-source comparison](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/71db54271124f072c330ef3da101c1480ef6aae8/companion/docs/evidence/native-controlled-baseline.json):
only `npc.cpp` is replaced with the `06db38942be4` source, while the listed ABI,
test and helper inputs are identical. This supports the recorded inherited
behavior under those controlled inputs. It is not a complete baseline build,
does not turn the failures into passes, and does not prove that all regressions
have been excluded.

The joint scenario processes replies through the native input-wait path without
advancing game time or granting NPC/avatar action points before execution. It
uses the official SDK against synthetic loopback HTTP, with no paid call or
real-model quality claim. Native social fixtures exercise the 15 configurable
permissions and their effects; 15 personality scenes driven by a real model in
ordinary graphical play remain `NOT_RUN`. The
[15-behavior coverage matrix](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/71db54271124f072c330ef3da101c1480ef6aae8/companion/docs/evidence/personality-coverage.json) maps each
permission to its tested effects, defaults and limitations.

The gathering action is ground pickup, and the queued attack is melee. Broader
harvesting and model-directed ranged attacks are outside this candidate's
implemented catalog; native NPC fallback keeps its normal combat behavior.
