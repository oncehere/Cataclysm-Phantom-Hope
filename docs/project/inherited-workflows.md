# E0 继承工作流审计与初始化隔离

## 状态与来源

- 主规格：CPH_CODEX_EXECUTION_SPEC_v1.md；本报告只据锁定源与本轮实际检查，不合并旧计划。
- CCB 源：`CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb`。
- 锁定提交 U：`bcb85682f3d28ab0f0123b05e45651bb9888b61b`；tree：`204b14a135ae307ad2180a348a6d6553374a07af`。
- 覆盖：29/29 个 workflow 和 2/2 个本地 composite action 的入口静态审计；重点本地调用链见后文。
- 初始化改动：将 29 个原始 YAML 从 `.github/workflows/` 原样移至 `project/inherited-workflows/`。其相对文件名、原始 blob、大小及 SHA-256 记录在该目录的 `manifest.json`。
- 当前初始化策略：活动 workflow 数必须为 0。原游戏、Make/CMake/Gradle、SDL3、shader 代码和本地 actions 保留。隔离入口不代表删除平台功能，也不代表任何平台构建已验收。
- 本地隔离检查和 fixture 测试为 `PASS`；远端禁用、Actions 设置、可信 W/L 门槛与发布部署为 `NOT_RUN`。这批初始化代码状态为 `IMPLEMENTED_NOT_DEPLOYED`。

后续新增受控 CI 必须经过单独审查并更新初始化策略；本检查器不提供任意 allowlist 绕过开关。它不是可信合入门槛，不证明候选策略不能自行修改，不证明 GitHub 权限实际生效。主线保护、公开发布、签名和稳定版入口均不得因本地测试通过而启用。

## 全部 29 个入口

以下行号均指 U 的 `.github/workflows/<文件名>`，隔离副本行号相同。`C/A/PR/I` 分别表示 contents/actions/pull-requests/issues；`R/W` 表示 read/write；“未声明”表示须查询实际默认权限，不能认定只读。`G` 为内置 `GITHUB_TOKEN` 或 `github.token`；“无自定义”不表示 runner 不存在内置令牌。

