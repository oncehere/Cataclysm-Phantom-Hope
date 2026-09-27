# CPH：Codex 分阶段实施规格 v1.0

**阅读定位（2026-09-27 UTC）：**第 1 节的 R01—R18 仍是当前需求；本文其余部分保留 2026-09-26 初始实施时的假设、建议和任务顺序。其后用户已明确授权 `oncehere/Cataclysm-Phantom-Hope`，原生 CDDA fork 与保留历史的 `main` 已建立，受控 CI/sync 入口也已部署。文中“目标尚未给出”“尚无 CI”等句子是当时的初始化条件，已由后续明确决定和实施回证取代，不应再次执行建仓或据此否认现有目标。当前运行状态与恢复步骤先读 [status.md](status.md) 和 [resume.md](resume.md)；本地路径边界见 [workspace-layout.md](workspace-layout.md)。本说明不修改任何 R 需求。

- 日期：2026-09-26。
- 中文工作名：虚假的希望；英文工作名：Cataclysm: Phantom Hope，简称 CPH。正式名称、仓库名和永久应用 ID 尚未最终确认。
- 文档用途：把已经确认的需求和两轮审查收敛为可以交给 Codex 执行的任务。不是已经执行完成的项目，也不是可以直接运行的工作流代码。
- 本次核验范围：完整读取原计划、上一轮 review 和历史 Git 小实验结果；重新读取锁定 CCB 快照的通用 CI、翻译工作流；复核相关官方文档。未创建或修改远程仓库，未编译或实测游戏。

## 0. 给执行者的入口

请实施，不要只复述计划。先检查真实工作区、现有指令、历史对象和工具条件，然后在授权范围内完成可验证的小步改动。按依赖推进，不必每一步重新征求常规确认；确有未授权或缺失条件时，只暂停依赖它的动作，继续其他安全工作。

本规格是本轮执行的主文档。原计划和旧 review 是背景证据，不能当成两个同时生效、互相冲突的任务列表。用户后续明确指示优先；不能将本文的“建议默认值”说成用户此前已经逐项确认的要求。真实源码和实际运行结果决定事实，不能用文档描述替代核验。

正式远程目标尚未在当前需求中给出。不要从聊天显示名、机器用户名或账号中随意选一个仓库开始修改。允许先在用户授权的本地工作区完成只读探查、隔离验证、脚本与测试开发。

## 1. 已确认、不可擅自更改的需求

| ID | 要求 |
|---|---|
| R01 | 个人 GitHub 账号下的长期公开项目，具有独立技术、界面和功能路线；不以成立组织或组建团队为前置条件。 |
| R02 | GitHub 上必须显示为 CDDA 的 fork；不能改成 CCB 的 fork 或无 fork 关系的独立仓库。 |
| R03 | 从与 CCB 相同的 CDDA 历史起点出发，沿原有历史纳入选定 CCB 基线；保留来源和作者记录。 |
| R04 | 持续跟进 CCB 一个指定主要开发分支的全部更新；其他分支和未合入 PR 不自动引入。 |
| R05 | CDDA 只按需引入选定改进及必要依赖，不全面同步 CDDA。 |
| R06 | 本项目核心设计优先；允许延迟、适配、保留自有实现或撤销冲突行为。“全部整合”不等于照搬全部最终行为。 |
| R07 | AI 仅由用户主动启动。普通定时同步、构建、检查、发布可以无人值守，但不能自动调用 AI。 |
| R08 | 用户授权范围内，完成改动并通过约定检查即可自动合入；未授权范围和新设计取舍必须暂停并报告。 |
| R09 | Windows、Linux 构建及约定检查是合入硬门槛；macOS、Android 的暂时失败不自动阻止合入。 |
| R10 | 当前交付开发版，暂不交付稳定版。未来稳定版必须由用户明确确认。 |
| R11 | 每天一次发布检查。有未成功发布的新提交才尝试；失败候选仍可重试；没有新变化不重复发布。 |
| R12 | Windows、Linux、macOS、Android 四平台的当轮包齐备并通过约定检查后，统一自动公开开发版；任何必需平台不满足条件就不发布本轮。 |
| R13 | 四个平台安装包属于首期范围，iOS 后置。优先维护 Windows、Linux 不等于可以不出另两个平台的包。 |
| R14 | 首期以新开存档为支持路径，不承诺 CCB 旧档迁移。自身稳定版本之间允许断档；不因此授权覆盖、删除他人存档。 |
| R15 | 与 CCB 并行安装、分别更新，隔离安装身份和数据目录；安装、启动、升级和卸载不得破坏 CCB 程序、配置及存档。 |
| R16 | 用户有 Android 实机，没有 Mac。macOS 必须构建、打包并通过约定自动检查，但不以人工实机游玩验证作为首期发布前置条件；未验证范围必须说明。 |
| R17 | 第一阶段建立基线、更新与四平台交付能力，不同时进行桌面 SDL3 迁移、CDDA 新 UI 移植、玩法扩展或 iOS 支持。已继承的 SDL3 等功能不因此被删除或回退。 |
| R18 | 未授权购买服务、无限使用 API 或索取/公开密钥。缺资源应如实记录，不以关闭检查冒充完成。 |

## 2. 本次 review 对旧文档的必要修正

### 2.1 阻塞条件必须对应动作

旧 review 的“全部 P1 关闭前不启用自动合入或发布”过于宽泛，不能照抄。

