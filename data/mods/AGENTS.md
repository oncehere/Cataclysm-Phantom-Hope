# `data/mods/` agent instructions

- Each bundled mod is an independent compatibility surface. Read its README,
  tests, dependencies, and actual entrypoint before editing it: `modinfo.json`
  for JSON mods, or `mod.lua`/`main.lua` for Lua Platform mods.
- Avoid cross-mod IDs or implicit load-order dependencies unless explicitly
  declared.
- Keep spoilers and player-facing text in their existing documentation domain.
- Choose validation by the changed runtime input; do not reformat unrelated
  mod files. JSON changes need formatting of the changed files and the changed
  Mod loader check; `make -j2 json-check` only covers core `data/json` syntax.
  Pure Lua changes need the Lua contract checks and a Lua-enabled native
  loader check; JSON formatting alone does not validate Lua. Mixed changes need
  both routes. Read `data/lua/AGENTS.md` for the Lua contract in addition to all
  ancestor instructions.

```sh
python3 -m unittest discover -s tools/lua_api -p 'test_*.py'
```

Use a Lua-enabled binary matching the source with `--check-mods <changed-mod-id>`
and `--datadir ./data/` from the source root, with isolated
`--userdir <temporary-directory>/` and
`--configdir <temporary-config-directory>/`; confirm the Mod ID in `mod.lua`.
Run the relevant native regression filter when behaviour changes. The
`lua-mod-load` and `lua-playable-mvp` routes document these separate checks.

内置 MOD 是独立兼容性边界；先阅读本 MOD 的说明和依赖，再做最小范围修改。
