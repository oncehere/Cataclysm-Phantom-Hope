# Reporting CPH issues / 报告问题

Use [CPH Issues](https://github.com/oncehere/Cataclysm-Phantom-Hope/issues/new/choose) for reproducible defects and actionable work **when that repository feature is enabled**. Check the dated [project status](docs/project/status.md) and the GitHub page for availability. If the form is unavailable, discuss public questions and early ideas in [CPH Discussions](https://github.com/oncehere/Cataclysm-Phantom-Hope/discussions). Do not file a CPH problem in CCB or CDDA merely because this repository's Issues are unavailable.

请先核对 CPH Issues 是否开放。未开放时，可在本仓库 Discussions 讨论公开问题；勿把 CPH 问题误投到 CCB/CDDA。涉及漏洞、凭据或私密玩家资料时按 [SECURITY.md](SECURITY.md) 核对私密渠道，**不要**贴在公开 Issue 或 Discussion。

## Before filing

1. Search existing CPH discussions, issues and PRs for the same problem.
2. Reproduce on a CPH commit or CPH release if one exists; give its exact SHA/tag. A CCB/CDDA version alone cannot establish a CPH regression.
3. Reduce active mods and use a disposable copy of the save. CPH's supported initial path is a new save; do not test unknown builds against irreplaceable or CCB saves.
4. Give OS, architecture, build variant, numbered steps, expected and actual result, logs and screenshots where useful.
5. Remove tokens, usernames, private chat and unrelated personal data before attaching public material.

## Choose a form

| Form | Purpose |
| --- | --- |
| Bug report | Reproducible crash, regression or incorrect behavior |
| Feature proposal | Concrete user problem and observable outcome |
| Mechanics and balance | Gameplay rule, realism, difficulty and trade-offs with evidence |
| JSON content | Stable IDs, recipes, items, maps, EOC or bundled mods |
| Performance | Measured CPU, GPU, memory, I/O or loading regression |
| Documentation | Incorrect, stale, missing or broken in-repository documentation |
| Upstream sync | Exact licensed CCB/CDDA/other source change and CPH conflict analysis |

Forms are repository preparation; their presence does not prove Issues are enabled. Labels are triage hints, not an assignment or schedule; see [LABELS.md](LABELS.md).

## Useful evidence

For a crash, include a minimal reproduction, exact CPH commit, platform, mod list, `debug.log`/`crash.log` and a disposable save if needed. For performance, compare equivalent builds and scenarios on the same hardware and state the measuring method. For JSON/EOC, name the object type, stable ID, source file, load order, relevant conditions/effects and validation. For docs, identify the path, language, inaccurate text and source path that establishes the correction. For an upstream port, give source commit and authors, license, CPH purpose, compatibility effects and tests against CPH `main`.

Maintainers may close duplicates, reports outside scope, unreproducible reports after a reasonable request for information, or rejected proposals with a reason. New evidence can justify reopening. Discuss scope before large work and use a Draft PR when implementation begins.
