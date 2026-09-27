<!-- CPH-DOC: getting-started.how-you-can-help -->
> **CPH repository documentation / 本仓维护。** Stable document ID: `getting-started.how-you-can-help`.
> This page is maintained with the CPH source. The inherited
> [CCB migration record](migration/history-assessment.md) is historical.
> [Documentation index / 文档导航](../docs/README.md).

# How to help CPH / 如何参与

CPH is a native CDDA fork with a selected CCB history baseline and its own development direction. You can help by reproducing a CPH defect, reviewing a proposed change, improving an in-repository guide, translating with attribution, or preparing a focused source/data/mod PR. Read [CONTRIBUTING.md](../CONTRIBUTING.md) and the nearest `AGENTS.md` before editing.

## Find work and discuss ideas

Use [CPH Discussions](https://github.com/oncehere/Cataclysm-Phantom-Hope/discussions) for public questions, early ideas and build help. If CPH Issues is available, use its [forms](../ISSUES.md) for actionable work and search existing CPH reports first. Check the dated [project status](../docs/project/status.md) and GitHub page for feature availability. The inherited CDDA issue tracker, Google form, Discord roles and labels are not CPH contribution routes.

A useful report names the exact CPH commit or release, platform, mod set, steps, expected/actual result and sanitized evidence. Test against a disposable save. For a suspected vulnerability, follow [SECURITY.md](../SECURITY.md) and never publish sensitive details.

## Contribute a change

1. Fork [the CPH repository](https://github.com/oncehere/Cataclysm-Phantom-Hope), branch from CPH `main`, and keep one coherent change per PR.
2. Identify the current source, schema, tests and nearest `AGENTS.md`; check [project map](../ai/project-map.yml) and [test matrix](../ai/test-matrix.yml).
3. Record upstream commits, authors and licenses for any imported CCB/CDDA/other work. Preserve stable IDs and public contracts, or propose an explicit migration.
4. Run focused checks and report exact commands, exit codes, platform and unrun checks. A local test is not remote CI or a published release.
5. Open a Draft PR when useful, name a real Responsible human, and complete documentation paths/IDs in the [PR template](../.github/pull_request_template.md).

Documentation, tests and reproducible platform failures are useful contributions even without gameplay changes. For current project progress, read the [status](../docs/project/status.md), [execution specification](../docs/project/execution-spec.md) and [remaining work](../docs/project/resume.md). Labels, if present, are triage hints rather than assignment or acceptance promises; see [LABELS.md](../LABELS.md).
