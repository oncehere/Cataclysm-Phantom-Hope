# Acceptance and release evidence

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

Native operation journal and multi-file save/crash scenarios are currently
`NOT_RUN`. Python memory, provider and package tests do not establish those
native recovery results. Final compatibility records must bind the actual
tested CPH commit and built package before claiming a jointly supported pair.
