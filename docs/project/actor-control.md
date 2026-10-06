<!-- CPH-DOC: cph.actor-control -->
# Actor control

ActorControl is a native CPH service for one explicitly bound, recruited NPC.
It preserves that entity's identity, items, skills, physiological state and
native costs. Death does not select a replacement. Player control is reserved
for a future adapter and is not implemented.

Multiplayer player proxies are excluded using the existing live partner identity
and persistent `mp_proxy` marker. A restored binding to a proxy cannot observe,
plan or execute actions. Stopping such a binding clears only controller state;
it does not cancel the proxy's native activity or change its entity values.

The separately distributed `cph-ai-companion` is maintained under
[`companion/`](../../companion/README.md) and contains the Python 3.12 runtime,
file memory and Lua companion Mod. CPH contains the authoritative control,
activity and save integration. The original independent code retains its
Apache-2.0 license; native CPH changes retain the repository's license.
Multiplayer and companion control remain separate workflows.

The single protocol authority is
[`companion/src/cph_ai_companion/resources/protocol/`](../../companion/src/cph_ai_companion/resources/protocol/).
`python3 tools/actor_control/generate_protocol.py` embeds its `protocol.json`
and shared `fixtures.json` into `src/actor_control_protocol_generated.h`.
The header records both source paths and the SHA-256 of each input's exact
bytes, without tying generation to a changing Git HEAD. Valid uncommitted
protocol edits can be generated locally; `--check` checks both inputs without
writing. The Python package ships those same resources. Retired copies under
`data/reference/actor_control/` are no longer consumed or distributed.

## Public entry points

Lua uses only `require("ccb").services.actor_control`: `enable`, `bind`, `chat`,
`status`, `pause`, `cancel` and `stop`. Writes require a writable callback and
binding requires a current typed NPC handle. Returned tables are detached
snapshots. Native execution and save/load hooks are not Lua tools. Definitions
and native inventory are generated through the existing Lua contract workflow.

The recruited companion's normal chat menu contains **AI companion control**.
Use it to bind a profile, exchange messages, pause/cancel, safely stop or inspect
status. Reconnection requires the same bound entity/profile. Debug information
is available only when explicitly configured. NPC task/reward management remains
available in the native chat menu after stopping AI or removing its Mod.

The native service uses existing Asio infrastructure, a random loopback port,
one authenticated client, private session files and a one MiB NDJSON message
limit. Descriptor paths are reported by `status`; user/config/save paths are
absolute. Python must select the descriptor explicitly. Credentials live in a
separate private file; model keys are never read by the game. The first supported
runtime platform is Linux x86_64.

External methods cover handshake, capabilities, status, configure, memory sync,
decision request, candidate submission, receipt queries, checkpoints,
cancellation, safe stop and removal checks. They do not set items, attributes,
the game clock, task completion or another character's consent. Protocol 1.1's
schemas and shared valid/invalid samples are the executable contract.

## Native execution and knowledge

Emergency reactions and current native activities precede queued actions;
otherwise accepted steps run before normal NPC logic. Polling communication,
including while waiting for player input, grants no action points and advances
no game time. Actual execution uses the NPC's existing turn budget.

Current actions cover movement, picking up perceived ground items, native
crafting, queued melee attacks, spoken dialogue, native NPC enquiries, real
inventory trading and NPC-assigned antibiotic tasks. This first adapter does
not implement general harvesting/tree cutting or a model-directed ranged
combat controller; ordinary NPC combat remains responsible for native fallback.
Craft progress belongs to the real craft activity. The initial craft test uses
bandages; the task test uses `MISSION_GET_ANTIBIOTICS`, its actual three medicine
alternatives and deadlines.

Observations are bounded and originate from the companion's real sight/hearing
and known exchanges. Another NPC's stock or mission offer appears only after a
legitimate enquiry. Statements and beliefs remain typed information, not facts.
Player trades require the player's native confirmation. NPC tasks have a
separate claimant; rewards retain original issuer, balance and deduplication
receipts without charging player debt or moving tasks to the player's list.

Plans have stable step IDs and request identities. The engine validates scope,
load epoch, configuration/memory versions, perceived targets, native permission
and resources. Time progression alone does not invalidate a plan. Accepted
duplicates return existing receipts. Later steps execute only after successful
dependencies and refer to real native inventory/results; text never grants
objects, consent or rewards. Speech occupies the same bounded queue budget.
Player chat exposes a stable requirement ID. Work answering that request carries
`step.requirement_id`; an explicit refusal persists a decision for the same ID.
The controller rejects contradictory work and later plans that revive it. A
new player request can receive a new identity; unstructured prose alone does not
invent or override a native decision. A completed craft keeps its success and
outputs when cancellation arrives before the next queue reconciliation.