| 文件 | 触发、分支与过滤 | 权限与秘密名字 | 外部输入、本地调用及产物流向 |
|---|---|---|---|
| CBA.yml | dispatch；3–4 | 未声明；无自定义 | apt、未锁 commit 的 ClangBuildAnalyzer clone；Make 分析；上传 analysis/traces，19–47 |
| agent-context.yml | PR；push master；dispatch，3–7 | C:R | 文档清单指定历史对象 fetch；pinned Python requirements；PR body/base/head；本地元数据、JSON/EOC、docs-impact 检查，31–88；无发布 |
| assign_mission_target_needs_om_special.yml | PR，仅 `**.json`，3–6 | C:R | 本地 JSON shell 检查，19–22；输出检查结果 |
| build-translations.yml | dispatch/call，2–7 | A:R、C:R；TX_TOKEN 可选、G | checkout master；Transifex CLI/服务，或本仓库成功 master matrix artifact；上传 PO/MO/stats，31–124 |
| clang-tidy.yml | PR master；C/C++/CMake/Make/分析器配置路径；dispatch，3–26 | 未声明；无自定义 | apt.llvm.org 脚本、LLVM、pip lit；本地 tidy build/run/wrapper；插件缓存/artifact；PR changed files；汇总接受 skipped，177–190 |
| cmake-format.yml | push/PR master；CMakeLists、cmake、cmake.in，3–17 | C:R | 未锁版本 cmakelang；本地 lint，33–36；无发布 |
| comment-commands.yml | issue_comment created，3–6 | issue job 未声明；PR job C:R、I:W、PR:W、A:W；G | Comvent 读评论/配置；改 issue/PR 标签、reopen、重跑 failed jobs、写评论，29–117 |
| compose-tilesets.yml | dispatch/call，2–4 | 未声明；G | master formatter；I-am-Erk/CDDA-Tilesets、pixel-32/CDDA-tileset、CCB_UNDEAD_PEOPLE；可变 master/最新 Release；上传 tools/tilesets，11–208 |
| detect-translation-file-changes.yml | PR_target；lang/po 的 PO/POT，4–11 | 未声明；G | PR body 的允许短语；读取并创建 PR 评论，23–62 |
| emscripten.yml | 仅 call，3–4；matrix 调用已注释 | 未声明；无自定义 | emsdk/ccache；本地 build-emscripten/prepare-web；上传 play-cdda，23–93 |
| flake8.yml | push/PR master，仅 Python，3–13 | C:R | apt flake8；make python-check，30–35；无发布 |
| greet-first-time-comment.yml | issue_comment created；PR 评论，3–6、16 | PR:W；G | 硬编码 CCB 仓库贡献查询；当前 PR 写 CCB 欢迎文案，27–45 |
| iwyu.yml | PR master，src/tests/IWYU/CMake 路径；dispatch，2–18 | 未声明；无自定义 | 外部 IWYU clang_19 ref；本地受影响文件/编译库分析与 include 修复；失败上传 suggestions；汇总接受 skipped，71–197 |
| label-first-time-contributor.yml | PR_target opened，3–9 | 未声明；github-script 隐式 G | PR 列表；写 new contributor 标签，23–48 |
| labeler.yml | PR_target，2–4 | C:R、PR:W；G | multi-labeler 读取配置/PR；写 labels，11–24 |
| linter.yml | PR opened/reopened/synchronize/ready_for_review；C/C++/JSON/Make 等路径，排除 src/third-party，3–14 | 未声明；无自定义 | checkout PR head；本地格式器改 runner 文件后检查 diff；失败上传 suggestions，27–108 |
| lua-contract.yml | PR；push master；Lua/元数据路径过滤；dispatch，3–47 | C:R | pinned requirements；Lua、带 SHA256 的 LuaLS 3.19.1；工具单测/契约/编辑器诊断，67–95；无发布 |
| matrix.yml | push/PR master；dispatch run_tests，3–17 | A:R、C:R；变量/门槛 job C:none；TX_TOKEN 仅非 PR | 翻译 reusable、shader action、系统包/SDL/MacPorts/ccache/cache；Linux/Mac/Android 编译和部分实际回归；失败测试二进制与 PR 包 artifacts，110–522 |
| msvc-full-features.yml | push/PR master；排除 android/doc/gfx/lang/tools 等，保留 tools/format；dispatch run_tests，3–39 | C:R；翻译 A:R/C:R；TX_TOKEN 仅非 PR | Windows 2022、MSYS2、固定 vcpkg SHA、ccache；MSBuild；广泛测试仅 dispatch；PR ZIP artifact，65–294 |
| post-spell-check-result.yml | Text Changes Analyzer workflow_run completed；仅 PR success，4–16 | 未声明；G | 下载指定 run 的 PR ID/retcode/output；按 artifact 的 PR ID 删除/创建评论，18–81 |
| post-suggestions.yml | IWYU/Code Style Reviewer workflow_run completed；非 master 且 failure，3–10 | 未声明；G | 指定 run 的 suggestions.zip；固定四个成员解压；未锁 PyGithub；本地脚本按 artifact PR/commit 删/发 review comments，17–42 |
| publish-pr-artifacts.yml | matrix/Windows workflow_run requested/completed，3–8 | A:R、C:R、PR:W；G | 校验 workflow path、PR/head/base master、artifact 元数据；创建/更新固定平台下载链接评论；不下载执行包，28–438 |
| push-translation-template.yml | Experimental Release workflow_run completed；push success 且 repository=CCB，5–21 | C:R；TX_TOKEN | gettext/tx/polib；本地生成 POT 后向 .tx/config 的 CCB Transifex resource tx push -s，23–42 |
| release-android-bundle.yaml | dispatch，2–3 | 默认 C:R；release job A:R、C:W；G、KEYSTORE、KEYSTORE_PASSWORD、KEYSTORE_PROPERTIES | shader action、JDK/Gradle；构建中解密签名；直接公开 AAB prerelease，60–80 |
| release.yml | push master，源码/资源等路径；dispatch channel=experimental/candidate/stable、version，5–39 | 默认 C:R；创建/构建 C:W，构建 A:R；G、TX_TOKEN、KEYSTORE、KEYSTORE_PASSWORD、KEYSTORE_PROPERTIES | 先公开 Release 再构建逐包上传；翻译/tilesets/soundpack/SDK；Android 构建内签名，121–144、230–235、361–363、875–899 |
| request-review.yml | PR_target opened/synchronize/ready_for_review/reopened，4–7 | C:R、PR:W；G | 仅 CCB 仓库；reviewers 配置及外部 action 请求审阅，20–32 |
| sdl3-matrix.yml | dispatch，3–4；要求 CCB_DESKTOP_SDL3_ENABLED=true | 未声明；无自定义 | SDL3/shadercross/SDK/vcpkg/cache；三桌面编译、Windows sound_backend 测试；上传 shaders；自动 trigger 已暂停，11–15、268–271 |
| text-changes-analyzer.yml | PR master；extractor/C++/JSON 路径，4–15 | C:R | base/merge POT；执行 PR extractor；拼写检查；上传 PR ID/retcode/output，34–107 |
| validate-github-config.yml | PR；push master；GitHub/governance 路径过滤；dispatch，3–24 | C:R | Ruby YAML parse、pinned Python requirements、本地治理目标检查，42–50；不验证实际部署 |

