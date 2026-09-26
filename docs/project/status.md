# CPH 本轮实施与交接（2026-09-26）

目标是用户提供的 execution-spec v1；旧研究/review 仅作背景。本轮实施从 E0
开始，完成 Linux E1 并继续当前可执行的隔离与本地控制工作。未完成整个首期。
翻译按用户最新指示先接入真实临时 MO，完整 PO 维护后置。

工作目录 `/home/oncehere/文档/ChatGPT/CPH/cph`，分支
`codex/e0-e1-bootstrap`；从 U `bcb85682f3d28ab0f0123b05e45651bb9888b61b`
开始，第一项自有提交 `166042538d8` 的父提交及 tree 与 U 完全一致。
CDDA B `221c786e7d61b3c9254f7cb1625bc69494b8181c` 是 U 祖先，原始
5322 个后续提交/986 个 merge 保留；没有全面同步 CDDA、squash 或强推。
目标 `OWNER/REPO` 未提供，没有 `origin`，三个来源 remote 的 push URL
均为 `DISABLED`。本地独立克隆不等于已经建立 GitHub fork。
部分更早历史仍带 promisor 元数据；没有宣称所有历史 blob 都已离线齐备。
当前 U 工作树及本轮所需历史对象已核验；后续缺失对象必须显式获取后再验收。

## 游戏与资源真实证据

| 范围 | 状态 | 真实执行与证据 |
|---|---|---|
| E0 本地历史、U tree、环境和工作流隔离 | PASS | preflight 与负例；29 个继承 workflow 原样移到非活动目录，活动入口为零；外部 action 内部行为未运行 |
| E2 目标个人 CDDA fork | BLOCKED | 未明确目标；只读准备工具已实现，无远程写入 |
| E1 翻译冷启动 | PASS | 真实 CCB 发布资源，摘要核验，49 个 MO、24 个许可/署名；无 TX_TOKEN、历史 artifact 或缓存依赖；实际中文加载通过 |
| E1 Linux 真实编译及最小回归 | PASS | 测试提交 c9ffec15d30；configure/build/版本检查及下列 5 组测试均退出 0 |
| E3 Linux 测试身份 | PASS（限定范围） | 测试提交 6cd76598a44；安装、5 种路径解析、73 项资源、核心数据加载、卸载及 CCB 哨兵均通过 |
| Windows/macOS/Android 原生验收 | NOT_RUN / BLOCKED | 本机缺对应运行环境；Windows 探针已实现，macOS/Android 恢复命令与缺口已记录 |
| GUI、新建世界/读写存档、默认 HOME 完整启动、跨版本升级 | NOT_RUN | 核心数据检查不能代替这些场景；未使用用户真实 CCB 安装或存档 |

Linux 实际环境为 x86_64 NixOS，Clang 21.1.8、CMake 4.4.2、Ninja 1.13.2；
复用已有 Nix store 中的依赖开发环境，没有使用旧游戏二进制。继承当前基线的
SDL3/Lua/声音/翻译配置，本轮没有做 SDL 迁移、新 UI 或其他重构。此构建仅证明
本机环境，不是独立可分发包或其他 Linux 发行版兼容承诺。

| 实际游戏测试选择 | 用例 | 断言 | 退出码 |
|---|---:|---:|---:|
| `[translations]~[.]` | 27 | 2620307 | 0 |
| `TranslationPluralRulesEvaluatorPerformance` | 1 | 3 | 0 |
| `horde_map_*` | 10 | 118 | 0 |
| `lua_platform_callback_errors_name_the_trigger_and_continue_dispatch` | 1 | 18 | 0 |
| `lua_platform_task_failure_message_identifies_the_scheduled_instance` | 1 | 9 | 0 |

以上合计 40 个真实用例、2620455 个断言，固定 RNG 4902，JUnit 有非零断言。
中文用例实际核验 `battery → 电池`。没有把工具 fixture 当成游戏运行。
49 个语言文件中 13 个是上游本来只有 header 的文件，如实记录零条翻译；必需
中文和俄文均非空。没有生成空 MO 或宣称所有语言/完整 PO 链验收通过。

