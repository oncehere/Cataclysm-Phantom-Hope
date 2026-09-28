# Contributing to CPH / 参与 CPH

Cataclysm: Phantom Hope（CPH，中文工作名“虚假的希望”）是保留 CDDA 与选定 CCB 历史的独立开发项目。名称仍是工作名称。本指南适用于 [oncehere/Cataclysm-Phantom-Hope](https://github.com/oncehere/Cataclysm-Phantom-Hope)；CCB 的仓库、`master`、发布和外部 CCB-Docs 不是本仓库的贡献入口。

CPH 的公开讨论入口是 [Discussions](https://github.com/oncehere/Cataclysm-Phantom-Hope/discussions)；Issue 表单可用性请先核对[项目状态](docs/project/status.md)和 GitHub 页面。Issues 尚不可用时，公开问题或早期提案可先在 Discussions 讨论。安全问题按 [SECURITY.md](SECURITY.md) 处理，不要公开漏洞细节。请用明确的 CPH Git 提交或实际 CPH Release 描述复现环境，不要填写 CCB 版本作为 CPH 版本；发布状态见[项目状态](docs/project/status.md)。

## Source of truth / 权威来源

| Topic | Check first |
| --- | --- |
| Requirements and current acceptance boundary | [Execution specification](docs/project/execution-spec.md), dated [status](docs/project/status.md), actual remote runs |
| Runtime, data, public API | Current source, tests, schemas, LuaLS declarations, registrations, generated inventories |
| Build and validation | CMake/Make/Gradle, CI workflows, [test matrix](ai/test-matrix.yml) |
| Contribution rules | [AGENTS.md](AGENTS.md), nearest nested `AGENTS.md`, this guide, [governance](GOVERNANCE.md) |
| Developer explanation | Current in-repository `docs/` and inherited `doc/`, checked against the source |

Read [docs/README.md](docs/README.md) for navigation. Inherited material can describe CCB behavior or older toolchains; cite a current source path when reporting a conflict. Historical CCB exclusions are recorded in [SYNC_EXCLUDED_PRS.md](SYNC_EXCLUDED_PRS.md) and require a new CPH decision before becoming policy here.

## License, provenance, and accountable review

The inherited game and its contributions are distributed under CC BY-SA 3.0 and applicable compatible terms. By contributing to CPH, you agree to contribute under that license, subject to applicable file-specific notices and compatible third-party terms. Preserve those notices and credits. Record the exact source repository, commit/PR, authors and license for adapted material; retain history and original authorship where practical. Do not submit third-party material without compatible rights. An AI output or a link alone is not proof of provenance.

Each PR must name a real **Responsible human**. That person reviews the final diff, understands compatibility impact, owns every claimed test result, checks licenses and attribution, and responds to review. AI-assisted and bot-authored PRs may be submitted; naming the tool/model is optional. This role is PR accountability, not a permanent CODEOWNERS assignment.

## Fork, branch, and propose

Fork **CPH**, then branch from CPH `main`:

```sh
git clone https://github.com/YOUR_USERNAME/Cataclysm-Phantom-Hope.git
cd Cataclysm-Phantom-Hope
git remote add upstream https://github.com/oncehere/Cataclysm-Phantom-Hope.git
git fetch upstream main
git switch -c topic/short-description upstream/main
```

Keep a branch focused and reviewable. For a substantial change, start a Draft PR and update it as evidence arrives. Avoid rewriting imported third-party history, unrelated formatting changes, committed credentials, build caches, local SDK paths, or `obj-lua/`. A contribution with public contract changes must include the corresponding source, declarations, tests, generated outputs and documentation impact.

## Development routes

| Change | Read and verify |
| --- | --- |
| C++ | `src/AGENTS.md`, `doc/c++/CODE_STYLE.md`, relevant tests; `make astyle-check`, focused `./tests/cata_test` after building |
| JSON and EOC | `data/AGENTS.md`, loaders/schema and stable IDs; format changed files and run `make -j2 json-check` |
| Lua | `data/lua/AGENTS.md`, Platform v1 declarations/registrations and `tools/lua_api/` checks; use the generator for inventories |
| Bundled mod | Closest mod instructions and a real loaded mod set; read `modinfo.json` for JSON mods, or `mod.lua`/`main.lua` for Lua Platform mods |
| Android | `android/AGENTS.md`, Gradle test and actual SDK/ABI evidence |
| Translation | Existing PO attribution, `.tx/config`, [translation inputs](docs/project/translation-inputs.md); do not treat temporary MO assets as an editable PO pipeline |
| Docs, automation, governance | `docs/`, `ai/`, `.github/` instructions, metadata tests and current remote state |

The inherited compiling guides remain in `doc/c++/`; choose the guide that matches your toolchain, then check flags against current build files. Keep save tests in temporary data directories. CPH's first supported path is a new save; CCB save migration and installation/data isolation are still acceptance work. Do not test an unvalidated build against a real save or CCB installation.

For ports from CCB, CDDA, or another compatible source, record the exact commits, authors and license, the CPH purpose, conflicts with current CPH behavior, save/stable-ID/mod/Lua/platform impact, and tests against CPH `main`. CDDA is selected case by case; CCB updates are integrated with history while allowing explicit CPH adaptations. Upstream policy and old CCB decisions do not automatically apply.

## Test and documentation evidence

Use [ai/test-matrix.yml](ai/test-matrix.yml) to choose the narrowest useful check. State exact commands, exit codes, platform/toolchain, commit, manual steps, and anything unrun. Local tests, hosted CI, installed game behavior and release acceptance are distinct claims. Do not call a candidate platform check or tracked settings target active until the remote result is read back.

Keep the PR template headings. Use a one-line `Summary` category from the [changelog guidelines](doc/CHANGELOG_GUIDELINES.md) or `None`. Fill in `Documentation impact`, `Repository documentation impact`, `Affected documentation IDs`, and `Generated reference impact`. For paths with a **required** mapping in `ai/docs-impact.yml`, include a current repository document path and the corresponding stable ID; placeholders such as `None`, `N/A`, and `TBD` do not satisfy required fields. This records CPH repository documentation impact without requiring an external CCB-Docs PR. Regenerate official registries only through their generators.

Before requesting merge, verify the final diff and attribution, run applicable checks, document compatibility and upstream divergence, and resolve review comments. Owner-initiated and explicitly authorized personal maintenance uses applicable local results under [execution-spec section 6.1](docs/project/execution-spec.md#61-合入), without waiting for Actions. Docs/Python-only work does not require a full game build; C++/build changes need corresponding local build and regression evidence. Record Linux and Windows separately, including unverified Windows scope, and arrange Windows validation for Windows-specific code or packaging. Reuse existing sufficient checks when their relevant inputs have not changed, recording original SHA, commands, exit codes and the comparison. Unattended sync/automatic merge retains remote Windows/Linux gates; public four-platform releases retain separate acceptance. Any GitHub protection adjustment needs its own impact explanation and user confirmation.

## 中文简要流程

从 CPH `main` 派生分支，先读最近的 `AGENTS.md`、源码与测试。PR 写明真实责任人、来源许可证、兼容性、文档路径/ID、实际运行命令及未运行项。CPH Discussions 是公开讨论入口；提交 Issue 前核对其实际可用性，私密漏洞报告按 SECURITY.md 核对按钮可用性。任何公开附件先删除秘密信息与个人数据。