| 条件不足 | 阻塞什么 | 不应自动阻塞什么 |
|---|---|---|
| 目标仓库不明确或没有远程写权限 | 远程创建、推送、设置修改及实际部署 | 授权本地工作区的只读核验、隔离实验、实现与本地测试 |
| Windows/Linux 必需检查未真实通过 | 自动合入、依赖这次提交的正式开发版发布 | 功能分支开发、修复、非公开测试 |
| 验收器不可信或分支保护未生效 | 自动合入 | 低权限构建、测试与权限配置代码开发 |
| macOS/Android 构建失败 | 当轮四平台公开发布 | 满足 Windows/Linux 门槛且已授权的改动合入 |
| Android 发布密钥或长期应用 ID 未就绪 | 正式身份签名及公开发布 | 本地构建、隔离测试、签名接口实现 |
| 翻译输入不可取得 | 依赖该输入的检查和发布；若必需 W/L 检查因此失败，也阻塞合入 | 无关工具开发、使用明确标注测试样本的单元测试 |
| Android 每日运行验证方式未确定 | 按未确定规则宣称发布就绪 | 构建、ABI/资源检查、模拟器可行性验证和其他平台工作 |

### 2.2 工作流能运行，不等于它满足 PR 必需检查

当前 GitHub 官方文档明确：`workflow_dispatch` 触发的普通 workflow job checks 不直接满足 PR 的 required status checks。即使指定了 PR head SHA，也不能仅凭相同 SHA 或同名绿色状态认定合入门槛已打通。[S1]

首选实现为：受限 GitHub App 安装令牌创建/更新 PR，触发适用的 `pull_request` CI，再由经过验证的门槛控制合入。App 是仓库自动化身份，不要求另建常驻服务。`GITHUB_TOKEN` 所触发的 PR 在当前规则下可能需要批准，不能把它当作天然无人值守链路。[S2]

显式 dispatch 可以用于基线探针、手动测试和发布。若用于合入门槛后端，必须有一个符合平台规则的可信检查发布者，并以实际受保护 PR 证明有效；不是简单把 job 改名。不得通过删掉 required checks 来解决事件不兼容。

### 2.3 不要配置与原历史相冲突的保护

CCB 整合保留 merge 历史，不能同时启用 `Require linear history` 或把所有 PR 强制 squash/rebase。线性历史会阻止 merge commits。[S3]

不要默认要求所有继承历史提交重新签名，也不要强行改写上游作者和 SHA。普通已授权任务不应新增“每个 PR 必须人工批准”的全局门槛；对控制规则变更的明确授权则继续保留。

### 2.4 安全措施不是绝对保证

候选代码不能自行修改可信门槛；构建不能接触签名/仓库写入密钥；这些需要平台权限和任务隔离，不是写一句 AGENTS 规则就完成。[S4]

“有 checksum”“来自某个 workflow”“开了 immutable releases”分别只能证明部分属性。GitHub 的 immutable releases 仍允许修改标题、说明、prerelease/latest 标记，所以它不能单独保证“稳定版只能人工批准”。[S5]

不声称任何有限测试都能发现所有语义冲突或证明候选代码没有恶意。报告控制覆盖与剩余风险，不用“安全隔离已完成”替代具体证据。

### 2.5 不把实现建议变成新增硬需求

默认分支名字、App 方案、原生安装器、所有 CPU 架构、所有语言 100% 翻译、每天 Android ARM64 实机运行，都不是用户此前逐项确认的硬需求。

但不能以此为由删掉四平台出包、Windows/Linux 合入门槛、已约定测试或数据隔离。具体测试方案应在实现初期按实际资源固定；尚未确定的高影响边界单列，不用假通过跨过。

### 2.6 明确区分旧实验与本项目证据

旧的 `CPH_review_git_regression_2026-09-26.json` 只是历史上一个独立临时 Git 实验的摘要，不是 CCB 或本项目编译、游戏功能、CI、签名或发布验证。需要相关回归时重做可运行测试，不能把旧文件当成已通过项目验收。

## 3. 执行参数和只读起点

以下是调查快照，必须在执行环境核验；不能冒充执行当天的最新状态。

```text
CDDA_REPO = CleverRaven/Cataclysm-DDA
CCB_REPO = CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb
CCB_REF = refs/heads/master
CDDA_BASE = 221c786e7d61b3c9254f7cb1625bc69494b8181c
CCB_BASELINE = bcb85682f3d28ab0f0123b05e45651bb9888b61b
TARGET_REPOSITORY = 尚未由当前需求给出
```

若这两个对象可读取且祖先关系成立，就把它们用作可复核的首次基线，不静默改成执行时任意最新 SHA。可以同时只读查询上游当前 head 并记录差异；在基线验证完成后，再通过正常整合流程跟进后续提交。对象缺失时排查浅克隆和获取范围，不得伪造对象、重新制作同名提交或使用 unrelated-histories 强行拼接。

可调整的实施默认值如下，实际采用时记入配置：

