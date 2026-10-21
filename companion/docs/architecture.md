# Architecture and authority

| Module | Location | Owns |
| --- | --- | --- |
| ActorControl / NpcExecutionAdapter | CPH `src/`, C++ | Fixed actor identity, actual perception, capability checks, persistent tasks, short queue, native activities, receipts, save state |
| Companion MOD | `companion/` Python package resources, Lua | Binding and game-side chat/status/debug entry points through `require("ccb").services.actor_control` |
| AgentRuntime / LlmProvider | `companion/src/cph_ai_companion/`, Python | Bounded planning, context, provider worker lifetime, protocol requests |
| AgentMemory | `companion/src/cph_ai_companion/`, Python | Background reads, file-backed cognition, manual precedence, checkpoints and retrieval |

The Python project and MOD now share the CPH source repository under
`companion/`. They retain separate package artifacts and an external Python
process; source consolidation does not merge the multiplayer and NPC control
flows or start a model automatically.

`companion/src/cph_ai_companion/resources/protocol/protocol.json` and
`fixtures.json` / `task_fixtures.json` are the single protocol and fixture authority. The CPH-root
`tools/actor_control/generate_protocol.py` reads them directly and embeds the
contract and test fixtures in the native generated header. Its `--check` mode
rejects a stale header. The cross-repository export tool and the native
`data/reference/actor_control/` snapshot are retired. Built Python resources and
native code still carry the exact protocol digest; builds never fetch a moving
specification. Only the game thread mutates game-world state.

The loopback bridge authenticates one external client per instance. Instance
descriptors and credentials are private files; explicit session selection avoids
cross-instance control. The model does not receive arbitrary state setters,
code execution, movement-point mutation or hidden world information.
Ordinary recruited NPCs are eligible; multiplayer player proxies are excluded
from new bindings and restored control. Safe stop retires controller work while
preserving a proxy's native activity, action-point budget and own state.

The Windows implementation retains that loopback protocol and the existing
external Python runtime and spawned provider worker. Native private files use
the current user's SID and an explicit owner/SYSTEM-only ACL; POSIX mode bits
are not treated as Windows access control. Journal files and lock files reject
hardlinks, and path checks reject reparse-point parents, alternate data streams,
device names and Win32 filename aliases. Session metadata uses the actual game
directories and the process creation FILETIME rather than `/proc` start ticks.
These platform seams do not create another control service or simulation.

The native save transaction uses the same beforeimage manifest on Windows and
Linux. A process-held world lease excludes another writer, including during a
read-only dimension snapshot; abrupt process exit releases the lease without
pretending that a pending journal committed. Recovery validates all backups
before restoring any file, and a durable committed marker prevents replay of
old physical work. Windows flushes files before write-through publication;
it does not claim that POSIX directory `fsync` exists on Windows. Ordinary
worlds without a companion journal keep their ordinary loading path. Windows
build, process-crash, filesystem and graphical acceptance remain separate
results and must be reported against the actual tested inputs.

Model candidates pass schema and personality validation, then native validation.
The native executor handles urgent reactions, current activity, queued steps and
ordinary NPC logic in that order. Input-wait message processing does not advance
game time. Accepted step IDs and receipts establish completion, including
dependencies on preceding output. Provider text is never a completion receipt.

All 15 explicit social permissions are independently configurable. Parent
deception/betrayal switches constrain their leaves. Natural language is not a
perfectly classified action: structured intent checks do not prove every
unannotated sentence truthful or harmless. Native targets and effects receive
separate checks.

Protocol 1.2 retains each incoming player message's native requirement identity.
An explicit `refuse` step names that identity and persists the decision; the
controller rejects contradictory work and later attempts to revive the same
requirement. A new request has a new identity. Natural prose is still subject to
the documented classification boundary; it cannot fabricate an engine decision.

Planning budgets belong to an event episode rather than a polling call. Calls,
read-only queries and the active deadline span successive polls. A private
metadata journal retains counters and terminal state across runtime restarts;
interrupted episodes wait for new information instead of acquiring a fresh
deadline. Cooldown, an ordinary clock tick or an internally refreshed request
ID does not grant another budget. The journal contains identities and budget
metadata, never a provider key or prompt body.

## Persistent tasks and delayed planning

The protocol 1.2 implementation candidate adds task offers without changing
short-action plans. `offer_tasks` carries the existing context, optional
`append`/`prioritize` mode and at most five task entries. The supported kinds
are follow, guard, move, gather and craft. Task IDs and requirement links retain
their normal bounds. Dependencies may reference earlier accepted tasks; native
admission resolves their identities and state. A task offer cannot contain
short `steps`, social `intent` or speech; dialogue and refusals retain the
existing plan format and native permission checks.

