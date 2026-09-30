#!/bin/bash
# The inherited SDL2 WebAssembly build is retired. Keep this entrypoint so
# callers get a clear failure before installing an obsolete emsdk or building.
# SDL3 web dependencies and runtime integration require a separate project.
printf '%s\n' 'The old Emscripten/WebAssembly build is retired in CPH. Use a native SDL3 build.' >&2
exit 2