| 项目 | 默认处理 |
|---|---|
| 本地工作名 | `CPH`，只用于临时目录和文档，不自动冻结品牌及应用 ID。 |
| 新仓库候选名 | `Cataclysm-Phantom-Hope`，只是候选；未明确目标前不创建。 |
| 自有默认分支 | 已有正确项目则沿用实际默认分支；新项目可用未占用的 `main`。发生冲突创建独立新分支，不重置既有分支。 |
| CCB 同步检查 | 每 6 小时一次的可逆默认值；不是用户原先指定频率。 |
| 开发版发布检查 | 每天 03:17 UTC 的可逆默认值；用户确认的是每天一次。 |
| Windows 包 | x86_64 图形版 ZIP 候选，必须可运行，非只有源码。 |
| Linux 包 | x86_64 图形版 tar.gz 候选，标明实际支持环境和运行依赖。 |
| macOS 包 | 优先验证继承的 `.app`/`.dmg` 路径；架构范围以实际验证后的 targets 清单为准。不能假称 universal。 |
| Android 包 | arm64-v8a APK 候选；先核实用户实际设备 ABI，再固定发布目标。 |
| 平台最低版本 | 从所选工具链/代码配置和实际测试确定并记录；不得凭记忆填版本。 |
| 自动公开发布 | 初始化期间关闭；达到本文相应条件、目标与身份明确后才启用。稳定发布始终关闭。 |

这些包格式是实施候选；不得把 ZIP/tar.gz 描述成 MSI/DEB/RPM。首期不自动增加商店上架、所有安装器、32 位系统、所有图形/声音变体或字节级完全可复现承诺。

## 4. 权限、工作区和秘密边界

### 4.1 第一条命令之前

先读取当前目录及适用范围内的 `AGENTS.md`、`AGENTS.override.md` 和现有项目指导。不要无提示覆盖这些文件或修改用户全局 Codex 配置。

检查工作区根目录、Git remotes、当前分支、未提交修改、已有任务状态、工具版本和认证状态；只记录非秘密摘要。不能输出整个环境变量表、GitHub token、私钥或 keystore。远程 URL 含凭据时先脱敏。

如果当前目录不是授权目标，不在该目录创建项目文件。建立明确的隔离工作区；若无法判断可写位置，保持只读并说明缺口。

### 4.2 允许与禁止

允许在授权项目范围内实现脚本、测试、文档及必要构建/隔离修复，创建独立工作分支并保留可审查提交。明确目标与权限后，可以按本规格配置该目标的 CI 和开发版流程；不能绕过执行环境自身的审批或权限限制。

禁止向 CDDA、CCB 或无关仓库推送、开 PR、改设置；禁止删除或复用既有 fork；禁止 `git push --mirror`、强推改写主线、清空用户工作区、批量删除标签/Release 或全盘替换项目名称。

不要使用已有 Windows/Android 安装和真实存档做破坏性隔离测试。使用临时数据目录、测试用户、模拟器或明确批准的测试设备。

不要在运行来自候选分支的构建脚本时注入 App 私钥、正式签名密钥或仓库写权限。不将 token 持久留在 checkout 的 Git 配置中。

### 4.3 缺少外部条件时

不要编造 owner、应用 ID、签名身份、测试设备或远程权限。产出一次性配置清单：缺少什么、阻塞哪个动作、用户需在何处配置、配置后从哪一步继续。不要求用户把密钥粘贴进聊天。

无权限时交付已实现代码、实际运行的本地检查、部署命令/配置与待办；状态标为“实现但未部署”，不能标为“自动化已启用”。

## 5. 执行任务与依赖

下面是执行顺序，不是要求一个大提交完成全部工作，也不要求第一轮必须停在纯文档阶段。每完成一项，更新进度、证据和阻塞依赖，再继续可执行项。

### E0：真实环境与历史预检

**实施：**

1. 读取现有项目指令及工作区；核实目标仓库和 GitHub fork 元数据是否已经存在。
2. 在隔离 Git 目录中取回 B/U 对象和足够的提交历史。不要依赖 depth=1 的祖先判断。
3. 校验 B 是 U 的祖先；记录两个 commit/tree ID 和来源。GitHub parent 检查与 Git 对象检查分别记录。
4. 审计全部继承工作流及其调用链，列出触发事件、分支过滤、权限、secrets、外部输入和产物去向。
5. 检查可用编译器、SDK、磁盘、runner 和网络；只列实际可用项，不假定能访问四种系统。
6. 编写可重复执行的只读 preflight 工具；对缺参、错误对象、浅历史、错误仓库、未提交用户改动等情形添加测试。

已核实可用的只读校验形式如下。变量由预检安全赋值，不是让用户手填后直接运行一个破坏性脚本：

```sh
git cat-file -e "${B}^{commit}"
git cat-file -e "${U}^{commit}"
git merge-base --is-ancestor "$B" "$U"
git rev-parse "${B}^{tree}"
git rev-parse "${U}^{tree}"
```

**交付：**环境/来源报告、继承工作流清单、可运行 preflight 和测试结果。失败必须保留具体退出码和脱敏日志。

### E1：最小基线构建与资源探针

**实施：**

从锁定 U 的构建文档、Make/CMake/Gradle 和现有 CI 读取实际命令，不凭空发明测试目标或参数。优先复用现有入口，必要修复用独立补丁记录。

先完成当前可用环境的一次真实主力平台构建与最小实际测试；没有另一平台环境，就开发对应 CI 探针并标记待运行。四平台真实检查可在 E2 的受控仓库初始化后继续，不要求为了先做四平台探针而先购买设备。

