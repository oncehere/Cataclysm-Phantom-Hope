<!-- CPH-DOC: build-cmake -->
> **CPH repository documentation / 本仓维护。** Stable document ID: `build-cmake`.
> This page is maintained with the CPH source. The inherited
> [CCB migration record](../migration/history-assessment.md) is historical.
> [Documentation index / 文档导航](../../docs/README.md).

# Building CPH with CMake

CMake is used by CPH's native validation workflow. The checked-in
[`CMakeLists.txt`](../../CMakeLists.txt) and
[`CMakePresets.json`](../../CMakePresets.json) define the available options.
CPH requires CMake 3.20 or newer and C++17; dependency/toolchain compatibility
still needs validation for the selected configuration.

## Source and dependencies

Start from CPH `main`, or your contribution branch based on it:

```sh
git clone --branch main https://github.com/oncehere/Cataclysm-Phantom-Hope.git cph
cd cph
cmake --list-presets
```

Install a compiler, the preset's build tool (Ninja or Visual Studio 2022), and
its dependencies before configuring. Tiles require SDL3; `-DUSE_SDL3=OFF` is
rejected. Sound and localization add their own library and gettext requirements. Both native target definitions
select SDL3; a checked-in definition is not evidence of a successful platform run. Use [the dependency lock](../../project/assets.lock.json)
and [check policy](../../project/check-policy.json) to reproduce the exact gate,
including its generator overrides. Ordinary preset examples below are local
development recipes, not a substitute for that evidence contract.

## Local configure and build

Keep the source directory separate from the build directory. From the source
root, a Linux tiles/sound build using the checked-in multi-config preset is:

```sh
cmake --preset linux-tiles-sounds-x64
cmake --build --preset linux-tiles-sounds-x64 --parallel 2
ctest --preset linux-tiles-sounds-x64 --output-on-failure
```

The build preset selects `RelWithDebInfo`; its directory is
`out/build/linux-tiles-sounds-x64`. The native CI runner overrides this with its
own isolated build directory, single-config Ninja and explicit flags. Do not
reuse a build cache after changing compiler, generator or source worktree.

Adding or removing engine `.cpp`/`.h` files or test `.cpp` files triggers
automatic reconfiguration on the next ordinary build through CMake's
`CONFIGURE_DEPENDS` source globs. Existing Lua source selection still applies.
The source-discovery regression compiles small disposable fixtures using the
actual engine/test target definitions with Ninja, Ninja Multi-Config and Unix
Makefiles when the corresponding tools are available. Run it together with
the version and document-install recipes after changing CMake configuration:

```sh
python3 -m unittest discover -s tests/project -p 'test_cmake*.py' -v
```

These checks validate build recipes, including added/removed files, rather
than game behaviour. Missing CMake/compiler/generator dependencies are reported
as skipped tests; install them before claiming the corresponding check passed.

For native Windows, follow [CMake with vcpkg](COMPILING-CMAKE-VCPKG.md).
Use the `[translations]` and other project-specific test selections from the
check policy when producing gate evidence; a passing subset is only that subset.

## Options and installation

Pass overrides at configuration time, for example `-DLOCALIZE=OFF` for a local
experiment without gettext. Such a build does **not** satisfy a gate requiring
localization. Likewise `-DTESTS=OFF` removes test coverage, and
`-DCATA_ENABLE_LUA_PLATFORM=OFF` does not validate the required Lua runtime.
Use `cmake -LAH -N out/build/<preset>` to inspect the actual cache.

Terminal builds remain available with `-DTILES=OFF -DCURSES=ON`; optional
`-DSOUND=ON` uses SDL3 audio without the tiles renderer. Headless builds default
to no SDL dependency when sound is disabled.

Useful options are `TILES`, `SOUND`, `CURSES`, `HEADLESS`, `LOCALIZE`,
`TESTS`, `CATA_ENABLE_LUA_PLATFORM`, `JSON_FORMAT`, `USE_HOME_DIR`, `USE_XDG_DIR`
and `USE_PREFIX_DATA_DIR`. Defaults and interactions are defined in the build
files. `CPH_TEST_IDENTITY` is a Linux-only unpublished isolation test identity;
it does not assign the permanent application identity.

Stage installation in a fresh directory:

```sh
cmake --install out/build/linux-tiles-sounds-x64 \
  --config RelWithDebInfo --prefix /tmp/cph-local-stage
```

Check the install manifest before running the staged executable. Use disposable
user/save/config directories for probes. Installation copies technical `doc/`
content; its existing paths and the JSON loading-order alias must stay usable.
See [Linux probe](../../docs/project/linux-probe.md) for isolated runtime evidence
and [compiler/platform scope](COMPILER_SUPPORT.md) for limits on support claims.

The `scope`, `baseline_status` and `deployment_blockers` prose inside the
check-policy file records the original E4 local baseline. Those fields do not
describe live GitHub deployment. Current remote observations are dated in
[project status](../../docs/project/status.md); actual acceptance requires the
run and settings readback for the candidate. The target/options/test selections
remain the machine-readable inputs used by the current CI runner.
