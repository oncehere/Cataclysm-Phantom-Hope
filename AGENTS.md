# CPH repository instructions / CPH 仓库指南

Before implementation, read [docs/project/execution-spec.md](docs/project/execution-spec.md) completely. It is the primary CPH requirement document; earlier reviews and inherited CCB instructions are historical context. Read the nearest `AGENTS.md` for the path being changed, then route tests with `ai/project-map.yml` and `ai/test-matrix.yml`. Current source, tests, build files, schemas, and registrations determine actual behavior. Documentation and tracked targets do not prove a GitHub setting, platform run, release, or deployment.

实施前完整阅读执行规格和最近的 `AGENTS.md`；结合项目地图与测试路由选择验证。不要把历史 CCB 文档、目标配置或本地测试结果写成 CPH 已部署事实。

## Repository and source boundaries

- The authorized CPH remote is `oncehere/Cataclysm-Phantom-Hope`, a native CDDA fork; its default development branch is `main`. CCB `master` is an upstream input, while CDDA changes are selected individually. Preserve ancestry, source authors, attribution, and intentional CPH adaptations. Do not push to CDDA, CCB, or unrelated repositories.
- Preserve the user's work and existing refs. Use an isolated worktree for independent changes. Never touch `obj-lua/`, commit build caches or credentials, or modify global Codex configuration.
- Keep permanent application identity, public APIs, stable JSON IDs, save formats, and real GitHub settings unchanged unless the task explicitly requires and verifies that change. Inherited names inside source contracts may be intentional; changing prose does not authorize renaming them.
- Do not edit vendored third-party code unless the task explicitly targets it.
- Do not hand-edit generated inventories or documentation registries. Use their declared generators in `ai/generated-files.yml`, then inspect the diff.
- No automatic AI, stable release, public development release, signing, or protected automatic merge may be inferred from candidate files. Windows/Linux gate results, four-platform artifacts, identity isolation, ruleset activation, and releases each need their own evidence.

## Work and review

- Use `rg` and narrow reads to find declarations, callers, registrations, tests, and applicable instructions. Keep each change coherent and avoid unrelated formatting churn.
- Select focused checks from `ai/test-matrix.yml`. Report exact command, exit code, tested commit/platform, and skipped checks. A successful local tool test is not game, CI, platform, or deployment acceptance.
- Every PR names a real **Responsible human** who understands the final diff, owns test claims, verifies licenses/provenance, and answers review. AI tool disclosure is optional.
- Complete the PR template's `Documentation impact`, `Repository documentation impact`, `Affected documentation IDs`, and `Generated reference impact` fields. For a required `ai/docs-impact.yml` mapping, name current in-repository document paths and mapped IDs; unrelated changes remain advisory. Explanatory docs do not override source contracts.
- Keep security reports and personal data out of public logs and PRs. Follow [SECURITY.md](SECURITY.md), and verify that GitHub's private form is available before sharing details; current availability is recorded in the dated [project status](docs/project/status.md).

## Common validation entry points

Use only checks applicable to changed paths; these examples are not a universal gate:

```sh
python3 tools/agent/check_project_metadata.py
python3 -m unittest discover -s tools/agent -p 'test_*.py'
python3 -m unittest discover -s tests/project -p 'test_*.py'
make astyle-check
make -j2 json-check
make -j2 tests
```

Lua, Android, data, and other subsystems have their own nearest `AGENTS.md`, source contracts, and focused checks. Preserve source/test provenance when bringing changes from CCB or CDDA. Do not claim unrun commands passed.
