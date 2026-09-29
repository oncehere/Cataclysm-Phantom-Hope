# `data/lua/` agent instructions

Read `LUA_FIRST_EOC_WORKFLOW.md` for the current goal and progress. Source,
registrations, LuaLS declarations, and relevant tests define current behavior;
`LUA_FIRST_PLATFORM.md` records architecture inherited from CCB and maintained
by CPH. The repository execution specification remains the acceptance policy.

- Use `require("ccb")` as the sole behavior authoring entrypoint. Do not add
  v5, `game.*`, EOC-key APIs, a public JSON loader/EOC runner, or a second Lua
  runtime. Static JSON may remain.
- Full standard libraries and external/native modules are allowed at the
  player's risk; do not reintroduce a sandbox or mandatory global quotas.
  Preserve correctness and lifetime checks; policy acceptance alone does not
  prove implementation or startup acceptance.
- When changing a public API, update declarations and regenerate affected
  references with the generators in `ai/generated-files.yml`. Never hand-edit
  generated files. The replacement ledger is generated on demand by
  `tools/agent/generate_lua_first_replacement_ledger.py`; its expanded YAML is
  not tracked.
- Implement actual gameplay needs and add focused regression tests for changed
  behavior. Run relevant checks; a per-selector EOC audit is not a routine gate.
  Report what was not tested. Historical roadmap and ledger entries describe
  their exact scope; bounded or primitive coverage is not complete migration.
- Migration output is a reviewable Lua skeleton with classified TODOs, never
  a hidden JSON loader, EOC runner, or raw legacy object.
- Keep templates and examples runnable; Mods need neither a `lua/` subdirectory
  nor an author-maintained JSON manifest. Optional `.luarc.json` and `.ccb-sdk/`
  are editor aids, not runtime requirements.

The single Lua contract suite includes live checks and tool regressions:

```sh
python3 -m unittest discover -s tools/lua_api -p 'test_*.py'
```

本仓库的现行文档用于解释这些契约；与源码或声明冲突时更新对应文档。
文档影响通过 `ai/docs-impact.yml` 的稳定 ID 和本仓路径关联，不能用历史
CCB-Docs 记录代替同步，也不得以文档覆盖契约。
