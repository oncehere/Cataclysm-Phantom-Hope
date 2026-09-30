<!-- CPH-DOC: legacy.doc-c-compiling-cmake-vcpkg -->
> **CPH repository documentation / 本仓维护。** Stable document ID: `legacy.doc-c-compiling-cmake-vcpkg`.
> This page is maintained with the CPH source. The inherited
> [CCB migration record](../migration/history-assessment.md) is historical.
> [Documentation index / 文档导航](../../docs/README.md).

# CPH CMake and vcpkg builds

Use [CMake setup](COMPILING-CMAKE.md) for source checkout and the general flow.
The native Windows gate uses Visual Studio 2022, the
`windows-tiles-sounds-x64-msvc` preset, SDL3, gettext and the locked static x64
vcpkg dependency set. Its precise commands are produced by
[`tools/project/ci_build.py`](../../tools/project/ci_build.py) from
[`project/check-policy.json`](../../project/check-policy.json).

## Local development

The separate VS18 solution-header choice does not change this CMake generator.

Open a Visual Studio 2022 developer shell with C++ build tools installed.
Provide a vcpkg checkout matching your intended dependency configuration and
set `VCPKG_ROOT` before configuring. The checked-in MSVC toolchain and manifests
are in [`build-scripts/`](../../build-scripts/) and
[`msvc-full-features/`](../../msvc-full-features/). Do not edit tracked presets
just to store a machine-specific path.

```powershell
$env:VCPKG_ROOT = 'C:\dev\vcpkg'
cmake --preset windows-tiles-sounds-x64-msvc
cmake --build --preset windows-tiles-sounds-x64-msvc --parallel 2
ctest --preset windows-tiles-sounds-x64-msvc --output-on-failure
```

The examples require the selected dependencies and `msgfmt` to be discoverable;
they are not a record of a successful Windows run. For exact CI reproduction,
use its locked vcpkg commit, overlay ports, preinstalled package handling and
output-directory overrides, not a fresh unpinned vcpkg update.

In Visual Studio's CMake interface, select the same configure/build preset and
`RelWithDebInfo`. Presets write under `out/build/<preset>`. To install locally,
use a fresh staging prefix:

```powershell
cmake --install out/build/windows-tiles-sounds-x64-msvc --config RelWithDebInfo --prefix C:\temp\cph-local-stage
```

Read `install_manifest.txt` to locate installed files. Build output, staged
installation, startup and real-save behavior are separate checks. Run probes
with disposable user data, and record native test results against the exact
commit. A local `-DLOCALIZE=OFF` or disabled-test build cannot satisfy the normal
gate.

## Other presets

The repository also contains a Linux vcpkg preset and ClangCL/MinGW presets.
Their presence is configuration support, not native gate or release evidence.
See [compiler/platform scope](COMPILER_SUPPORT.md) before claiming support.
