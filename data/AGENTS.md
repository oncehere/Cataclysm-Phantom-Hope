# `data/` agent instructions

Applies to core JSON, bundled mods, schemas, and Lua data.

- Read the nearest nested `AGENTS.md` for `data/lua/` or `data/mods/`.
- Preserve stable IDs unless an explicit migration/obsolete entry accompanies
  the change.
- Keep JSON in repository formatter style and validate data loading.
- Treat schemas and checked generated inventories as contracts, not prose.
- Keep content changes separate from unrelated engine refactors.

Choose checks by their actual coverage. `make -j2 json-check` only parses
`data/json` and checks object `type` strings; it does not validate runtime
references, dependencies, `data/core`, or bundled Mod content. Format changed
JSON files with the repository formatter:

```sh
make -j2 json-check
make -j2 tools/format/json_formatter.cgi
tools/format/json_formatter.cgi <changed-json-file>
```

For actual content loading, use a native binary matching the checked source,
run from the source root, and set `CPH_MOD_ID=ccb` for core or the actual changed
Mod ID. The core directory name `dda` is not its current ID. Create fresh,
task-owned user and configuration directories, then run the `json-load` route:

```sh
"${CPH_GAME_BINARY:?Set a matching game binary}" \
  --datadir ./data/ \
  --userdir "${CPH_TEST_USERDIR:?Set an isolated temporary userdir}/" \
  --configdir "${CPH_TEST_CONFIGDIR:?Set an isolated temporary config directory}/" \
  --check-mods "${CPH_MOD_ID:?Set ccb for core or the changed Mod ID}"
```

Pin `--datadir ./data/` to load the candidate's data rather than a compiled-in
installation prefix. Set both user directories explicitly: XDG builds may otherwise share the normal
configuration directory even with `--userdir`. Put `--check-mods` last because
it consumes all remaining arguments as Mod IDs. Do not substitute `--jsonverify`,
which exits after static initialization before content loading. Record a missing
matching binary as NOT_RUN; syntax PASS does not establish loading PASS. Keep
necessary loader failure logs before cleaning task-owned temporary directories
under the [task cleanup rules](../docs/project/workspace-layout.md#任务收尾与清理).

本目录以稳定 ID、Schema 和实际加载结果为准；修改数据后必须运行最小相关的
JSON 格式与加载检查。
