# E1 Windows, macOS and Android probes

These are local build/probe entrypoints, not E4 required checks or deployed
workflows. No target repository, platform runner or signing identity is inferred.
Current evidence was collected on Linux; native Windows/macOS/Android execution
and Windows PowerShell parsing are **NOT_RUN**. There is no `pwsh` here, so text
review does not establish that a Windows script parses or runs successfully.

## Windows: executable probe, awaiting a native environment

Use `tools/project/windows_probe.ps1` only in a disposable isolated checkout and
a VS 2022 x64 Developer PowerShell 7 session. Supply disjoint source/build/new
evidence directories, a verified translation-resource directory, the pinned
vcpkg checkout and its already populated `x64-windows-static` installation.
The checkout must satisfy the E0 initialization preflight's explicit read-only
remote configuration; this is not an entrypoint for arbitrary existing clones.

Required tools are Git, Python 3, CMake, MSBuild/MSVC and gettext `msgfmt` on PATH.
The inherited `.github/workflows/msvc-full-features.yml` at pinned U (see
[source inventory and Git read command](inherited-workflows.md)) uses Windows
2022, CMake 3.31.6, SDL2 and vcpkg commit
`f6672d8e480ccdecddfad3fd1b838ba369ffe6cd`. The new probe reads that commit from
`msvc-full-features/vcpkg.json`, checks the supplied checkout, records actual SDK
and MSVC developer-shell versions, and fails when dependencies are unavailable.
It does not guess an SDK, run a package manager, download executables, call
`vcpkg integrate install`, or request administrator rights. CMake's vcpkg
manifest installation is disabled; configure must resolve the supplied inputs.

First initialize and verify real translations using the existing bootstrap tool
in a separate resource directory. Place its locked `lang/mo` files in the
isolated source checkout before invoking the probe. The script independently
checks the complete resource directory and every source MO's size/SHA-256;
missing or changed resources fail. It never disables localization to proceed.

Example using explicit disposable directories, after dependencies/resources
have actually been prepared:

```powershell
pwsh -File C:\cph-lab\source\tools\project\windows_probe.ps1 `
  -SourceDir C:\cph-lab\source -BuildDir C:\cph-lab\build `
  -EvidenceDir C:\cph-lab\evidence\windows-attempt-001 `
  -ResourcesDir C:\cph-lab\resources `
  -VcpkgRoot C:\cph-lab\vcpkg `
  -VcpkgInstalled C:\cph-lab\vcpkg-installed -Parallel 2
```

The inherited workflow actually uses this MSBuild solution command:

```powershell
msbuild -m -p:Configuration=Release -p:Platform=x64 -p:UseSDL3=false `
  '-target:Cataclysm-vcpkg-static;Cataclysm-test-vcpkg-static;JsonFormatter-vcpkg-static;zzip' `
  msvc-full-features/Cataclysm-vcpkg-static.sln
