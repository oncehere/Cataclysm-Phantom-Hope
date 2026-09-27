# CPH governance / CPH 治理

This policy applies to `oncehere/Cataclysm-Phantom-Hope`. The inherited CCB source and its governance history do not assign CPH maintainers, GitHub permissions, release channels, or repository settings. CPH's active requirements are in [docs/project/execution-spec.md](docs/project/execution-spec.md); actual source, tests and remote settings decide what has been implemented.

## Authority and decisions

| Subject | Authority |
| --- | --- |
| Runtime, save, JSON and Lua behavior | Current source, tests, schemas, declarations and registrations |
| Build and checks | Build files, current workflows and actual run results |
| Project requirements | Execution specification, subsequent explicit user decisions |
| Contribution and review | `AGENTS.md`, `CONTRIBUTING.md`, this policy and PR template |
| Developer explanation | Current in-repository `docs/` and inherited `doc/`, checked against source |
| GitHub settings and releases | GitHub readback, not tracked target YAML or prose |

CPH is a native CDDA fork that preserves selected CCB history. The designated CCB branch is followed through history-preserving integration; CPH may adapt or revert a behavior for its own design. CDDA changes are selected individually. Record source commits, licenses, authors, compatibility effects and the reason for deviations. The inherited [CCB exclusion ledger](SYNC_EXCLUDED_PRS.md) is historical evidence, not a standing CPH veto list.

## Responsible human and review

Every PR names one real **Responsible human**. They review the final diff, understand the change, own test claims, verify provenance and licensing, and answer review questions. AI-assisted work and bot-authored PRs are allowed; tool disclosure is optional. This role does not imply permanent file ownership or a GitHub approval by a bot. See [OWNERSHIP.md](OWNERSHIP.md) for review roles; no CCB maintainer is assigned CPH authority by this document.

Use the PR template to record documentation impact, current repository document paths, stable document IDs, generated references and actual tests. `ai/docs-impact.yml` controls which mappings are required. The current CPH documentation is in this repository; there is no required CCB-Docs PR. Preserve public contract and generated-file consistency through source-linked checks.

## Merge and release boundaries

A candidate branch, local check or green workflow is not permission to merge. Windows and Linux checks, trusted check provenance, the active `main` protection rule, and a real protected PR must satisfy the [execution specification](docs/project/execution-spec.md) before protected automatic merge is enabled. Preserve merge ancestry; do not require linear history or rewrite imported authors. Automatic AI is outside the unattended workflow design. Current sync and merge state is recorded in the dated [project status](docs/project/status.md) and must be read back remotely before changing settings.

Four-platform artifacts and their agreed checks must all pass before an entire development release is made public. Release availability is recorded in the dated project status and GitHub Releases. Stable publication requires separate explicit authorization. Permanent identity, signing and installation/data isolation also require their own acceptance evidence. [REPOSITORY_SETTINGS.md](REPOSITORY_SETTINGS.md) records the setting boundary; [docs/project/status.md](docs/project/status.md) is a dated implementation snapshot.

## Administrator review

Before changing a privileged setting, an authorized maintainer should record the exact target repository, current value, intended value, check names, bypass actor if required, operator, timestamp and post-change readback. Tracked configuration is a proposal until applied. Do not count a bot review as the required human review, loosen a required gate to make a run green, or describe an untested emergency path as accepted.

本文中的角色与目标不会自动改变 GitHub 设置。实际合入、发布和私密报告渠道均以目标仓库的当前状态与回读为准；旧 CCB 管理员及其审计记录不构成 CPH 授权。