翻译初始化必须避开“新仓库依赖自己的历史成功 artifact”循环。取得可核验来源的翻译与必要素材，记录原始对象、哈希、许可、署名和实际覆盖；没有 TX_TOKEN、没有历史 artifacts、没有缓存时也应能初始化声明的输入，或者明确失败。[S11]

优先取得可维护的 `.po` 输入；仅有 `.mo` 时只能报告实际取得的编译资源，不能宣称获得完整源码维护链。可以验证该候选路径，但是否作为长期输入须在资源方案中明确。不能为了证明初始化成功生成空翻译、悄悄禁用中文或丢弃必要素材。

未修改 CCB 身份的包仅用于隔离验证，不作为本项目开发版公开，也不安装覆盖用户现有 CCB。对 macOS/Android 先核实工具链和自动运行条件，不承诺不存在的环境。

**交付：**真实命令、依赖/资源锁定清单、至少一个实际可用环境的构建证据，以及其他平台具体探针/阻塞。不能仅交付四个没有执行证据的 YAML 文件就宣称 E1 完成。

### E2：受控建立真正的 CDDA fork 与初始化检查入口

**前置：**已明确唯一 `OWNER/REPO`、当前账号权限和创建/修改范围。没有这些条件时实现脚本的 dry-run 与测试，不执行远程写入。

**实施：**

通过 GitHub fork 机制从 CDDA 建仓；核验 `fork=true` 和 `parent.full_name=CleverRaven/Cataclysm-DDA`。不是 fork CCB，也不是新建普通空仓库上传。已有 fork 或名称冲突不自行删除、覆盖或迁移。

新 fork 可能带有当前 CDDA 的默认分支。不要把该分支强推回 B/U；在未占用的新开发分支建立自己的历史线，保留其他已有引用。默认分支切换只作用于本次明确的新目标并记录。

在隔离本地记录从 B 沿原历史到 U 的导入检查点。第一个自有改动之前验证 tree 与 U 一致。随后用独立提交加入必要初始化改动，不重做或改写 CCB 历史。

审计并禁用或限缩继承的自动公开发布、PR 产物通知和高权限回调，再启用本项目入口。不能先打开所有 Actions 和 secrets，再指望检查器事后阻止旧 workflow。

**有限的初始化边界：**新项目尚无 CI 时，创建种子分支和最小受控 CI 入口是本任务的初始化操作，不冒充已经通过日常自动合入。只用于新目标、原有历史保留、无公开发布、无正式签名密钥；初始化结束后启用正常门槛。不得把这个边界扩展成以后管理员随意绕过检查。

**交付：**GitHub parent 证据、B/U/导入 tree 验证、初始化提交列表、默认分支和 workflow 审计结果。远程规则查询失败是“未核验”，不能记录为“已保护”。

### E3：最小独立身份及四平台构建输入

**实施：**

审计并定点修改应用身份、启动器、默认路径、配置/存档目录、卸载范围和包元数据。显示名、永久技术 ID、内部翻译域/文件格式标识分开处理，不做全仓字符串替换。

Android 重点检查 applicationId、组件 authorities/Java 目录访问、外部存储路径、签名与升级；macOS 检查 bundle ID、包与 Application Support 路径；Windows/Linux 检查普通运行、便携目录、启动参数、系统默认与 XDG 路径。

永久身份未定时使用明显的仅测试身份完成隔离验证，不以临时 ID 或临时密钥公开长期开发版。正式身份配置只能来自明确的项目决定。

测试先建立模拟 CCB 程序、配置和存档哨兵，记录哈希；执行本项目安装、启动、更新、卸载等所适用路径，再验证哨兵未变。不扫描真实用户目录做清理，不自动导入 CCB 存档。

建立发布目标清单：每个平台的 ABI、格式、构建配置、源码/资源输入、预期文件、签名状态和检查范围。由同一个固定提交及资源清单生成所有包。

**交付：**定点代码改动、四平台构建目标、隔离回归、首个同输入候选集或明确分平台状态。macOS/Android 尚未通过发布检查时，允许继续满足 W/L 条件的开发。

### E4：可信 Windows/Linux 合入门槛

**实施：**

建立明确的检查契约，不原样把上游“General build matrix 成功”当作验收。锁定快照中普通 push/PR 会令广泛 C++ 测试 `skip_tests=true`，需要另外明确哪些测试真正执行。[S10]

每个 required check 记录：ID、实际命令和目录、构建配置、执行平台、测试集合、输入提交/合并树、策略版本、结果文件和判定条件。先跑通有效的基线回归，再固化必需集合，不承诺一开始所有历史测试全部通过。

汇总器必须在依赖失败时仍做拒绝判定；不接受 missing、skipped、neutral、cancelled、timeout、零测试或旧候选报告作为必需成功。路径过滤、skip annotations、空矩阵和 `continue-on-error` 不得绕过硬门槛。[S1][S3]

证据绑定至少包括仓库 ID、PR、base/head、实际测试 tree、策略 SHA、workflow 路径与 ID、事件、run ID/attempt 和目标配置。最终 merge commit 的 SHA 未必与测试合并提交相同，应验证对应 base/head 和实际结果 tree，不盲目把字面 SHA 相同当作唯一条件。

候选涉及验收政策、可信脚本、workflow 权限、发布身份等保护面时，不能自动用候选的新规则批准自己。普通代码测试可以变化，但删除或放宽既定门槛必须是单独、明确授权的规则修改。

