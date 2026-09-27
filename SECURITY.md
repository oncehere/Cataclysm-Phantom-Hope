# CPH security policy / 安全政策

## Private reports

The intended CPH private vulnerability route is [GitHub private vulnerability reporting for this repository](https://github.com/oncehere/Cataclysm-Phantom-Hope/security/advisories/new). **Submit details only if GitHub actually shows and accepts the private report form.** Its availability is a repository setting, not something this file can enable; check the dated [project status](docs/project/status.md) and the actual button. If unavailable, this project has no configured official private vulnerability intake yet. Keep the details private until a channel is configured; do not use a public Issue, Discussion, PR, attachment or the CCB/CDDA security channels as a substitute.

CPH 计划使用本仓库的 GitHub 私密漏洞报告。只有入口实际可用时才提交细节；若不可用，目前没有已配置的官方私密收件渠道。请勿在公开位置披露可利用细节、凭据或私密资料。

When the private form is available, include the affected CPH commit/release and platform, threat model and impact, minimal reproduction, sanitized logs, known public disclosure elsewhere and a safe reply route. Do not send credentials; rotate any that may have leaked.

## Scope and response

Relevant CPH-controlled scope includes the current CPH source and bundled content, Lua capability boundary, build and release workflows, official CPH artifacts when available, and CPH installation/data isolation. Third-party mods, unofficial packages and upstream repositories should normally be reported to their owners, while a CPH integration flaw belongs here. A normal crash without security impact belongs in the public bug route when available.

Maintainers will triage as capacity permits; there is no promised response or release deadline. Allow time to reproduce, fix, attribute and coordinate disclosure. A tracked policy or planned release pipeline is not proof of a deployed mitigation. For non-security conduct concerns, see [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md); the vulnerability form is not a general conduct mailbox.
