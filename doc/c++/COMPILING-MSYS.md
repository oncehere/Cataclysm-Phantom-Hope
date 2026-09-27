<!-- CPH-DOC: build-windows-msys2 -->
> **CPH repository documentation / 本仓维护。** Stable document ID: `build-windows-msys2`.
> This page is maintained with the CPH source. The inherited
> [CCB migration record](../migration/history-assessment.md) is historical.
> [Documentation index / 文档导航](../../docs/README.md).

> Build scope: [CPH CMake presets](COMPILING-CMAKE.md) and the [compiler/platform contract](COMPILER_SUPPORT.md) describe the native validation targets. The additional recipes below are inherited local alternatives; their presence does not establish a successful CPH build or release on that platform.

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
*Contents*

- [Compilation guide for 64-bit Windows (using MSYS2)](#compilation-guide-for-64-bit-windows-using-msys2)
  - [Prerequisites:](#prerequisites)
    - [MINGW64](#mingw64)
    - [UCRT64](#ucrt64)
  - [Installation:](#installation)
  - [Configuration:](#configuration)
  - [Cloning and compilation:](#cloning-and-compilation)
  - [Running:](#running)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Compilation guide for 64-bit Windows (using MSYS2)

This is an inherited recipe for local CPH builds with MSYS2/MinGW. It is not a redistributable package or native MSVC acceptance recipe. CPH downloads, when published, are linked from the [project README](../../README.md); upstream CDDA packages are not CPH builds.


## Prerequisites:

**Compatibility boundary:** Use a Windows version supported by your selected MSYS2 toolchain and record an actual CPH build/test result. Toolchain selection below is not an operating-system support promise.

### MINGW64
* MINGW64 dependency environment; the example below selects SDL2.
* NTFS partition with ~10 Gb free space (~2 Gb for MSYS2 installation, ~3 Gb for repository and ~5 Gb for ccache)
* 64-bit version of MSYS2

### UCRT64
* UCRT64 dependency environment; the example below selects SDL3.


## Installation:

1. Go to the [MSYS2 homepage](http://www.msys2.org/) and download the installer.

2. Run the installer. It is suggested that you install to a dev-specific folder (C:\dev\msys64\ or similar), but it's not strictly necessary.

3. After installation, run MSYS2 64bit now.

When working from Microsoft Terminal default MSYS2 profile, run:
```
MSYSTEM=MINGW64 bash -l
```
or
```
MSYSTEM=UCRT64 bash -l
```

## Configuration:

1. Update the package database and core system packages:

```bash
pacman -Syyu
```

2. Follow any restart instruction from the updater, then reopen the selected MSYS2 environment. Resolve unexpected update errors before installing dependencies or building; an error is not a successful setup.

3. Update remaining packages:

```bash
pacman -Su
```

4. Install packages required for compilation:

-> MINGW64 (SDL2 fallback)
```bash
pacman -S git make ncurses-devel gettext-devel mingw-w64-x86_64-{astyle,ccache,cmake,gcc,libmad,libwebp,pkgconf,SDL2,libzip,libavif} mingw-w64-x86_64-SDL2_{image,mixer,ttf}
```

-> UCRT64 (SDL3)
```bash
pacman -S git make ncurses-devel gettext-devel mingw-w64-ucrt-x86_64-{astyle,ccache,cmake,freetype,gcc,libmad,libwebp,pkgconf,sdl3,libzip,libavif} mingw-w64-ucrt-x86_64-sdl3-{image,mixer,ttf} zlib-devel
```

-> Windows 10 and later (With SDL2)
```bash
pacman -S git make ncurses-devel gettext-devel mingw-w64-ucrt-x86_64-{astyle,ccache,cmake,freetype,gcc,libmad,libwebp,pkgconf,SDL2,libzip,libavif} mingw-w64-ucrt-x86_64-SDL2_{image,mixer,ttf} zlib-devel
```

5. Close MSYS2.

## Cloning and compilation:

1. Open MSYS2 and clone the CPH repository:

```bash
cd /c/dev/
git clone --branch main https://github.com/oncehere/Cataclysm-Phantom-Hope.git cph
```

**Note:** A shallow clone can reduce a local trial download; contribution and history checks may require the full relevant Git history.

**Note:** If you want to contribute to CPH, see [example git workflow](../../CONTRIBUTING.md).

2. Compile with following command line:

```bash
cd cph
make -j$((`nproc`+0)) CCACHE=1 RELEASE=1 MSYS2=1 DYNAMIC_LINKING=1 SDL3=1 TILES=1 SOUND=1 LOCALIZE=1 LANGUAGES=all LINTJSON=0 ASTYLE=0 TESTS=0
```

You will receive warnings about unterminated character constants; they do not impact the compilation as far as this writer is aware.

This will compile a release version with Sound and Tiles support and all localization languages, skipping checks and tests, and using ccache for build acceleration. You can use other switches, but `MSYS2=1`, `DYNAMIC_LINKING=1` and probably `RELEASE=1` are required to compile without issues.

It is now using `SDL3` flag to determine wether to use `SDL2` or `SDL3`, it is set to `SDL3=1` by default when you don't pass in this parameter, you can set it to `SDL3=0` to use SDL2 instead.

**Note:** See [CMake setup](COMPILING-CMAKE.md) for the out-of-source workflow. The `windows-tiles-sounds-x64` preset targets MSYS2/MinGW; provide its matching dependencies and record your own build/test results. It is not the native MSVC acceptance target.

## Running:

1. Run inside MSYS2 from Cataclysm's directory with the following command:

```bash
./cataclysm-tiles
```

**Note:** If you want to run the compiled executable outside of MSYS2, you will also need to update your user or system `PATH` variable with the path to MSYS2's runtime binaries (e.g. `C:\dev\msys64\mingw64\bin`).