全部上述入口均已本地隔离。没有继承每日 schedule。已读 workflow/action 内未发现直接 AI 调用；这一结论不涵盖未深审的第三方依赖内部实现。

## 必须修正的控制与资源边界

1. **公开前置顺序不符。** `release.yml:121–134` 未使用 draft，先公开 Release；`230–235` 的构建才依赖 Release；`898–899` 逐包上传。不能保证四平台齐备后最后公开。`25–39、128–130` 还允许 stable，当前必须关闭。独立 AAB 入口见 `release-android-bundle.yaml:60–80`。
2. **签名/写权限与候选构建混合。** `release.yml:361–363` 给构建 contents:write，`875–896` 解密 keystore 后执行候选 Gradle；AAB 同类问题见 `28–30、60–69`。新发布器应隔离签名及写权限，不能复制该模式。
3. **artifact 高权限回调。** publish-pr-artifacts、post-suggestions、post-spell-check-result 写 PR 评论。前者已有 workflow path/PR/head 匹配，但仍不是 CPH 的可信验收器。后两者从 artifact 接受 PR/commit 元数据，需建立完整来源契约再考虑启用。
4. **跨项目身份。** push-translation-template 和 request-review 虽有 CCB 仓库条件，不能简单换仓库名启用；`.tx/config:28–33` 仍指向 CCB Transifex。欢迎文案、issue/PR command/labeler 也要按明确目标单独审查。
5. **测试默认跳过。** `matrix.yml:99–108` 仅 dispatch 且 run_tests=true 令 skip_tests=false；`294` 对 Android/macOS 还强制跳过广泛测试。`428–430` 才执行 gha_test_only。Windows 同样仅 dispatch 执行广泛测试（msvc-full-features:240–243）。编译测试程序不是执行测试。
6. **不能称继承 CI 完全没有测试。** matrix:409–411 跑 horde_map；432–434 跑隔离 wait_popup_cleanup；435–439 跑 Lua semantic。gha_compile_only:41–54 有 JSON/dialogue/gun 校验。新门槛应准确写入真正执行的集合。
7. **汇总允许 skipped。** matrix 的 PR Gate 在 574–576 接受 success/skipped，并按路径路由；不能直接当成规格的 W/L 必需实际成功门槛。Clang-tidy/IWYU 也允许 skipped。
8. **翻译首次初始化循环。** build-translations:31–40 固定 checkout master；86–102 在无 TX_TOKEN 时查询当前 GITHUB_REPOSITORY 的成功 matrix/master/push，再下载 translations。无历史时 94–96 exit 1；matrix:110–118、133–134 又依赖该 reusable。新仓库不能靠自己的第一次成功历史启动。
9. **U 不自带真实翻译。** 锁定 Git tree 的 lang/po 仅有 `_DO_NOT_EDIT_FILES_IN_THIS_DIR_BY_HAND`，lang/mo 仅 `.gitignore`。已有源 clone 的未追踪缓存不是 U 的输入。资源初始化应另行锁定真实来源、哈希、许可、署名与覆盖，不生成空 PO/MO。
10. **资源验收要报告实际范围。** discard_invalid_po:26–34 会丢弃不合格语言，不能以余下非空宣称全覆盖。release:392–407 的零真实 PO 对非 master 仅 warning；不能保留这种由分支名降低质量要求的规则。
11. **笔记生成与发布状态不可信。** generate-release-notes.js:44–72 只读一页 Release，116–118 失败退出 0。不能作为规格中的可恢复候选/发布查询器。

## 本地调用链与外部依赖