The game stores tasks and replenishes the bounded action queue locally.
Gathering uses actual perceived permitted sources, defaults to newly acquired
quantity, and optionally targets inventory quantity. Its item type/count are
required; coordinates are optional as a complete x/y/z group. The task's
distance bound defaults to 12 native tiles from its initial anchor, up to 60.
Execution continues through existing NPC pathing, inventory transactions and
activities. There is no second simulation in Python and no shared multiplayer
identity, network state, observation packet or turn scheduler.

One worker and one pending candidate bound prefetch. Planning is requested only
for a necessary decision with sufficient context, and a ready candidate waits
for a safe native handoff. Old generations, changed permissions and invalid
resources reject adoption. Local progress, failed calls and unchanged blocked
conditions cannot silently allocate new planning episodes. Danger reactions
remain native; provider latency grants neither game time nor action points.

New accepted work appends unless explicitly prioritized. Conversation alone
does not erase an accepted task. Explicit cancel/stop invalidates outstanding
results and follows native interruption rules. Beyond basic follow/guard,
`duties.allowed_tasks` is the explicit scope for autonomous task proposals;
the empty default does not permit autonomous travel, gathering or crafting.
The scope does not waive native ownership, risk or player-requirement checks.

## Known abilities and checked casting

The existing native observation exposes `actor.abilities` (at most 64 known
spells), `ability_count`, `abilities_truncated`, current mana/stamina and their
maxima. Each ability includes its ID, level,
effect, support/reason, cost, native casting time, range, targets, failure chance
and current `castable` state. A supported/castable entry does not authorize any
particular target. Querying these fields requires no extra RPC or model call.

`cast_spell` is a short action with exactly `{spell, x, y, z}`; coordinates are
absolute map squares, including the caster's tile for self-casts. The native
activity owns time, energy, failures and completion. Target identity, perception,
line of sight, resources and permissions are checked again at completion.
Requirement refusal/false-promise/withdrawal, multiplayer exclusion and existing
save/receipt protection still apply. Python adds spell guidance only when the
advertised catalog makes casting available, without changing planning budgets.

The first implementation admits only pure single-target `attack` and self-target
`recover_energy` for MANA, STAMINA, SLEEPINESS, PAIN or HEALTH. STAMINA requires
finite native stamina. Components, extra
effects/EOC chains, damage-type hooks, failure callbacks, channeling, interactive/avatar-only kinds,
blood/HP or vitamin costs, unsupported flags/status effects and area/field/multiple
projectile effects return fixed rejection codes. Many ordinary Magiclysm spells
have setup chains and remain unsupported; this is not full support for that Mod,
Mind Over Matter or Xedra Evolved. Learning and sustained-ability control are
outside this change. Binding persists the character's finite-stamina eligibility
across detach, rebind and saves. Movement, recovery and spell costs use existing
native fields and formulas; safe local rest preserves pending work without model
calls. Ordinary NPC and MP scheduling remain independent.

