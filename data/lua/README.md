# CPH Lua-first Platform

CPH inherits one supported Lua runtime from CCB: Platform v1.  A Platform Mod is discovered
from its root `main.lua`; optional metadata is returned by `mod.lua` through
`ccb.ModDefinition`.  Mods do not use JSON manifests, an authored `lua/`
subdirectory, EOCs, or the former `game.*` API.

The architecture and authoring contract are documented in
[LUA_FIRST_PLATFORM.md](LUA_FIRST_PLATFORM.md). The short current goal and
progress page is [LUA_FIRST_EOC_WORKFLOW.md](LUA_FIRST_EOC_WORKFLOW.md).

The `ccb` module name and `ccb_platform_v1` filenames are existing compatibility
identifiers; this documentation cleanup does not rename them. LuaLS declarations
are in `types/ccb_platform_v1.d.lua`.  Contract and
inventory checks are documented in
[tools/lua_api/README.md](../../tools/lua_api/README.md).

The `ccb.services.gameplay.options.get` and `ccb.services.gameplay.options.value` readers return the active world's
effective values, including explicit advanced world rules. Core and Mod loading
continues to update the inherited layer; an explicit player override takes
precedence. These overrides can only be edited when creating or copying a world.
See [advanced world rules](../../docs/project/world-advanced-options.md) for scope
and compatibility effects.

Graphical builds use SDL3, including the native canvas used by Platform Mods;
SDL2 is no longer a build option. This backend change preserves Platform v1
and the existing dialogue interface. Terminal and headless builds remain
available, with UI capabilities still determined by the active build. See the
[build guide](../../doc/c++/COMPILING.md) for platform requirements.

The ImGui conversation view retains `ccb.dialogue` registration, response
callbacks and native start/option/end hooks. Regenerating responses or closing
a child dialogue clears only that dialogue's callbacks, preserving the parent's
pending choice. Selected callbacks are consumed once; topic changes, moves and
destruction continue to invalidate their contexts. See
[nested dialogue ownership](LUA_FIRST_PLATFORM.md#dialogue-presentation-and-nested-callbacks--对话界面与嵌套回调).

## Tool validation environment

The Lua API and agent tools share the pinned dependencies in
`tools/requirements-validation.txt` (Python 3.10 or newer). Install the existing
Lua entry point in an isolated environment; it includes that shared file:

```sh
python3 -m venv .venv-validation
.venv-validation/bin/python -m pip install -r tools/lua_api/requirements.txt
.venv-validation/bin/python -m unittest discover -s tools/lua_api -p 'test_*.py'
```

Run these commands from the repository root. Translation-tool tests also need
gettext's `msgfmt` and `msgcat` on PATH. LuaLS editor integration needs the
separate `CCB_LUALS` executable; report those tests as unrun when it is absent.
Tool regression results do not establish native Lua loading or gameplay.

## Actor control

`require("ccb").services.actor_control` provides the bounded `enable`, `bind`,
`chat`, `status`, `pause`, `cancel` and `stop` surface for the explicitly selected
recruited companion. Binding uses a current typed NPC handle; writable operations
require a writable callback. Snapshots do not expose native pointers. Native
execution, save/load hooks and arbitrary game-state setters are not Lua tools.
The service is dormant until enabled by an active Mod; it does not call a model.
See [ActorControl](../../docs/project/actor-control.md) for the loopback protocol,
native action/knowledge boundaries, lifecycle and independent companion package.
