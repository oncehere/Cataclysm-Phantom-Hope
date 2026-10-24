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

`cph-ai-companion` is maintained under
[`companion/`](../../companion/README.md) and contains the Python 3.12 runtime,
file memory and Lua companion Mod. Windows delivery includes an optional built-in
Mod and a matching Python/SDK bundle; players enable the Mod and explicitly start
AI from the game menu. The wheel remains an independently testable build input.
Canonical Mod source stays in the package resources and is copied from the exact
wheel during game staging. CPH contains the authoritative control,
activity and save integration. The original independent code retains its
Apache-2.0 license; native CPH changes retain the repository's license.
Multiplayer and companion control remain separate workflows.

The single protocol authority is
[`companion/src/cph_ai_companion/resources/protocol/`](../../companion/src/cph_ai_companion/resources/protocol/).
`python3 tools/actor_control/generate_protocol.py` embeds its `protocol.json`,
shared plan `fixtures.json` and task `task_fixtures.json` into
`src/actor_control_protocol_generated.h`.
The header records all source paths and the SHA-256 of each input's exact
bytes, without tying generation to a changing Git HEAD. Valid uncommitted
protocol edits can be generated locally; `--check` checks all inputs without
writing. The Python package ships those same resources. Retired copies under
`data/reference/actor_control/` are no longer consumed or distributed.

## Public entry points

Lua uses only `require("ccb").services.actor_control`: `enable`, `bind`, `chat`,
`status`, `pause`, `cancel` and `stop`. Writes require a writable callback and
binding requires a current typed NPC handle. Returned tables are detached
snapshots. Native execution and save/load hooks are not Lua tools. Definitions
and native inventory are generated through the existing Lua contract workflow.

The recruited companion's normal chat menu contains **AI companion control**.
Use it to bind the companion, configure endpoint/model, a masked session API key,
background and scoped daily duties, explicitly start AI, exchange messages,
pause/cancel, withdraw a specific player request, safely stop or inspect status. The game launches the bundled runtime
without a console and owns its child process; players need no Python installation,
session identifier or shell command. Reconnection requires the same bound entity/profile. Debug information
is available only when explicitly configured. The ordinary menu shows connection
and response/handoff status, the companion's own statements, and native progress
previously visible to the avatar. It does not reveal the actual private task
queue, hidden goals or whether a spoken promise was sincere. An unseen result
leaves the last known progress unchanged; no observation is shown as unknown.
Binding and stopping use this same player view. Full controller state remains
in the explicitly enabled diagnostic view. NPC task/reward management remains
available in the native chat menu after stopping AI or removing its Mod.

The native service uses existing Asio infrastructure, a random loopback port,
one authenticated client, private session files and a one MiB NDJSON message
limit. Descriptor paths are reported by `status`; user/config/save paths are
absolute. The game-owned launcher selects the current descriptor; the developer
CLI still requires an explicit selection. Bridge authentication credentials live
in a separate private file. The model API key entered in the game stays in process
memory and is passed only through the child's environment, never configuration,
saves, command arguments or logs. Windows x86_64 is the current built-in delivery
target; the Linux developer runtime remains separate. Matching artifacts and
platform-specific evidence are required for either path.

External methods cover handshake, capabilities, status, configure, memory sync,
decision request, candidate submission, receipt queries, checkpoints,
cancellation, safe stop and removal checks. They do not set items, attributes,
the game clock, task completion or another character's consent. Protocol 1.2's
schemas and shared valid/invalid samples are the executable contract.

