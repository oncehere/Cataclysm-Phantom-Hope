# Cataclysm: Phantom Hope（大灾变：虚假的希望，CPH）

CPH 是目前使用的**工作名称**。本仓库是 [Cataclysm: Dark Days Ahead](https://github.com/CleverRaven/Cataclysm-DDA) 的 GitHub fork，以保留原始 CDDA 历史的方式纳入了选定的 [Cataclysm: Cleanwater Bomb（CCB）](https://github.com/CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb) 基线。CPH 在此基础上发展自己的技术、界面与功能路线；CCB 是重要来源，并非本仓库的名称或发布渠道。

项目分别维护同步、构建、合入与发布的验证证据。**下载和发布状态以目标仓库实际 [CPH Releases](https://github.com/oncehere/Cataclysm-Phantom-Hope/releases) 为准**；[项目状态](docs/project/status.md)是带日期的快照。用户明确授权的个人维护按[执行规格第 6.1 节](docs/project/execution-spec.md#61-合入)使用相关本机证据合入，不强制等待 Actions，明确记录未验证平台；无人值守同步和自动合入继续要求固定候选的远端 Windows/Linux 结果。GitHub 设置调整须另行说明影响并确认，四平台发布条件保持。不要将 CCB/CDDA 的安装包或承诺视为 CPH 的发布与承诺；恢复入口见[继续实施清单](docs/project/resume.md)。

## 开始参与

- 源码与 PR：<https://github.com/oncehere/Cataclysm-Phantom-Hope>。贡献者应从 **CPH `main`** 建立分支，参见[贡献指南](CONTRIBUTING.md)。
- 远端 Windows/Linux 检查见 [CPH Native CI](https://github.com/oncehere/Cataclysm-Phantom-Hope/actions/workflows/project-ci.yml)；CCB 同步与暂停/恢复操作见[远端同步说明](docs/project/remote-sync.md)。
- 项目讨论与一般求助：[CPH Discussions](https://github.com/oncehere/Cataclysm-Phantom-Hope/discussions) 已启用；报告时请注明准确提交、平台和复现步骤。
- [Issues 说明](ISSUES.md)及仓库内表单已合入；入口是否已启用以 GitHub 页面为准。不可用时可在 Discussions 讨论可公开的问题。敏感漏洞请先阅读[安全政策](SECURITY.md)，勿在公开讨论中发布细节。
- 开发资料从[项目文档导航](docs/README.md)、[项目地图](ai/project-map.yml)及目标路径上全部祖先 `AGENTS.md` 开始。`doc/` 保留继承的游戏与构建资料；使用时按当前源码和测试核对。

## 方向与边界

CPH 将持续检查 CCB 指定主分支的更新，以保留历史的方式整合，并允许为自身设计保留适配或撤销；CDDA 只按需选取改进。首期支持新建存档，不承诺迁移 CCB 旧存档。CPH 与 CCB 的安装身份、配置及存档隔离仍需继续验证；不要用真实存档试验未验收的构建。具体需求见[执行规格](docs/project/execution-spec.md)，来源基线见[上游记录](docs/project/upstreams.md)。旧的 CCB 上游取舍记录属于历史证据，见[排除 PR 记录](SYNC_EXCLUDED_PRS.md)，不自动成为 CPH 决定。

## 许可证与来源

本仓库继承原项目的 **CC BY-SA 3.0** 及各文件所附的兼容许可与第三方声明。保留原作者、提交历史、资产署名和单独许可文件；翻译来源和当前临时输入见[翻译署名](TRANSLATION_CREDITS.md)。

---

## English

**Cataclysm: Phantom Hope (CPH) is a working name.** This repository is a native GitHub fork of Cataclysm: Dark Days Ahead. It retains CDDA history and incorporates a selected Cataclysm: Cleanwater Bomb baseline with authorship intact. CPH has its own development direction; CCB remains a source project, not CPH's release or support channel.

CPH maintains separate evidence for synchronization, builds, merges, and releases. **Check this repository’s Releases for download availability.** Owner-initiated, explicitly authorized personal maintenance uses applicable local evidence without waiting for Actions and records unverified platforms. Unattended sync/automatic merge retains remote Windows/Linux gates bound to the exact candidate; four-platform release acceptance remains separate. Protection-setting changes require an impact explanation and user confirmation. See [execution-spec section 6.1](docs/project/execution-spec.md#61-合入), [CPH Native CI](https://github.com/oncehere/Cataclysm-Phantom-Hope/actions/workflows/project-ci.yml), [sync operations](docs/project/remote-sync.md), and the dated [status](docs/project/status.md).

Fork [this repository](https://github.com/oncehere/Cataclysm-Phantom-Hope) and base contributions on CPH `main`; read [CONTRIBUTING.md](CONTRIBUTING.md). [CPH Discussions](https://github.com/oncehere/Cataclysm-Phantom-Hope/discussions) is available for public questions. Check the [issue guide](ISSUES.md) and the dated [status snapshot](docs/project/status.md) before filing; if Issues are unavailable, use Discussions for public matters. Do not disclose sensitive vulnerabilities in public; see [SECURITY.md](SECURITY.md) for the private-route availability condition.

The initial supported path is a new save, without a promise to migrate CCB saves. Installation and data isolation from CCB need further acceptance evidence. Inherited CCB decisions are identified as history in [SYNC_EXCLUDED_PRS.md](SYNC_EXCLUDED_PRS.md). Source, assets, and contributions retain CC BY-SA 3.0 and applicable third-party notices; see [translation credits](TRANSLATION_CREDITS.md).