配置符合需求的分支规则：必需检查有效、基线更新后重验、禁止常规强推/删除；允许保留 merge 历史，不默认增加人工逐 PR 审批或要求重新签署全部继承提交。自动化身份不能以管理员 bypass 放行失败。

**交付：**检查契约、实现与负例测试，以及实际 GitHub PR 上“正常检查允许、必需失败阻止”的证据。仅本地单测不能标为 GitHub 保护已经生效。

### E5：非 AI 自动同步及有边界的自动合入

**前置：**E4 和相关授权/隔离/保护条件已满足。不要求所有仅影响发布的 E6 问题先关闭。

**实施：**

固定一次同步的本项目 base SHA H 和 CCB head U1。无更新则结束；有更新则建立隔离集成候选。验证上游连续性，发现改写历史/对象缺失/来源变化不强制同步。

在新 workflow 能进入可执行远程分支前检查保护面变化。文本冲突停下，不用 `-X theirs`、强制 reset 或删除本项目功能换取无冲突。没有文本冲突不能代表没有语义问题；由已知约束和回归测试限制，无法判断的新设计取舍报告给用户。

采用已证明能满足 required checks 的事件/检查链。首选受限 GitHub App；缺少 App 配置时先实现和测试 dry-run，不自行购买服务或索取秘密。不能将 dispatch 绿色状态直接接到 merge。[S1][S2]

每次更新整合候选后重跑适用检查。base/head 在等待期间变化，先重建组合再验收。合入保留上游 merge 历史；禁止 squash 全部上游提交以绕开祖先验证。来源 SHA 与主动适配/撤销记录分开维护。

同一上游待处理问题复用或更新任务记录，不每次轮询制造重复 Issue/PR。日常流程不需要 AI key，不调用 Codex API。

**交付：**无变化、正常整合、冲突、策略变化、上游改写、W/L 失败和基线变化的测试；真实自动合入只在平台权限和门槛已验证后启用。

### E6：四平台开发版发布协议

**前置：**所有当轮平台和资源检查、长期身份与必要签名均就绪。Android 未确定的验收配置不得用空字段视为通过；macOS 已接受的人工作业豁免不得被擅自取消。

先做不公开的端到端演练，再启用真实发布。具体协议见第 8 节。首次开发版自动公开不等于现在允许用四个占位包测试发布；真实项目只有真实齐备产物才可公开。发布 API 的故障注入先用 mock 或明确授权的测试空间完成。

**交付：**发布器、状态恢复、签名接口、清单/摘要、故障测试、实际四平台候选和真实发布验收。缺正式密钥只阻签名/发布；测试密钥仅用于明确的本地/隔离 fixture。

### E7：启用、运行手册与交接

确认相应 readiness 后分别启用自动同步合入与每日发布；不是一个总开关把所有能力一起打开。普通周期采用第 3 节可逆默认值并记录。定时工作流不是准点交付保证，应保留手动重试和停滞可见性。[S8]

提供暂停同步、暂停发布、封禁指定候选、恢复重试、撤销已合入改动和修复已公开问题版的操作说明。暂停检查应在实际合入/公开前再做一次。

不静默替换旧包；必要时通过公告和新版本修复。撤销 merge 不会移除其祖先关系，不能指望下一次 merge 同一个 U 自动恢复；维护主动撤销记录并通过明确的新提交恢复。

稳定版入口保持未启用，不留一个可任意传 `channel=stable` 的开发版发布后门。未来稳定版方案另行实现，不能拿本次长期开发版授权代替用户批准。

## 6. 合入和发布的最小有效判定

### 6.1 合入

```text
范围已授权
AND 可信策略有效
AND 上游/候选来源有效
AND 无待用户决定的冲突
AND 当前 base/head/测试树匹配
AND Windows 必需构建与检查实际成功
AND Linux 必需构建与检查实际成功
AND GitHub 实际分支规则认可这些检查
AND 合入暂停开关未打开
```

macOS/Android 失败不得被意外写成这一布尔表达式的必需项。它们的结果仍必须可见。

### 6.2 发布

```text
候选尚未成功公开，且未被撤回/取代
AND 候选来自当前项目认可的开发线
AND 输入版本和构建目标已锁定
AND Windows/Linux/macOS/Android 必需产物全部存在
AND 每个平台本轮必需检查实际成功
AND 包/manifest/源码/资源/架构一致
AND 独立身份和必要签名有效
AND 更新说明与未验证范围准确
AND 公开前再核验暂停、候选状态与远端资产
```

禁止跨候选补齐四平台包。某个检查尚未确定时是 pending/blocked，不是 optional=true；已经确定为非阻塞的信息项则可以如实保留。

## 7. 平台验收边界：先固定可执行方案

| 类别 | 每轮应记录 | 不得冒称 |
|---|---|---|
| Windows/Linux | 实际目标构建、选定回归、资源/依赖、隔离和适用的启动检查；区分原生与交叉编译。 | 在 Linux 交叉编译 Windows 成功，就等于 Windows 原生启动成功。 |
| macOS | runner 实际架构、产物架构和依赖、签名状态、包检查及可执行自动探针。 | universal 包的存在证明两个架构都运行过；无人工实机测试等于不能发首期开发版。 |
| Android | APK ABI/ID/版本/资源/签名、实际可用运行测试环境与对应包摘要。 | x86_64 companion APK 成功就是 ARM64 发行 APK 已实测。 |

