# Lua-first implementation notes / Lua-first 实现历史记录

This retained snapshot was separated from `LUA_FIRST_PLATFORM.md` on
2026-09-28 without changing its implementation or acceptance claims. Its source
is [CPH main at b7954f2](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/b7954f2eba1a38f068f2f861857f0841cab0091f/data/lua/LUA_FIRST_PLATFORM.md).
Except for the explicitly dated loader checkpoint, the source did not date the
individual entries; the extraction date is not their implementation or test date.
Statements such as “tests pass,” “now,” and “pending” below belong to that
snapshot. They are not fresh CPH test results or current acceptance status.

本文件于 2026-09-28 从上述固定源码版本摘出并保留原文。除明确标注日期的加载器断点外，
各条原文未注明实施日期；整理日期不作为实施或测试日期。下文“通过”“已实现”“待验收”等
表述仅记录当时的说明，不证明本轮或当前 CPH 已通过相关验收。

The durable design contract remains [LUA_FIRST_PLATFORM.md](LUA_FIRST_PLATFORM.md).
Use the [roadmap](../../ai/lua-first-roadmap.yml) for milestone evidence and the
[EOC capability workflow](LUA_FIRST_EOC_WORKFLOW.md) for scoped acceptance.
Current API details come from [LuaLS declarations](types/ccb_platform_v1.d.lua),
native registrations and actual tests. This file is a historical reference;
record new batch progress in the existing roadmap and its evidence references.

长期架构仍以架构契约为准，里程碑及新批次证据沿用 roadmap 与现行能力流程，不在此建立
第二份进度表。旧记录中的 API 描述须结合当前声明、原生源码和实际测试结果使用。

## Loader checkpoint / 加载器断点

