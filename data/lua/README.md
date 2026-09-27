# CPH Lua-first Platform

CPH inherits one supported Lua runtime from CCB: Platform v1.  A Platform Mod is discovered
from its root `main.lua`; optional metadata is returned by `mod.lua` through
`ccb.ModDefinition`.  Mods do not use JSON manifests, an authored `lua/`
subdirectory, EOCs, or the former `game.*` API.

The architecture and authoring contract are documented in
[LUA_FIRST_PLATFORM.md](LUA_FIRST_PLATFORM.md).  EOC capability migration
follows [LUA_FIRST_EOC_WORKFLOW.md](LUA_FIRST_EOC_WORKFLOW.md); migrated content
is only accepted after its native Platform domain is complete.

The `ccb` module name and `ccb_platform_v1` filenames are existing compatibility
identifiers; this documentation cleanup does not rename them. LuaLS declarations
are in `types/ccb_platform_v1.d.lua`.  Contract and
inventory checks are documented in
[tools/lua_api/README.md](../../tools/lua_api/README.md).
