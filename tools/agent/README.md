# Agent metadata tools

Run these commands from the repository root. Install the pinned Python tool
dependencies from `tools/agent/requirements.txt` into your chosen environment.
For example, use `python3 -m venv /absolute/path/to/venv`, then that environment's
Python with `-m pip install -r tools/agent/requirements.txt`. A missing dependency
is an environment failure, not a passed repository check.

## Context selection

```sh
python3 tools/agent/build_context_pack.py --task "Change an EOC condition" --file src/condition.cpp --format markdown
python3 tools/agent/build_context_pack.py --task-id lua-api --format json
```

`ai/project-map.yml` maps subsystems to instructions and boundaries;
`ai/task-router.yml` maps task wording and paths to those subsystems and documents;
`ai/test-matrix.yml` defines validation commands and their path coverage. The
context pack combines route and subsystem checks with every test-matrix entry
matching an explicit `--file`. An explicit `--task-id` selects the task route but
does not suppress checks for supplied files. Without files, route and subsystem
checks remain available. Commands are recommendations; this tool does not run them.

`documentation_ids` in task routes and context packs are
the unique `id` fields in `ai/documentation-registry.yml`. Their current paths
appear in `source_paths`; unknown, historical and non-indexed targets fail.
PR `Affected documentation IDs` continues to use the separate stable IDs declared
by `ai/docs-impact.yml` and the registry. Old CCB-Docs aliases are not task-route IDs.
The JSON schema retains version 1; consumers of the former route aliases must
switch to registry entry IDs. Small token budgets may truncate listed paths and
instruction text; `truncated` records this and does not waive the source instructions.
If the remaining context cannot fit the budget, the command refuses with exit 2
and asks for a larger `--token-limit`; it never drops validation checks to fit.

`json-syntax` runs the limited Make JSON check. `json-load` requires an actual
game binary, Mod ID and isolated user/config directories through the variables
declared in the test matrix. Both loader commands run from the source root with
`--datadir ./data/`, so a compiled installation prefix cannot select another
installation's data. A syntax result does not prove game data loading.
`lua-mod-load` likewise needs a Lua-enabled game and isolated directories.

## Checks and generated outputs

```sh
python3 tools/agent/check_project_metadata.py
python3 -m unittest discover -s tools/agent -p 'test_*.py'
```

The metadata command validates routing, current documentation registry contents,
the Lua roadmap and replacement ledger, and repository policy. The unit suite
checks tool behaviour and routing directly. Run only the affected tests while
editing a tool; use the metadata command once for the final repository state.

The documentation registry remains tracked. Regenerate it with
`python3 tools/agent/generate_documentation_registry.py` after changing its inputs;
review the resulting diff. Discovery uses tracked Git paths, so stage intended
new or removed document paths before regenerating. Do not edit its YAML by hand.

The expanded Lua replacement ledger is an on-demand output. Running
`python3 tools/agent/generate_lua_first_replacement_ledger.py` prints YAML to stdout;
`--output /absolute/path/report` exports a file. Its `--check` validates current
inputs in memory, or rejects a missing or stale file when `--output` is also given,
without rewriting the file. Reports are not automatically versioned.