- `matrix → requirements.sh → gha_compile_only.sh → Make/CMake/Gradle`。广泛测试是 `gha_test_only.sh → cata_test/parallel/get_all_mods.py`。JSON 校验还调用 validate_json、dialogue_validator、generic_guns_validator、gun_variant_validator。没有因为文档存在就报告这些平台构建已执行。
- `build-sdl3-shaders/action.yml:41–71` 拉取固定 shadercross commit，调用该外部仓库的 CMake 脚本下载 DXC；随后 `tools/build_shaders.py` 编译 spv/dxil/msl，上传 cdda-shaders（73–102）。shadercross 的外部下载实现未深审。
- `setup-sdl3-stack/action.yml:50–153` 从 SDL 3.4.10/image 3.4.4/ttf 3.2.2/mixer 3.2.4 tag 构建，缓存安装前缀、输出环境、可收集许可证。tags 与缓存尚不等于内容锁定。
- `compose-tilesets → tools/gfx_tools/compose.py/json_formatter`。资源来自两个仓库的 master 及 CCB_UNDEAD_PEOPLE 最新 Release（compose-tilesets:42–128、150–173）。release:376–380 另从未锁定 soundpack clone 取得 CC-Sounds。
- `build-translations → tx pull → discard_invalid_po.sh → update_stats.sh → compile_mo.sh → translations artifact`。内部 gettext 域仍是 cataclysm-dda；隔离并不进行全仓改名。
- `text-changes/push-template → update_pot.sh → extract_json_strings.py/string_extractor + unicode_check.py`。只有 push-template 含 Transifex 上传动作。
- `post-suggestions → post-diff-as-comments.py:49–85、285–313`：读 artifact PR/commit，删除 marker 评论再创建 review comments。
- `clang-tidy → clang-tidy-build.sh/run.sh/wrapper.sh → CMake、lit、get_affected_files.py、clang-tidy`；`iwyu → ci-iwyu-run.py → get_affected_files.py、外部 iwyu_tool.py/fix_includes.py`。修改仅发生在 runner 工作树，用于生成 suggestions，不是本轮执行过的修复。
- `release → generate-release-notes.js、windist.ps1、Make bindist/dmgdist、Gradle APK`；AAB 入口直接调用 bundleExperimentalRelease。Windows 打包脚本会重建本地 bindist；只能在隔离构建目录运行。

全部显式外部 `uses:` 已锁 40 位 SHA，清单及调用位置保存在 `project/inherited-workflows/external-actions.json`。这不是第三方 Action 内部安全深审。apt/npm/pip、CLI tarball、可变 branch/tag、外部 Make/Gradle/CMake 递归输入仍需资源锁定与实际构建验证。42 个直接文本引用已做存在性与外部 I/O 静态扫描；该数量不是整个构建依赖闭包。未深审项明确保留为 `NOT_RUN`，不声称供应链全部审计完成。

## 可重复检查与本轮证据

在仓库根运行：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/project/check_workflow_quarantine.py --repo "$PWD"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/project -p test_workflow_quarantine.py -v
```

检查器只读取指定 Git 源和工作树，不联网、不 fetch、不修改配置。它拒绝影响 Git 身份/历史的 GIT_* 环境覆盖、replace refs 和 grafts；每次 Git 调用设置 GIT_NO_LAZY_FETCH=1、GIT_OPTIONAL_LOCKS=0、关闭全局/系统配置、替代对象、fsmonitor、hooks 和默认 transport。它从 U 的 Git 对象重新计算清单，而不是信任可修改的 manifest 哈希。缺失/改动/额外 YAML、伪造 manifest、symlink、活动入口、空 baseline 都拒绝；CLI 退出码 0=通过，1=本地隔离失败，2=参数或源读取错误。`--baseline` 仅用于明确的替代来源调查/合成 fixture，正式验收使用默认 U。

本轮 Linux x86_64 实测：两个命令退出 0，29 个文件与源大小/SHA-256 相同，活动入口 0；16 项合成 Git fixture 回归通过。fixture 测试覆盖保持字节、修改并伪造清单、缺失/额外文件、活动 project workflow、缺清单、文件及目录 symlink、无效对象/错误仓库根、空源、CLI 退出码、环境覆盖不泄值、replace/graft 拒绝、全局配置隔离、缺失 promisor blob 不触发 transport。最后一项使用只在临时目录写哨兵的本地 transport fixture，并有解除只读保护时确实触发哨兵的正对照；不访问网络。它们不是游戏/Windows/macOS/Android 或 GitHub 平台验收。

日志位于授权工作区仓库外 `../evidence/e0-e1-20260926/`：

- `workflows-validation.json`：真实 argv、cwd、平台、退出码、耗时、stdout/stderr 文件名。
- `workflows-quarantine.stdout.log`：29 项内容摘要及检查结论；stderr 单独保存。
- `workflows-tests.stderr.log`：逐例结果及计数；stdout 单独保存。
- `workflows-diff-review.json`：本轮自身 diff 与原始字节保留复核。

源码静态读取使用 `git ls-tree -r --name-only U .github`、`git show U:path`、`git cat-file`，实际 29 个入口及 2 个 action 均读取成功。早期探索错误旧脚本名/截断扩展名的探针返回 128，已改用确认存在的实际路径；不把这些探索错误报告成游戏或 CI 失败。

恢复入口：目标 OWNER/REPO 与权限明确后，在 E2 的受控种子提交中保留隔离状态，再从已实际验证的构建/测试命令建立最小低权限入口；W/L 真实门槛、四平台发布、签名和稳定版各有独立前置条件。不能批量把归档 YAML 搬回去或将本检查器改成总是通过。原继承元数据/工具测试若硬编码旧 workflow 路径会需要后续有范围的适配，未把它们列为本轮已通过检查。
