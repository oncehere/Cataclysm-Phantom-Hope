# CPH 当前状态

本页只保留最新人工核验快照；操作前重新读取 GitHub。需求见 [执行规格](execution-spec.md)，未完成动作见 [恢复入口](resume.md)，本机位置见 [工作区布局](workspace-layout.md)。定时任务不向主线追加运行记录。

## 2026-10-19 接续快照

本轮接续基线为远端 main `ccd32c2bab71`；main 规则已重新读取。
同步游标、旧机安装和平台结果仍引用 10 月 18 日 PR #33 收尾回证，
不把这些历史结果写成新机器或本轮候选的验收。

| 范围 | 已确认状态 | 边界 |
| --- | --- | --- |
| 仓库与历史 | `oncehere/Cataclysm-Phantom-Hope`；原生 CDDA fork，默认 `main` | CCB `master` 是同步输入，CDDA 仅选择性引入；保留来源和 merge 历史 |
| 已合入维护 | main `ccd32c2bab71644cc0f93baee6b18d8e1f516131`，tree `772b5aeab9a20c2deab6cab9c5453c4fc2399f1b`；包含同仓 companion、联机更新、中文快捷键、NPC 赠送修复及 PR #33 CCB 同步 | 历史 PR 不重新实施；后续任务固定当时的实际 main |
| main 保护 | 规则 `24056126` active；严格 `cph/trusted-gate` / App 15368；已保存空 bypass 规则锁 | 个人维护仍按第 6.1 节及具体授权办理；不发布合成的 trusted PASS |
| 自动同步与合入 | **用户要求暂停**：state revision 69，ref `9853fb7b44197d97cbaa345d5e7f9d862ee924f3`；`sync_paused=true`、`merge_paused=true`、`auto_merge_enabled=false`，sync workflow `disabled_manually` | 临时例外已撤销、空 bypass 恢复；只有用户后续明确要求才能恢复同步 |
| CCB 整合游标 | `6a0c46788f43`，PR #33 已合入；完整来源 SHA 见该 PR 及收尾回证 | 后续增量重新读取指定上游分支，不把此游标当作上游实时 HEAD |
| 实际验证 | PR #33 的本机聚焦构建、回归及工具检查通过；Hosted Plan/Tooling 成功，Linux GCC 和 Windows shader 工具仍有失败 | 无 hosted `cph/trusted-gate` PASS；新电脑构建、GUI、真实存档和其他平台未据此验收 |
| 个人维护 | 相关本机检查是验收依据，允许按输入一致性复用旧证据 | Linux 通过不代表 Windows/GUI/完整游戏通过；Windows 专属变化须对应验证 |
| 接续资料与源码 | 私有意图台账 revision 46、1162 项；Dot 三项修复来源 `7b434fc3898e` 已纳入本次源码变更；旧 Nix devshell 保留为未验收候选 | 私有台账不随源码推送；按[换机接续](workspace-layout.md#换机继续开发)恢复。仅这三项修复获本轮合入授权，其他历史审查项不自动推进 |
| 本机安装 | 最近部署回证仍为 `c3dc4e17d441` / system-57，含本机附注补丁 | PR #32/#33 合入不代表已更新实际安装 |
| 公开发布 | 四平台交付及正式身份/签名验收尚未齐备；每日公开发布和稳定版未启用 | 不把上游安装包、本地工具回归或旧平台运行当作本轮发布产物 |

## 证据与历史

- [PR #33](https://github.com/oncehere/Cataclysm-Phantom-Hope/pull/33) 固定受测 head `8eb8ec113df805b8e161738129bbea8007e9a4ae`，实际 merge/tree 与上述记录一致。本机详细回证在 `evidence/ccb-sync-20261015/merge-20261018/completion.json`。
- 本机当前职责和证据位置由外层 `WORKSPACE.md` 登记；这些资料不随源码推送。接续包只携带其 README 明列的资料，缺少原始证据时按需补取或重验。
- 社区、普通设置及更早的维护记录保留在 [9 月 28 日状态版本](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/abd9222e01b77ac9e187f53cd6cfe85275453a69/docs/project/status.md)；它们不证明当前设置或新候选验收。
