<!-- CPH-DOC: contributing.changelog-guidelines -->
> **CPH repository documentation / 本仓维护。** Stable document ID: `contributing.changelog-guidelines`.
> [Documentation index / 文档导航](../docs/README.md).

# CPH changelog summary categories

The [PR template](../.github/pull_request_template.md) asks for a one-line `Summary`: `Category "short description"` or `None`. This is a reviewable proposed summary, not proof that a release or changelog automation is active. Use a player-facing description and avoid claiming a CCB/CDDA release entry.

| Category | Use for |
| --- | --- |
| `Features` | New player-visible capabilities or events |
| `Content` | New or substantially changed creatures, items, maps or other content |
| `Interface` | Controls, menus, information and accessibility |
| `Mods` | Bundled-mod content or mod authoring support |
| `Balance` | Tuning of existing play without a new feature |
| `Bugfixes` | Correcting unintended behavior |
| `Performance` | Measured reduction in load, latency or resource use |
| `Infrastructure` | Maintainer tools, internal refactors and validation |
| `Build` | Build, package or platform support |
| `I18N` | Translation extraction, catalogs and localization support |
| `None` | Changes that do not need a player-facing changelog line, such as many docs or small maintenance fixes |

The category is descriptive; the reviewer can request a clearer summary. Do not add text after `None`. Release-note inclusion is decided by the actual CPH release process in [RELEASE_PROCESS.md](RELEASE_PROCESS.md).
