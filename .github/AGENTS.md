# CPH `.github/` agent instructions

- Workflows are authoritative build and validation contracts.
- Pin third-party actions to full commit SHAs and grant minimum permissions.
- Treat PR titles, bodies, labels, and fork input as untrusted data.
- Stage documentation-impact enforcement through `ai/docs-impact.yml`; require
  a mapping only after its docs and default-branch checks are complete.
- Repository settings described by `ai/repository-settings.target.yml` are a
  CPH target and manual checklist, not proof that settings are active. The CCB
  audit is preserved separately in `ai/history/` and must not be applied here.
- CPH Issues, private vulnerability reporting, branch protection and release
  availability require GitHub readback. A template does not enable its feature.

CI 修改应使用最小权限并固定第三方 Action；不得把目标配置描述成已经生效。
