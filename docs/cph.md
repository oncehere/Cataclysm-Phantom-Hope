# CPH 本地接入

本工具只接收本地 PO/POT。CPH 接入方负责固定上游翻译包版本、校验下载摘要和许可、提取源码、维护术语及游戏标签规则、安装 MO、测试游戏加载及 CI 资源。核心不认识 CDDA、CCB、CPH，也不下载这些项目。

## 后续实际补译

同日按用户要求建立了 [cph-translation](../cph-translation/README.md) 独立翻译项目。在重新读取 WORKSPACE.md 与适用说明后，从相同 `a43a8f2f...` 提交制作临时源码归档，使用原有提取流程生成 117,224 条完整模板；下载并核对固定官方 CDDA/CCB 翻译构建的原始 PO，实际执行精确合并与 Gemini 补译。下面初版的“完整提取/上游合并 NOT_RUN”现已由 [来源记录](../cph-translation/inputs/source-manifest.json) 和实际翻译项目的结果取代。当前 WORKSPACE.md 已反映该源码版本，不能再把下述早期文档滞后作为当前状态。

游戏工作树仍只读，真实 `obj-lua/` 和存档未访问，MO 安装、游戏加载与 CI 资源验证仍为 **NOT_RUN**。早期 API 补译使用过3.8和3.5；用户随后确认没有 API 额度，当前改为 [Antigravity 内置模型直接翻译、离线导入](../cph-translation/ANTIGRAVITY_HANDOFF.md)。过去的 API 型号选择不约束 Antigravity 当前可用模型。

## 工具初版的只读核验（历史）

2026-09-28 已先读 `/home/oncehere/文档/ChatGPT/CPH/WORKSPACE.md`、`cph/AGENTS.md`、`docs/project/execution-spec.md` 及翻译输入说明。先检查 Git 配置的 `filter.*.clean/process`（无匹配，退出 1），再以 `GIT_OPTIONAL_LOCKS=0` 读取 worktree、HEAD 和排除 `obj-lua/` 的完整改动列表。当前主检出为 `main@a43a8f2f270994dad716ab067c48aad7c2eeaee3`，该范围无改动。WORKSPACE.md 所写主线 `57530d7...` 已滞后，以本次 Git 读回为准。

- `lang/cph/zh_CN.po` 实际存在：251 条，全部已译，无 fuzzy/obsolete；`Plural-Forms: nplurals=1; plural=0;`。SHA256 为 `01f608117db52f720dcdb911dd22eac98a9c05bdcfc7adf16aab8c8f6a929914`。
- `lang/CPHTranslations.cmake`、顶层/`lang/Makefile` 和 `lang/compile_mo.sh` 都有 `msgfmt -c` 编译补充 PO 的路径，输出为 `lang/mo/cph/zh_CN/LC_MESSAGES/cataclysm-dda.mo`。这与已有上游基础 MO 分开。
- `lang/update_pot.sh` 复用 xgettext、JSON 提取器及 msguniq；`lang/merge_po.sh` 使用 `msgmerge --no-fuzzy-matching`。本次未运行提取脚本，因为它会写入游戏树。
- 当前主检出的 `lang/po/cataclysm-dda.pot`、`lang/po/zh_CN.po` 不存在。上游锁定 MO 只能证明编译资源输入，不能充当可维护 PO 的来源。

实际检查命令：

```sh
/nix/store/db8cwzsgxv3lijvf18kqvjjbylm5hrpi-gettext-1.0/bin/msgfmt \
  --check --check-format -o /tmp/pokeeper-real-project/cph-reference.mo \
  /home/oncehere/文档/ChatGPT/CPH/cph/lang/cph/zh_CN.po
```

结果 **PASS，退出 0**（GNU gettext 1.0）。输出仅写入本次 `/tmp`，未修改 CPH。游戏加载、安装、多平台构建、完整 CPH 翻译提取及真实上游 PO 合并均 **NOT_RUN**。本次未访问真实 `obj-lua/`、用户存档或同步控制；没有恢复自动同步。

## 首次建立隔离翻译项目

将 [examples/cph.toml](../examples/cph.toml) 复制为隔离目录的 `project.toml`，准备以下本地文件。不要直接把输出指向游戏树。

```text
cph-translations/
  project.toml
  inputs/cph.pot
  inputs/cdda/zh_CN.po
  inputs/ccb/zh_CN.po
  po/zh_CN.po
```

`inputs/cph.pot` 应由接入方在已核对版本的独立源码检出中运行项目已有提取流程生成。快照必须覆盖维护者希望输出的完整消息集合；当前 `lang/cph/zh_CN.po` 是补充目录，不能自动当成完整游戏 POT。固定 CDDA、CCB 来源版本，替换配置的 `revision` 占位值；工具另记录实际文件摘要，用于区别同一版本标签下的不同文件。所有路径基于配置所在目录。

首次可将 CPH 补充 PO 复制为 `po/zh_CN.po`。因为原 PO 没有本工具基线，使用 `--adopt-existing protect` 明确把已有译文作为需保留的人工内容；若是普通来源导入，可显式选择 `reuse`。以后贡献者直接修改 PO 并提交 PR 即可，不必编辑状态。维护者应把工具应用后的来源状态与 PO 一起提交，基线随项目分支保存。

```sh
pokeeper plan --config cph-translations/project.toml \
  --candidate /tmp/cph-first-candidate --adopt-existing protect
# 审阅完整候选 PO、冲突和缺口报告后应用。
pokeeper apply /tmp/cph-first-candidate
pokeeper check --config cph-translations/project.toml
pokeeper compile --config cph-translations/project.toml --output /tmp/cph-candidate.mo
```

来源顺序实现：受保护人工译文 → 有效 CDDA → 有效 CCB → 现有有效译文；Gemini 只在显式补译操作中填缺口。核心保留精确 `msgctxt/msgid/msgid_plural`；不会猜测新旧原文关系，也不会把来源不同的复数规则自动补齐。项目标签可在配置的 `rules.token_patterns` 中声明，术语由补译配置提供；不要把这些规则写进核心。

示例补译模型为 `gemini-3.7-flash`，附游戏界面、叙述与人物口吻的提示。选择依据见 [模型选型](gemini-model.md)；术语及已确认例句需接入方填写。选择模型不触发 API，原有人工保护与候选审查流程仍然适用。

整体 PO 审阅通过后，由 CPH 维护者在另一个明确授权的接入任务中决定替换哪一个目录、是否继续保留上游基础 MO，以及运行时重复条目的优先级。完整 PO 直接覆盖当前补充 PO 会改变其覆盖范围，本工具不自动执行该操作。MO 加载、安装身份、CI 打包输入和真实游戏显示均需接入方单独验证。