```

The probe intentionally uses the separately inherited, real
`windows-tiles-sounds-x64-msvc` CMake preset and builds `cataclysm-tiles` plus
`cata_test-tiles` in `RelWithDebInfo`. This is a CMake baseline probe, not a claim
that the solution workflow was replayed. SDL2 is explicit (`USE_SDL3=OFF`),
matching that workflow. Localization and tests remain enabled; binaries go to
the explicit build directory, and existing CMake caches must match the source.
Lua stays enabled. Home/XDG data modes are explicitly disabled, with process-only
XDG directories additionally redirected into this attempt. The actual configured
cache must match all declared options, generator/platform and explicit vcpkg
root/install/output paths; a previous cache cannot silently substitute them.

After the game `--version` invocation, the probe runs these real C++ selections
from the source directory with distinct temporary user directories and seed
4902: `[translations]~[.]`, `TranslationPluralRulesEvaluatorPerformance`, and
`horde_map_*`. The explicit Chinese benchmark is hidden from ordinary default
selection; it loads `zh_CN` and requires the real `battery` translation. Its
Russian section uses the maintained `TEST_DATA` fixture in this checkout.
`tests/CMakeLists.txt` compiles that fixture from its checked-in PO through the
`test_mo` dependency. This fixture is a C++ regression input, not a substitute
for the locked real game MO resources.

Native nonzero exit codes propagate. JUnit reports must contain executed cases
and positive assertion counts in each suite, with consistent totals and no
failure/error/skipped/disabled outcomes, even if a process returns zero. This
Catch2 version uses the JUnit `tests` attribute for assertions. Missing/zero
counts are rejected even when a `<testcase>` element exists.
Each command records argv, directory, platform, exit code, log and digest in
`commands.jsonl`; `inputs.json` and `result.json` describe the actual attempt.
`configured-cache.json` records the verified configure inputs and cache hash.
Results include both executable hashes and every JUnit hash/count. Afterward,
preflight must pass again with the same HEAD and branch; MO and binary hashes
must still match the inputs. Game arguments use `--userdir`, while the separate
test harness uses `--user-dir`, matching their respective source interfaces.
Missing prerequisites return `BLOCKED`/3; failed commands/tests return failure.
Old evidence is never replaced. Common credential variables are removed only
within this process and restored afterward; use a disposable runner without
secrets, rather than treating variable filtering as a security sandbox.

This does not test a packaged ZIP, interactive GUI, concurrent CCB installation,
upgrades/uninstall, Windows signing or a protected GitHub PR. Those remain
unverified even if this native probe later passes.

## macOS: inherited commands, not yet an executed CPH probe

The locked matrix's SDL2 graphical leg targets `macos-15`, Apple Clang 17 and
the original Make build. Its actual packaging command is:

```sh
make -j1 CCACHE=1 LINTJSON=0 DEBUG_SYMBOLS=1 NATIVE=osx TILES=1 SOUND=1 SDL3=0 RELEASE=1 LOCALIZE=1 LANGUAGES=all BACKTRACE=1 PCH=0 FRAMEWORK=1 UNIVERSAL_BINARY=1 WARN_STALE_DATA=0 dmgdist
```

Run only in a dedicated macOS checkout after supplying the actual toolchain,
gettext, ccache, SDL2 frameworks, universal dependency libraries, `dylibbundler`
and DMG tooling described in the quarantined inherited workflow. Record
`xcrun --show-sdk-path`, `clang++ --version`, `uname -m`, command exits and the
resulting `.app`/`Cataclysm.dmg` hashes. Inspect each executable with `file`,
`lipo -archs` and `otool -L`; then perform the applicable native startup and
resource checks from isolated data directories.

The inherited command requests a universal build; that does not prove two
architectures exist or execute. The inherited matrix also skips macOS C++ test
execution; copying that skip cannot become CPH test acceptance. The MO-only
bootstrap must be checked against Make's localization/packaging behavior before
using its output for a candidate. No macOS runner/toolchain or DMG run has been
verified here, and no installation or host package changes were attempted.

## Android: inherited ARM64 build, identity and runtime still blocked

`build-scripts/gha_compile_only.sh` invokes this from the `android/` directory:

```sh
./gradlew -Pj=2 -Pabi_arm_32=false -Pprebuilt_shaders=true assembleExperimentalRelease
```

Here `-Pj=2` is a bounded local concurrency setting replacing the inherited
`nproc` value. The source defaults enable ARM64 and disable x86/x86_64. Verify
the user's actual device ABI before fixing a release target. The locked sources
declare JDK 17 in the matrix, Gradle 8.9, Android Gradle plugin 8.7.3, SDK
compile/target 35, minimum 24, NDK `28.1.13356709`, and CMake 3.22.1. These are
declared inputs, not evidence that this machine has them installed.

The command requires the real SDL3 Android dependencies and validated prebuilt
shader inputs. Android retains its inherited SDL3 behavior; this is not a
desktop SDL3 migration. `android/app/build.gradle` still runs `make localization
LANGUAGES=all` on Linux hosts or `lang/compile_mo.sh` on Windows when localization
is enabled. The new MO bootstrap has not yet been integrated and verified for
that Gradle path; do not substitute `-Plocalize=false` or an empty translation
artifact to claim success.

Use a disposable checkout with no `keystore.properties`, signing secrets or
real CCB installation. The inherited application ID is still
`com.crimsoncrossbunker.cataclysmcb`; do not install this candidate onto the
user's CCB device or call it a CPH release. Capture the Gradle exit and APK
inventory under `android/app/build/outputs/apk/experimental/release`, then inspect
actual ABI, resources and metadata using the installed SDK tools. An unsigned
artifact does not satisfy a signing check. Runtime acceptance requires a
separately fixed emulator/device profile tied to the actual package; static
ARM64 inspection or a companion x86_64 run alone is not ARM64 runtime proof.

Native Windows/macOS runners, Android SDK/NDK/shader inputs and an authorized
device/runtime profile block their respective probes. Permanent identity and
signing block installation under the final identity and public release, while
the local source/tooling work and already executable Linux checks can continue.
