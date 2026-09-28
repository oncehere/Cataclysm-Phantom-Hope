# E4 本地可信证据聚合与保护面检查

**本地工具契约：**本页描述 `check_merge_evidence.py` 自身，不是当前 GitHub 门槛的部署报告。后续已部署受控 CI/gate/sync 入口，`main` 规则是否启用、真实 Windows/Linux 结果及 PR 验收应查 [status.md](status.md)。以下“没有 workflow/发布者”仅指这个离线检查命令。

`tools/project/check_merge_evidence.py` 实现只读的证据一致性检查和保护面
扫描。本步没有 GitHub API、workflow、check 发布者或合入动作。
`evidence_accepted=true` 只表示收到的证据满足本地契约；
`merge_ready`、`github_gate_verified` 和 `public_release_ready` 始终为 false。
普通 dispatch 的成功记录不能变成 PR required check。

## 采用的最小契约

`project/check-policy.json` 按现有 E1 探针记录命令、目标配置和选择，不新增
发布包目标，也不要求全部历史测试。Windows/Linux 都需要原生 x86_64：

| 平台 | 真实入口来源 | 必需记录 |
| --- | --- | --- |
| Linux | `linux_probe.py`，Ninja，继承 SDL3 图形/声音 preset | 构建 `cataclysm-tiles`、`cata_test-tiles`；版本入口；翻译、中文、horde、Lua callback/task 五组 |
| Windows | `windows_probe.ps1`，VS 2022 x64，SDL2 CMake preset | 相同两个构建目标；版本入口；翻译、中文、horde 三组 |

配置为 E1 的 RelWithDebInfo；Linux 保留实际采用的 `-O1 -g0 -DNDEBUG`。
命令及工作目录由可信 context 的 source/build/evidence 路径、并行度与
已审查策略生成，再与收集记录逐项比较。测试固定 RNG 4902 和 lex 顺序；
普通翻译使用 `[translations]~[.]`，隐藏中文用例单独显式选择。
路径和 ID 没有猜测远程目标；fixture 中的 ID 与二进制均明确为合成测试。

这是最初 E1 的本地契约；编写时 Windows 原生基线与相关 E3 平台隔离尚未完成。
后续原生运行及受保护合入回证见 [status.md](status.md)，不能由本工具测试通过
倒推出这些远端结果。本文件不单独声明任何当前候选已通过最终门槛。
macOS/Android 结果可见，但不参与本地合入证据布尔判定，也不构成发布许可。

## 信任边界与输入

必须从已经审查的控制 checkout 执行检查器。候选工作树不能写控制 checkout、
调用参数或可信 context；单靠这个 Python 程序无法建立 OS/runner 权限隔离。
策略和 context 必须来自候选与 artifacts 目录之外的显式路径，调用者提供
各自的 SHA-256。策略再锁定同目录的 `protected-surfaces.json` 摘要。
检查器拒绝符号链接输入、路径逃逸、摘要不符和重复 JSON key。
不要从候选提供的脚本、policy 或环境参数取得这些信任根。

context 是可信收集器在低权限构建结束后形成的预期快照，不能直接采用
上传者自报的 JSON。其最小字段如下：

- `schema_version=1`；正整数 `repository_id`、`pull_request`。
- `base_ref`、`head_ref` 为显式 refs；`base_sha`、`head_sha`、
  `tested_commit`、`tested_tree` 为完整 SHA。测试提交必须有按次序排列的
  base/head 两个父提交。可选 `final_merge_commit` 允许不同 SHA，但必须有
  相同父提交和结果 tree。检查前后重新解析 refs，变化即拒绝。
- `policy_sha`；`inputs_digest` 为收集器锁定源码、资源、依赖和构建输入的
  SHA-256。工具检查它跨收集记录一致，不凭这个字符串证明资源内容正确；
  实际资源锁及 CMake cache 校验仍由已审查的平台探针执行。
- `scope_authorized=true`、`source_verified=true`、
  `conflicts_resolved=true`、`merge_paused=false`。这些是可信控制器输入，
  不是候选能够自签的授权。最后合入前还需控制器重新查暂停与远端状态。
- `runs.windows`、`runs.linux` 各含 `workflow_path`、正整数
  `workflow_id/run_id/run_attempt`、`event=pull_request`，以及
  `layout={source,build,evidence}` 绝对执行路径、正整数 `parallel`。
  `receipt={path,sha256}` 锁定本轮可信收集记录的原始字节。
- 可选 `informational.macos/android` 只原样展示，标记为本工具未验证。

每份 receipt 包含 `schema_version=1`、上述 repo/PR/base/head/tested
commit/tree/policy/input/run 绑定、与策略完全相同的 `target`、
`execution_environment={os,arch,native:true}`。`checks` 必须恰好含 build、
game-version 和该平台全部测试 ID，不能缺失或重复。每项有
`status=PASS`、`actually_executed=true`、整数 `exit_code=0`、完整 `argv/cwd`、
`log={path,sha256}`；测试另有 `junit={path,sha256}`。
`binaries` 按策略相对路径命名，值同样为实际文件的 `{path,sha256}`。
全部 artifact 路径均相对本次 artifacts 根目录，文件实际存在且非空，逐个
重算摘要；日志和二进制流式读取。JUnit 每套必须有直接 testcase 和正数
断言，不接受失败、跳过、disabled、零断言或不一致聚合。