Android 先验证是否有可用 ARM64 自动运行环境。若没有，可提出“实际 ARM64 包静态与签名检查 + 同源码兼容架构模拟器回归 + 首次/高风险实机验收”的明确 profile；它是待采用的实现方案，不是用户已确认每天提供真机。没有配置完成前继续开发，但不自报整个发布验收已完成。[S9]

首次或高风险人工验收只对明确版本/变更范围有效，不能将一次手工试玩结果无限沿用为以后所有包都实测。不要增加每天人工批准开发版的隐藏门槛。

包目标和检查策略的改变必须留决策记录。不能为了避免 Mac 失败静默缩成三平台，也不能为了“更全面”把所有历史 ABI 全列为首期必需。

## 8. 最小发布状态协议

无需引入数据库、常驻机器人、外部工作流引擎或自建制品平台。优先用仓库脚本、GitHub API、受控草稿及清单管理；测试可以 mock API，但生产通过证据不能使用 mock。

### 8.1 身份

- `source_sha`：本次固定源码提交 H。
- `inputs_digest`：资源锁、目标配置、构建/验收策略版本等规范化输入的摘要。
- `candidate_id`：由 H 与 inputs_digest 派生的稳定身份；重试不更换逻辑候选。
- `attempt_id`：workflow/run/attempt 标识，区别于候选身份。
- `tag`：稳定、唯一并最终解析到 H 的开发版标签；公开后不得覆盖。
- `android_version_code`：从持久记录分配、对后续公开版持续递增；同一候选重试复用分配值，不通过倒退版本号“回滚”。[S6]

同 SHA 不代表不同编译环境可得到字节完全相同的产物。记录实际 runner 镜像、工具链和依赖版本，不假称已实现 bit-for-bit reproducibility。

### 8.2 串行化与恢复

首期可使用一个固定并发组串行化“候选预留—构建—签名—最终公开”整个发布流程，`cancel-in-progress` 不自动杀掉正在公开的事务。同步/PR CI 不使用这个组，不因此被发布阻塞。

互斥只是简化实现，不是幂等证明。重试和手动触发仍必须查询持久远端状态。不要假定按调度发起顺序 FIFO，也不要依赖 runner 临时磁盘作为唯一记录。[S14]

建议状态是 `reserved → building → verified → draft_complete → published`，失败记录在独立 attempt；blocked/superseded 不算成功。可以调整内部表示，但必须覆盖相同失败场景。

Android versionCode 的预留可在同一受控草稿/状态清单记录，串行分配并检查 API 超时后的既存记录。失败候选的预留不回退复用给另一个候选；已公开的版本身份不可重用。

不要每次运行向主分支提交“最后构建时间/最后发布 SHA”。这种运行状态更新本身会制造新提交，导致每日空转发布。使用发布清单/草稿或独立受保护状态位置；状态变更不得再被当作游戏源码新版本。

### 8.3 查询与公开

不要使用 `/releases/latest` 查询最后开发版，该接口排除 prerelease/draft。[S7]

分页读取并筛选有效项目开发版，验证 tag 与 manifest；区分“尚无开发版”和 403/429/网络错误，不能把任意读取失败当作“从零发布”。排序/推荐状态不能只取 API 第一项。

在同一固定 H 和锁定资源下构建四平台。结果暂存可用 Actions artifacts 或草稿；公开仓库的 artifacts 可能可访问，不宣称它们天然保密，也不公告单平台暂存包为完整开发版。

构建阶段不带正式签名/写权限。签名在独立受控环境使用固定工具完成，不重新运行候选 Gradle/CMake/任意项目脚本；签名前完成所需对齐，签名后再校验并计算最终摘要。[S12]

公开前核验四平台预期资产、来源/run/attempt、版本、摘要、签名证书指纹和候选状态。先草稿、全部上传核验、最后公开为 prerelease。immutable releases 可作为额外保护，但不会代替频道授权和流程控制。[S5]

发布最后一步超时：先查相同 candidate/tag/manifest 的远端状态，已完成则记录成功；未完成才补做，不能直接创建另一份。旧候选晚到时不覆盖新版本，也不把已被封禁的候选重新公开。

### 8.4 Manifest 最小字段

由可信控制器产生预期清单并与构建结果核对；不能让上传者自己填写一个“success=true”就获准发布。

```text
schema_version, candidate_id, source_sha, ccb_integrated_sha
policy_sha, inputs_digest, tag, version_name, android_version_code
platforms[]: target_id, os, arch, format, build_configuration
artifacts[]: name, size, sha256, repository_id, workflow_id,
             event, run_id, run_attempt, tested_source/tree, signing_status
checks[]: check_id, required_scope, execution_environment,
          actually_executed, status, evidence_reference
asset_sources[], toolchain_versions[], licenses[], known_issues[]
manual_validation_scope[], unverified_scope[]
```

这里只规定数据含义；Codex 应实现 schema/校验和测试，而不是把这段伪结构当成已生成的有效 JSON。

## 9. 可信控制与最小复杂度

优先复用上游构建脚本，围绕它们加少量可本地测试的预检、锁定、核验与发布控制。不要先做一套通用 CI 平台或几十个抽象层。

本轮可信控制至少覆盖：workflow/权限、检查器和阈值、发布器、签名调用、应用 ID、上游地址和受保护设计记录。候选修改这些内容必须作为明确的任务审查，不自动消除原有保护。

