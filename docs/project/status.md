# CPH 当前状态

本页只保留最新人工核验快照；操作前重新读取 GitHub。需求见 [执行规格](execution-spec.md)，未完成动作见 [恢复入口](resume.md)，本机位置见 [工作区布局](workspace-layout.md)。定时任务不向主线追加运行记录。

## 2026-09-28 UTC 核验

| 范围 | 已确认状态 | 边界 |
| --- | --- | --- |
| 仓库与历史 | `oncehere/Cataclysm-Phantom-Hope`；原生 CDDA fork，默认 `main` | CCB `master` 是同步输入，CDDA 仅选择性引入；保留来源和 merge 历史 |
| 已合入维护 | PR #4/#5/#6 已合入；本次整理基线 `abd9222e01b77ac9e187f53cd6cfe85275453a69` | PR #3 已被替代关闭，不能继续按旧待办合入 |
| main 保护 | 规则 `24056126` active；严格 `cph/trusted-gate` / App 15368；已保存空 bypass 规则锁 | 个人维护仍按第 6.1 节及具体授权办理；不发布合成的 trusted PASS |
| 自动同步与合入 | **用户要求暂停**：state revision 10，`sync_paused=true`、`merge_paused=true`、`auto_merge_enabled=false`；sync workflow `disabled_manually` | 只有用户后续明确要求才能恢复；旧 revision 3/6/9 的启用记录不再代表当前开关 |
| CI 入口 | Native CI 与 Trusted Gate workflow active；工具检查源码已随 #6 合入 | 新 tooling 的真实普通 PR 放行/拒绝验收 **NOT_RUN**；源码部署与端到端验收分开 |
| 个人维护 | 相关本机检查是验收依据，允许按输入一致性复用旧证据 | Linux 通过不代表 Windows/GUI/完整游戏通过；Windows 专属变化须对应验证 |
| 社区入口 | Issues、Discussions、私密漏洞报告已启用并回读 | 敏感内容仍须通过实际私密表单；不自动发送报告 |
| 普通仓库设置 | 仅 merge commit；已合入 PR head 自动删除；简介明确 CPH 来源；GitHub 原生 auto-merge 关闭 | 保护分支与同步状态分支保留；已结束分支的恢复依靠 PR/可达提交 |
| AI | AI Scan 与 Copilot Autofix 均关闭 | AI 仅由用户主动启动，定时同步不调用 AI |
| 公开发布 | 四平台交付及正式身份/签名验收尚未齐备；每日公开发布和稳定版未启用 | 不把上游安装包、本地工具回归或旧平台运行当作本轮发布产物 |

## 证据与历史

- [PR #6](https://github.com/oncehere/Cataclysm-Phantom-Hope/pull/6) 的实际 merge 为上述基线。其个人维护本地证据、临时例外撤销、父提交/tree 核验见本机工作区 `evidence/maintenance-policy-20260928/`。
- 本次设置与暂停回读、整理方案和结果集中于本机 `evidence/structure-maintenance-20260928/`；这些本机文件不随源码推送。
- 暂停指令的独立回证在本机 `evidence/sync-pause-20260928T043812Z/`，后续回读仍为 revision 10。
- 旧 PR #1/#2 的远端正反例、早期构建失败和所有阶段原文保留在 [整理前状态版本](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/abd9222e01b77ac9e187f53cd6cfe85275453a69/docs/project/status.md)。它们只证明原提交与原策略，不替代新 tooling 验收。
- 原始日志和锁定输入保留。后续更新替换本页快照并引用证据，不在 status、resume、操作手册重复追加同一时序。
