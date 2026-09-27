<!-- CPH-DOC: pr-review-guide -->
> **CPH repository documentation / 本仓维护。** Stable document ID: `pr-review-guide`.
> This page is maintained with the CPH source. The inherited
> [CCB migration record](migration/history-assessment.md) is historical.
> [Documentation index / 文档导航](../docs/README.md).

# Reviewing CPH pull requests / 审阅 PR

Use this guide with [GOVERNANCE.md](../GOVERNANCE.md), [CONTRIBUTING.md](../CONTRIBUTING.md) and the PR template. Review applies to `oncehere/Cataclysm-Phantom-Hope`; old CDDA lead/Discord roles and CCB maintainers do not determine CPH authority. A Responsible human named in the PR owns the final diff, test claims, licensing and follow-up. A bot review does not count as that human's review.

## Review the change

1. Confirm the base is CPH `main`, the goal and diff are coherent, and imported commits preserve authorship and compatible licenses.
2. Trace relevant source, schema, registration and tests. Check stable IDs, saves, mods, Lua/public API, platform and translation effects where applicable.
3. Verify the PR's commands, exit codes, tested SHA/platform and skipped checks. Distinguish local tests, CI, installed behavior, protected merge and release evidence. A reported unrelated CI failure still needs evidence that it is unrelated; do not waive a required gate by assertion.
4. Check the template's documentation paths, stable IDs and generated-reference impact against `ai/docs-impact.yml`. Current in-repository docs must agree with code.
5. Resolve review questions and re-read the final diff after updates. A large mechanical diff can be reviewable if scope and provenance are clear; use focused commits or a second domain reviewer for complex, high-impact work.

## Merge and escalation

Seek extra review for privileged workflows, security, licensing, data migration, public contract changes, major balance/design changes, or a port that conflicts with CPH behavior. The number of comments is not a substitute for verified authority or required checks. Automatic merge stays within the explicit execution-spec authorization and only after Windows/Linux, trusted check provenance and active protected-PR acceptance are proven. A review cannot authorize a stable/public release by itself. Use CPH Discussions or the PR itself for public coordination; sensitive security reports follow [SECURITY.md](../SECURITY.md).
