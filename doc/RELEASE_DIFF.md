<!-- CPH-DOC: legacy.doc-release-diff -->
> **CPH repository documentation / 本仓维护。** Stable document ID: `legacy.doc-release-diff`.
> This page is maintained with the CPH source. The inherited
> [CCB migration record](migration/history-assessment.md) is historical.
> [Documentation index / 文档导航](../docs/README.md).

# CPH release diff / CPH 发行差异

No historical CDDA `0.E`/`0.F` tag or `master` checkout is a CPH release comparison. Use two **verified CPH refs**: the previous public CPH release if one exists and the accepted candidate commit. Check [project status](../docs/project/status.md) and GitHub Releases before selecting them; if no previous CPH release exists, label the report `initial baseline comparison` rather than `since last release`.

Record both full SHAs and their provenance. Inspect commit authors and changes without modifying the checkout:

```sh
git rev-parse --verify PREVIOUS_REF^{commit}
git rev-parse --verify CANDIDATE_REF^{commit}
git log --format='%H %an <%ae>' PREVIOUS_REF..CANDIDATE_REF
git diff --stat PREVIOUS_REF CANDIDATE_REF
git diff --name-status PREVIOUS_REF CANDIDATE_REF -- data/json data/mods
```

Replace the placeholder refs with actual fixed tags or SHAs; never paste these commands with literal placeholders. An entity count requires a consistent JSON loader/parser on both trees and a documented mod selection. Raw file or line counts do not show gameplay additions, translations, compatibility or release readiness. If `tools/json_tools/jq/` methods are used, check the scripts against both selected trees and record filtered paths, errors and deletions. Do not switch the user's working tree or reuse CDDA's old numbered examples. Publication acceptance is in [RELEASE_PROCESS.md](RELEASE_PROCESS.md).
