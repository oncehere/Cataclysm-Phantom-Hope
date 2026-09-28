<!-- 使用说明：在下面每个「#### 标题」下填写与你的 PR 相关的信息。
请保留这些标题。像这样的注释可以安全删除。

如果你是在 GitHub 网页界面发起这个 PR，可以用「preview（预览）」按钮查看 PR 对他人显示的样子。

PR 提交准则：
- 让你的改动只聚焦于一个具体的问题或变更，外加为实现它所必需的最小相关改动。
- 一个经验法则：大多数 PR 的改动应少于 500 行。
- 你可以另开 PR 来拆分一次较大的预期改动；如果不确定怎么拆，尽管问。我们很乐意与你协作，并建议合并你 PR 的最佳方式。
-->

#### Summary
<!-- #### 概述 -->
分类 "简要描述"

<!-- 这一节应当只有一行，请编辑上面那一行。
1. 把「分类」替换为下列具体分类之一：Features、Content、Interface、Mods、Balance、Bugfixes、Performance、Infrastructure、Build、I18N。
2. 把引号内的文字替换为对你改动的简要描述。
如果你不希望生成更新日志条目，把整行替换为单独一个词「None」（不带引号）。
示例：
1. None
2. Bugfixes "修复长矛无法锁定不同楼层敌人的问题"
3. Interface "在制作界面显示制作失败几率"
分类含义详见本仓库 doc/CHANGELOG_GUIDELINES.md。
是否进入 CPH 更新日志以实际维护流程为准；不要链接 CCB 的 changelog 当作 CPH 输出。 -->

#### Responsible human
<!-- #### 责任人 -->

@username

<!-- 每个 PR 必须指定一名真实的人类责任人。AI 工具或模型无需披露，但责任人
必须理解修改、审查最终 diff、确认测试与许可证/外部来源，并回答审阅问题。 -->

#### Purpose of change
<!-- #### 变更目的 -->

<!-- 用几句话描述你做这次改动的原因。
如果 CPH Issues 已启用，且与本仓库某个 issue 相关，可以用「#」加编号关联，例如 #1234。

【重要】当你的 PR 能完全解决某个 issue 时，必须使用 [GitHub 的英文关闭关键字](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/using-keywords-in-issues-and-pull-requests#linking-a-pull-request-to-an-issue)
才能在 PR 合并后自动关闭该 issue，例如：Fixes #1234。
只能用以下英文关键词（后面紧跟「#编号」）：
  close / closes / closed
  fix / fixes / fixed
  resolve / resolves / resolved
注意：中文「修复 #1234」不会触发自动关闭，GitHub 只识别上述英文关键词。

如果没有相关 issue，请在这里说明你要解决的问题、特性或其他关注点。如果这是一个 bug 修复，请附上复现原始 bug 的步骤，以便你的修复可以被验证。 -->


#### Describe the solution
<!-- #### 解决方案描述 -->

<!-- 这个特性是如何工作的，或者这个 bug 是怎么被修复的？方案越易于理解，就越快能被合并。 -->

#### Describe alternatives you've considered
<!-- #### 你考虑过的替代方案 -->

<!-- 说明你为解决同一问题考虑过的其他方案、不同思路或可能性。 -->

#### Testing
<!-- #### 测试 -->

<!-- 描述你采取了哪些步骤来测试这个 PR 是否修复了 bug 或添加了特性，以及你做了哪些测试以确保没有引入回归问题。也请为审阅者和维护者提供测试建议。参见 TESTING_YOUR_CHANGES.md -->

#### Documentation impact
<!-- None，或说明需要新增、更新、迁移、归档或标记 stale 的本仓库文档。
实际执行级别以 ai/docs-impact.yml 为准。required 映射不能填写 None/N/A/TBD。 -->

None

#### Repository documentation impact
<!-- None，或填写本仓库现行文档路径及对应改动；required 映射必须列出
与下方稳定 ID 对应、可在本仓库追踪的文档路径，如 doc/JSON/JSON_INFO.md。
本字段不要求外部 CCB-Docs PR。 -->

None

#### Affected documentation IDs
<!-- None，或填写 ai/documentation-registry.yml 中稳定的文档 ID，多个 ID 用逗号分隔。
required 映射至少填写一个 ai/docs-impact.yml 列出的对应 ID。 -->

None

#### Generated reference impact
<!-- None，或说明 Schema、LuaLS、注册信息或生成清单是否需要刷新。 -->

None

#### Additional context
<!-- #### 补充说明 -->

<!-- 在此添加关于这个特性或 bug 修复的其他背景信息（例如原型图、概念验证或截图）。 -->


<!-- CPH 继承原作 Creative Commons Attribution ShareAlike 3.0 许可及适用的
第三方许可/署名要求。通过向本项目提交贡献，你同意该许可的条款，并同意你的
贡献受同一许可覆盖；提交前请核对来源权利并保留原作者记录。详见 CONTRIBUTING.md。
详见 https://creativecommons.org/licenses/by-sa/3.0/ 。 -->
