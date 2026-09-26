# E2 个人 CDDA fork 实际执行回证

2026-09-26，用户明确授权创建并写入
[`oncehere/Cataclysm-Phantom-Hope`](https://github.com/oncehere/Cataclysm-Phantom-Hope)。
命令行 API 核验当前个人账号为 `oncehere`，目标名称不存在；既有个人 CCB fork
属于 CCB 的独立网络，未复用、删除或改动。执行平台为 Linux x86_64 / NixOS。

## 已部署的范围

| 项目 | 远端回证 | 状态 |
|---|---|---|
| 原生 fork | `POST /repos/CleverRaven/Cataclysm-DDA/forks` 返回 202；目标 ID `1389460908` | PASS |
| 身份和权限 | `fork=true`，个人 owner `oncehere`，parent/source 均为 `CleverRaven/Cataclysm-DDA`；public，admin/push=true | PASS |
| 种子上传 | 新 `main` 指向 `51184a84ba33ce37ab47199081b59c68412fd8d9`，tree `47254cb90b352b13626e789bae25aeb166ca90de`，与本地相同 | PASS |
| 原历史 | 远端 compare 确认 U 是种子祖先，ahead=30、behind=0；B→U 的 5322 个提交和 986 个 merge 保留 | PASS |
| 继承分支 | `master=83548cf6c125857209f72e492e8dcdc21aae9955`，上传前后相同；未强推、重置或合入该分支 | PASS |
| 默认分支 | 种子 SHA/tree 验证后，将本次新目标的默认分支切换为 `main` 并回读 | PASS |
| Actions | 上传前 PUT 关闭且 GET `enabled=false`；默认分支切换后再次确认，run 总数为 0 | PASS |
| 默认 workflow token | `default_workflow_permissions=read`，`can_approve_pull_request_reviews=false` | PASS |
| 自动合入/发布 | `allow_auto_merge=false`；Release 列表为空，没有上传游戏包或配置密钥 | PASS（保持关闭） |
| 分支规则 | rulesets 为空；main protection 返回 404 `Branch not protected` | NOT_RUN（必需检查/保护验收尚未实施） |
| W/L PR 检查与四平台发布链 | 完整可信执行链尚未实现、部署和验收；仅 E4—E7 已有本地组件为 IMPLEMENTED_NOT_DEPLOYED | NOT_RUN |

种子是此次上传前的固定提交；本回证及状态更新由其后独立文档提交追加，不将
文档提交冒充此前 E1/E3 已测试的游戏 SHA。最终远端 HEAD/tree 回读保存在下述
本地证据目录。

## 实际命令、失败闭环与证据

完整 argv、HTTP 状态、进程退出码、平台和日志文件名记录在工作区外的
`evidence/e2-fork-20260926/commands.jsonl`。API 响应仅保存必要字段，不保存 token
或原始认证响应。下表中的简写路径以该 ledger 为准。

| 命令或动作 | 退出码 / HTTP | 结果与日志 |
|---|---|---|
| `prepare_fork.py --repo ... --target oncehere/Cataclysm-Phantom-Hope --branch main --github --dry-run` | 3 | 本地 PASS；当时目标 404，仅报告需要真实 fork；未把 dry-run 当创建成功 |
| `gh api --method POST repos/CleverRaven/Cataclysm-DDA/forks`，指定名称及 `default_branch_only=true` | 0 / 202 | `native-fork-create.json`；原生异步响应先报 main，完成后的 GET 为 master，操作采用完成后的实查值 |
| 目标 Actions 关闭、token 权限设置及分别 GET 回读 | 0 / 204、200 | `actions-disable.json`、`actions-disabled-readback.json`、`workflow-token-readonly-readback.json` |
| `git rev-list --objects --missing=print H --not B` | 0 | 最初缺 8758 个对象；定向 fetch 后缺失数为 0 |
| `git fetch --no-tags --no-write-fetch-head --recurse-submodules=no --refmap= --filter=blob:none ccb --stdin` | 0 | 仅取明确 OID，`directed-object-fetch.*`；没有移动项目 refs 或引入新 CCB 提交 |
| `preflight.py --repo ... --target oncehere/Cataclysm-Phantom-Hope --github` | 0 | 本地历史与真实目标 fork PASS；其只读工具固有的 remote_write_authorization=BLOCKED 不是用户授权失效 |
| 普通固定 SHA 上传，第 1–4 次 | 1 | 均因未缓存的 B 边界对象失败；每次后续回读 main 仍为 404；`seed-push*.stderr.log` 保留，不计 PASS |
| 明确取得继承 master 的 commit/tree 图及 B 边界所缺 1061 个对象 | 0 | `inherited-master-metadata-fetch.*`、`boundary-object-fetch.*`；只读固定历史，没有将当前 CDDA 代码合入 CPH |
| 普通固定 SHA 上传，第 5 次 | 0 | `seed-push-attempt5.*`，仅创建新 main；关闭 lazy fetch、sparse 打包和 thin pack，不使用强推或跳过缺失对象 |
| GET main commit/tree、master 与 U compare；PATCH 默认分支后 GET | 0 / 200 | `main-seed-readback.json`、`seed-commit-readback.json`、`master-after-seed.json`、`u-ancestor-seed-remote.json`、`target-after-default-switch.json` |

缺失对象 `c824c454b80ee953bab8f156d71876bcaa1927e4` 经 `git ls-tree` 确认为 B
中的旧 `.github/labeler.yml`。仅使用 `--no-thin` 或再关闭 sparse 打包仍失败，
不能报告为这些选项单独修复；明确补齐 B 的边界对象后实际上传通过。没有对
缺失对象使用忽略/排除参数，也没有以 dry-run 或工具 fixture 替代真实上传。

成功上传的核心命令如下；实际认证仅使用当前 `gh` 的逐命令 credential helper，
未修改全局 Git/Codex 配置。没有推送 tags、所有分支或 mirror。

```sh
GIT_NO_LAZY_FETCH=1 git \
  -c push.followTags=false -c push.recurseSubmodules=no \
  -c push.negotiate=true -c pack.useSparse=false \
  push --porcelain --no-thin --no-follow-tags --no-force \
  https://github.com/oncehere/Cataclysm-Phantom-Hope.git \
  51184a84ba33ce37ab47199081b59c68412fd8d9:refs/heads/main
```

本地 `origin` 指向上述唯一目标。为兼容 E0 只读预检的边界，所有 remote 的
push URL 仍为 `DISABLED`；实际授权上传明确使用完整目标 URL。CDDA、CCB、
原个人 CCB fork 和无关仓库均未作为写入目标。

## 继续工作的边界

HISTORY_AND_FORK_VERIFIED 已成立；整个首期尚未完成。main 的 29 个继承入口
已隔离，但保留的 master 仍含上游 workflow，因此仓库 Actions 继续关闭。恢复
时先完成最小受控 CI 与可信结果收集，再验证真实 PR 的 Windows/Linux 门槛；
不能把普通 workflow_dispatch 绿色结果当作 PR 必需检查，也不能启用线性历史
要求来破坏继承的 merge 历史。

本轮只变更远端初始化配置和交接文档，没有新的游戏代码改动；游戏/平台构建
本轮 NOT_RUN，已有 E1/E3 证据及其固定测试 SHA 见 [status.md](status.md)。
四平台齐备之前保持公开开发版关闭，稳定版仍需用户单独确认。剩余最小配置
及恢复入口见 [resume.md](resume.md)。