Casting preparation carries the actual caster, including dynamic spell levels;
observations never dispatch preparation. Loaded spellbook EOC/Lua hooks are
explicitly refused with `npc_unsupported_spellbook_event`, even for otherwise
pure helpers, rather than skipping Mod prerequisites or executing unreviewed
scripts. NPC calorie/sleep/cardio progression and broad Mod compatibility remain
outside this support. The
[native interface contract](../../docs/project/actor-control.md#known-abilities-and-checked-casting)
defines the fields and rejection boundary; the model cannot substitute guessed
spell IDs, arbitrary Lua/EOC or free effects.

## Provider configuration and consumption

The defaults remain five short steps, three model calls and four read-only
queries per decision episode, a 30-second request deadline, a 90-second episode
deadline and a 10-second cooldown. Input/output limits are 32,768/2,048 tokens.
`limits.session_max_calls` and `session_max_tokens` default to 100 and 100,000.
These bounds are configurable; they do not change NPC speed or task progress.

`runtime-budget.json` is a private profile-local consumption ledger, separate
from memory and game saves. An account binds profile, world, actor and explicit
`limits.budget_period` (default `default`), without using the current load epoch
or request ID to reset spending. Reservation happens before a provider worker
starts. Failed, cancelled and unknown-outcome attempts retain that reservation;
reported usage can increase it. Reloading, memory restoration and process
restart cannot refund calls. An explicit new budget period is a user decision,
not a scheduled or game-time reset.

Optional `llm.thinking_mode` accepts `enabled` or `disabled` and forwards the
provider-specific `extra_body.thinking.type` setting. Omitting it sends no
thinking override. Endpoint support remains the endpoint's responsibility;
this switch does not expose internal reasoning, change native permissions or
make a plan immediately executable. Profile changes invalidate in-flight
work before the new configuration is used.

`ProviderError.code` and its string remain fixed public codes such as
`provider_request_failed`. Optional `diagnostics` preserves only a strict
allowlist of HTTP status, classified reason, known exception type and known
structured error type/code/parameter. It is filtered in the worker, IPC reply
and parent; raw error messages, bodies, headers, URLs and credentials never
cross that boundary. Authentication/balance failures must not be retried by
an acceptance harness. Errors still consume the reserved call budget.

JSON-mode prompts explicitly request one JSON object and include a format
example. Task envelopes and per-task fields are described separately from
step-only speech, intent and reflections; every player task copies the exact
shown requirement ID. These instructions assist model output; the local
protocol and native admission checks remain authoritative.

Task `mode=append` queues new work; `mode=prioritize` pauses earlier work at
the native safe interruption boundary. Accepting an immediate switch or
stop-now request requires `prioritize`; refusal remains a `refuse` action.
Neither prompt guidance nor correction rewrites a rejected candidate's mode.

`build_messages` still accepts a legacy correction code string. Trusted
structured mode feedback may supply `code=mode_mismatch`, `expected_mode` and
`actual_mode`; only `append` and `prioritize` values are retained. The prompt
keeps `previous_candidate_error` as a string and adds bounded
`previous_candidate_feedback` with the allowed enums and a fixed instruction.
Mode and native task-dependency errors receive actionable hints. Unknown
fields, caller-supplied instructions and arbitrary rejected model text are
not forwarded as feedback. This changes planning messages, not protocol 1.2
or native permissions; the model still has to return a new valid proposal.

## Player knowledge and diagnostic state

Ordinary UI reads `planning_state` and `player_progress`, not `task_summary`
or the internal queue. `thinking` means waiting for a model response;
`pending` means a decision exists but no worker is running; `suspended` reports
an exhausted spending limit; `failed` reports a completed, unsuccessful planning
episode. `candidate_pending` means waiting for a safe handoff; `idle` permits local
behavior to continue; `offline` reports an unavailable connection. These are
system states, not claims about the character's private motives.

The authenticated coordinator reports its transient worker state through the
existing `status` RPC's optional `planning_report`. The shared protocol schema
allows only fixed states/reasons plus the current decision and request IDs.
Unknown fields are rejected. An expired report cannot relabel a newer request;
load, disconnect and request invalidation clear the report. It is neither a
saved task nor a model query, and does not change decisions, permissions or budget.

The main menu header contains a short public status summary and updates when
the menu is rebuilt. The **Status and conversation** page shows the complete
public projection, including recent dialogue. Header text uses the standard
menu layout so its height is measured; callbacks do not draw extra conversation
below the entry list.

Progress is recorded by native code only after the avatar actually sees a
physical result. It persists as the last known observation and does not update
for unseen work. Task kind, state and observed progress/target counts are the
only ordinary progress fields. Character self-report remains in the transcript
and may differ from reality. Full task state, hidden intent and diagnostics are
available only in the explicitly enabled debug view. A player's knowledge of
a promise does not prove that the promise is sincere or fulfilled.

## Local cognition

`paths.background` names the user-controlled background file; automatic code
never writes it. `paths.memory` selects the memory root. Relative paths are
anchored at the profile. A profile lock and a memory-directory lock allow one
automatic writer while ordinary text editing remains available.

Memory kinds distinguish observations, statements, beliefs, commitments,
receipts, relationships, growth, summaries and personal goals. A player's claim
does not become a world fact. Goals come from accepted native goal events, not
unaccepted model proposals. Retrieval checks actor/world/branch policy before
ranking by query relevance, importance and game time.
Unfinished commitments and current-goal receipts are marked as mandatory in a
snapshot before ordinary retrieval is ranked or trimmed. If those mandatory
records and the fixed context exceed the configured input limit, planning stops
with a context-budget error; it does not silently discard the obligation.
Native cognition synchronization compares its bounded projection as well as the
file revision, so game-time forgetting can refresh the cache without treating
every ordinary clock advance as a new file revision or invalidating all plans.

The same bounded planning response may propose up to three subjective reflections
with references to retrieved records. The runtime validates their sources and
stores them only after native plan or task acceptance and a final revision check. Beliefs,
relationships, growth and summaries remain interpretations, including possible
misjudgment; they cannot create observations, commitments or action receipts.
Growth and relationship preferences may change only the bounded `caution`
value, and require real source records. The original background remains fixed.
Raw structured observations and receipts are preserved locally up to 1 MiB
per payload; each readable record has a separate 2 MiB file limit. Subjective
reflections cannot supply raw game data. A native goal event may attach the
matching successful goal-acceptance receipt as evidence, with its receipt source
ID; this records acceptance without turning its desired outcome into a fact.

Records and manifests use unique revision paths. Edited current records win
over automatic candidates, and conflicting bodies remain inspectable. Deleting
a head writes a durable tombstone and removes all managed versions plus derived
memories, including historical checkpoint dependencies. Audit evidence contains
original actor-delivered events for human inspection; it is never scanned for
retrieval, restore or automatic relearning. Deletion purges those audit bodies
too, retaining only identifiers, hashes and reasons as a trace. A later event
derived from a tombstoned source is suppressed while unrelated valid events
continue; a genuinely unknown source rejects the whole batch. Old checkpoints cannot undo a manual
edit or deletion. Revision checks invalidate in-flight model output.

Checkpoints name existing record revisions and have `state: prepared`. CPH's
successful save association determines which checkpoint can be restored.
The reference retains its true local file `revision`; `projection_version` and
the handshake `version` bind the native projection captured for that save.
These versions are distinct. A concurrent edit before submission rejects the
checkpoint instead of assigning an unrelated file revision to the projection.
Restoration changes cognition only. Items, tasks, teams, physical relationships
and queued physical effects remain authoritative in CPH. Explicitly imported
old-world experiences are labelled as experiences, not current world facts.
The disposable native cache gives imported beliefs, relationships, growth and
summaries the current binding scope and preserves `origin_context`, `imported`
and their continuity label. Imported observations, statements, receipts,
commitments and goals remain local historical experiences; they cannot become
current native facts. Unmarked foreign records are never silently rebound.
The first entry into a world establishes a durable, versioned set of imported
growth records. Subsequent growth in the origin world does not change that
starting point. Explicit continuity configuration changes can add permitted
sources. Manual edits and tombstones remain authoritative over frozen references;
the optional import manifest is backwards compatible with memory format 1.

The native save design also journals accepted physical operations across CPH's
separate avatar, world, mission and map files. A prepared external checkpoint is
not proof that those game files committed together. An interrupted save must
preserve the journal and pause uncertain work for reconciliation rather than
replay a physical effect using an older queue or memory checkpoint. Memory
restoration and deletion cannot restore spent materials, pay rewards or repair
game files. Focused native fault tests passed for journal rollback/commit,
beforeimages, native file writers and gameplay snapshot boundaries. They are
automated isolated fixtures; a complete physical crash campaign spanning all
game files and graphical save/load journeys remain `NOT_RUN`.

The action catalog gathers actual ground items, executes queued melee attacks
and admits the bounded spell casts described above. Broader harvesting and
model-directed ranged weapon attacks require additional native adapters.
Native NPC fallback retains its ordinary combat
logic, including ranged behavior when the game permits it.

## Disconnect and detach

Unexpected disconnection leaves accepted valid native work running; afterward
the NPC uses local behavior with the last confirmed, stale cognition snapshot.
Explicit stop rejects old replies and clears unstarted work. A current native
activity hands off or cancels according to native interruption rules; pending
detach is distinct from stopped provider calls.

Leaving the simulation area pauses work without granting offline action points.
Unsupported future formats stop takeover and preserve files. Safe MOD removal
requires native confirmation that detach and world dependency release completed.
The NPC's real items, mission assignment and reward rights survive removal.

Release assembly reads wheel metadata and source archive metadata without
extracting the archive. Project/version/Python requirement, protocol digest and
all MOD bytes must agree. Canonical paths, duplicate members, referenced file
types and present ancestor directories are checked; supplied evidence cannot
silently change protocol digest. Tests and compatibility still bind the actual
built wheel, native binary and source commits independently of assembly.
Default assembly and `--candidate-only` create a fresh unvalidated record,
without copying historical candidate status, acceptance or supported pairs.
`--compatibility` selects an explicit evidence file; every validated combination
must match the built wheel's exact SHA-256, package version and protocol. Empty
combination lists remain unvalidated. This check preserves supplied evidence
for its identified artifact; it does not run or infer native acceptance.
