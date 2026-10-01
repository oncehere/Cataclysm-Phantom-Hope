# Architecture and authority

| Module | Location | Owns |
| --- | --- | --- |
| ActorControl / NpcExecutionAdapter | CPH C++ | Fixed actor identity, actual perception, capability checks, queues, native activities, receipts, save state |
| Companion MOD | Python package resources, Lua | Binding and game-side chat/status/debug entry points through `require("ccb").services.actor_control` |
| AgentRuntime / LlmProvider | Python | Bounded planning, context, provider worker lifetime, protocol requests |
| AgentMemory | Python | Background reads, file-backed cognition, manual precedence, checkpoints and retrieval |

The protocol and shared fixtures in package resources are the specification.
`tools/export_cph_protocol.py` copies a fixed snapshot to a selected CPH tree.
Its digest and source identity accompany the native snapshot; builds never fetch
the latest specification. Only the game thread mutates game-world state.

The loopback bridge authenticates one external client per instance. Instance
descriptors and credentials are private files; explicit session selection avoids
cross-instance control. The model does not receive arbitrary state setters,
code execution, movement-point mutation or hidden world information.
Ordinary recruited NPCs are eligible; multiplayer player proxies are excluded
from new bindings and restored control. Safe stop retires controller work while
preserving a proxy's native activity, action-point budget and own state.

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

The same bounded planning response may propose up to three subjective reflections
with references to retrieved records. The runtime validates their sources and
stores them only after native plan acceptance and a final revision check. Beliefs,
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
Restoration changes cognition only. Items, tasks, teams, physical relationships
and queued physical effects remain authoritative in CPH. Explicitly imported
old-world experiences are labelled as experiences, not current world facts.
The disposable native cache gives imported beliefs, relationships, growth and
summaries the current binding scope and preserves `origin_context`, `imported`
and their continuity label. Imported observations, statements, receipts,
commitments and goals remain local historical experiences; they cannot become
current native facts. Unmarked foreign records are never silently rebound.

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

The initial action catalog gathers actual ground items and executes queued
melee attacks. Broader harvesting and model-directed ranged attacks require
additional native adapters. Native NPC fallback retains its ordinary combat
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
