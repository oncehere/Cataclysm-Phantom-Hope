# Linux E1 原生构建与最小运行探针

**本地探针操作说明及 2026-09-26 回证：**本文的实际构建和测试结果只绑定当时源码、资源及 NixOS 环境。当前远端 Windows/Linux 门槛与发布状态见 [status.md](status.md)；`../evidence/` 是本机工作区中的私有证据位置，路径规则见 [workspace-layout.md](workspace-layout.md)。

本入口构建隔离源码中的 `cataclysm-tiles` 和 `cata_test-tiles`，执行真实
Catch2 测试。它不是 GitHub required check、安装验收或开发版发布器。
未完成 E3 独立身份前，二进制只能在显式临时用户目录内验证。

## 输入与运行

从 U 继承 `linux-tiles-sounds-x64` CMake preset，保留已经存在的 SDL3、
声音、Lua、翻译及测试配置；没有在本轮迁移 SDL 或重构游戏代码。
使用 Ninja 单配置、RelWithDebInfo 和 `-O1 -g0 -DNDEBUG` 控制本机
内存开销。该配置是 E1 实验配置，不是四平台发布目标决定。
`USE_PREFIX_DATA_DIR=OFF` 让测试读取隔离源码数据。

当前探针从脚本所属检出的 `project/check-policy.json` 读取 Linux 目标、
构建选项、二进制及完整测试清单，与同版本 CI 使用同一声明；不再维护独立列表。
这不把本机结果变成远端可信检查。下方 2026-09-26 回证只证明当时执行范围，
不能追溯扩展为后来加入的测试也已运行。

先按 `translation-inputs.md` 下载并验证临时 MO，再将锁定的 `lang/mo`
文件复制到没有既有 MO 的隔离源码。保留许可与署名原件。测试前逐项核验
MO 的摘要；源码和构建目录必须对应，构建成功记录绑定源码、资源和二进制。

在具备所需依赖的原生 Linux 环境运行：

```sh
python3 tools/project/linux_probe.py \
  --source /absolute/isolated/source \
  --build /absolute/isolated/build \
  --evidence /absolute/new/evidence-directory --parallel 3
```

`--phase configure|build|test|all` 可分别执行。每次使用新的证据目录，失败
日志保留。单独 test 必须有同输入的成功 build 记录，不能拿其他 checkout
或旧二进制生成当前源码的 PASS。`result.json` 与 `commands.jsonl` 记录
状态、命令、退出码、平台、报告/日志摘要；验证脚本的 fixture 单测另列。

本机依赖来自已在 Nix store 中的
`/nix/store/r9ah8qzj0fj8fjq8frkc9x93wn8wkwzr-cataclysm-ccb-sdl3-engine-2026-09-23-0407-bcb85682-sdl3.drv`
开发环境。仅复用依赖，不复用原游戏二进制、构建结果或发行包中的程序。
以 `nix develop --offline --ignore-environment --keep HOME <drv> --command ...`
启动，原样保留已有 HOME；探针拒绝缺失或空 HOME，不改写它。
不改 NixOS 或全局 Codex 配置，不向构建注入签名或写权限凭据。
实际工具/依赖版本另存本轮环境证据；此本机 store 引用不是跨机器依赖锁。

本轮首次成功链接后的版本检查曾因 `--ignore-environment` 移除 HOME 而
SIGSEGV。回溯确认游戏在初始用户路径解析时报告缺失 HOME，早期错误处理
递归崩溃；同一摘要的二进制保留原 HOME 后 `--version` 返回 0。失败环境和
日志原样保留，不能把该次崩溃归为正常环境中的游戏启动失败。

## 非 ASCII 路径问题

首次在中文路径 configure 返回 1：Nix 编译器 wrapper 在 CMake 的
`LC_ALL=C` 检测中对路径产生 ANSI-C 引号，编译器把引号作为参数内容。
仅改外层 locale 后 configure 返回 0，但仍有错误的 ABI/特性检测，不能
采用该结果。最终使用新的 ASCII 临时构建目录，以及指向隔离源码的 ASCII
符号链接，ABI 和特性检测才真正成功。原失败目录/日志保留，不冒称成功。

当前本机 ASCII 根路径记录在仓库外
`../evidence/e0-e1-20260926/linux-build-location.json`。恢复运行应读取该
记录；目录不存在时重新创建隔离目录并 configure/build，不依赖旧路径存在。

## 实际测试集合

下表为 2026-09-26 的历史集合。当前实际选择以策略为准，现已包含
`lua_platform_same_signature_callbacks_destroy_their_own_captures`（`lua-gc`）；
本次声明收敛只验证工具行为，未重跑真实游戏构建和该 C++ 用例。

| 检查 | 来源/命令选择 | 证明范围 |
|---|---|---|
| 游戏版本启动 | `cataclysm-tiles --version` | 二进制能装载并执行版本入口，不是 GUI 启动 |
| 普通翻译回归 | `[translations]~[.]` | U 中普通翻译测试；显式隐藏用例不属于此集合 |
| 中文游戏侧装载 | `TranslationPluralRulesEvaluatorPerformance` | 原有隐藏 benchmark 内的真实中文 `battery → 电池` 及俄文断言 |
| 最小游戏回归 | `horde_map_*` | 继承 matrix 的实际测试选择与游戏数据初始化 |
| 编译修复回归 | `lua_platform_callback_errors_name_the_trigger_and_continue_dispatch` | 错误回调报告上下文，后续回调继续执行 |
| 任务回调修复回归 | `lua_platform_task_failure_message_identifies_the_scheduled_instance` | 错误消息包含实际调度任务身份 |

所有测试固定 RNG `4902`、lex 顺序，各自使用新建 `--user-dir`。
每个选择生成 JUnit，必须实际有 testcase 和正数断言；非零退出、缺失报告、
失败、错误、skipped、disabled 或零断言均失败。Catch2 的 JUnit `tests`
字段在本仓库代表断言数，不把文件存在或空用例当作执行成功。
未选择的隐藏英文翻译 fixture 需要另一套显式资源准备；不能据本集合宣称
所有翻译测试、全部历史测试、语言覆盖或完整 PO 维护链通过。

首次真实构建在 Clang 21 的 `-Werror,-Wmissing-noreturn` 处失败：上述 Lua
测试将始终抛异常的 lambda 直接注册为回调。最小修复改为显式
`[[noreturn]]` 的静态函数，保持异常文本和断言原义，不禁用警告或测试。
修复用例加入本轮真实运行集合，工具 fixture 验证不能代替该用例执行。
继续构建在任务回调测试发现同样的问题，采用相同最小修复。定向检查其余
测试中的 throw 后，没有给仍含正常返回路径的 lambda 添加 noreturn。

GUI、打包、安装/更新/卸载、默认目录隔离、跨发行版兼容、Windows/macOS/
Android 原生运行和签名都需要独立证据。E1 的成功不会自动开启合入或发布。
