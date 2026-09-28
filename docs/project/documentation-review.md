# CPH 文档与工作区整理审计（2026-09-27 UTC）

本次从源码仓库的 Git 跟踪路径建立清单，基线为
`d88815158ad31104ab4cde9fdd7537c7180cf7ff`。候选新增文档也纳入清单。
旧的 [冻结迁移清单](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/1057a15bf802572b7497ffd9617083a9b6935321/doc/migration/markdown-inventory.yml) 仅用于追溯 CCB 迁移历史，
不决定本轮现行文档范围。

整理期间主线先前进至 `785bcc2a9e540b46b7b12f37b19510390236e6f9`，
随后 PR #1 合入为 `39859e1b253e28e2c34b6a19935b7edcce51b9b6`。
整理分支保留历史整合这些提交，并保留主线新增的 CI 与同步入口。
主线推进后，旧 base 上的在途 W/L 被取消；新候选须重新取得对应回证。

## 审查范围和边界

覆盖根部入口、子目录 AGENTS、CPH 项目操作说明、游戏与构建技术资料、
工具说明、GitHub 表单，以及随仓库保存的第三方、历史和纯文本说明。
对 `.txt` 的候选清单另行识别构建配置、依赖清单及运行数据，避免将其误认成
待改写的说明文档。原作者、许可证、翻译归属和历史排除决定保留。

技术页的核验包括身份与维护声明、现行入口、相对文件链接、标题锚点、
构建/生成/安装引用和与源码可对照的过时步骤。该静态审计不等于逐个 JSON
字段、游戏机制或平台配方都重新运行通过；运行时结论须附各自的提交与测试证据。

## 目录与内容决定

- 根目录提供项目、贡献、支持、安全和治理入口；`docs/README.md` 统一导航。
- `docs/project/` 保存 CPH 需求、操作、带日期的状态及历史回证。
- `doc/` 继续承载游戏与构建技术文档，保留安装规则和加载顺序兼容路径。
- 现行技术页恢复本仓维护，保留稳定 ID；来源与历史 CCB 迁移记录分开链接。
- CDDA/CCB 的历史设计、退役构建流程和第三方材料保留，不能满足现行政策或
  必须同步的文档引用要求。
- 文档影响配置、schema、校验器、测试和注册表采用本仓路径及稳定 ID。
  必须同步文档的风险范围保持，缺失/错误/历史引用须拒绝。

## 验证与后续依赖

本机命令、退出码和完整输出保存在工作区
`evidence/project-cleanup-20260927/`；该目录不随源码提交。可共享的固定提交、
审查和 Windows/Linux 回证应附在各自的整理 PR 上，不把本机路径伪装成 GitHub 链接。

本地检查实际执行并通过：代理工具单测 85 项、JSON 契约单测 15 项、
文档安装单测 7 项，以及工作流回归单测 4 项。文档安装覆盖默认安装、
隔离测试身份、portable 和自定义路径。元数据、注册表、基准、替换清单、
JSON 契约生成一致性、工作流清单与 action 固定版本检查均通过。
首次安装测试因 PATH 中无 CMake 而跳过，记为 NOT_RUN；上述 7 项是补齐
工具路径后实际运行的结果。生成 JSON 使用官方生成器和仓库格式化器；
独立逐叶比较确认只有项目名、来源指纹和文档位置变化，API 契约保持一致。
固定 PR 的远端检查结果另附 PR，不以本地通过代替原生 W/L 回证。

实体归档先受[工作区布局](workspace-layout.md)中的空闲条件阻塞；相关任务结束
并核对宿主进程后，五个阶段工作树及三个失败 E3 目录已移入 `archive/`。
八处原路径保留兼容符号链接；93,199 个文件的内容哈希、权限、原始链接目标
及既有断链状态在移动前后相同，Git 工作树注册、分支与 HEAD 均已核对。
Lua 崩溃诊断、远端 CI 证据和复现输入继续原位保留。原始日志和结果 JSON
未改写，主工作树尚未切换到整理后的主线。

可信合入检查器会拒绝本轮涉及的保护路径。本次不更改它的放行规则。
2026-09-27 UTC 主线推进后的回读已确认规则集 `24056126` 为 active、
`main` 已受保护，原先“规则仍关闭时的一次性引导合入”条件不再成立。
因此本轮继续完成冲突处理、固定 base/head/合并树的真实 W/L 与审查回证，
将合入记为 BLOCKED；不关闭规则或伪造可信状态来继续。即使用户审阅具体
候选，仍须有符合现行保护规则的合入路径。整理回证不作为日常自动合入
门槛已验收的替代证据。

2026-09-27 15:31 UTC 拆分回读：原 PR #3 保留审查，但其 34 条保护路径
导致可信收集器拒绝；原生 Windows/Linux 成功不能批准该 PR。普通路径已
另开 PR #4，截至该时点 plan 成功、Windows/Linux 仍在运行、可信状态
待发布。保护路径仅作为独立审查候选准备，须在普通 PR 的结果和目标主线
确定后重新固定 base/head 并履行受保护规则的明确治理流程。两个候选都
不得借用 PR #3 的原生 CI 结果或把待运行状态记为通过。

## 逐篇处理记录

本次清单共 **279** 个文档/纯文本/表单候选；按用途分类，包含非说明的 `.txt` 配置与运行数据。
此表直接枚举 Git 跟踪文件及候选新增项，不以旧迁移注册表筛选。

此表保留审计时的数量与决定。2026-09-28 按用户要求删除三个仅转指
`AGENTS.md` 的厂商适配入口；相关行改链到删除前的固定提交，仅作历史回证。

| 分类 | 数量 |
| --- | ---: |
| CPH 项目文档 | 21 |
| 兼容路径 | 1 |
| 历史 | 30 |
| 历史变更记录 | 2 |
| 独立 Mod 材料 | 49 |
| 现行入口/指令 | 26 |
| 现行技术参考 | 98 |
| 现行表单 | 8 |
| 生成记录 | 1 |
| 第三方/许可 | 20 |
| 继承翻译参考 | 2 |
| 配置/运行数据 | 21 |

每项的“修订”均是编辑与静态契约核验范围；运行证据边界见上文。完整基线 blob、候选 blob 和命令输出另存本机证据目录。

