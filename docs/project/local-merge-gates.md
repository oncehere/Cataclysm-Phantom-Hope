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

这是临时的 E1 契约，Windows 原生基线尚未执行，相关 E3 平台隔离尚未完成。
这些事实不能因本工具测试通过而消除。部署前需将真实跑通的基线和适用 E3
验收纳入经明确审查的策略修订；本文件不是最终门槛已经固化的声明。
macOS/Android 结果可见，但不参与本地合入证据布尔判定，也不构成发布许可。

## 信任边界与输入

必须从已经审查的控制 checkout 执行检查器。候选工作树不能写控制 checkout、
调用参数或可信 context；单靠这个 Python 程序无法建立 OS/runner 权限隔离。
策略和 context 必须来自候选与 artifacts 目录之外的显式路径，调用者提供
各自的 SHA-256。策略再锁定同目录的 `protected-surfaces.json` 摘要。
检查器拒绝符号链接输入、路径逃逸、摘要不符和重复 JSON key。
不要从候选提供的脚本、policy 或环境参数取得这些信任根。

context 是未来可信收集器在低权限构建结束后生成的预期快照，不能直接采用
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
绑定，不能只对上传者声明盖章。当前没有这个 GitHub 收集器或真实规则回证，
因此任何本地 PASS 都不会开放远程合入。JSON/JUnit 应来自受控大小的收集器；
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

目标仓库 `oncehere/Cataclysm-Phantom-Hope` 与管理权限已核验。完成门槛仍需原生 Windows 基线、适用 E3 隔离证据、真实
pull_request 收集/检查发布链，以及受保护 PR 上正常通过、必需失败阻止、
base/head 更新重验的规则回证。规则必须保留 merge 历史、禁止常规强推/删除，
不得要求线性历史或给自动化管理员 bypass。后续虽创建了 `main` 规则，当前仍未启用或验收；本地工具的 PASS 不改变这一状态。

## 验证范围

`python3 -m unittest discover -s tests/project -p test_merge_evidence.py -v`
以新建的真实本地 Git 对象配合明确合成的日志、JUnit 和假二进制覆盖 T01—T06：
W/L 失败、非必需平台失败、缺失/跳过/空报告、dispatch、refs 移动与自批策略。
另验证信任路径、摘要、重复报告、命令/配置、来源/run/attempt、原生标记、
符号链接/逃逸、Git overrides/replace/grafts 及不同最终 merge SHA。
这些是工具模型回归，不能当作游戏、Windows、GitHub 规则或公开发布验收。
