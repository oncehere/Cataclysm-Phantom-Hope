# 缺失条件与恢复入口

**现行恢复入口，状态按日期核验：**2026-09-27 UTC 复核时远端 `main=d88815158ad31104ab4cde9fdd7537c7180cf7ff`，三个受控 workflow active，main 规则 `24056126` 仍 disabled；PR #1 的新一轮 Windows/Linux 运行中，结果不得预判为 PASS。旧失败 run 保留为历史事实。远端 Issues 关闭、private vulnerability reporting 关闭、Discussions 开启；这些开关不构成 W/L 或发布验收。实际操作前重新读取远端状态；本地证据位置见 [workspace-layout.md](workspace-layout.md)。

这是检查发现的外部条件清单，不要求把密钥发到聊天中，也不把配置文件
存在当作已经部署。目标 `oncehere/Cataclysm-Phantom-Hope` 已由用户明确授权，
原生 CDDA fork、管理权限和历史上传已核验；`origin` 已配置，默认分支为 `main`。
执行回证见 [fork-deployment.md](fork-deployment.md)。四个 remote 的 push URL
均保留 `DISABLED`，需要写入时必须使用明确目标和固定 ref，不猜测或使用默认 push。

2026-09-26 部署快照：`main=5dc53160e6e877ef0526d686a2c3b9a9c2bfb3ec` 时，CI/gate/sync
三个 workflow 均为远端 active；Actions 仅允许 5 个精确 action SHA。继承
`master` 冻结并保持原 SHA。持久状态 revision 1 已恢复同步检查，合入仍暂停，
`auto_merge_enabled=false`；暂停和无更新路径均真实 PASS。PR #1 首次 CI 的
Windows 因 vcpkg 浅克隆缺历史 tree 失败，Linux 取消，不计 PASS；collector
已发布 failure。main 规则 `24056126` 仍 disabled，受保护合入验收 **PENDING**。
随后已提交 vcpkg 与 Linux 诊断修复，新一轮仍待结果；后续以 Actions 与 `evidence/remote-ci-sync-20260926/`
为准，不随每次运行更新源码文档。
本轮入口及开关见 [remote-sync.md](remote-sync.md)，完成状态见
[status.md](status.md)；`fork-deployment.md` 中 Actions 关闭的记录是初次建仓快照。

| 最小条件 | 仅阻塞的动作 | 配置位置与恢复入口 |
|---|---|---|
| 真实必需检查及启用后的 main 规则验收 | 日常自动合入 | 三个入口已部署；先核验 PR #1 新运行结果，再在目标 PR 验证 `cph/trusted-gate` 成功允许、失败阻止、base/head 移动需重验；保持 merge 历史，不启用线性历史要求 |
| GitHub 托管 Windows/Linux runner 的实际构建、测试及来源绑定结果 | W/L 合入门槛计为通过 | 使用已实现的 `project-ci.yml` 原生执行；本机缺 Windows 不阻塞部署，Linux 结果也不能替代 Windows 原生结果 |
| 原生 macOS runner、所选架构依赖 | macOS 构建/包检查和四平台发布 | 先复用已审计入口作候选检查；包架构与实际运行架构分别记录，不能擅自增加每日人工批准条件 |
| Android SDK/NDK/JDK、可用运行环境、明确验收 profile | Android 包/运行验收和四平台发布 | 先探测 ARM64 自动环境；替代 profile 需要明确采纳，兼容架构模拟器结果不能标成 ARM64 包实测 |
| 永久项目身份决定 | 长期应用 ID、包身份和公开开发版 | E3 先可使用明显的本地测试身份；默认配置、存档、升级清理和卸载都要隔离，不能只改显示名 |
| 正式签名材料及平台身份 | 必须签名的包与公开发布 | 后续放在目标受控签名环境/秘密存储中。构建不带正式密钥，签名阶段不运行候选构建脚本 |
| 管理员核验的无 bypass 规则锁、可信 collector 与最终开关检查 | E5 日常自动同步合入 | 采用受限 `GITHUB_TOKEN` 创建 PR，再 dispatch 主分支 CI；collector 独立核验并发布 commit status。核验规则锁与真实 PR 门槛后才恢复合入；不以普通 dispatch 绿色 job 代替门槛，不要求先配置个人 PAT/App 私钥 |

没有权限和签名只阻塞依赖动作。不得购买服务、复用既有 CCB fork、猜测
目标、用临时签名包公开发布，或要求用户提供每日人工测试来掩盖自动化缺项。
AI 不在日常运行链中；新增设计取舍另行明确。

本轮暂停/恢复边界：Actions 已限缩启用，继承 workflow 保持隔离，master 已冻结。
同步 workflow 每 6 小时检查，快照状态为 `sync_paused=false`、
`merge_paused=true`、`auto_merge_enabled=false`；检查启用不等于已启用合入。
自动合入、每日公开开发版和稳定版均未启用。旧 `operator-controls.md` 描述的本地
模型继续保留，远端操作应使用 `remote-sync.md` 的持久状态与 revision 检查。
实际在途任务暂停/封禁、最终动作前重查和状态恢复仍需远端验收；本地 fixture
通过不能代替这些回证。主分支保护规则变化后必须重新核验规则锁，不能把公开 API
未返回 bypass 字段解释为“没有 bypass”。

稳定版仍没有运行入口。将来发布稳定版需要用户单独确认。