普通候选在低权限临时 runner 执行；高权限任务只读取经过验证的元数据/产物，不执行候选内容。校验 artifact 来源、run/attempt 与摘要，安全处理归档路径和体积，不直接执行解包出的脚本。签名/发布不复用不可信执行环境或可执行缓存。[S4]

App 仅安装目标仓库，工作令牌按任务缩权；管理权限与日常权限分开。首次配置可能需要用户在 GitHub 中完成有限动作；不要把用户长期个人 token 当作默认万能权限。

若目标账号/计划不支持某个预想的保护功能，记录实际能力并提出等价最小控制或阻塞，不擅自升级套餐，也不套用仅组织账号可用的限制到个人仓库。

## 10. 必需的负例和恢复测试

下列每一项都要记录它验证的是本地模型/单元测试，还是实际 GitHub/设备行为；二者不可互相冒充。

| 编号 | 场景 | 预期 |
|---|---|---|
| T01 | Windows 或 Linux 必需构建/回归失败 | 拒绝自动合入。 |
| T02 | W/L 成功但 Mac/Android 失败 | 合入可按规则继续；发布拒绝。 |
| T03 | 必需检查 skipped/neutral/空测试/超时/取消/缺失 | 不放行。 |
| T04 | dispatch job 同名且绿色，但不是平台认可的必需检查 | 不误判为 PR 可合入。 |
| T05 | base/head 在测试期间改变 | 重新建立并验收组合。 |
| T06 | 候选修改检查器/阈值/权限自报成功 | 保护面拦截，不能自我批准。 |
| T07 | 上游文本冲突、历史改写或未授权设计变化 | 停止该次整合并报告，不自行调用 AI。 |
| T08 | 完整导入/后续整合 | B/U 祖先及预期 tree/merge 历史正确，不被 squash 丢失。 |
| T09 | 四平台中一包缺失、为空、错误 ABI、错误 H 或资源摘要 | 不签发完整开发版。 |
| T10 | 同名 artifact 来自别的 repo/run/attempt | 拒绝签名/发布。 |
| T11 | 没有 stable，只有分页后的 prerelease | 正确识别最后有效开发版。 |
| T12 | 读取发布状态时权限/限流/网络错误 | 明确失败或重试，不当作无版本。 |
| T13 | 同候选昨日失败今日无新提交、已成功候选重复触发 | 前者允许重试；后者不重复公开。 |
| T14 | 定时和手动运行重叠，旧候选晚完成 | 无覆盖、重复或版本倒退。 |
| T15 | 最终公开成功但响应丢失 | 查询远端后恢复，不重复发布。 |
| T16 | Android versionCode 回退、签名身份错误、签名后包被改 | 拒绝长期升级发布。 |
| T17 | 暂停或封禁后在途 job 到达合入/发布步骤 | 动作仍被拒绝。 |
| T18 | 撤销一次 upstream merge 后再 merge 同一 U | 不把祖先关系误当作功能恢复，按差异记录处理。 |
| T19 | 安装/启动/升级/卸载项目 | CCB 模拟程序、配置和存档哨兵不变。 |
| T20 | 无 TX_TOKEN、无历史 artifacts、无缓存 | 已声明输入可取得并校验；否则失败，不伪造翻译。 |
| T21 | 试图从开发发布入口传入 stable、或提升 prerelease | 受控开发入口拒绝；不能宣称 contents:write 或 immutable 在底层 API 权限上禁止频道变更。 |
| T22 | 发布写入状态后触发下一轮检查 | 运行状态不制造主分支新源码提交和无限发布循环。 |

没有真实平台环境就把相应测试标为 NOT_RUN/BLOCKED，不能因为 mock 正常就记录全部端到端通过。故障注入不在真实上游仓库、用户真实存档或已公开正式产物上进行。

## 11. 文件布局与任务规模

先看现有仓库习惯，以下是建议路径，可以收敛合并，不要求机械创建全部空文件：

```text
AGENTS.md                          # 简短入口；保留既有适用规则
docs/project/execution-spec.md      # 本规格
docs/project/status.md              # 分阶段实际进展和恢复入口
docs/project/upstreams.md           # 历史及整合约定
docs/project/design-differences.md  # 主动差异、撤销和恢复
docs/project/release-runbook.md     # 日常、暂停、重试、签名操作
project/upstreams.lock.json
project/assets.lock.json
project/build-targets.json
project/check-policy.json
project/protected-surfaces.json
tools/project/...                   # 复用仓库既有语言/工具，优先小模块
tests/project/...                   # 使用适合该仓库的测试位置
.github/workflows/project-*.yml     # 按角色拆分；不保留意外第二发行入口
```

文件名存在不等于完成。不要创建上百行 TODO 和永远返回成功的占位脚本，再声称已实现架构。兼顾合理的增量改动，不以统一目录风格重构整个上游仓库。

每个逻辑改动单独提交：预检、资源、身份、平台修复、检查、同步、发布分别可回顾和撤销；不把这些与 SDL3/UI 功能改造混在一个提交中。没有适当提交权限或身份时交付 diff，不伪造作者。`status.md` 用于实施交接，不让定时工作流每运行一次就修改主分支中的这个文件。

