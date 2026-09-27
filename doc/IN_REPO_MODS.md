<!-- CPH-DOC: mods.in-repository-policy -->
> **CPH repository documentation / 本仓维护。** Stable document ID: `mods.in-repository-policy`.
> This page is maintained with the CPH source. The inherited
> [CCB migration record](migration/history-assessment.md) is historical.
> [Documentation index / 文档导航](../docs/README.md).

# Bundled mods in CPH / 仓库内 Mod

CPH inherits bundled mods through CDDA and the selected CCB history. Their source, authorship and dependencies remain relevant, but this document does not adopt CleverRaven's issue tracker, curator appointments or automatic removal schedule as CPH policy. Read `data/mods/AGENTS.md`, each mod's README and tests, and its actual entrypoint: `modinfo.json` for a JSON mod or `mod.lua`/`main.lua` for a Lua Platform mod.

## Proposing an addition or change

Describe the player's use case, why bundling is appropriate, license/author provenance, dependencies, stable IDs, load order and compatibility with other bundled mods. A third-party mod is not accepted merely because it works in CDDA or CCB. Avoid undeclared cross-mod references and preserve save compatibility or document an explicit migration. For CPH's Lua Platform v1 content, check the native/public API contract rather than assuming a CDDA or old CCB runtime.

Use a CPH branch and PR, name a Responsible human, and run the core JSON load plus the affected mod set. Include tests for parser/runtime edge cases, and report exact commands, installed platform and anything unrun. When CPH Issues is available, track actionable defects there; otherwise use [Discussions](https://github.com/oncehere/Cataclysm-Phantom-Hope/discussions) for public coordination. See [CONTRIBUTING.md](../CONTRIBUTING.md) and [ISSUES.md](../ISSUES.md).

## Maintenance and removal

A proposed mod maintainer or curator can help review but acquires no permanent authority without verified permission and explicit agreement under [OWNERSHIP.md](../OWNERSHIP.md). Another contributor may fix a bundled mod. Deprecating, obsoleting or removing a mod can affect worlds, IDs and saved data; review the actual loader and migration path, test affected saves with disposable copies and record the decision. Do not silently remove inherited credits or classify a CCB/CDDA status as a CPH decision.