| 路径 | 用途 | 属性 | 问题/审查点 | 处理结果/依据 |
| --- | --- | --- | --- | --- |
| [.deepcode/plans/sim-render-decoupling-plan.md](../../.deepcode/plans/sim-render-decoupling-plan.md) | CDDA 模拟↔渲染解耦 — 长期计划 | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [.github/AGENTS.md](../../.github/AGENTS.md) | CPH .github/ agent instructions | 现行入口/指令 | 按现行入口、角色及维护边界复核 | CPH settings and historical CCB audit boundary clarified; workflow security guidance preserved. |
| [.github/ISSUE_TEMPLATE/bug_report.yml](../../.github/ISSUE_TEMPLATE/bug_report.yml) | name: Bug report / 缺陷报告 | 现行表单 | 按现行入口、角色及维护边界复核 | CPH commit/release, CPH reproduction and public attachment checks replace CCB labels and version examples. |
| [.github/ISSUE_TEMPLATE/config.yml](../../.github/ISSUE_TEMPLATE/config.yml) | blank_issues_enabled: false | 现行表单 | 按现行入口、角色及维护边界复核 | CCB Docs/Discussions/PVR links replaced by CPH docs, Discussions and conditional security policy; no false private-report button. |
| [.github/ISSUE_TEMPLATE/content_json.yml](../../.github/ISSUE_TEMPLATE/content_json.yml) | name: JSON, EOC, or Mod content / JSON、EOC 或 Mod 内容 | 现行表单 | 按现行入口、角色及维护边界复核 | Data contract form retained; unverified inherited auto-label removed so form can work when CPH Issues enables. |
| [.github/ISSUE_TEMPLATE/documentation.yml](../../.github/ISSUE_TEMPLATE/documentation.yml) | name: Documentation / 文档问题 | 现行表单 | 按现行入口、角色及维护边界复核 | CPH repository documentation identity replaces CCB; question shape retained. |
| [.github/ISSUE_TEMPLATE/feature_proposal.yml](../../.github/ISSUE_TEMPLATE/feature_proposal.yml) | name: Feature proposal / 功能提案 | 现行表单 | 按现行入口、角色及维护边界复核 | CPH proposal and search checks replace CCB project identity; Discussions remains early-idea route. |
| [.github/ISSUE_TEMPLATE/mechanics_balance.yml](../../.github/ISSUE_TEMPLATE/mechanics_balance.yml) | name: Mechanics and balance / 机制与平衡 | 现行表单 | 按现行入口、角色及维护边界复核 | Evidence and compatibility questions retained; unverified inherited auto-label removed. |
| [.github/ISSUE_TEMPLATE/performance.yml](../../.github/ISSUE_TEMPLATE/performance.yml) | name: Performance regression / 性能问题 | 现行表单 | 按现行入口、角色及维护边界复核 | CPH commit/release identity replaces CCB version; measurement questions retained. |
| [.github/ISSUE_TEMPLATE/upstream_sync.yml](../../.github/ISSUE_TEMPLATE/upstream_sync.yml) | name: Upstream sync or port / 上游同步或移植 | 现行表单 | 按现行入口、角色及维护边界复核 | CPH purpose/divergence and main validation replace CCB master; source authorship/license questions retained. |
| [.github/copilot-instructions.md](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/b7a6cbb67044f6542c8b81c6ff37189724432590/.github/copilot-instructions.md) | GitHub Copilot adapter | 审计时入口，后续已删除 | 仅转指 AGENTS 的冗余适配入口 | 2026-09-28 删除；固定链接保留原审计对象 |
| [.github/pull_request_template.md](../../.github/pull_request_template.md) | Summary | 现行入口/指令 | 按现行入口、角色及维护边界复核 | Related CCB-Docs PR replaced by exact checker field Repository documentation impact; local paths/IDs and CPH summary guidance. |
| [AGENTS.md](../../AGENTS.md) | CPH repository instructions / CPH 仓库指南 | 现行入口/指令 | 按现行入口、角色及维护边界复核 | CPH execution specification and remote boundary replace inherited CCB agent governance; source, generated-file and evidence rules retained. |
| [CLAUDE.md](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/b7a6cbb67044f6542c8b81c6ff37189724432590/CLAUDE.md) | Claude adapter | 审计时入口，后续已删除 | 仅转指 AGENTS 的冗余适配入口 | 2026-09-28 删除；固定链接保留原审计对象 |
| [CMakeLists.txt](../../CMakeLists.txt) | Build options | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
| [CODE_OF_CONDUCT.md](../../CODE_OF_CONDUCT.md) | Our Pledge | 现行入口/指令 | 按现行入口、角色及维护边界复核 | Core standards and Contributor Covenant/GNU attribution retained; old CCB lead email removed; no configured private CPH conduct channel disclosed. |
| [CONTRIBUTING.md](../../CONTRIBUTING.md) | Contributing to CPH / 参与 CPH | 现行入口/指令 | 按现行入口、角色及维护边界复核 | Fork CPH main, responsible human, source/compatibility validation and in-repository documentation impact replace CCB master/CCB-Docs route. |
| [GEMINI.md](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/b7a6cbb67044f6542c8b81c6ff37189724432590/GEMINI.md) | Gemini adapter | 审计时入口，后续已删除 | 仅转指 AGENTS 的冗余适配入口 | 2026-09-28 删除；固定链接保留原审计对象 |
| [GOVERNANCE.md](../../GOVERNANCE.md) | CPH governance / CPH 治理 | 现行入口/指令 | 按现行入口、角色及维护边界复核 | CPH authority, provenance, human review, merge and four-platform release gates replace CCB governance and reviewer claims. |
| [ISSUES.md](../../ISSUES.md) | Reporting CPH issues / 报告问题 | 现行入口/指令 | 按现行入口、角色及维护边界复核 | CPH issue form route is conditional on feature availability; Discussions handles public early reports; CCB/DDA routes removed. |
| [LABELS.md](../../LABELS.md) | CPH issue and pull-request labels | 现行入口/指令 | 按现行入口、角色及维护边界复核 | Inherited CCB label names are triage examples, not verified live CPH labels or owner assignments. |
| [LICENSE-Apache-Robot-Font.txt](../../LICENSE-Apache-Robot-Font.txt) | Apache License | 第三方/许可 | 无本轮改写需求；保留归属/原契约 | 保留原作者与许可证；原始字节和基线一致 |
| [LICENSE-OFL-Terminus-Font.txt](../../LICENSE-OFL-Terminus-Font.txt) | Copyright (C) 2020 Dimitar Toshkov Zhekov, | 第三方/许可 | 无本轮改写需求；保留归属/原契约 | 保留原作者与许可证；原始字节和基线一致 |
| [LICENSE.txt](../../LICENSE.txt) | Copyright (C) 2012-2016 Free Software Foundation, Inc. | 第三方/许可 | 无本轮改写需求；保留归属/原契约 | 保留原作者与许可证；原始字节和基线一致 |
| [OWNERSHIP.md](../../OWNERSHIP.md) | CPH ownership and review / 责任与审阅 | 现行入口/指令 | 按现行入口、角色及维护边界复核 | No inherited CCB maintainer or fabricated CODEOWNERS assignment; real per-PR accountability and verified durable ownership criteria. |
| [README.md](../../README.md) | Cataclysm: Phantom Hope（大灾变：虚假的希望，CPH） | 现行入口/指令 | 按现行入口、角色及维护边界复核 | CPH native CDDA fork, selected CCB provenance, conditional release and support routes; current availability points to dated status. |
| [REPOSITORY_SETTINGS.md](../../REPOSITORY_SETTINGS.md) | CPH repository settings / 仓库设置 | 现行入口/指令 | 按现行入口、角色及维护边界复核 | Replaced the obsolete activation sequence with active-ruleset and candidate-specific verification; recorded sync-state switches separately from branch protection. |
| [SECURITY.md](../../SECURITY.md) | CPH security policy / 安全政策 | 现行入口/指令 | 按现行入口、角色及维护边界复核 | CPH private vulnerability URL only when GitHub form accepts reports; no public disclosure or fabricated private channel. |
| [SUPPORT.md](../../SUPPORT.md) | CPH support / 支持入口 | 现行入口/指令 | 按现行入口、角色及维护边界复核 | CPH Discussions, conditional Issues and security policy replace CCB release, community and support links. |
| [SYNC_EXCLUDED_PRS.md](../../SYNC_EXCLUDED_PRS.md) | 被剔除的上游 PR 记录 / Excluded Upstream PRs | 历史 | 历史内容不得误认作 CPH 当前规范 | Original CCB exclusion and sync log retained verbatim below a prominent CPH historical-boundary notice. |
| [TRANSLATION_CREDITS.md](../../TRANSLATION_CREDITS.md) | Translation credits / 翻译署名 | 现行入口/指令 | 按现行入口、角色及维护边界复核 | Inherited translator attribution kept; temporary verified CCB MO input distinguished from editable CPH PO/Transifex pipeline. |
| [ai/history/README.md](../../ai/history/README.md) | Inherited CCB governance evidence | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [android/AGENTS.md](../../android/AGENTS.md) | android/ agent instructions | 现行入口/指令 | 按现行入口、角色及维护边界复核 | 复核指向现行 AGENTS/项目入口；保留内容 |
| [android/app/jni/CMakeLists.txt](../../android/app/jni/CMakeLists.txt) | Output libmain.so; SDL3 dlsym's SDL_main from it | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
| [build-data/osx/LICENSE-libiconv.txt](../../build-data/osx/LICENSE-libiconv.txt) |                   GNU LESSER GENERAL PUBLIC LICENSE | 第三方/许可 | 无本轮改写需求；保留归属/原契约 | 保留原作者与许可证；原始字节和基线一致 |
| [build-scripts/AGENTS.md](../../build-scripts/AGENTS.md) | build-scripts/ agent instructions | 现行入口/指令 | 按现行入口、角色及维护边界复核 | 复核指向现行 AGENTS/项目入口；保留内容 |
| [data/AGENTS.md](../../data/AGENTS.md) | data/ agent instructions | 现行入口/指令 | 按现行入口、角色及维护边界复核 | 复核指向现行 AGENTS/项目入口；保留内容 |
| [data/CMakeLists.txt](../../data/CMakeLists.txt) | set(CATACLYSM_DATA_DIRS | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
| [data/changelog.txt](../../data/changelog.txt) | 0.I | 历史变更记录 | 无本轮改写需求；保留归属/原契约 | 保留原始变更记录，不当作 CPH 当前发布状态 |
| [data/json/LOADING_ORDER.md](../../data/json/LOADING_ORDER.md) | JSON Loading Order # | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 恢复仓内维护并保留双 ID、跟踪别名和安装行为 |
| [data/json/npcs/godco/NECC_INFO.md](../../data/json/npcs/godco/NECC_INFO.md) | Members of The Congregation | 现行技术参考 | 按现行入口、角色及维护边界复核 | 静态核对用途、入口、维护声明与链接；保留内容和兼容边界 |
| [data/json/npcs/refugee_center/FREE_MERCHANTS_INFO.md](../../data/json/npcs/refugee_center/FREE_MERCHANTS_INFO.md) | Shops | 现行技术参考 | 按现行入口、角色及维护边界复核 | 静态核对用途、入口、维护声明与链接；保留内容和兼容边界 |
| [data/lua/AGENTS.md](../../data/lua/AGENTS.md) | data/lua/ agent instructions | 现行入口/指令 | 按现行入口、角色及维护边界复核 | 修正遗漏的 CCB-Docs 现行维护指令，改为本仓稳定 ID/路径；保留继承的 CCB Lua 设计来源和运行契约 |
| [data/lua/LUA_FIRST_EOC_WORKFLOW.md](../../data/lua/LUA_FIRST_EOC_WORKFLOW.md) | Lua-first EOC capability workflow / Lua-first EOC 能力流程 | 现行技术参考 | 按现行入口、角色及维护边界复核 | 静态核对用途、入口、维护声明与链接；保留内容和兼容边界 |
| [data/lua/LUA_FIRST_PLATFORM.md](../../data/lua/LUA_FIRST_PLATFORM.md) | CPH Lua-first Platform v1 / CPH Lua-first 平台 v1 | 现行技术参考 | 按现行入口、角色及维护边界复核 | 保留架构与 ccb API；将 CCB PR 验收标为来源历史，文档同步转本仓 ID/路径 |
| [data/lua/README.md](../../data/lua/README.md) | CPH Lua-first Platform | 现行技术参考 | 按现行入口、角色及维护边界复核 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [data/lua/templates/complete/README.md](../../data/lua/templates/complete/README.md) | Complete Lua-first Platform template | 现行技术参考 | 按现行入口、角色及维护边界复核 | 静态核对用途、入口、维护声明与链接；保留内容和兼容边界 |
| [data/mods/AGENTS.md](../../data/mods/AGENTS.md) | data/mods/ agent instructions | 现行入口/指令 | 按现行入口、角色及维护边界复核 | Mod entrypoint split by JSON modinfo and Lua Platform mod.lua/main.lua; existing compatibility validation retained. |
| [data/mods/Backrooms/README.md](../../data/mods/Backrooms/README.md) | Backrooms CDDA | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/BombasticPerks/docs/contributing.md](../../data/mods/BombasticPerks/docs/contributing.md) | Contributing to Bombastic Perks | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/BombasticPerks/docs/expanding_with_mods.md](../../data/mods/BombasticPerks/docs/expanding_with_mods.md) | Expanding Bombastic Perks With Mods | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/DinoMod/DESIGN.md](../../data/mods/DinoMod/DESIGN.md) | Design Document SPOILERS AHEAD | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/DinoMod/README.md](../../data/mods/DinoMod/README.md) | DinoMod | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/Lua_First_Example/README.md](../../data/mods/Lua_First_Example/README.md) | Lua-First Bundled Example & Mod Developer Tutorial | 现行技术参考 | 按现行入口、角色及维护边界复核 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [data/mods/MA/README.md](../../data/mods/MA/README.md) | MA | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/Magiclysm/lore.md](../../data/mods/Magiclysm/lore.md) | History | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/Magiclysm/magic_balance.md](../../data/mods/Magiclysm/magic_balance.md) | Contents | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/Megafauna/readme.md](../../data/mods/Megafauna/readme.md) | **Description** | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/Migrated_Core/MIGRATION_REPORT.md](../../data/mods/Migrated_Core/MIGRATION_REPORT.md) | Lua-first migration report: Migrated_Core | 生成记录 | 按现行入口、角色及维护边界复核 | 保留官方迁移器输出；TODO 不表示迁移验收完成 |
| [data/mods/Migrated_Core/README.md](../../data/mods/Migrated_Core/README.md) | Migrated Core | 现行技术参考 | 按现行入口、角色及维护边界复核 | 静态核对用途、入口、维护声明与链接；保留内容和兼容边界 |
| [data/mods/MindOverMatter/GainingPowerSpoilers.md](../../data/mods/MindOverMatter/GainingPowerSpoilers.md) | Learning New Paths | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/MindOverMatter/NetherAttunementSpoilers.md](../../data/mods/MindOverMatter/NetherAttunementSpoilers.md) | Nether Attunement | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/MindOverMatter/NewPowerGuide.md](../../data/mods/MindOverMatter/NewPowerGuide.md) | Adding New Powers | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/MindOverMatter/PowerDescriptionSpoilers.md](../../data/mods/MindOverMatter/PowerDescriptionSpoilers.md) | Power Descriptions | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/MindOverMatter/README.md](../../data/mods/MindOverMatter/README.md) | Mind Over Matter | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/MindOverMatter/lore_spoilers.md](../../data/mods/MindOverMatter/lore_spoilers.md) | LORE | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/MindOverMatterNoKnacks/README.md](../../data/mods/MindOverMatterNoKnacks/README.md) | Mind Over Matter: Psychic Scream | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/No_Hope/CONTRIBUTING.md](../../data/mods/No_Hope/CONTRIBUTING.md) | No Hope Contributing | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/No_Hope/DIFFICULTY_OPTIONS.md](../../data/mods/No_Hope/DIFFICULTY_OPTIONS.md) | No Hope Difficulty Settings | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/Sky_Island/README.md](../../data/mods/Sky_Island/README.md) | Sky Islands | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/Sorcerer/README.md](../../data/mods/Sorcerer/README.md) | Sorcerer | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/Sorcerer/tools/spell_data.txt](../../data/mods/Sorcerer/tools/spell_data.txt) | [ | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/TEST_DATA/README.md](../../data/mods/TEST_DATA/README.md) | Test Data pseudo-mod # | 现行技术参考 | 按现行入口、角色及维护边界复核 | 静态核对用途、入口、维护声明与链接；保留内容和兼容边界 |
| [data/mods/XedraWood/README.md](../../data/mods/XedraWood/README.md) | XedraWood: Stone and Sorcery | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/Xedra_Evolved/README.md](../../data/mods/Xedra_Evolved/README.md) | Agents of Change | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/Xedra_Evolved/design_doc_spoilers.md](../../data/mods/Xedra_Evolved/design_doc_spoilers.md) | Design Docs | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/Xedra_Evolved/vampire_guide.md](../../data/mods/Xedra_Evolved/vampire_guide.md) | A Thirst for Blood | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/aftershock_exoplanet/doc/Hacking.md](../../data/mods/aftershock_exoplanet/doc/Hacking.md) | Hacking | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/aftershock_exoplanet/doc/crafting_system.md](../../data/mods/aftershock_exoplanet/doc/crafting_system.md) | Scrap Crafting System | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/aftershock_exoplanet/doc/lore/cyberpunk_future.md](../../data/mods/aftershock_exoplanet/doc/lore/cyberpunk_future.md) | Solar Corporations | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/aftershock_exoplanet/doc/lore/factions.md](../../data/mods/aftershock_exoplanet/doc/lore/factions.md) | United Interstellar Coordination Agency [UICA] | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/aftershock_exoplanet/doc/lore/organizations.md](../../data/mods/aftershock_exoplanet/doc/lore/organizations.md) | Organizations | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/aftershock_exoplanet/doc/lore/points_of_interest.md](../../data/mods/aftershock_exoplanet/doc/lore/points_of_interest.md) | Settlements | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/aftershock_exoplanet/doc/lore/ranged_weapon_balance.md](../../data/mods/aftershock_exoplanet/doc/lore/ranged_weapon_balance.md) | Weapon Damage  | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/aftershock_exoplanet/doc/lore/salus_4.md](../../data/mods/aftershock_exoplanet/doc/lore/salus_4.md) | Aftershock takes place in a desolate exoplanet named Salus IV at the very edges of the Orion arm.  | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/aftershock_exoplanet/doc/lore/timeline.md](../../data/mods/aftershock_exoplanet/doc/lore/timeline.md) | Earthbound Epoch and Early Space Age ( ???-2080 ) | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/aftershock_exoplanet/doc/suit_operating_time.md](../../data/mods/aftershock_exoplanet/doc/suit_operating_time.md) | Powered Armor Balance | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/aftershock_exoplanet/items/armor/exosuit/exosuit_guide.md](../../data/mods/aftershock_exoplanet/items/armor/exosuit/exosuit_guide.md) | Exosuit Guide | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/alt_map_key/README.md](../../data/mods/alt_map_key/README.md) | Alternative Map Key | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/classic_zombies/design-doc.md](../../data/mods/classic_zombies/design-doc.md) | The DDotDDD - Dark Days of the Dead Design Document | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/classic_zombies/place_names.md](../../data/mods/classic_zombies/place_names.md) | [ | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/folder_info.txt](../../data/mods/folder_info.txt) | The folders in this directory contain mods provided as part of CPH. Third party and private mod plac | 现行技术参考 | 按现行入口、角色及维护边界复核 | 修正随游戏提供的 Mod 项目名称，保留用户 Mod 路径 |
| [data/mods/hunvre/credits.txt](../../data/mods/hunvre/credits.txt) | Special thanks to: | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/hunvre/documentation/lore.md](../../data/mods/hunvre/documentation/lore.md) | Lore | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/hunvre/progress_tracker.md](../../data/mods/hunvre/progress_tracker.md) | Progress Tracker | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/immortal_path/GLOSSARY.md](../../data/mods/immortal_path/GLOSSARY.md) | 术语表 / Glossary | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/immortal_path/LANGUAGE_CONVENTION.md](../../data/mods/immortal_path/LANGUAGE_CONVENTION.md) | 灾变仙路 — 初期语言约定 / Language Convention (Early Stage) | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/immortal_path/doc/game-design.md](../../data/mods/immortal_path/doc/game-design.md) | 属性机制 | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/immortal_path/doc/lore.md](../../data/mods/immortal_path/doc/lore.md) | 设定 | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/immortal_path/doc/spell-design.md](../../data/mods/immortal_path/doc/spell-design.md) | 分类 | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/innawood/readme.md](../../data/mods/innawood/readme.md) | Goal | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/mods/translate-dialogue/README.md](../../data/mods/translate-dialogue/README.md) | Use tools/json_tools/update-translate-dialogue-mod.py to update the mod. | 独立 Mod 材料 | 无本轮改写需求；保留归属/原契约 | 保留独立组件原文和归属；不套用 CPH 治理/发布声明 |
| [data/raw/sokoban.txt](../../data/raw/sokoban.txt) | ###.# | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
| [data/sound/Menu_Sound_Test/soundpack.txt](../../data/sound/Menu_Sound_Test/soundpack.txt) | #Basic provided soundpack | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
| [doc/ASCII_ART.md](../../doc/ASCII_ART.md) | Making ASCII art for CDDA | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/Blank_Building_Template.txt](../../doc/Blank_Building_Template.txt) | json for buildings blank template | 现行技术参考 | 按现行入口、角色及维护边界复核 | 静态核对用途、入口、维护声明与链接；保留内容和兼容边界 |
| [doc/CHANGELOG_GUIDELINES.md](../../doc/CHANGELOG_GUIDELINES.md) | CPH changelog summary categories | 现行技术参考 | 按现行入口、角色及维护边界复核 | Retains category vocabulary while clarifying Summary is proposal, not active release/changelog proof. |
| [doc/DEVELOPER_FAQ.md](../../doc/DEVELOPER_FAQ.md) | CPH developer FAQ / 开发常见问题 | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | Old omdata/monsters hard-coded recipes replaced by current-source route, JSON guides, stable ID and test checks. |
| [doc/FREQUENTLY_MADE_SUGGESTIONS.md](../../doc/FREQUENTLY_MADE_SUGGESTIONS.md) | Suggestions and inherited design positions | 历史 | 历史内容不得误认作 CPH 当前规范 | Current CPH proposal route added; long inherited CDDA/CCB position list retained with explicit historical boundary. |
| [doc/GUN_NAMING_AND_INCLUSION.md](../../doc/GUN_NAMING_AND_INCLUSION.md) | Gun Naming and Inclusion Guidelines | 历史 | 历史内容不得误认作 CPH 当前规范 | Original gun-naming design reference retained; current CPH review must recheck data and does not inherit mandatory thresholds. |
| [doc/HOWTO_MASSAGE_MA_GUN_DATA.md](../../doc/HOWTO_MASSAGE_MA_GUN_DATA.md) | > **CPH historical reference / 历史参考。** This inherited CDDA/CCB document | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/HOW_YOU_CAN_HELP.md](../../doc/HOW_YOU_CAN_HELP.md) | How to help CPH / 如何参与 | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | Removed CDDA issue tracker, Google form, Discord roles and label links; CPH fork/main, public discussion and contribution route. |
| [doc/IN_REPO_MODS.md](../../doc/IN_REPO_MODS.md) | Bundled mods in CPH / 仓库内 Mod | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | CPH mod review and compatibility route replaces CleverRaven issue tracker and curator/removal authority assumptions. |
| [doc/ISSUE_TRIAGE.md](../../doc/ISSUE_TRIAGE.md) | CPH issue triage / CPH 问题分诊 | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | CPH-only conditional Issues triage, evidence, new-save boundary and actual labels replace inherited stable-save/priority assumptions. |
| [doc/JSON/ARTIFACTS.md](../../doc/JSON/ARTIFACTS.md) | Artifacts | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/BASECAMP.md](../../doc/JSON/BASECAMP.md) | Basecamp | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/CLIMBING.md](../../doc/JSON/CLIMBING.md) | Climbing Aids | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/DIMENSIONS.md](../../doc/JSON/DIMENSIONS.md) | Dimensions | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/EFFECTS_JSON.md](../../doc/JSON/EFFECTS_JSON.md) | Effects | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/EFFECT_ON_CONDITION.md](../../doc/JSON/EFFECT_ON_CONDITION.md) | Effect On Condition | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/EXAMINE.md](../../doc/JSON/EXAMINE.md) | Terrain/Furniture Examination Actions | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/FACTIONS.md](../../doc/JSON/FACTIONS.md) | NPC factions | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/FACTION_MISSIONS.md](../../doc/JSON/FACTION_MISSIONS.md) | Overview | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/GUIDE_COMESTIBLES.md](../../doc/JSON/GUIDE_COMESTIBLES.md) | Guide to add Comestibles | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/HELP_MENU.md](../../doc/JSON/HELP_MENU.md) | Help Menu | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/ITEM.md](../../doc/JSON/ITEM.md) | Subtypes | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/ITEM_CRAFT_AND_DISASSEMBLY.md](../../doc/JSON/ITEM_CRAFT_AND_DISASSEMBLY.md) | Recipes | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/ITEM_SPAWN.md](../../doc/JSON/ITEM_SPAWN.md) | Item spawn system | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/JSON_FLAGS.md](../../doc/JSON/JSON_FLAGS.md) | JSON Flags | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/JSON_INFO.md](../../doc/JSON/JSON_INFO.md) | JSON INFO | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/JSON_INHERITANCE.md](../../doc/JSON/JSON_INHERITANCE.md) | JSON Inheritance | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/JSON_LOADING_ORDER.md](../../doc/JSON/JSON_LOADING_ORDER.md) | 加载顺序文档的跟踪符号链接 | 兼容路径 | 旧 CCB 外部维护/迁移声明 | 保留原链接目标；文档安装实测 7 项 PASS |
| [doc/JSON/JSON_Mapping_Guides/Guide_for_beginning_mapgen.md](../../doc/JSON/JSON_Mapping_Guides/Guide_for_beginning_mapgen.md) | Guide for basic mapgen | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/JSON_Mapping_Guides/Guide_for_intermediate_mapgen.md](../../doc/JSON/JSON_Mapping_Guides/Guide_for_intermediate_mapgen.md) | Guide For Intermediate Mapgen | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/JSON_Mapping_Guides/JSON_ROOF_MAPGEN.md](../../doc/JSON/JSON_Mapping_Guides/JSON_ROOF_MAPGEN.md) | Adding Json Roof Guide | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/JSON_STYLE.md](../../doc/JSON/JSON_STYLE.md) | JSON Style Guide | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/JSON_TOOLS.md](../../doc/JSON/JSON_TOOLS.md) | JSON tools | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/MAGIC.md](../../doc/JSON/MAGIC.md) | Magic, Spells, and Enchantments | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/MAPGEN.md](../../doc/JSON/MAPGEN.md) | MAPGEN | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/MAP_SMASHING.md](../../doc/JSON/MAP_SMASHING.md) | Smashing | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/MARTIALART_JSON.md](../../doc/JSON/MARTIALART_JSON.md) | Martial arts and Techniques | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/MISSIONS_JSON.md](../../doc/JSON/MISSIONS_JSON.md) | Creating missions | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/MONSTERS.md](../../doc/JSON/MONSTERS.md) | MONSTERS | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/MONSTER_SPECIAL_ATTACKS.md](../../doc/JSON/MONSTER_SPECIAL_ATTACKS.md) | Monster special attacks | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/MOVE_MODE.md](../../doc/JSON/MOVE_MODE.md) | Movement Modes | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/MUTATIONS.md](../../doc/JSON/MUTATIONS.md) | Mutations | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/NPCs.md](../../doc/JSON/NPCs.md) | NPCs | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/OBSOLETION_AND_MIGRATION.md](../../doc/JSON/OBSOLETION_AND_MIGRATION.md) | Item migration | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/OPTIONS.md](../../doc/JSON/OPTIONS.md) | Game Options | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/OVERMAP.md](../../doc/JSON/OVERMAP.md) | Overmap Generation | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/PRACTICE_RECIPES.md](../../doc/JSON/PRACTICE_RECIPES.md) | Practice Recipes | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/PROFICIENCY.md](../../doc/JSON/PROFICIENCY.md) | Proficiencies | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/PROFICIENCY_LIST.md](../../doc/JSON/PROFICIENCY_LIST.md) | Proficiencies List | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/REGION_LAYOUT.md](../../doc/JSON/REGION_LAYOUT.md) | Region Layout | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/REGION_SETTINGS.md](../../doc/JSON/REGION_SETTINGS.md) | Region Settings | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/TER_FURN_TRANSFORM.md](../../doc/JSON/TER_FURN_TRANSFORM.md) | Terrain and Furniture Transforms | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/VEHICLES_JSON.md](../../doc/JSON/VEHICLES_JSON.md) | Vehicle prototypes | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/VITAMIN.md](../../doc/JSON/VITAMIN.md) | Vitamins | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/WEATHER_TYPE.md](../../doc/JSON/WEATHER_TYPE.md) | Weather Types | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/JSON/WOUNDS.md](../../doc/JSON/WOUNDS.md) | Wounds | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/MANUAL_OF_STYLE.md](../../doc/MANUAL_OF_STYLE.md) | Manual Of Style | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/MODDING.md](../../doc/MODDING.md) | Modding guide | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 旧 JSON manifest 规则被说成所有 Mod 前提；区分 Lua Platform 与 JSON 兼容内容 |
| [doc/MOD_COMPATIBILITY.md](../../doc/MOD_COMPATIBILITY.md) | Mod Compatibility | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 明确 JSON/EOC 兼容范围；不把旧 mod_interactions 当作 Lua 公共 API |
| [doc/PLAYER_ACTIVITY.md](../../doc/PLAYER_ACTIVITY.md) | Activities | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/RELEASE_DIFF.md](../../doc/RELEASE_DIFF.md) | CPH release diff / CPH 发行差异 | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | Fixed CPH refs and read-only diff replace old CDDA tags and master checkout; initial-baseline case explicit. |
| [doc/RELEASE_PROCESS.md](../../doc/RELEASE_PROCESS.md) | CPH release preparation / CPH 发布准备 | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | CPH four-platform and controlled release acceptance replace obsolete CDDA 0.G/0.H branch instructions. |
| [doc/SOUNDPACKS.md](../../doc/SOUNDPACKS.md) | Soundpacks | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/TESTING_YOUR_CHANGES.md](../../doc/TESTING_YOUR_CHANGES.md) | Testing your changes and making sure they work as expected | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 移除所有发布包均带 formatter 及仅靠可执行文件位置选数据的假设；要求匹配提交和独立数据目录 |
| [doc/TILESET.md](../../doc/TILESET.md) | TILESETS | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/TRANSLATING.md](../../doc/TRANSLATING.md) | Translating CPH / 翻译 CPH | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | Keeps inherited gettext developer examples and attribution, removes CCB Transifex submission route and old weekly update claim; pins MO/PO boundary. |
| [doc/TRANSLATING_MOD.md](../../doc/TRANSLATING_MOD.md) | Translating a mod for CPH / 翻译 CPH Mod | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | Corrects nonexistent extractor -o flag using source -r contract; separates mod PO/MO and JSON/Lua mod entrypoints. |
| [doc/USER_INTERFACE_AND_ACCESSIBILITY.md](../../doc/USER_INTERFACE_AND_ACCESSIBILITY.md) | User Interface / Accessibility | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/WIDGETS.md](../../doc/WIDGETS.md) | Widgets | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/c++/CODE_STYLE.md](../../doc/c++/CODE_STYLE.md) | Code Style Guide | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/c++/COMPILER_SUPPORT.md](../../doc/c++/COMPILER_SUPPORT.md) | CPH compiler and platform contract | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 旧最低编译器表、发行版与市场份额不能证明 CPH 支持；改为 C++17 和当前 W/L 配置与证据边界 |
| [doc/c++/COMPILING-CMAKE-VCPKG.md](../../doc/c++/COMPILING-CMAKE-VCPKG.md) | CPH CMake and vcpkg builds | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 旧 CMake 支持声明和路径指导过时；使用当前 MSVC/preset/锁定依赖契约 |
| [doc/c++/COMPILING-CMAKE.md](../../doc/c++/COMPILING-CMAKE.md) | Building CPH with CMake | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 旧文误称 CMake 非官方且仅支持 SDL2；按现行 presets/options 重写，区分 E4 历史状态字段与当前目标 |
| [doc/c++/COMPILING-CYGWIN.md](../../doc/c++/COMPILING-CYGWIN.md) | Compilation guide for 64 bit Windows (using Cygwin) | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/c++/COMPILING-DEVCONTAINER.md](../../doc/c++/COMPILING-DEVCONTAINER.md) | CPH development containers | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 旧截图要求修改不存在的 Dockerfile 段；改为现有三种配置与 SDL2 环境边界 |
| [doc/c++/COMPILING-FLATPAK.md](../../doc/c++/COMPILING-FLATPAK.md) | Compiling Flatpak | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/c++/COMPILING-MSYS.md](../../doc/c++/COMPILING-MSYS.md) | Compilation guide for 64-bit Windows (using MSYS2) | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 旧 CDDA 下载、仓库及 Windows 7 等支持声明误导；改 CPH 来源和按实际工具链验证 |
| [doc/c++/COMPILING-VS-VCPKG.md](../../doc/c++/COMPILING-VS-VCPKG.md) | Compilation guide for Windows (using Visual Studio and vcpkg) | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 旧上游测试被当作现行证据、vcpkg 使用移动分支；区分继承记录并锁定当前政策提交 |
| [doc/c++/COMPILING.md](../../doc/c++/COMPILING.md) | Compiling | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 旧 clone 和 Homebrew 指向上游游戏下载；纠正来源，保留本地替代构建配方及未验证范围 |
| [doc/c++/DEVELOPER_TOOLING.md](../../doc/c++/DEVELOPER_TOOLING.md) | Developer Tooling | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 旧 clang-tidy CI 已删除；保留本地工具步骤并移除已部署检查声明 |
| [doc/c++/JSON_INTERFACE.md](../../doc/c++/JSON_INTERFACE.md) | The JSON Interface | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/c++/PERFORMANCE.md](../../doc/c++/PERFORMANCE.md) | Performance measurement | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/c++/POINTS_COORDINATES.md](../../doc/c++/POINTS_COORDINATES.md) | Points, tripoints, and coordinate systems | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/c++/TESTING.md](../../doc/c++/TESTING.md) | Testing Cataclysm | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/design-balance-lore/ARMOR_BALANCE_AND_DESIGN.md](../../doc/design-balance-lore/ARMOR_BALANCE_AND_DESIGN.md) | Armor Balance And Design | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/design-balance-lore/CONSTRUCTION_BALANCE.md](../../doc/design-balance-lore/CONSTRUCTION_BALANCE.md) | Construction Balance | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/design-balance-lore/GAME_BALANCE.md](../../doc/design-balance-lore/GAME_BALANCE.md) | Game Balance | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/design-balance-lore/LORE_FAQ.md](../../doc/design-balance-lore/LORE_FAQ.md) | Faction Lore | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/design-balance-lore/PORTAL_STORM_BALANCE_AND_DESIGN.md](../../doc/design-balance-lore/PORTAL_STORM_BALANCE_AND_DESIGN.md) | Portal Storm Design | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/design-balance-lore/POSTAPOC_PRICE_GUIDE.md](../../doc/design-balance-lore/POSTAPOC_PRICE_GUIDE.md) | Post-apocalypse Price Guide | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/design-balance-lore/STEEL_CRAFTING.md](../../doc/design-balance-lore/STEEL_CRAFTING.md) | Making and working with steel grades | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/design-balance-lore/VARIANTS.md](../../doc/design-balance-lore/VARIANTS.md) | Variants | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/design-balance-lore/batteries_and_electricity.md](../../doc/design-balance-lore/batteries_and_electricity.md) | Voltage, Current, Capacity | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/design-balance-lore/design-balance.md](../../doc/design-balance-lore/design-balance.md) | Design - Overview of game balance principles | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/design-balance-lore/design-doc.md](../../doc/design-balance-lore/design-doc.md) | Design - Design Doc Overview | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/design-balance-lore/design-gameplay.md](../../doc/design-balance-lore/design-gameplay.md) | Design - Gameplay | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/design-balance-lore/design-user-experience.md](../../doc/design-balance-lore/design-user-experience.md) | Design - User Experience | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/design-balance-lore/lore-background.md](../../doc/design-balance-lore/lore-background.md) | Lore - Background Story | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/design-balance-lore/lore-factions.md](../../doc/design-balance-lore/lore-factions.md) | Lore - CDDA Faction Lore and Design Document | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/design-balance-lore/lore.md](../../doc/design-balance-lore/lore.md) | Lore - Setting | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/design-balance-lore/melee_weapons/MELEE_BALANCE_SPREADSHEET.md](../../doc/design-balance-lore/melee_weapons/MELEE_BALANCE_SPREADSHEET.md) | Melee Balance Spreadsheet | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/design-balance-lore/technology.md](../../doc/design-balance-lore/technology.md) | Lore - Technology in the Cataclysm | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/development_process.md](../../doc/development_process.md) | The DDA Development Process | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/migration/classification-report.md](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/1057a15bf802572b7497ffd9617083a9b6935321/doc/migration/classification-report.md) | Legacy Markdown classification report | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/migration/history-assessment.md](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/1057a15bf802572b7497ffd9617083a9b6935321/doc/migration/history-assessment.md) | Documentation history assessment | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [doc/reviewing_PR_guide.md](../../doc/reviewing_PR_guide.md) | Reviewing CPH pull requests / 审阅 PR | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | CPH review checklist and required gate evidence replace CDDA Discord role and senior lead authority. |
| [doc/unicode_chars_palette.txt](../../doc/unicode_chars_palette.txt) | Unicode chars palette: | 现行技术参考 | 按现行入口、角色及维护边界复核 | 静态核对用途、入口、维护声明与链接；保留内容和兼容边界 |
| [doc/user-guides/COLOR.md](../../doc/user-guides/COLOR.md) | Colors | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [doc/user-guides/FONT_OPTIONS.md](../../doc/user-guides/FONT_OPTIONS.md) | Configuring Fonts | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [docs/README.md](../../docs/README.md) | CPH 文档入口 | 现行入口/指令 | 按现行入口、角色及维护边界复核 | 统一 CPH 贡献、维护与报告入口；保留来源和人工审查边界 |
| [docs/project/design-differences.md](../../docs/project/design-differences.md) | Source ancestry and intentional differences | CPH 项目文档 | 按现行入口、角色及维护边界复核 | Clarified local ledger contract versus dated remote protection evidence. |
| [docs/project/documentation-review.md](../../docs/project/documentation-review.md) | CPH 文档与工作区整理审计（2026-09-27 UTC） | CPH 项目文档 | 按现行入口、角色及维护边界复核 | 区分需求、操作、带日期状态和历史回证；链接及命令路径复核 |
| [docs/project/execution-spec.md](../../docs/project/execution-spec.md) | CPH：Codex 分阶段实施规格 v1.0 | CPH 项目文档 | 按现行入口、角色及维护边界复核 | Added current entry note; R01-R18 unchanged; original initialization assumptions retained as history. |
| [docs/project/fork-deployment.md](../../docs/project/fork-deployment.md) | E2 个人 CDDA fork 实际执行回证 | CPH 项目文档 | 按现行入口、角色及维护边界复核 | Labeled 2026-09-26 seed deployment and Actions-disabled state as historical; linked current status and local evidence boundary. |
| [docs/project/fork-initialization.md](../../docs/project/fork-initialization.md) | E2 read-only preparation and fork deployment | CPH 项目文档 | 按现行入口、角色及维护边界复核 | Updated known target example and distinguished initial Actions shutdown from later controlled workflows. |
| [docs/project/identity-audit.md](../../docs/project/identity-audit.md) | E3 身份与四平台构建输入审计（U 基线） | CPH 项目文档 | 按现行入口、角色及维护边界复核 | Clarified locked U scope and no Windows/macOS/Android runtime proof. |
| [docs/project/inherited-workflows.md](../../docs/project/inherited-workflows.md) | E0 继承工作流审计与初始化隔离 | CPH 项目文档 | 按现行入口、角色及维护边界复核 | Corrected primary spec link and limited zero-active-workflow claim to initial inherited-workflow isolation. |
| [docs/project/linux-probe.md](../../docs/project/linux-probe.md) | Linux E1 原生构建与最小运行探针 | CPH 项目文档 | 按现行入口、角色及维护边界复核 | Clarified fixed local E1 scope and workspace-local evidence. |
| [docs/project/linux-test-identity.md](../../docs/project/linux-test-identity.md) | E3 Linux 仅测试身份 | CPH 项目文档 | 按现行入口、角色及维护边界复核 | Replaced occupied failed run directory with a fresh output template bound to install prefix; retained original run4 receipt. |
| [docs/project/local-merge-gates.md](../../docs/project/local-merge-gates.md) | E4 本地可信证据聚合与保护面检查 | CPH 项目文档 | 按现行入口、角色及维护边界复核 | Scoped the offline checker’s old unrun/undeployed claims to its initial contract and linked present remote acceptance to status.md. |
| [docs/project/local-sync.md](../../docs/project/local-sync.md) | Local CCB integration rehearsal | CPH 项目文档 | 按现行入口、角色及维护边界复核 | Removed obsolete unknown-target/App prerequisite; distinguished deployed scoped-token controller from local-only rehearsal. |
| [docs/project/operator-controls.md](../../docs/project/operator-controls.md) | E7 本地暂停与封禁前置检查 | CPH 项目文档 | 按现行入口、角色及维护边界复核 | Directed live remote operator control to remote-sync and dated status. |
| [docs/project/other-platform-probes.md](../../docs/project/other-platform-probes.md) | E1 Windows, macOS and Android probes | CPH 项目文档 | 按现行入口、角色及维护边界复核 | Preserved local Windows PowerShell NOT_RUN while acknowledging separate hosted CI attempt. |
| [docs/project/preflight.md](../../docs/project/preflight.md) | E0 read-only preflight | CPH 项目文档 | 按现行入口、角色及维护边界复核 | Used explicit authorized target in current example without implying remote write capability. |
| [docs/project/release-contract.md](../../docs/project/release-contract.md) | E6 本地开发版契约 | CPH 项目文档 | 按现行入口、角色及维护边界复核 | Recorded known fork/CI target and continuing release, identity, signing blockers. |
| [docs/project/remote-sync.md](../../docs/project/remote-sync.md) | CCB remote synchronization | CPH 项目文档 | 按现行入口、角色及维护边界复核 | Added a dated operational readback for the active rule and sync-state revision 3 before the earlier disabled-rule snapshot. |
| [docs/project/resume.md](../../docs/project/resume.md) | 缺失条件与恢复入口 | CPH 项目文档 | 按现行入口、角色及维护边界复核 | Added current recovery state, updated per-candidate conditions and switch status; preserved the 03:31 and initial deployment paragraphs under historical headings. |
| [docs/project/status.md](../../docs/project/status.md) | CPH 本轮实施与交接（2026-09-26） | CPH 项目文档 | 按现行入口、角色及维护边界复核 | Added a dated current remote snapshot with protected main, PR #1/#2 acceptance, revision 3 switch state and PR #3 blocker; retained the 03:31 and 2026-09-26 results as historical snapshots. |
| [docs/project/translation-inputs.md](../../docs/project/translation-inputs.md) | Baseline translation input | CPH 项目文档 | 按现行入口、角色及维护边界复核 | Clarified local input boundary and used fresh workspace-derived output path. |
| [docs/project/upstreams.md](../../docs/project/upstreams.md) | Locked initial history | CPH 项目文档 | 按现行入口、角色及维护边界复核 | Replaced stale no-target conclusion with recorded native fork while retaining B/U provenance. |
| [docs/project/workspace-layout.md](../../docs/project/workspace-layout.md) | CPH 工作区布局与路径边界 | CPH 项目文档 | 按现行入口、角色及维护边界复核 | 明确目录职责；记录已完成五个工作树和三个失败 E3 目录归档、原路径兼容链接、内容核验及原始回证保留边界 |
| [doxygen_doc/doxygen_conf.txt](../../doxygen_doc/doxygen_conf.txt) | Doxyfile 1.8.4 | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
| [gfx/ASCIITileset/tileset.txt](../../gfx/ASCIITileset/tileset.txt) | #RETRO ASCII TILESET | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
| [gfx/Larwick_Overmap/tileset.txt](../../gfx/Larwick_Overmap/tileset.txt) | #Name of the tileset | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
| [lang/CMakeLists.txt](../../lang/CMakeLists.txt) | Generate cataclysm-dda.pot | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
| [lang/notes/README_all_translators.md](../../lang/notes/README_all_translators.md) | Inherited gettext notes for CPH translators | 现行技术参考 | 旧 CCB 外部维护/迁移声明 | CCB-Docs moved stub replaced with CPH format reference; CDDA PO header examples and translator attribution retained as history. |
| [lang/notes/de.txt](../../lang/notes/de.txt) | This file contains notes/discussion regarding translation for German, written in German. | 继承翻译参考 | 无本轮改写需求；保留归属/原契约 | 保留语言团队建议与归属；当前贡献流程另见 TRANSLATING |
| [lang/notes/ru-notes.md](../../lang/notes/ru-notes.md) | Основы | 继承翻译参考 | 无本轮改写需求；保留归属/原契约 | 保留语言团队建议与归属；当前贡献流程另见 TRANSLATING |
| [src/AGENTS.md](../../src/AGENTS.md) | src/ agent instructions | 现行入口/指令 | 按现行入口、角色及维护边界复核 | 复核指向现行 AGENTS/项目入口；保留内容 |
| [src/CMakeLists.txt](../../src/CMakeLists.txt) | Configure a target's Lua Platform compile definition and optional runtime dependency. | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
| [src/chkjson/CMakeLists.txt](../../src/chkjson/CMakeLists.txt) | test chain | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
| [src/lua/CMakeLists.txt](../../src/lua/CMakeLists.txt) | Keep the bundled runtime on Lua's standard C ABI.  Make also compiles these | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
| [src/lua/LICENSE.md](../../src/lua/LICENSE.md) | Copyright © 1994–2025 Lua.org, PUC-Rio. | 第三方/许可 | 无本轮改写需求；保留归属/原契约 | 保留原作者与许可证；原始字节和基线一致 |
| [src/lua/README.md](../../src/lua/README.md) | This folder contains the Lua 5.4.8 library source code, compiled into builds | 现行技术参考 | 按现行入口、角色及维护边界复核 | 本仓 vendoring 说明更新 CPH 归属；保留上游 Lua 版本、SHA256 及许可证 |
| [src/sol/CMakeLists.txt](../../src/sol/CMakeLists.txt) | HACK: "/.." here keeps the generated path layout compatible with existing includes. | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
| [src/sol/changes.txt](../../src/sol/changes.txt) | Changes done to sol.hpp header: | 历史变更记录 | 无本轮改写需求；保留归属/原契约 | 保留原始变更记录，不当作 CPH 当前发布状态 |
| [src/third-party/CMakeLists.txt](../../src/third-party/CMakeLists.txt) | Defaults to CMAKE_SOURCE_DIR for in-tree builds; Android sets it explicitly. | 第三方/许可 | 无本轮改写需求；保留归属/原契约 | 保留原作者与许可证；原始字节和基线一致 |
| [src/third-party/asio/asio/LICENSE_1_0.txt](../../src/third-party/asio/asio/LICENSE_1_0.txt) | Boost Software License - Version 1.0 - August 17th, 2003 | 第三方/许可 | 无本轮改写需求；保留归属/原契约 | 保留原作者与许可证；原始字节和基线一致 |
| [src/third-party/asio/asio/src/doc/boost_bind_dox.txt](../../src/third-party/asio/asio/src/doc/boost_bind_dox.txt) | /** | 第三方/许可 | 无本轮改写需求；保留归属/原契约 | 保留原作者与许可证；原始字节和基线一致 |
| [src/third-party/asio/asio/src/doc/model_dox.txt](../../src/third-party/asio/asio/src/doc/model_dox.txt) | // | 第三方/许可 | 无本轮改写需求；保留归属/原契约 | 保留原作者与许可证；原始字节和基线一致 |
| [src/third-party/asio/asio/src/doc/noncopyable_dox.txt](../../src/third-party/asio/asio/src/doc/noncopyable_dox.txt) | /** | 第三方/许可 | 无本轮改写需求；保留归属/原契约 | 保留原作者与许可证；原始字节和基线一致 |
| [src/third-party/asio/asio/src/doc/std_exception_dox.txt](../../src/third-party/asio/asio/src/doc/std_exception_dox.txt) | /** | 第三方/许可 | 无本轮改写需求；保留归属/原契约 | 保留原作者与许可证；原始字节和基线一致 |
| [src/third-party/asio/asio/src/examples/cpp03/tutorial/daytime_dox.txt](../../src/third-party/asio/asio/src/examples/cpp03/tutorial/daytime_dox.txt) | // | 第三方/许可 | 无本轮改写需求；保留归属/原契约 | 保留原作者与许可证；原始字节和基线一致 |
| [src/third-party/asio/asio/src/examples/cpp03/tutorial/index_dox.txt](../../src/third-party/asio/asio/src/examples/cpp03/tutorial/index_dox.txt) | // | 第三方/许可 | 无本轮改写需求；保留归属/原契约 | 保留原作者与许可证；原始字节和基线一致 |
| [src/third-party/asio/asio/src/examples/cpp03/tutorial/timer_dox.txt](../../src/third-party/asio/asio/src/examples/cpp03/tutorial/timer_dox.txt) | // | 第三方/许可 | 无本轮改写需求；保留归属/原契约 | 保留原作者与许可证；原始字节和基线一致 |
| [src/third-party/imgui/LICENSE.txt](../../src/third-party/imgui/LICENSE.txt) | The MIT License (MIT) | 第三方/许可 | 无本轮改写需求；保留归属/原契约 | 保留原作者与许可证；原始字节和基线一致 |
| [src/third-party/snmalloc/README.md](../../src/third-party/snmalloc/README.md) | Include hierarchy | 第三方/许可 | 无本轮改写需求；保留归属/原契约 | 保留原作者与许可证；原始字节和基线一致 |
| [src/third-party/snmalloc/stl/README.md](../../src/third-party/snmalloc/stl/README.md) | Standard Library Implementation | 第三方/许可 | 无本轮改写需求；保留归属/原契约 | 保留原作者与许可证；原始字节和基线一致 |
| [src/third-party/snmalloc/stl/cxx/README.md](../../src/third-party/snmalloc/stl/cxx/README.md) | CXX Standard Library | 第三方/许可 | 无本轮改写需求；保留归属/原契约 | 保留原作者与许可证；原始字节和基线一致 |
| [src/third-party/snmalloc/stl/gnu/README.md](../../src/third-party/snmalloc/stl/gnu/README.md) | Self-Vendored STL Using GNU Language Extensions | 第三方/许可 | 无本轮改写需求；保留归属/原契约 | 保留原作者与许可证；原始字节和基线一致 |
| [src/third-party/zstd/README.md](../../src/third-party/zstd/README.md) | Building | 第三方/许可 | 无本轮改写需求；保留归属/原契约 | 保留原作者与许可证；原始字节和基线一致 |
| [tests/AGENTS.md](../../tests/AGENTS.md) | tests/ agent instructions | 现行入口/指令 | 按现行入口、角色及维护边界复核 | 复核指向现行 AGENTS/项目入口；保留内容 |
| [tests/CMakeLists.txt](../../tests/CMakeLists.txt) | cmake_minimum_required(VERSION 3.20) | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
| [tools/AGENTS.md](../../tools/AGENTS.md) | tools/ agent instructions | 现行入口/指令 | 按现行入口、角色及维护边界复核 | 复核指向现行 AGENTS/项目入口；保留内容 |
| [tools/agent/requirements.txt](../../tools/agent/requirements.txt) | PyYAML==6.0.2 | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
| [tools/clang-tidy-plugin/CMakeLists.txt](../../tools/clang-tidy-plugin/CMakeLists.txt) | We need to turn off exceptions and RTTI to match the LLVM build. | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
| [tools/format/CMakeLists.txt](../../tools/format/CMakeLists.txt) | include(ExternalProject) | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
| [tools/iwyu/bad_files.txt](../../tools/iwyu/bad_files.txt) | This file is fed to grep -v -f to select the files that should be skipped | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
| [tools/json_api/README.md](../../tools/json_api/README.md) | JSON and EOC contract inventories | 现行技术参考 | 按现行入口、角色及维护边界复核 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [tools/json_tools/requirements.txt](../../tools/json_tools/requirements.txt) | Pillow>=9.0.0  # for the generate_overmap_sprites.py | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
| [tools/llama/README.md](../../tools/llama/README.md) | Using llama to accelerate your build | 历史 | 历史内容不得误认作 CPH 当前规范 | 保留原文/历史决定；现行入口另行说明，不作为当前政策或同步文档 |
| [tools/lua_api/README.md](../../tools/lua_api/README.md) | Lua-first Platform tools | 现行技术参考 | 按现行入口、角色及维护边界复核 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [tools/lua_api/fixtures/native_probe/README.md](../../tools/lua_api/fixtures/native_probe/README.md) | Optional native-module acceptance probe | 现行技术参考 | 按现行入口、角色及维护边界复核 | 修订仓内维护、项目身份、过时步骤或链接；核对相应源码/工具入口 |
| [tools/lua_api/requirements.txt](../../tools/lua_api/requirements.txt) | jsonschema==4.26.0 | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
| [tools/spell_checker/dictionary.txt](../../tools/spell_checker/dictionary.txt) | AA | 配置/运行数据 | 无本轮改写需求；保留归属/原契约 | 识别为非说明文件，保留现行构建/依赖/资源契约；本轮未改 |
