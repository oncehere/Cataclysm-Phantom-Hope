# Linux E1 原生构建与最小运行探针

本入口构建隔离源码中的 `cataclysm-tiles` 和 `cata_test-tiles`，执行真实
Catch2 测试。它不是 GitHub required check、安装验收或开发版发布器。
未完成 E3 独立身份前，二进制只能在显式临时用户目录内验证。

## 输入与运行

从 U 继承 `linux-tiles-sounds-x64` CMake preset，保留已经存在的 SDL3、
声音、Lua、翻译及测试配置；没有在本轮迁移 SDL 或重构游戏代码。
使用 Ninja 单配置、RelWithDebInfo 和 `-O1 -g0 -DNDEBUG` 控制本机
内存开销。该配置是 E1 实验配置，不是四平台发布目标决定。
`USE_PREFIX_DATA_DIR=OFF` 让测试读取隔离源码数据。

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
以 `nix develop --offline --ignore-environment <drv> --command ...` 启动，
不改 NixOS 或全局 Codex 配置，不向构建注入签名或写权限凭据。
实际工具/依赖版本另存本轮环境证据；此本机 store 引用不是跨机器依赖锁。

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

| 检查 | 来源/命令选择 | 证明范围 |
|---|---|---|
| 游戏版本启动 | `cataclysm-tiles --version` | 二进制能装载并执行版本入口，不是 GUI 启动 |
| 普通翻译回归 | `[translations]~[.]` | U 中普通翻译测试；显式隐藏用例不属于此集合 |
| 中文游戏侧装载 | `TranslationPluralRulesEvaluatorPerformance` | 原有隐藏 benchmark 内的真实中文 `battery → 电池` 及俄文断言 |
| 最小游戏回归 | `horde_map_*` | 继承 matrix 的实际测试选择与游戏数据初始化 |
| 编译修复回归 | `lua_platform_callback_errors_name_the_trigger_and_continue_dispatch` | 错误回调报告上下文，后续回调继续执行 |

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

GUI、打包、安装/更新/卸载、默认目录隔离、跨发行版兼容、Windows/macOS/
Android 原生运行和签名都需要独立证据。E1 的成功不会自动开启合入或发布。