Historical CCB integration evidence is recorded in [PR #768](https://github.com/CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb/pull/768), including the tested build configurations and native runtime results. The behavior below is the source contract; test source alone is not passing evidence. Interactive UI checks and native module packaging on each target platform require their own evidence.

CCB 原整合批次的历史编译配置、原生运行结果与验收边界记录在 [PR #768](https://github.com/CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb/pull/768)。下文描述源码契约，测试源码存在本身不代表通过；交互界面与各目标平台原生模块打包仍需各自证据。

Implementation checkpoint (2026-09-08): the loader source now opens the bundled
standard libraries, retains normal package searchers and native loading, and
inserts a Mod-local searcher before the ordinary searchers. Native search paths
also start with the Mod root's `?.so` (`?.dll` on Windows), preserving the original
cpath. Roots containing cpath metacharacters `;` or `?` use explicit
`package.loadlib` paths instead of an ambiguous automatic prefix. The reserved `ccb`
entry remains bound to the state-owned Platform table.
Native loading still depends on the host Lua build and module ABI. The Mod manager now presents a session execution-risk notice before discovering
Lua metadata (stderr for headless hosts); its startup UI ordering still requires
interactive acceptance. Direct loader embedders must provide their own notice.

实现断点（2026-09-08）：加载器源码已开放 bundled 标准库，保留普通 package 查找器与原生
加载入口，并优先查找 Mod 本地模块。原生库搜索路径增加 Mod 根目录的 `?.so`（Windows
为 `?.dll`），同时保留原有路径；根目录含 `;` 或 `?` 时可使用明确的 `package.loadlib`
路径，避免 cpath 语法歧义。`require("ccb")` 仍固定返回所属 state 的 Platform 根表。原生模块仍取决于宿主 Lua
构建与 ABI。Mod 管理器已在元数据发现前加入每会话风险告知（无界面宿主输出到 stderr），
启动 UI 顺序仍待交互验收；直接调用加载器的宿主应自行提供告知。

## Migration progress snapshot / 迁移进展快照

The entries below were appended beneath “Persistent dense arrays” in the source
architecture document. Their migration scope and pending acceptance boundaries
are retained here together; they do not expand the API or establish EOC parity.

以下条目原先连续追加在“Persistent dense arrays”小节之后。迁移范围与未验收边界一并
保留，不扩大现行 API，也不证明 EOC 语义等价已完成。

### Iteration and string expressions / 迭代与字符串表达式

Migrated nested `foreach` loops snapshot their inputs separately and share
the dialogue variable store. An inner loop does not restore the outer iterator
value on return; the next outer iteration overwrites it normally. Unsupported
nested effects still leave a migration gap. Generated Lua execution covers this
ordering; native comparison execution remains due.

Migrated `foreach` arrays also accept the string `game_option` mutator.
Its option name resolves dialogue participants independently, and all option
values are read before the first iterator write or body effect. Missing or
non-string options fail explicitly. Generated Lua tests cover both participants,
snapshot timing and failure before body execution; native execution is pending.

Dynamic `foreach` strings can read monster default factions and translated
martial-art technique names or flavor descriptions through typed definition
services. Their identifiers may recursively use supported string expressions;
participant variables retain their own alpha/beta ownership. Generated Lua
execution checks nested option lookup and full-array evaluation before effects.
Native comparison execution and the remaining string mutators are still due.

Migrated `foreach` strings support `valid_technique` through
`characters.choose_technique`, selecting for alpha against beta before body
execution. Dynamic blacklist strings retain participant ownership. Blacklists
have no additional entry-count cap; required character provenance and ID
validation remain explicit migration limits. Generated Lua tests cover flags,
300-entry lists and selection timing. A same-seed native comparison test is
provided but has not run; this is not evidence of full native selector parity.

Explicit `{str = ..., i18n = true}` string expressions in migrated
`foreach` arrays use `services.translate`, including nested supported mutator
arguments. Plain string literals remain untranslated. Translation runs while
building the input snapshot, before body effects. Generated Lua execution covers
this order; native localization comparison is still pending.

### Activities and NPC interactions / 活动与 NPC 交互

`activities.revert_npc_job` always performs native NPC state restoration,
including idle NPCs with pending backlog or saved mission/attitude state.
Migrated `revert_activity` calls this operation instead of cancellation.
The result reports `restored = true`; the legacy `changed` field only records
whether a job was active beforehand. Generated Lua routing/error tests pass;
the idle-NPC native comparison test still awaits execution.

NPC work migration uses `activities.assign_npc_job` for butchery, planks,
trees, construction, farming, fishing, mining, mopping, repeated reading,
study, loot sorting, disassembly, and vehicle deconstruction/repair. These
operations assign the native activity actors instead of approximating work
with a fixed duration. Generated Lua tests verify all fourteen routes and
failure propagation. Native assignment comparison test source is present but
has not executed; other interactive NPC job paths still require review.

Migrated NPC reading, ebook reading and crafting use the corresponding
`assign_npc_job` operations and native selection flows. A returned
`assignment_rejected` leaves execution free to continue, matching native
return-without-assignment behavior; other service errors propagate. Generated
Lua tests cover success, no assignment and stale-handle failure. Interactive
selection and gameplay acceptance remain pending.

The `find_mount` NPC job follows native creature traversal and assigns the
selected mount. When none is available, it restores an active player-directed
NPC job before returning `no_match`; idle NPCs remain unchanged. Migrated
`find_mount` treats that result as a normal return and propagates other errors.
Generated Lua branch tests pass; native active/idle no-match comparison source
is present but has not executed. Successful mount selection still needs runtime
acceptance.

Migrated `morale_chat_activity` uses the native socialize actor for the
avatar and the exact NPC partner for ten minutes. `drop_items_in_place` uses
the native `drop_carried_items` order, retaining its inventory filtering and
empty-inventory behavior. Generated Lua tests verify event and overridden NPC
participants; native activity execution and inventory outcomes remain unverified.

Migrated `start_training` calls `npcs.training.start_selected` with the
exact NPC provider and avatar student. It retains the native selected course,
payment and duration calculation instead of assigning a fixed training timer.
A successful call that starts no training remains a normal return. Generated
Lua routing/error tests pass; native course/payment execution remains pending.

`npcs.training.start_selected(provider, avatar, "seminar")` opens native
seminar participant selection, retaining follower eligibility and cancellation.
The avatar handle is validated before selection; returned provider/player flags
do not enumerate all seminar students. Migrated `start_training_seminar` uses
this mode. Generated Lua cancellation/routing tests pass; native menu, payment
and multi-student training acceptance remain pending.

Selected training also supports `"npc"` mode: the avatar teaches the exact
NPC using that NPC's selected dialogue course. The avatar argument remains
explicit and validated even though its role changes to teacher. Migrated
`start_training_npc` uses this mode when its NPC is proven. Generated Lua
role/routing tests pass; native skill transfer, fees and activity completion
remain pending acceptance.

Grooming effect migration invokes native style selection for hair/beard and
native haircut/shave services with the exact NPC and avatar client. These
effects are no longer silently discarded. Without a proven NPC they remain
explicit migration gaps. Generated Lua tests cover all four calls and missing
provider handling; native appearance and morale outcomes await acceptance.

`trade.open` optionally resolves the seller's native intercom trade delegate;
default calls retain the explicit seller. Migrated `start_trade` enables
delegation, uses the active avatar, zero initial cost and a translated title.
Cancellation is a normal return. Generated Lua tests cover that contract;
native buyer-validation test source is present but unexecuted, and delegated
barter UI acceptance remains pending.

NPC wake, dismount, temporary-rule reset and lead-to-safety effects migrate
to native NPC orders. This preserves wake effects/rules and native dismount
and destination behavior instead of skipping the command or only changing
attitude. Generated Lua routing tests pass; wake/rule-reset native comparison
test source is present but unexecuted. Mounted and pathfinding outcomes still
require native acceptance.

Migrated NPC conversation ending calls `npcs.dialogue.finish`, preserving
the native first-topic change to `TALK_DONE` without exiting the Lua callback.
Stat reveal and combat-style selection open their native NPC interfaces.
Generated Lua tests cover the three operations in sequence; native topic-state
comparison source is present but unexecuted, and the two menus await interactive
acceptance. Missing NPC provenance remains a migration gap.

Combat-insult migration invokes `npcs.dialogue.provoke_combat`, preserving
the native topic change and hostility together. Generated Lua tests verify
event/override NPC routing; native topic/attitude comparison source is present
but unexecuted. This does not establish combat gameplay acceptance.

Follower migration uses `join_player`, `stop_temporary_following` and
`make_neutral` instead of attitude-only writes. This retains follower/faction
setup and cash transfer, the allied-NPC stop guard and stranger-topic reset.
Generated Lua routing tests pass; allied/non-allied state comparison source
is present but unexecuted. Join-state runtime evidence remains outstanding. Stop/neutral operations
now call native talk functions so their notification rules are retained; message
comparison test source is present but has not executed.

Migrated `leave` uses `leave_player` to remove follower membership, create
the independent faction and reset work priorities/topic. Native leave notification
and direct mission reset are preserved, including the previous-mission value.
`follow_only` uses `follow_temporarily` to clear guard and long-term goals
without transferring cash or joining the player faction. Generated Lua routing
tests pass; temporary-follow native comparison source is unexecuted and full
leave/faction runtime acceptance remains pending.

Confrontation migration routes `hostile`, `flee`, `player_leaving`,
`start_mugging` and `remove_stolen_status` through their existing NPC services.
This preserves hostile-event dispatch and its already-hostile guard, visibility-based
hostility notification, flee/mugging messages, departure patience and stolen-item
claim clearing. Generated Lua exercises participant overrides and error propagation;
native message/patience comparison source is present but unexecuted. Hostile event,
visibility and stolen-item lifecycle runtime acceptance remain pending.

Guard assignment/removal migration uses `set_guarding` and its native talk functions,
rather than attitude-only changes. This retains the allied/non-allied branches,
activity restoration, guard destinations and topics, and the allied stop notification.
Generated Lua participant/error tests pass; allied/non-allied stop-state comparison
source remains unexecuted, and assignment/camp/activity runtime coverage is pending.

Gratitude migration checks the `make_thankful` result and retains the resolved NPC
participant. Generated Lua covers routing and failure propagation; native comparison
source covers hostile/non-hostile attitudes, friend-topic retention and personality
bounds, but has not been compiled or executed.

Medical-aid migration uses `npcs.medical.provide_aid` for all four native aid effects:
basic/advanced treatment with or without nearby walking allies. The existing service
calls the native talk functions, including healing, relevant wound removal, patient
waiting activity and provider busy duration. Unproven NPC providers remain explicit
migration gaps. Generated Lua tests cover all four level/allies combinations, avatar
patient identity, provider overrides and failure propagation. Random healing, ally
range filtering and activity/effect duration runtime acceptance remain pending.

### Control transfer and handle identity / 控制权与句柄身份

Control transfer and its menu are no longer classified as successfully migrated
no-ops. Their migration still needs participant continuity across handle invalidation
and, for direct transfer, original dialogue branching. Bare-string `clear_dimension`
and `place_override` are also explicit gaps: their native registrations require
object parameters. This does not affect the existing object-form world renderers.

Control-service rejection test source checks non-allied targets and wrong avatar
participants, including identity/faction/attitude retention and no handle invalidation.
This source has not run and does not establish successful transfer, menu cancellation,
or post-transfer callback continuity. The menu implementation already invalidates
handles only when the native avatar identity changes.

Avatar handles now capture the native character ID and reject an in-place identity
change with `stale_avatar_identity`, even before the enclosing control service
invalidates the runtime handles. Fresh handles use the new character ID. This closes
the stale-avatar window during native control-transfer hooks without changing their
ordering. A focused in-place identity regression is present as unexecuted test source;
full control-transfer and hook runtime acceptance remain pending.

### Animal placement / 动物放置

Animal-purchase migration keeps center-first nearby placement and passes
`upgrade=false` to `spawns.monster` (omitted upgrade retains the existing true default).
Successful chicken/horse/cow placement sets friendliness to -1 and the permanent pet
effect. Blocked placement continues; other errors propagate. These native effects do
not charge payment themselves. Generated Lua tests cover species, participant overrides,
pet setup and blocked/error continuation. Native placement/upgrade/pet runtime acceptance
and the original blocked-placement debug notification remain outstanding.
A fixed-seed native comparison source now covers chicken/horse/cow position, type,
friendliness and permanent pet duration; it has not been compiled or executed.

Spawn-upgrade regression source additionally uses an upgrade-capable test monster
with evolution enabled, covering omitted/true/false arguments and uninitialized
upgrade time for the disabled path. It remains unexecuted; ordinary pet species
alone are not evidence that the upgrade option works.

### NPC variables and requests / NPC 变量与请求

Refusal migration uses `npcs.record_refusal` for follow, lead, equipment, training
and personal-info requests, checking failures and retaining the resolved participant.
The native cooldown durations are unchanged. Generated Lua verifies all request routes
and failure propagation; repeated-request duration/permanence comparison exists as
unexecuted C++ test source.

NPC class/faction/first-topic migration resolves supported string expressions at each
operation through the participant-aware string renderer, then checks the service result.
The earlier class/faction branch that rejected dynamic values has been consolidated.
Generated Lua tests mutate a context variable between operations to verify live lookup,
participant overrides and failure propagation. Full native parameter/participant
coverage remains unverified; unsupported expressions retain explicit migration gaps.

NPC radio-representative migration now calls `set_radio_representative` with the
resolved NPC and current avatar owner, matching the native global-owner choice.
Generated Lua checks participant overrides, owner identity and failure propagation.
Unexecuted native test source checks representative marking, repeated registration
and retention of other representatives. Full native dialogue/owner acceptance is pending.

`npcs.request_talk` retains the native wants-to-talk notification: only on an actual
attitude transition and only when the NPC sees the avatar. NPC wants-to-talk migration
uses this service and checks its result. Generated routing/error tests pass; repeated
request silence has unexecuted C++ coverage, and visible/hidden native comparison
remains pending. Generic attitude writes keep their existing behavior.

Explicit callback wants-to-talk migration distinguishes alpha (`u_`) and beta (`npc_`).
Either participant may be an NPC; non-NPC participants are skipped as in native
`get_npc()` handling. Generated Lua covers two NPCs, avatar alpha, and two non-NPC
participants. This routing evidence does not replace native visibility acceptance.

Explicit callback `u_make_radio_representative` now registers an NPC alpha with the
current avatar owner; it does not substitute beta or use alpha as the owner.
Generated Lua verifies independent alpha/beta registrations. Non-NPC misuse is
skipped; parity with the original null-NPC debug diagnostic remains outstanding.
This diagnostic boundary and native runtime evidence prevent full semantic acceptance.

## Native selling offers acceptance / 原生售卖清单验收记录

The corresponding API explanation remains under
[domain services](LUA_FIRST_PLATFORM.md#domain-services--领域服务).
The source snapshot recorded:

A native comparison
source is present but unexecuted. Allowance-gift selection and settlement remain pending.

## Superseded trait migration description / 已更正的特质迁移说明

The following text from the same source snapshot was corrected during the
2026-09-28 documentation review. `render_mutation_action` already emits
`replace`, `erase`, and `invoke_activation` for bounded supported forms;
ordinary and false-effect callers keep unsupported forms as located
`manual_rewrite` TODOs. The old universal `semantic_choice` statement below
must not be used as the current migrator contract. Native semantic acceptance
is still separate from these source mappings.

以下旧文在 2026-09-28 文档复核时根据迁移器、LuaLS 声明与原生注册更正。旧文笼统将
全部形状归为 `semantic_choice`，已不符合源码；保留供历史追溯，不作为当前契约，
也不因修正文案将有关 selector 提升为语义等价已验收。

The migrator does not automatically lower legacy `add_trait`, `lose_trait`,
`activate_trait` or `deactivate_trait` effects (either actor) to `grant`, `remove`
or `set_active`. Adding a legacy trait clears other mutations sharing its types;
`grant` preserves them and emits an event. Removal differs in base-trait
bookkeeping and event policy. Repeated native activation/deactivation may consume
resources, transform a mutation or invoke callbacks, whereas `set_active` skips
an already-satisfied state. These inputs produce a located `semantic_choice`
TODO, including in false branches. Authors choose the intended ordinary Lua
composition; the public services retain their existing domain contracts. Their
ledger entries are primitive availability, not automatic migration equivalence.

旧特质增删与激活/停用不能直接等同于当前 Lua 操作。迁移器对这八个玩家/NPC 效果明确
报告 `semantic_choice`，而不是静默改变冲突清理、基础特质、事件或重复调用行为。
这表示已有可用领域接口，但旧行为的替代组合仍需明确设计，不能算迁移等价通过。
