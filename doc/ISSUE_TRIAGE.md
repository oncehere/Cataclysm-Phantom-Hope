<!-- CPH-DOC: maintainers.issue-triage -->
> **CPH repository documentation / 本仓维护。** Stable document ID: `maintainers.issue-triage`.
> This page is maintained with the CPH source. The inherited
> [CCB migration record](migration/history-assessment.md) is historical.
> [Documentation index / 文档导航](../docs/README.md).

# CPH issue triage / CPH 问题分诊

This guide applies when CPH Issues is enabled. Until then, public reports and early ideas can be discussed in [CPH Discussions](https://github.com/oncehere/Cataclysm-Phantom-Hope/discussions); feature availability is recorded in the dated [status](../docs/project/status.md). Do not process CPH work in the CDDA or CCB trackers. Sensitive vulnerabilities follow [SECURITY.md](../SECURITY.md), outside public triage.

## Intake

Check that a report concerns a CPH commit or actual CPH release. Search for duplicates, identify the platform/build and mod set, and ask for minimal steps, expected/actual behavior and sanitized logs. For save problems, protect the original and reproduce with a disposable copy. The initial CPH scope is new saves; CCB save migration is not promised. Link source and test evidence before assigning cause to an upstream project.

## Classify and prioritize

Distinguish observed defect, design proposal, support question, documentation error and upstream port. Crashes, data loss, security implications, installation/data isolation failures and broken merge/release controls need prompt attention, but a priority label is not proof of reproducibility or a release deadline. Confirm a bug with a focused reproduction when practical; state `unconfirmed` where evidence is missing. Balance and realism proposals should separate observations, sources and preferences, and include compatibility trade-offs.

Use only labels that actually exist in CPH; [LABELS.md](../LABELS.md) records inherited vocabulary as a reference. A triager may ask for details, link a duplicate, redirect a public question to Discussions, or close an out-of-scope/unreproducible report with a reason. Reopen when new evidence changes the conclusion. Do not infer owner consent or a promise to implement from a label, comment, or inherited CCB decision.

## Link to implementation

A PR should reference the CPH report where one exists, name a Responsible human, list focused tests and document compatibility, licensing and documentation impact. Protected automatic merge and release readiness are separate checks under the [governance policy](../GOVERNANCE.md). Triage does not bypass them.