Trading checks both its declared intent and actual beneficiary before items move,
including after player confirmation. Shared native inventory-transfer code
handles selection and capacity for ordinary NPC missions and the adapter;
mission reward ownership remains independent of AI control.

The 15 independently configurable social intents have native gates and debug
records. Natural speech uses explicit intention checks and bounded text
validation; these checks cannot guarantee that arbitrary generated prose is
truthful or non-provocative. Goals and beliefs guide cognition separately from
actual faction, team, hostility and ownership changes. Bounded learned caution
can adjust ordinary following distance; it cannot bypass explicit NPC orders.

Lua-authored mission names retain their translation descriptors through the
native `mission_type::set_platform_name(translation)` overload. This changes
name presentation, not mission claimants, rewards or companion permissions;
the string overload still represents untranslated text.

Native activities carry a process-local instance identity. Copying, replacing
or cancelling an activity changes that identity, even when its activity type
ID stays the same. Lua and native activity dispatch check both the character's
live reference and the dispatched activity instance before continuing or
applying returned fields. A callback that destroys the character or replaces
its activity cannot leave the old dispatch writing into the replacement. This
identity is not serialized and is not an ActorControl request or receipt ID;
the controller's existing binding, queue and native permission checks remain
separate requirements.

## Persistence and handoff

Native extension format 1 stores the binding, queue, receipts, knowledge snapshot
and memory checkpoint association. Request epochs change on load. A successful
game save writes a commit marker; a missing/mismatched marker freezes uncertain
work for reconciliation. External memory being offline never prevents a game
save. Event IDs/watermarks and retained checkpoint deltas permit replay into
file memory without repeating physical effects.

For a bound companion, Linux saves use a lazy before-image transaction in the
private `.cph-actor-save` world directory. A file's original bytes, size and
CRC32 are durably recorded before native replacement, writable mapping,
renaming or removal. NPC inventories, maps, missions, character data and the
memory association commit as one generation. Loading recovers a pending
generation before reading native world state. A damaged backup, unknown format,
unsafe path or conflicting world writer stops recovery and preserves evidence.
The transaction's limits (16,384 files, one GiB per file and 16 GiB in total)
fail before the next mutation rather than skipping protection. The journal is
never copied into gameplay snapshots. Cross-dimension transfers retain the
same world transaction until the destination's complete native save succeeds;
death separates character files from archived map-memory directories so the
physical save and character removal remain together.

Communication checkpoints are prepared before durable native commit and
promoted only afterwards. A failed commit retains events for reconciliation;
it does not confirm an external memory checkpoint. Other saves and readers
acquire the same world lease without creating before-images. Recovery and
fsync behaviour require the supported Linux filesystem; other platforms do
not acquire companion control support by compiling the interface.

Outside the reality bubble, activities pause; returning does not manufacture
offline action points. Accidental disconnect allows already accepted work to
finish and then falls back to native behaviour, with stale cognition marked.
Explicit stop cancels unstarted steps and returns the current activity safely;
non-interruptible work reports `detach_pending`. Unsupported future formats are
retained verbatim and external takeover stops.

Removal checks require native detachment and removal of the world's Mod
dependency, while preserving native task/reward state. Python installation
manifests limit filesystem deletion to the Mod files installed by this project;
profiles, memory and saves remain.

## Verification

Focused tests use `[actor_control]` for the controller, native adapter, bridge,
protocol fixtures, Lua surface, native writer hooks, crash recovery and snapshot
exclusion. The Linux-only hidden test
`[.actor_control_joint]` requires `CPH_COMPANION_PYTHON` pointing to an installed
Python 3.12 package. Run from the repository root to use
`companion/tools/joint_driver.py`, or set `CPH_COMPANION_JOINT_DRIVER` explicitly
when running elsewhere. The package under test remains an installed wheel,
not an implicit source import.
It runs the real SDK against a synthetic loopback endpoint, verifies a real NPC
pickup and journaled receipt, and confirms safe stop with isolated directories.
It makes no paid provider calls. Its pre-execution phase asserts that polling
does not change calendar time or player/NPC moves. It feeds recorded, unbound
characters through a dedicated native `input_context` to exercise the actual
input/communication path without a GUI backend or a gameplay action. This
input replay does not establish graphical acceptance.

Only combinations listed by the independent project's compatibility manifest
are jointly validated. Compilation, unit tests, the synthetic model joint test,
graphical play, save recovery, real model behaviour, hosted CI and publication
are separate evidence categories. No declaration or local mock test establishes
all of those categories.
