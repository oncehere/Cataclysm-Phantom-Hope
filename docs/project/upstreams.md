# CPH 上游来源与意图评审

本页维护上游评审、候选交付和持续台账的长期规则；需求以 [执行规格](execution-spec.md) R03—R06 为准。CCB 指定主分支的全部历史持续跟进，CPH 自身设计优先，允许适配、延迟或撤销冲突行为；CDDA 按需选取改进及必要依赖。CDDA 的单项取舍不得用于改成选择性接收 CCB 历史。CCB 有待决冲突时，记录待处理范围，实际整合前不推进整合游标。

## 上游评审与候选交付

以下规则适用于用户主动启动的上游调查、筛选和移植批次；用户明确限定“只读”或“只筛选”时遵守该范围。默认交付完整筛选清单和已选意图的可审查候选，由用户决定合入。制定流程本身不启动移植，也不恢复暂停的无人值守同步或发布。

- **D01，按意图评审。** 以“对象、前后变化、目的或效果”描述可独立取舍的修改意图，使用稳定 ID。一个 PR 可含多个意图，同一意图可关联多个提交或 PR；保留原始来源、作者、内部提交、后续修正和撤销关联。分别判断采用价值、移植难度和依赖；允许只采用有价值的部分或为 CPH 重写，不能把一个子项完成写成整个 PR 已处理，也不能以拆行掩盖实际耦合。
- **D02，按设计取舍确定决定权。** 证据明确、恢复预期行为的修复和保持行为的性能优化由助手完成筛选判断；先核对资源消耗、默认操作、失败方式、可用选项及平台/模组约定。改变玩法、操作或兼容约定，以及无法证明属于前两类的意图，须与用户共同决定。上游的 bugfix 标签不能代替判断；建议不采用也不能写成用户已经拒绝。筛选决定不自动授予实现或合入权限。
- **D03/D04，说明内容得失与常识收益。** 删除或合并已有可用物品、配方、选项须说明失去的用途、替代方式、资源/时间成本、操作和提示变化及收益，再与用户共同决定。常识一致性本身可以构成收益，允许考虑适度增加成本；不以成本上升直接排除，也不以“真实”自动接受。适度程度按具体场景和前后数值讨论，不自行设统一阈值。旧筛查仅因删减选择或增加成本而不选的项，须按此规则复核。
- **D05，分开记录覆盖与验证。** 对照当前源码/数据逐项核对意图效果，并检查后续撤销或覆盖；确认完整覆盖后可标记“源码已覆盖”并退出待移植清单，运行验证仍可为 NOT_RUN。历史可达、标题同号或 patch-id 只作线索。有疑点或高风险差异时补相应检查；部分覆盖只关闭已覆盖子项，证据不足则待核。
- **D06，成对交付筛选与候选。** 对本批已授权、已选且无待决问题的意图，在隔离工作树实现并完成必要测试。主动报告拟采纳、不采纳、暂缓、待核、已覆盖和不适用项及理由，附完整清单，不能只展示完成的代码或只给链接省略关键待决提醒。候选交付固定仓库、分支、base/head/tree、完整差异、来源映射、依赖、未采用部分、附带变化、实际检查与未验证范围，明确待用户决定的合入范围；按适用规则执行后回读实际结果。已授权的普通步骤无需重复确认；新设计取舍仍须讨论。
- **D07，大型依赖先评估。** 比较在 CPH 现有框架适配所需意图与引入上游机制及必要依赖两条路径，说明玩家收益、改动范围、附带意图、兼容影响、验证条件、维护成本和暂缓影响，再与用户决定。不能把未讨论的规则随依赖一并引入；只暂停依赖该决定的实现，继续已授权的独立工作。

## 意图台账与增量复核

**D08，持续回写并复用。** 每批开始先读总台账，明确本批复用、续接、复核项及原因，固定 CPH base、CCB/CDDA 来源分支和起止完整 SHA（包含/不包含端点）、UTC 时间、授权范围及历史完整性。保留范围内完整来源清单，尚未拆分或未审阅的来源显式记录，不以“没有意图”代替未完成审查。

本机总台账、可编辑源、导出方式和原始共同决定记录由工作区 `WORKSPACE.md` 登记唯一入口；它们属于 [本机工作区资料](workspace-layout.md)，不会随源码 clone 自动取得。独立 clone 应登记自己实际使用的台账和证据位置，不假设本机 `evidence/` 存在。由 JSON 等源记录派生的 CSV/XLSX 只通过源记录重新生成，不并行维护两套权威版本。

