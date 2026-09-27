# Inherited CCB governance evidence

Files in this directory preserve the CCB repository audit and complete PR artifact publisher test from the source history. They describe `CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb` and `.github/workflows/publish-pr-artifacts.yml`, which was removed before this cleanup. The test was retired from active discovery because its workflow no longer exists; this does not lower a current CPH gate. Current remote workflow inventory checks live in `tests/project/test_remote_workflows.py`. CPH's current observation and deferred gates are in `ai/repository-settings.target.yml`; active agent checks are listed in `ai/test-matrix.yml`.

`doc/migration/` remains a frozen CCB inventory. The old `tools/agent/finalize_legacy_migration.py` helper keeps its historical parser and read-only check, but its write mode is disabled so it cannot restore the retired CCB moved banners over current CPH documentation.