## 命令和失败闭环

完整命令（包含工作目录、平台、退出码、日志及摘要）保存在工作区外 evidence；
这里给出可复核入口，命令内的目录以对应 JSON 记录为准。

| 命令/阶段 | 退出码及结论 | 证据目录（相对 CPH 工作区） |
|---|---|---|
| `bootstrap_translations.py` 远程冷启动与资源 `--check` | 0 / PASS | `evidence/e0-e1-20260926/translations-cold-start.json`、`translations-commands.json` |
| `linux_probe.py --phase all --parallel 3` | 0 / PASS | `evidence/e0-e1-20260926/linux-attempt4/{commands.jsonl,result.json}` |
| E3 `cmake -S ... -B ... -DCPH_TEST_IDENTITY=ON -DUSE_PREFIX_DATA_DIR=ON ...` | 0 / PASS | `evidence/e3-linux-build-attempt4/commands.jsonl` |
| E3 `cmake --build ... --parallel 3 --target cataclysm-tiles` | 0 / PASS | 同上，build.log |
| `linux_identity_probe.py --build-dir ... --work-dir ...run4` | 0 / PASS | `evidence/e3-linux-main-identity-run4/result.json` 及 logs |
| AStyle 3.1 对实际修改 C++ 文件的 `--dry-run` | 0，未报告格式差异 / PASS | `evidence/e3-linux-style/command.json` |

Nix 启动命令保留原 HOME：`nix develop --offline --ignore-environment --keep HOME`
后接已核验的 derivation、locale 和探针命令。没有修改全局 Codex/NixOS 设置。

真实失败均保留，分别用独立提交修复：

- 最初中文构建路径受 Nix compiler wrapper 引号影响，configure/编译失败；仅改
  locale 的返回 0 不足以证明 ABI 检测正确。改用新的 ASCII 构建目录和源码别名。
- 两项 Lua 测试在 Clang 21 的 `-Werror,-Wmissing-noreturn` 失败，构建退出 1。
  改为显式 `[[noreturn]]` 静态函数，保留抛异常内容与断言；实际回归均已通过。
- 首次成功链接后的 `--version` 为 -11：`--ignore-environment` 删除 HOME，初始
  路径报错引发早期错误处理递归。保留原 HOME 后同一二进制退出 0；探针现提前
  拒绝缺失/空 HOME。前两次诊断曾误用临时 HOME，已记录偏离，不计验收。
- E3 attempt1 安装退出 1：继承列表有不存在的 data/help；实际帮助数据位于
  data/core，移除失效目录项。attempt2 安装本身退出 0，但探针拒绝失效文档链接；
  将加载顺序文档从真实目标文件安装为普通文件，没有丢弃文档或放宽验证。
- E3 attempt3 核心检查退出 1：显式 config/save 目录尚未建立，诊断日志也无法
  打开。探针先建立自己持有的新目录；同一实际程序独立诊断退出 0，随后 attempt4
  完整生命周期均退出 0。未隐藏游戏错误或修改数据标准。

E1 验证二进制、cache 和成功构建绑定已保存到 `inputs/e1-validated-local-build`；
E3 使用同一编译缓存做实际增量构建。两个场景的源码、配置和证据分别保留，不把
后续工具/文档提交冒充曾经运行过的游戏 SHA。

## 外部条件与继续执行

最小配置清单见 [resume.md](resume.md)。当前仅缺目标信息就足以阻止远程写入，
不影响上述本地修复。真实 GitHub required checks、分支规则、自动同步合入、
四平台打包/必要签名和每日公开开发版均未启用；稳定版没有发布入口。
永久身份、Android 验收 profile 等设计决定仍待明确，没有用测试 ID 或临时签名
包公开发布。无需向聊天提供任何秘密。