本工具不解析可执行格式，也不能独立证明某 OS 上确实执行过某命令。
SHA-256 证明字节一致，不证明来源；可信收集器必须从实际运行/API 身份获取
绑定，不能只对上传者声明盖章。本地检查器自身不读取或发布 GitHub 收集器、
规则和候选合入状态；当前远端回证见 [status.md](status.md)。因此任何本地
PASS 都不能独自开放远程合入。JSON/JUnit 应来自受控大小的收集器；
本检查器不是任意敌对 artifact 的通用沙箱或解包器，不执行任何 artifact。

## 保护面与恢复入口

保护面覆盖 workflow/权限、检查器与测试、项目策略、上游/资源锁、设计记录、
打包/签名入口和已知身份路径。Git 比较当前 base 与 tested merge tree；删除、
重命名旧路径和替换上层目录也会命中。匹配项只返回具体路径；任何匹配均使
本地证据拒绝，候选的 `protected_changes_approved` 等字段不起作用。
此初始保守清单可能要求对构建/身份改动单独审查；它不能检测所有语义变化。
经过授权的策略更改要在独立受控任务更新可信副本及摘要，再重跑检查。

没有目标 PR 时仍可在外部受控目录准备已经审查的策略及保护面副本，运行
真实本地 Git 保护面扫描（变量必须指向操作者已固定的路径/摘要/refs）：

```sh
python3 /trusted/control/tools/project/check_merge_evidence.py \
  --repo "$candidate_repo" --evidence "$artifact_root" \
  --trusted-policy "$trusted_policy" --policy-sha256 "$policy_digest" \
  --base "$base_ref" --head "$head_ref"
```

扫描缺少可信 PR context，返回 `BLOCKED`、退出码 3，不是门槛成功。
完整聚合用 `--trusted-context "$trusted_context" --context-sha256
"$context_digest"` 代替 base/head。本地一致性成功退出 0，拒绝退出 1，
参数错误退出 2。工具只向 stdout 输出 JSON，不覆盖输入或既有证据。

目标仓库 `oncehere/Cataclysm-Phantom-Hope` 与管理权限已核验。2026-09-27
07:40 UTC 远端回读显示 `main` 规则 `24056126` 已 active，PR #1/#2 的正常
合入与必需失败阻止已由状态分支记录；具体证据与其适用范围见 [status.md](status.md)。
每个新候选仍需自身的原生 Windows/Linux 运行、适用隔离证据、真实
pull_request 收集/检查发布，以及 base/head 更新后的重验。规则须保留 merge
历史、禁止常规强推/删除，不要求线性历史或给自动化管理员 bypass；本地工具
PASS 不能代替这些远端回证。

## 验证范围

`python3 -m unittest discover -s tests/project -p test_merge_evidence.py -v`
以新建的真实本地 Git 对象配合明确合成的日志、JUnit 和假二进制覆盖 T01—T06：
W/L 失败、非必需平台失败、缺失/跳过/空报告、dispatch、refs 移动与自批策略。
另验证信任路径、摘要、重复报告、命令/配置、来源/run/attempt、原生标记、
符号链接/逃逸、Git overrides/replace/grafts 及不同最终 merge SHA。
这些是工具模型回归，不能当作游戏、Windows、GitHub 规则或公开发布验收。

## 远端验收与本地契约的边界

本页本地模型不能代替 [§6.1](execution-spec.md#61-合入) 所需的真实无人值守门槛。每个 required check 须绑定实际命令/目录、配置、平台、测试集合、源码/测试 tree、策略、run/attempt 及结果；最终 merge SHA 可以不同，但父提交和结果 tree 必须与验收组合一致。依赖失败时汇总器仍须拒绝，路径过滤、空矩阵、skip 或 `continue-on-error` 不能放行缺失、跳过、neutral、取消、超时、零测试或过期报告。

候选不得使用自己修改的可信脚本、阈值、权限、发布身份或策略批准自身；放宽门槛须独立明确授权。真正受保护 PR 必须分别证明正常检查允许、必需失败阻止，设置操作见 [REPOSITORY_SETTINGS.md](../../REPOSITORY_SETTINGS.md)。上游总矩阵绿色不证明所需测试执行；旧 E1 测试集合也不自动覆盖当前策略。

历史核验来源（随原规格迁移，本次未重新在线核验）：[GitHub required checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)、[分支保护](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)、[锁定 CCB matrix](https://github.com/CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb/blob/bcb85682f3d28ab0f0123b05e45651bb9888b61b/.github/workflows/matrix.yml)。

## 验收场景

以下为保留的规范性场景；是否已通过须查实际证据，不由本表或模型测试推断。

| 编号 | 场景 | 预期 |
| --- | --- | --- |
| T01 | Windows 或 Linux 必需构建/回归失败 | 拒绝自动合入。 |
| T02 | W/L 成功但 Mac/Android 失败 | 合入可按规则继续；发布拒绝。 |
| T03 | 必需检查 skipped/neutral/空测试/超时/取消/缺失 | 不放行。 |
| T04 | dispatch job 同名且绿色，但不是平台认可的必需检查 | 不误判为 PR 可合入。 |
| T05 | base/head 在测试期间改变 | 重新建立并验收组合。 |
| T06 | 候选修改检查器/阈值/权限自报成功 | 保护面拦截，不能自我批准。 |
