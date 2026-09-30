# Lua 目标与进度 / Lua goal and progress

此页记录 CPH 的开发方向；实际接口以源码、LuaLS 声明和测试为准。
Source, LuaLS declarations, and tests define current behavior. Acceptance follows
[the CPH execution specification](../../docs/project/execution-spec.md).

## 目标 / Goal

- 让核心内容和 Mod 用 `require("ccb")` 编写行为；静态 JSON 可以保留。
- 优先做能加载、游玩、保存、重进的完整 Lua Mod，再按真实需求补原生接口。
- 迁移仍在使用的 EOC 内容；确认引用归零后再移除旧执行器。
- 不恢复 v5、`game.*`、EOC 风格的新创作入口、公开 JSON loader 或隐藏兼容调用。

## 进度 / Progress

- `ai/lua-first-roadmap.yml` 保留继承的 Platform v1 核心里程碑；这不等于旧内容迁移、完整玩法或 CPH 部署已完成。
- 变量、命名谓词、动态字符串和迁移边界的实现及回归来自 CCB [#923](https://github.com/CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb/pull/923)。源码和测试存在不等于当轮验收通过；实际结果按固定候选另行记录。
- replacement ledger 由 `tools/agent/generate_lua_first_replacement_ledger.py` 按需导出，展开 YAML 不跟踪。`primitive_available_unverified` 仅表示原生积木，`bounded_implemented_unverified` 仅表示明确形状；条目数量不代表完成率。
- 后续缺口从真实 Lua Mod 的加载、持续行为、存档恢复和实际迁移中选取，不为填满覆盖表扩张 Platform。

## 开发与验证 / Development and checks

围绕实际功能写代码，保留能发现行为回归的聚焦测试。新增接口或迁移映射须说明当前用途、行为验收及被替代路径的退出条件；保留现有行为与回归。公共接口变化同步声明和受影响的生成文件；原生行为变化构建匹配程序并运行相应测试。按 `ai/test-matrix.yml` 选择检查，不把逐条 EOC 语义对照或全量语料审计作为每次改动的门槛。只有声明完整替代或删除旧路径时，才核对该声明涉及的合法输入与实际引用。

Lua 契约及工具使用统一套件，它包含 LuaLS、原生清单、公开契约、同步覆盖和 CMake 校验；无需重复运行其各个检查器：

```sh
python3 -m unittest discover -s tools/lua_api -p 'test_*.py'
```

受影响的生成输出按 `ai/generated-files.yml` 刷新；Lua 参考按原生清单、公开契约、同步覆盖的依赖顺序生成，禁止手改。迁移 TODO 保留源位置及 `auto_fix`、`manual_rewrite`、`platform_gap`、`semantic_choice` 分类；只有原生能力缺口驱动核心接口扩展。准确区分源码覆盖、实际验证和语料迁移，报告未执行范围；相关输入不变时按执行规格复用证据。

Implement actual author workflows, preserve focused regressions, and select
checks for changed inputs. Broad parity or EOC removal claims need evidence for
their exact scope. The trust/library policy remains in `LUA_FIRST_PLATFORM.md`;
it does not replace implementation or runtime acceptance.
