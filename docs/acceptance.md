# Acceptance and release evidence

Current checkout: **0.1.2.dev0 local review fixes / protocol 1.1**. New verification
is recorded separately in `docs/evidence/review-fixes-20261001/`; the historical
0.1.1 results below do not certify these changed sources. No new release or
mainline merge is implied.


Current review-fix verification binds source `df138cbbb24e` / package
`0.1.2.dev0` to CPH `e01386a1eba1`, protocol `1.1`. See the
[exact evidence and hashes](evidence/review-fixes-20261001/verified.json).

| New candidate check | Outcome |
| --- | --- |
| Python source / installed wheel outside checkout | PASS, 149 tests each, Python 3.12.14 |
| Native focused regressions | PASS, 72 cases / 1,968 assertions |
| Installed wheel / native joint test | PASS, 1 case / 1,377 assertions; real ground pickup/AP/receipt, cognition checkpoint preparation and safe handoff |
| Adjacent mission checks | PASS, 3 cases / 63 assertions |
| Game build / actual installed MOD load | PASS, local Clang full game target and native MOD scanner |
| GNU regression / metadata / generators / style | PASS within their recorded scopes; GNU compiles the actual changed test translation unit, not the full game |
| Real provider / GUI / actual user saves / full official suite / hosted CI / publication | NOT_RUN; no new push, mainline merge or release |

The wheel and sdist were built from the frozen code commit before this
documentation-only evidence update. The external assembled compatibility
manifest records the tested wheel hash. Archive validation reads the real sdist
metadata and exact protocol/MOD payloads without extracting it; assembly does
not upgrade unrun acceptance. Historical 0.1.1 tables below remain historical.

This file describes required evidence. Actual outcomes belong in the dated
implementation evidence and the machine-readable compatibility record. Never
promote `NOT_RUN` to `PASS` solely because an implementation or test exists.

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

Offline Python tests use fakes and local loopback sockets. The configured CI
workflow builds package artifacts and runs those tests; it does not call a model, publish, modify game
saves or prove GUI/native gameplay acceptance. Native tests, real game scenarios,
GUI, real-provider work, hosted execution and actual release each require their
own command, platform, exact identity and result.

## Historical 0.1.1 evidence

The historical candidate is an experimental prerelease. The recorded outcomes have bounded
scope; the compatibility manifest binds the release package to the tested native
commit `a04e657dc009cc5dceacec20eb1acdc23068f248` and the installed `0.1.1`
111-test wheel. Previous `0.1.0` evidence remains historical.

The revision fixes two internal native helpers rejected by the actual `0.1.0`
CPH Linux CI build's missing-declaration checks. The
[diagnosis and exact validation boundary](evidence/v0.1.1/gcc-helper-fix-20261001.md)
preserve that introduced failure; a local GNU module check does not convert it
into hosted success. Latest hosted CI and publication are recorded separately.

The first focused native execution failed 8 cases / 20 assertions. Its
[failure history and assertion excerpt](evidence/native-failure-history.json)
are retained alongside the passing rerun, including the observation fix and
fixture/JSON diagnostic corrections.

| Recorded check | Outcome and scope |
| --- | --- |
| Python source and installed package | **PASS**, 111 tests in each environment; installed non-editable wheel tested outside the source checkout |
| Installed MOD loading | **PASS**, actual nativea04 `--check-mods` for newly installed `0.1.1`; [revision report](evidence/v0.1.1/native-mod-load-v011-a04-20261001.json); original metadata failure remains historical |
| Focused native suite | **PASS**, 63 cases / 1,727 assertions from canonical engine objects and selected real test objects; [revision report and exact a04 identity mapping](evidence/v0.1.1/native-acceptance.json) |
| Multiplayer proxy exclusion | **PASS**, two native regression cases / 96 assertions after reproducing the prior gap; live multiplayer host/client session remains **NOT_RUN** |
| Native journal/recovery fixtures | **PASS** within that focused suite: rollback/commit, beforeimages, native writers, checkpoint markers and gameplay snapshot boundaries |
| Installed/native integration | **PASS**, nativea04 / installed `0.1.1`, one case / 1,538 assertions: real NPC ground-item gather, native action-point cost, receipt, local memory and safe handoff; [joint report](evidence/v0.1.1/native-installed-joint.json) |
| Full native game build | **PASS**, local Clang 21.1.8 nativea04 `cataclysm-tiles`; this is compilation, not GUI execution |
| GNU module diagnostics | **PASS**, GCC 15.3.0 checks `actor_control.cpp` with strict missing-declaration diagnostics; full GNU game and final hosted CPH result remain separate |
| Adjacent native regressions | **FAIL**, 15 of 17 cases pass; `crafting_with_a_companion` and `on_load-sane-values` fail three assertions; [raw log](evidence/native-adjacent-regressions.log) |
| Hosted independent-project CI | **PASS for historical `0.1.0` final commit `ce8b6a5`**, [run 36830812721](https://github.com/oncehere/cph-ai-companion/actions/runs/36830812721); `0.1.1` CI is recorded separately after its final commit |
| Full official native suite | **NOT_RUN**; the focused runner is not the full `cata_test-tiles` target |
| GUI, real provider and actual user environment | **NOT_RUN** |
| Complete physical crash campaign, graphical save/load, actual cross-dimension journey and death/replacement GUI | **NOT_RUN** |
| Other operating systems and publication | Recorded separately; not established by local package assembly |

The two adjacent failures also reproduce in a
[controlled base-source comparison](evidence/native-controlled-baseline.json):
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
[15-behavior coverage matrix](evidence/personality-coverage.json) maps each
permission to its tested effects, defaults and limitations.

The gathering action is ground pickup, and the queued attack is melee. Broader
harvesting and model-directed ranged attacks are outside this candidate's
implemented catalog; native NPC fallback keeps its normal combat behavior.
