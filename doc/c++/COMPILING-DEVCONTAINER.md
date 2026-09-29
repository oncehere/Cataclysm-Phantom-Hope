<!-- CPH-DOC: build-devcontainer -->
> **CPH repository documentation / 本仓维护。** Stable document ID: `build-devcontainer`.
> This page is maintained with the CPH source. The inherited
> [CCB migration record](../migration/history-assessment.md) is historical.
> [Documentation index / 文档导航](../../docs/README.md).

# CPH development containers

The repository contains inherited container configurations for local development:

- [Standard](../../.devcontainer/devcontainer.json)
- [Graphical](../../.devcontainer/graphical/devcontainer.json)
- [Cross compilation](../../.devcontainer/cross-compile/devcontainer.json)

Clone your CPH fork from `main` following [CONTRIBUTING](../../CONTRIBUTING.md),
open it in an editor with Dev Containers support, and select the intended
configuration. Read that configuration's Dockerfile before rebuilding it.
The old screenshot-driven directions to uncomment Windows/Qt blocks described
a different Dockerfile layout and no longer apply.

The standard Ubuntu 24.04 image supplies the curses dependencies. The graphical
image builds the locked SDL3 stack from source; tiles no longer accept an SDL2
fallback. SDL3, SDL3_image, SDL3_ttf and SDL3_mixer (for sound) are required,
along with the shader compiler. Use [CMake](COMPILING-CMAKE.md) or
[Make recipes](COMPILING.md) and retain logs for the actual container and commit.
The inherited MXE container has no complete SDL3 sound dependency recipe; its
presence is not a verified Windows build path.

These containers have not been established as CPH's release or native W/L
acceptance environment. Cross compilation cannot substitute for a native
Windows runtime test. Container builds, graphical display forwarding, startup
and save/load behavior need separate verification. Use disposable user data
when running a locally built game.
