<!-- CPH-DOC: legacy.doc-release-process -->
> **CPH repository documentation / 本仓维护。** Stable document ID: `legacy.doc-release-process`.
> This page is maintained with the CPH source. The inherited
> [CCB migration record](migration/history-assessment.md) is historical.
> [Documentation index / 文档导航](../docs/README.md).

# CPH release preparation / CPH 发布准备

This is a preparation guide, not a live publish command. CPH's [execution specification](../docs/project/execution-spec.md) requires a complete, checked Windows, Linux, macOS and Android set for each public development release; stable releases require a separate explicit decision. Check the dated [status](../docs/project/status.md) and actual GitHub Releases before claiming anything is available. The inherited CDDA `0.G`/`0.H` branch instructions and old CCB release process do not apply to CPH.

## Establish the candidate

Record the exact CPH source commit and upstream CCB integration state. The release controller should attempt a daily check only when an unpublished successful candidate exists, and retry a failed candidate without publishing an incomplete set. Verify [release prerequisites](../project/release-prerequisites.json) and the contract checks in `tools/project/release_contract.py`; a local manifest check is not proof of four platform builds, signatures, install isolation or upload success.

## Acceptance evidence

For each platform, record build/run ID, source commit, artifact digest, package contents, tests, architecture, identity/data path, signing state and any missing hardware validation. Windows/Linux are required merge checks; macOS/Android failures block the whole public release even when they do not block an otherwise authorized merge. Never use a CCB artifact or a Linux-only test as CPH four-platform proof. Use isolated data and disposable saves; installation, update and removal must not damage CCB.

## Before and after publication

The authorized release operator verifies all four artifacts belong to the same accepted candidate, reviews the manifest and checksums, then uses the controlled publication path when that path has been implemented and enabled. Read back the actual release tag, assets, visibility and source SHA. Record a failure as a failure; do not relabel a draft, cached package or historical test as a public release. Maintain third-party license, translation and asset notices. A changelog summary may use [CHANGELOG_GUIDELINES.md](CHANGELOG_GUIDELINES.md); entity diff methods are described in [RELEASE_DIFF.md](RELEASE_DIFF.md).