每项沿用稳定意图 ID，拆分或合并保留旧 ID 的继承关系。台账至少关联来源完整 SHA/PR、对象与效果、当前实现位置及各效果证据、依赖、决定人和理由、核对日期及基线、成果/恢复入口与下一步。以下维度分列：

| 维度 | 记录要求 |
| --- | --- |
| 当前覆盖 | 待核、源码已覆盖、部分覆盖、未覆盖或不适用；绑定 CPH SHA，并说明撤销核对范围与疑点。 |
| 意图决定 | 采纳意图、不采纳、暂缓、待核/待共同决定、无需移植-已覆盖或无需移植-不适用；每项只计一个决定状态。 |
| 执行阶段 | 未开始、候选实现中、可审查候选、已合入或已撤回；附工作树、base/head/tree，实际合入后才填目标分支和 merge SHA/PR，阻塞另记。 |
| 实际检查 | PASS、FAIL、NOT_RUN 或 BLOCKED；附命令、工作目录、退出码、平台及日志。源码覆盖、本地行为测试和远端 CI 分列，验收与证据复用按 [执行规格 §6.1](execution-spec.md#61-合入)。 |

每项评审、用户决定、实现、验证、合入或撤回后及时回写；批次结束前对账并保留固定基线快照，未回写不算交付完成。对账须覆盖每个来源组及全部子意图，commit、PR/组、唯一意图分别计数，不因多来源关联重复计算；纯流程、文案或不适用来源也须有明确处置。报告尚未完成拆分的来源数量与原因，仍有未拆分或未审阅来源时不得称该范围筛选完成；待决、暂缓或候选就绪也不得统称实施完成。

保存每项证据适用的路径/符号/数据 ID、调用和数据依赖、平台/模组及设计规则范围，记录复核触发条件。后续相关实现、依赖、规则、验证条件变化或上游修正/撤销时，只复核受影响项并追加结论、日期和变更理由，保留旧记录；HEAD 改变不自动使全表失效，原文件未变化也不能排除调用者或数据依赖的影响。有效结论复用，未完成项从实际断点继续；缺有效范围或证据的旧记录补证或标待核，不以模糊“已处理”永久跳过。

## Locked initial history

This page records the initial B/U history and the local source remotes. Its
original no-target conclusion has been superseded: the explicitly authorized
`oncehere/Cataclysm-Phantom-Hope` native CDDA fork and retained-history upload
are documented in [fork-deployment.md](fork-deployment.md). Current remote
checks and outstanding gates are dated in [status.md](status.md).

The primary specification is [execution-spec.md](execution-spec.md).

- CDDA source: `CleverRaven/Cataclysm-DDA`
- CDDA base B: `221c786e7d61b3c9254f7cb1625bc69494b8181c`
- B tree: `c7ad91e89ca75043106a74eb9c893130f378bd16`
- CCB source: `CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb`, `refs/heads/master`
- CCB baseline U: `bcb85682f3d28ab0f0123b05e45651bb9888b61b`
- U tree: `204b14a135ae307ad2180a348a6d6553374a07af`

The isolated branch `codex/e0-e1-bootstrap` was created at B, advanced to U
with an expected-old-value ref update, and checked out before any local changes.
`git merge-base --is-ancestor B U` returned 0. The initial clean HEAD/tree were
exactly U/the U tree above. No upstream commit was rewritten or squashed.
`refs/cph/cdda-base` and `refs/cph/ccb-baseline` retain local checkpoints.

`ccb` and `upstream` use the fixed public GitHub URLs and have disabled push URLs.
`source-cache` records the existing local object source and also has push disabled.
It is not an authorized CPH remote and is not independent upstream provenance.
The clone uses independent object files, not hardlinks or alternates. It has
non-shallow commit history but may need missing promisor blobs fetched locally.

At the initial local-history checkpoint no target OWNER/REPO was configured.
The target was later authorized and created as a real CDDA fork; `origin` now
points to it with push URL `DISABLED`, while actual authorized uploads used an
explicit URL and fixed ref. The initial absence of a fork is historical, not
a current blocker. The existing upstream refs remain preserved; the dated main
protection rule and per-PR acceptance results are in [status.md](status.md).

CCB master is followed through history-preserving integration; CDDA changes are
selected individually. Active adaptations and reverts must be recorded separately
from ancestry. Retrying the same already-merged ancestor does not undo a revert.
