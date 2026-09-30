<!-- CPH-DOC: platform-matrix -->
> **CPH repository documentation / 本仓维护。** Stable document ID: `platform-matrix`.
> This page is maintained with the CPH source. The inherited
> [CCB migration record](../migration/history-assessment.md) is historical.
> [Documentation index / 文档导航](../../docs/README.md).

# CPH compiler and platform contract

The language baseline is **C++17**, required by
[`CMakeLists.txt`](../../CMakeLists.txt). A successful configuration is not a
passing build or runtime test. CPH does not yet publish a separately verified
oldest-compiler matrix; the former GCC/Xcode/MSYS version table described an
upstream snapshot and must not be used as a CPH support promise.

## Maintained validation targets

| Target | Configuration source | Evidence required |
| --- | --- | --- |
| Linux x86_64 | `linux-tiles-sounds-x64`; native Ubuntu runner, SDL3 | Build, required tests, runtime metadata and artifact hashes for the candidate |
| Windows x86_64 | `windows-tiles-sounds-x64-msvc`; Visual Studio 2022 runner, SDL3 | Native MSVC build and required tests for the candidate |
| macOS and Android | Informational probes | Separate native/build/device evidence before claiming support |
| MinGW, cross builds, BSD and other recipes | Inherited local build instructions | Their own tested commit and toolchain; they do not satisfy native W/L gates |

The exact generators, options, dependency pins and selected tests are in
[`project/check-policy.json`](../../project/check-policy.json) and
[`project/remote-actions-policy.json`](../../project/remote-actions-policy.json).
Runner labels are in [`project-ci.yml`](../../.github/workflows/project-ci.yml).
A runner label or configured workflow is not a PASS. Record the compiler ID,
version, dependency revisions, commit, configuration, test command and exit
status with every result. See [remote CI](../../docs/project/remote-sync.md).

## Choosing a compiler or using newer features

Use a C++17-capable toolchain compatible with the selected dependency stack.
Test both required native targets before changing the language baseline,
standard-library assumptions, compiler flags or dependency pins. A newer
compiler passing locally does not establish an older minimum or all-platform
compatibility. Preserve the existing project wrappers and lifetime contracts
when replacing library facilities.

[Build instructions](COMPILING.md) and [CMake presets](COMPILING-CMAKE.md)
explain local builds. Keep platform-specific recipes and their evidence separate
from a release qualification claim; market-share estimates and old distribution
release dates are not compatibility tests.

The `scope`, `baseline_status` and `deployment_blockers` prose inside the
check-policy file records the original E4 local baseline. Those fields do not
describe live GitHub deployment. Current remote observations are dated in
[project status](../../docs/project/status.md); actual acceptance requires the
run and settings readback for the candidate. The target/options/test selections
remain the machine-readable inputs used by the current CI runner.