AGENTS.md 只放核心约束和“执行前完整读取 execution-spec”的入口。不要把原计划、review 和本规格全文拼进去。Codex 默认合并项目指令存在 32 KiB 上限，且目录覆盖规则会影响加载；该入口不能替代主动读取完整任务文件。[S13]

## 12. 每轮输出和最终完成定义

每轮输出包括：实际目标 repo/branch（脱敏）、起止提交、文件变更、每项真实命令/退出码/平台/日志引用、没有执行的项目及原因、未关闭阻塞及恢复步骤。

统一状态：

- `PASS`：规定的实际检查执行并满足标准，有证据。
- `FAIL`：实际执行失败，有退出码和记录。
- `NOT_RUN`：未执行，不推断结果。
- `BLOCKED`：缺少前置条件或授权，注明影响哪个动作。
- `IMPLEMENTED_NOT_DEPLOYED`：代码已实现，未在目标 GitHub 生效。

汇总 readiness 分别报告：

```text
LOCAL_IMPLEMENTATION_READY
HISTORY_AND_FORK_VERIFIED
WINDOWS_LINUX_GATE_VERIFIED
AUTO_SYNC_AND_MERGE_ENABLED
FOUR_PLATFORM_RELEASE_READY
DAILY_DEV_RELEASE_ENABLED
STABLE_RELEASE_ENABLED = false
```

每个 true 必须指向具体证据；schema 有字段或 YAML 能解析不能算部署完成。readiness 不能由空检查数组或缺省 true 计算出来。

如果时间/上下文或外部条件不足，提交已完成的小步，记录 `last_completed_task`、当前 diff、未完成检查与下一条可执行操作，然后停止在安全边界。不丢弃成果，不输出“所有步骤完成”掩盖余项。

整个首期的完成定义是：正确 fork/历史、独立身份、可初始化资源、有效 W/L 合入门槛、可持续 CCB 整合、真实四平台开发版交付、按日自动发布及可验证恢复路径均成立。只有写完脚本但未部署时，不算整个首期完成。

## 13. 建议给 Codex 的第一次执行范围

立即从 E0 和 E1 的可用部分开始，不先重新写一份宏观研究报告：

1. 建立真实工作区/目标/权限报告。
2. 实现并运行历史与环境 preflight，以及相应负例测试。
3. 清点全部继承 workflow，定位本地化初始化、测试默认跳过及旧发布入口。
4. 在可用环境跑一次实际构建/最小测试，或给出精确可复现的阻塞；对其余平台实现必要探针。
5. 具备明确目标和权限后继续 E2；以后按依赖继续，不把缺签名/缺 Mac 变成所有代码工作停工。

预计创建目录、临时环境、下载工具链等操作必须留在授权范围内；影响真实主机或收费资源时沿用执行环境的审批，不隐藏系统级改动。

## 14. 证据与复核资料

以下是本次审查所据资料，不是本项目构建日志。执行时仍须核实实际代码和平台规则。

### 输入文件及 SHA-256

```text
Cataclysm_derivative_research_and_plan_2026-09-26.md
e84e124f351ebd8dc1856aefad95993e397af1cfe0536157d346f6ce9ea052c6

Cataclysm_Phantom_Hope_plan_review_2026-09-26.md
bcdbeae814c50c8cf714e531038ac9c959866d665b82619dcec32640f95d707b

CPH_review_git_regression_2026-09-26.json
33193a2fb15d033a4fd16d20a3c3f083f6e8dac5de25434a587d354eb37d371a
```

### 官方来源

- [S1] GitHub：Required checks 的允许事件、dispatch 不满足规则、跳过/缺失检查。`https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks`
- [S2] GitHub：GITHUB_TOKEN 与 GitHub App 的 workflow 触发差异。`https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow`
- [S3] GitHub：分支保护、必需检查、合并基线和线性历史。`https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches`
- [S4] GitHub：Secure use reference。`https://docs.github.com/en/actions/reference/security/secure-use`
- [S5] GitHub：Immutable releases 的保护范围及草稿发布方式。`https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases`
- [S6] Android：版本号和 versionCode。`https://developer.android.com/studio/publish/versioning`
- [S7] GitHub：Releases REST API，latest 不包含 prerelease。`https://docs.github.com/en/rest/releases/releases`
- [S8] GitHub：定时和其他 workflow events。`https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows`
- [S9] Android：模拟器硬件加速与架构条件。`https://developer.android.com/studio/run/emulator-acceleration`
- [S10] 本次重新读取的 CCB 通用 CI，锁定基线。`https://github.com/CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb/blob/bcb85682f3d28ab0f0123b05e45651bb9888b61b/.github/workflows/matrix.yml`
- [S11] 本次重新读取的 CCB 翻译 workflow，锁定基线。`https://github.com/CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb/blob/bcb85682f3d28ab0f0123b05e45651bb9888b61b/.github/workflows/build-translations.yml`
- [S12] Android：apksigner。`https://developer.android.com/tools/apksigner`
- [S13] OpenAI：AGENTS.md 加载与大小限制。`https://developers.openai.com/codex/guides/agents-md`（本次访问重定向至 `https://learn.chatgpt.com/docs/agent-configuration/agents-md`）

- [S14] GitHub：并发组、排队和取消行为。`https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency`

以上列出的源码/官方文档事实与本规格提出的实施设计不同。实施设计仍需通过 E0—E7 的实际验证，不得以“ChatGPT 已 review”代替执行证据。
