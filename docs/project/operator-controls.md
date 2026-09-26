# E7 本地暂停与封禁前置检查

`tools/project/operator_controls.py` 是原生 Linux/POSIX 的本地状态工具，
**IMPLEMENTED_NOT_DEPLOYED**。它没有 GitHub、合入、签名、发布或启用调度的
能力。成功仅表示操作者的暂停/封禁条件允许继续核验，不能代替 E4/E6 门槛。
Windows 控制进程尚未验证；本工具不影响游戏的 Windows 构建目标。

状态应放在可信控制器独占的持久目录，脱离候选源码；本工具拒绝自身 checkout
内的状态，避免运行状态产生源码提交。未配置远端持久状态、任务隔离和权限前，
本地文件不能作为跨 runner 的正式控制面，也不提供独立安全边界。

```sh
python3 tools/project/operator_controls.py --state /absolute/controller/controls.json init
python3 tools/project/operator_controls.py --state /absolute/controller/controls.json inspect
```

父目录必须预先存在。初始化同时暂停同步合入和开发发布，拒绝覆盖现有状态。
状态包含严格 schema 和单调 revision；写入通过文件锁、原子替换与 fsync 完成。
下面的 `N` 必须替换成刚读取的 revision，每次修改后使用新的 revision。

```sh
python3 tools/project/operator_controls.py --state /absolute/controller/controls.json pause-sync --revision N
python3 tools/project/operator_controls.py --state /absolute/controller/controls.json pause-release --revision N
python3 tools/project/operator_controls.py --state /absolute/controller/controls.json block --candidate CANDIDATE --revision N
```

`resume-sync`、`resume-release` 分别恢复本地操作者开关，`unblock` 只解除指定候选
封禁，均不会自动启用任务、恢复另一个开关或公开候选。恢复后先重新读取持久远端
发布记录、源码/资源与运行证据；同一候选继续使用原身份和预留版本号。已公开的
候选不得重发；403/429/网络错误不得视为没有版本。完整重试执行器尚未部署。

在途任务在实际动作前必须重新运行对应检查，使用启动时记录的 revision：

```sh
python3 tools/project/operator_controls.py --state /absolute/controller/controls.json check-merge --candidate CANDIDATE --revision N
python3 tools/project/operator_controls.py --state /absolute/controller/controls.json check-dev --candidate CANDIDATE --revision N
```

暂停、候选封禁或 revision 变化均返回 **BLOCKED / exit 3**；缺失、损坏和未知
schema 返回 **FAIL / exit 1**。只有该项前置条件满足才返回 0，结果始终包含
`action_executed=false`、`deployment_verified=false`。没有 stable 动作或频道参数。

本工具的读取与后续网络动作之间仍有时间窗口。真实部署必须由可信执行器在发布
事务串行范围内查询持久状态，并在 merge/公开前再核验；本地文件锁并未实现远端
互斥、撤销远端已完成动作或 GitHub 最终公开响应丢失恢复。

撤销 upstream merge 时先记录原 merge、被撤销 U、差异和恢复决定，再以新提交
撤销；不 reset/force-push、不删除祖先。下一次同 U merge 不会自动恢复内容。
已公开问题版先封禁继续推进，记录受影响版本，通过新版本修复；不静默覆盖旧资产，
Android versionCode 仍应递增。公告与远端撤销操作需具体授权后执行。

本轮测试只覆盖本地 T17 暂停/封禁/在途 revision 和 T21 stable 拒绝，以及
T22 状态与源码分离约束；不是实际 GitHub 暂停、合入或发布故障演练。