The authenticated coordinator may attach a schema-checked `planning_report` to
the existing `status` query. Both its `decision_id` and exact `request_id` must match
the current request; expired reports and unknown fields are rejected. Only
fixed public states and reasons are accepted: `thinking` means an active model
worker, `pending` means no worker is running, `failed` ends an unsuccessful
episode, and `suspended` explains an exhausted spending limit. These reports are
transient and are cleared on request invalidation, disconnect, disable or load;
they are not saved and do not trigger decisions or change tasks, permissions or
budgets. See [public planning states](../../companion/docs/architecture.md#player-knowledge-and-diagnostic-state)
for the ordinary UI projection. Empty `status` parameters remain valid.

## Persistent task contract

The current implementation candidate adds `offer_tasks` alongside the unchanged
short-action `offer_plan`. It accepts up to five `follow`, `guard`, `move`,
`gather` or `craft` tasks with stable IDs, optional player requirement links,
dependencies and a distance bound. Follow and guard take empty arguments; guard
captures the actor position in the planning observation. Move and craft reuse their action
arguments. Gathering requires an item type and count and can search several
perceived, permitted sources; optional absolute coordinates must appear together
and restrict collection to that exact tile.
Its default `acquired` quantity counts results produced during that task;
`inventory` instead names the actor's target inventory stock. `max_distance`
defaults to 12 tiles from the planning observation's task anchor and is bounded
to 1–60. Delayed admission does not move that permission area with the actor.

Native task state owns progress, dependencies and the short queue it replenishes.
Accepted work appends by default. An explicitly accepted `prioritize` offer
switches at a safe native boundary while retaining valid interrupted work.
New conversation alone does not cancel accepted work. Actual refusal remains
attached to its requirement identity. Automatic work must remain within the
configured `duties.allowed_tasks`; the default empty list grants no additional
autonomous task kinds. Autonomous gather/craft additionally require their item
type/recipe in `duties.item_types`/`duties.recipes`, with distance limited by
`duties.max_distance` (default 12). Empty resource lists grant no permission.
Saving daily duties in the game updates the same native policy used by worker
configuration immediately, including while the worker is disconnected. Only
autonomous work uses these duty limits; an explicit player commission retains
its own authorization. A failed save or a different profile/entity cannot change
the bound actor's policy.
Tasks are finite in kind and resource scope; follow/guard
can remain active until changed or cancelled.

**Withdraw one of your requests** lists the player's recorded requests without
revealing whether the companion actually accepted, refused or falsely promised
them. Withdrawal prevents new steps for that requirement, retires only its live
tasks and ends owned activities at a safe boundary. Unrelated work, private goals
and completed effects remain intact. Replace a commission by withdrawing the
old request and issuing the new one; `prioritize` alone deliberately preserves
the old task for resumption. The internal withdrawal marker is saved with the
requirement; older saves without it default to not withdrawn. It is not a new
model or external RPC operation. Global cancel and safe stop remain available.

Only one planning request and one unaccepted candidate may be active. The native
request includes a task catalog and summary for planning. A candidate produces no
physical effects before native admission, and is checked again against the
current request generation, permissions, task dependencies and resources.
Necessary decisions with enough information can be requested before the current
work ends. A task announces its prefetch boundary once with a fresh decision
identity; the announcement survives saves, and an empty candidate does not make
every subsequent step request the model again. Routine progress does not itself
require another model call. Idle duties can wake on newly perceived choices even
when completed task history is retained. Task
completion comes from native results, not a separate model critic.
During model planning and pending native admission, ordinary receipts stay in
native storage until the next coordinator collection point, preserving the
candidate's cognition projection. A checkpoint collects those receipts before
writing memory. External memory/configuration edits and world, load, decision or
permission changes still invalidate the reply; native admission still rechecks
the actual resources and task dependencies.

Tasks that cannot progress keep their goal as blocked after bounded local retry;
an unchanged obstruction does not cause repeated attempts or model calls. A
permanently failed or cancelled predecessor fails its dependent tasks while
independent work continues. A
failed provider request is distinct from a failed game task. Valid local work
and native NPC behavior continue during model delay or disconnection, subject
to normal danger, simulation and move-budget rules. The game does not pause for
the model. Neither polling nor wall-clock cooldown grants moves.

An interrupted native craft is blocked for reconciliation: its in-progress item
already contains spent ingredients, so an inventory change cannot start a second
craft automatically. Active dependency receipts survive the recent-512 history
window. At 4096 retained receipts, new physical operations block until evidence
can safely retire; evidence is not silently evicted. At most 128 task records
are retained, with terminal records retired only when no live or proposed task
depends on them. Both dependency graphs and available capacity are checked before
the candidate RPC succeeds and again before adoption. Task definitions are
immutable; changed goals require a new task identity and old candidates are
invalidated by cancellation, configuration/memory changes or loading a world.

The accepted design and its remaining verification scope are documented in
[the companion design](companion-avatar-design.md). Source, focused native
tests and the exact installed wheel/native pair determine acceptance; this
contract does not declare graphical or real-provider validation.

## Native execution and knowledge

Mounted movement continues through the NPC's native movement and turn budget.
The player's active-technique menu does not add an ActorControl command or change
the control protocol. New native riding rules therefore remain subject to the
same ownership and scheduling checks as other NPC actions.

Emergency reactions and current native activities precede queued actions;
otherwise accepted steps run before normal NPC logic. Polling communication,
including while waiting for player input, grants no action points and advances
no game time. Actual execution uses the NPC's existing turn budget.

Current actions cover movement, picking up perceived ground items, native
crafting, queued melee attacks, checked known-ability casting, spoken dialogue,
native NPC enquiries, real inventory trading and NPC-assigned antibiotic tasks.
This first adapter does not implement general harvesting/tree cutting or a
model-directed ranged weapon combat controller; ordinary NPC combat remains
responsible for native fallback.
Craft progress belongs to the real craft activity. The initial craft test uses
bandages; the task test uses `MISSION_GET_ANTIBIOTICS`, its actual three medicine
alternatives and deadlines.

### Known abilities and checked casting

`observations.actor.abilities` contains at most 64 actually known spells, with
`ability_count` and `abilities_truncated` identifying truncation. Entries expose
`id`, `name`, `level`, `effect`, `supported`, a fixed-code `reason`, `energy_source`,
`energy_cost`, `casting_time_moves`, `range`, `targets`, `failure_chance` and
`castable`. The same actor observation includes current `mana`/`mana_max`,
`stamina`/`stamina_max`. Availability is a snapshot,
not permission to affect a particular target or proof of success.

The short action `cast_spell` requires exactly `{spell, x, y, z}`. Coordinates
are absolute map squares, including for a self-target; they are not reality-bubble
offsets. Native execution requires a known, supported spell and a currently
perceived creature, then checks range, line of sight/projectile obstruction,
actual effect area, target identity, permissions and resources again before
completion. Harmful player/ally targets require their existing social permissions;
self-harm is refused. Spell work answers player requirements under the same
refusal, false-promise and withdrawal gates as other real work. It starts the
native casting activity and retains real time, energy, failure and receipt
semantics; accepted duplicates and restored completed effects do not cast again.

Initial support is deliberately limited to pure single-target `attack` and
self-target `recover_energy` for MANA, STAMINA, SLEEPINESS, PAIN or HEALTH.
STAMINA costs and recovery require a character using finite native stamina.
Blood/HP costs, vitamin costs, components, extra effects/EOC chains, failure
callbacks (including damage-type EOC/Lua hooks), channeling, unsupported flags/status effects and area/field/multiple
projectile effects fail closed with stable reason codes such as
`interactive_energy_source`, `npc_unsupported_components`,
`npc_unsupported_effect_chain` and `npc_unsupported_area_effect`. Interactive
and avatar-only effect kinds are not admitted. This includes many common
Magiclysm spells with setup chains; it does not establish full support for
Magiclysm, Mind Over Matter or Xedra Evolved. Learning and sustained-ability
control remain outside this change.

Binding enables the saved character value `cph_ai.real_stamina`; it survives
disconnect, stop and rebind. Existing bound saves migrate on NPC load or the next
native control boundary. Enabling only clamps the stored value to its valid
range; it does not refill it. `Character::uses_stamina()` shares the existing
player/remote-player formulas and native stamina/cardio save fields. Successful
unmounted movement spends stamina from actual movement points, and body updates
recover once per elapsed game turn. Safe NPCs below one quarter stamina pause
between activities using only their existing moves; queued work resumes after
recovery. Urgent native reactions precede rest. Ordinary NPCs keep their existing
rule, while MP proxies keep network-owned debits and recovery.

Actual casting uses the same explicit-caster preparation as native avatar/NPC
casting. Ability queries remain read-only. Loaded `opens_spellbook` EOC or Lua
callbacks return `npc_unsupported_spellbook_event`: they are gameplay prerequisites
which this interface cannot safely skip or authorize as arbitrary scripts. This
also blocks otherwise pure helpers when such Mod-wide hooks are loaded. The
change does not implement NPC calorie costs, sleep or cardio training, general
EOC execution, or full compatibility with the three Mods.

Ability queries use the existing observation, without
another RPC, worker or model call. Python adds spell-specific instructions only
when the advertised action catalog makes casting available; unsupported effects
must not be retried through guessed IDs or Lua/EOC. Existing protocol-digest,
save/checkpoint and provider-budget protections remain in force.

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
`step.requirement_id` or `task.requirement_id`; an explicit refusal persists a decision for the same ID.
The controller rejects contradictory work and later plans that revive it. A
new player request can receive a new identity; unstructured prose alone does not
invent or override a native decision. A completed craft keeps its success and
outputs when cancellation arrives before the next queue reconciliation.

Trading checks both its declared intent and actual beneficiary before items move,
including after player confirmation. Shared native inventory-transfer code
handles selection and capacity for ordinary NPC missions and the adapter;
mission reward ownership remains independent of AI control.

Ordinary gathering, native inventory exchanges and mission rewards leave
reserved crafting providers and live passive crafts in place. Planning and
execution use the same reservation rule; releasing a claim makes its stock
available again. Explicit misappropriation remains a separate social intent.

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

Native extension format 1 stores the binding, task state, queue, receipts,
player-visible progress, knowledge snapshot and memory checkpoint association.
Older format-1 saves without task fields restore no speculative work. Request
epochs change on load; in-flight model output and unaccepted candidates do not
resume. Accepted tasks recheck their real actor, target, resources and activity
ownership before continuing, without repeating a recorded physical effect.
A successful
game save writes a commit marker; a missing/mismatched marker freezes uncertain
work for reconciliation. External memory being offline never prevents a game
save. Event IDs/watermarks and retained checkpoint deltas permit replay into
file memory without repeating physical effects.

For a bound companion, Windows and Linux saves use a lazy before-image transaction in the
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

Ordinary dimension travel without a capturing companion transaction uses a
pre-travel rollback marker until a complete checkpoint succeeds. Loading
recovers the ActorControl journal before inspecting that marker, under the
same world lease. If a later companion checkpoint removes the marker, that
removal joins its journal so a failed commit preserves recovery and retry.

Communication checkpoints are prepared before durable native commit and
promoted only afterwards. A failed commit retains events for reconciliation;
it does not confirm an external memory checkpoint. Other saves and readers
acquire the same world lease without creating before-images. Linux uses its
filesystem sync and lock operations. Windows uses owner/SYSTEM-only private ACLs,
process-held file locks, flushed files and write-through replacement; it does not
claim POSIX directory `fsync`. Both paths reject unsafe file aliases and links.
Compiling the interface alone does not establish platform crash-recovery acceptance.

Outside the reality bubble, activities pause; returning does not manufacture
offline action points. Accidental disconnect allows already accepted work to
finish and then falls back to native behaviour, with stale cognition marked.
Explicit stop cancels unstarted steps and returns the current activity safely;
non-interruptible work reports `detach_pending`. Unsupported future formats are
retained verbatim and external takeover stops.

World-specific memories, growth, commitments and task progress follow the game's
confirmed save association. Reloading does not import future memories as facts.
The user-controlled background and explicit personality preferences remain
separate. Provider consumption counters are private runtime metadata outside
game and cognition checkpoints, so reloading or restarting cannot refund calls.
See [the Python architecture](../../companion/docs/architecture.md) for budgets,
memory precedence and provider settings.

Removal checks require native detachment and removal of the world's Mod
dependency, while preserving native task/reward state. Stopping or disabling the
built-in Mod preserves profiles, memory and saves. For standalone CLI-installed
Mod files, the installation manifest limits removal to files it actually installed.

## Verification

Focused tests use `[actor_control]` for the controller, native adapter, bridge,
protocol fixtures, Lua surface, native writer hooks, crash recovery and snapshot
exclusion. The Windows/Linux hidden test
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

On Windows, `[.actor_control_managed_runtime]` uses `CPH_COMPANION_GAME_STAGE`
to select a matching staged game root. It starts that bundle's actual interpreter
through the production game launcher, uses the same joint driver's local fake
HTTP endpoint, and checks connection, real pickup, persisted native operation
receipt and normal process exit after safe stop. It does not exercise the GUI.
The ordinary joint test also supports `CPH_COMPANION_JOINT_TASKS=1` to cover task
offers while retaining its default short-plan coverage.

Independent content and story preparation uses
[`tools/scenarios/`](../../tools/scenarios/README.md): prepare an isolated run,
check Mod loading, launch, record actual outcomes in `CHECKLIST.md`, and rerun for
save/load checks or prepare a new directory for a clean start. The Lua/JSON
fixtures and scenario runner do not import the companion or require a model.
Process exit and load checks are distinct from observed gameplay results.

Joint-validation evidence must identify the exact native binary, installed wheel
and, for managed launch, runtime bundle. See the current package's
[acceptance record](../../companion/docs/acceptance.md) and compatibility record.
Compilation, unit tests, the synthetic model joint test,
graphical play, save recovery, real model behaviour, hosted CI and publication
are separate evidence categories. No declaration or local mock test establishes
all of those categories.
