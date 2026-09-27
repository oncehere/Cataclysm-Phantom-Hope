<!-- CPH-DOC: contributing.developer-faq -->
> **CPH repository documentation / 本仓维护。** Stable document ID: `contributing.developer-faq`.
> This page is maintained with the CPH source. The inherited
> [CCB migration record](migration/history-assessment.md) is historical.
> [Documentation index / 文档导航](../docs/README.md).

# CPH developer FAQ / 开发常见问题

This page is a route to current source contracts. The inherited FAQ previously prescribed obsolete C++ files and mapgen tables; do not copy those steps into CPH. Read the nearest `AGENTS.md`, [project map](../ai/project-map.yml), [test matrix](../ai/test-matrix.yml), and the relevant `doc/JSON/` guide before changing a subsystem. Use `rg` to locate its current loader, registration and focused tests.

## Adding a monster or item

Find the current JSON objects under `data/json/` and their type documentation in [MONSTERS.md](JSON/MONSTERS.md) or [ITEM.md](JSON/ITEM.md). Preserve or deliberately migrate stable IDs, check spawn/item groups and dependent mods, then run the changed-file formatter and `make -j2 json-check`. A valid definition does not guarantee the object appears in play; validate the actual group or scenario and a disposable world. Do not assume old filenames such as a single `monsters.json` remain authoritative.

## Adding a map or overmap feature

Start with [MAPGEN.md](JSON/MAPGEN.md), [OVERMAP.md](JSON/OVERMAP.md) and the current JSON examples. The old instructions that edit `omdata.h`, `oterlist`, `omspec_id` and a `draw_map` switch describe an older architecture and are not a CPH implementation path. Trace current terrain IDs, palette, overmap special, generation and tests before editing.

## Changing a bionic or item action

Inspect `data/json/bionics.json`, related item definitions, [JSON_INFO.md](JSON/JSON_INFO.md) and current C++ use/registration code. A flag, action or activation handler may have moved since the inherited FAQ; verify the actual symbol and test rather than adding a new enum or hard-coded entry by habit. Check save compatibility, stable IDs, translation and mod effects.

## Armor, damage and map internals

These are source-defined behaviors. Locate the current damage and coverage code, materials and tests, then document the specific call path and tested build. Historical numbers or old `MAPBUFFER` descriptions in earlier versions of this FAQ are not maintained CPH contracts. The [source guide index](../docs/README.md) points to current technical pages. For any gameplay change, include a focused test and state what a local build does not prove.

## How do I report a mismatch?

Give the document path, current source symbol, tested commit and proposed correction through the CPH [documentation form](../ISSUES.md) when Issues is available, or [Discussions](https://github.com/oncehere/Cataclysm-Phantom-Hope/discussions) for a public question. Sensitive security reports follow [SECURITY.md](../SECURITY.md).
