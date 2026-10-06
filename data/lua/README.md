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

## Domain services and callback ownership

The public services include character progression, skill and spell queries,
effects, wounds, variables and native NPC interactions. Use explicit typed
handles and the phase requirements of each operation. The current signatures
and result shapes are in the [LuaLS declarations](types/ccb_platform_v1.d.lua)
and [generated public surface](reference/ccb_platform_api_v1.json); availability
in that surface does not mean every legacy EOC shape has been migrated.
Lua-authored content text can retain translation descriptors instead of
freezing the currently displayed language.

Persistent Lua values retain separate integer and floating-point tags; integer
values use the signed 64-bit representation. Persistent absolute-coordinate
components require exact native-range integers. Reads take a detached value
snapshot before allocating Lua results, so a finalizer changing the store does
not invalidate the value being returned. These are value/lifetime contracts,
not a claim that arbitrary native handles can be saved or old worlds migrated.

Dialogue `on_action` runs in the native success/failure effect stage, before
opinion and hostility checks; `on_select` runs afterwards and can choose the
next topic. Native mission actions and item/pet transfer operations require a
writable action phase; selection callbacks do not acquire that action-only
permission. Action and selection callback IDs have separate namespaces and are
consumed once. Session
and topic validity, plus dialogue-owned cleanup, prevent a closed or refreshed
child dialogue from retaining actions or clearing its parent's pending choice.
Activity callbacks likewise apply results only while the character and the
same activity instance remain live.

Stored EOC conditions use the later evaluating dialogue's alpha and beta,
including scoped variable reads; they do not capture the setter's participants.
Migration requires explicit participant proof. A queried beta predicate returns
false for an absent, stale or incompatible handle. Boolean composition keeps
native short-circuit order; alpha/global predicates do not acquire an unrelated
beta requirement. NPC-only services still require an exact NPC handle.

Migrated combat numbers read their own variable scope independently of the
character receiving damage or casting a spell. Native integer fields truncate
fractional values toward zero after a single evaluation; they do not round to
the nearest integer. Shapes without a proven participant remain reported as
migration gaps.

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

Native test builds accept `CATA_TEST_SUITE=all` (the default) or `lua` in both
CMake and Make. The Lua selection compiles `lua_platform*.cpp` plus the shared
helpers in `tests/test_support_sources.txt`; it requires
`CATA_ENABLE_LUA_PLATFORM` and does not cover unrelated engine tests. Use
`-DCATA_TEST_SUITE=lua` for CMake or `CATA_TEST_SUITE=lua` for Make with a
task-owned build/output directory, then run the relevant Catch2 filter with
`--warn NoTests`. Suite selection narrows native compilation; it does not replace
the Lua contract/tool suite or the separate `cata_test-mp` target. See
[the test routes](../../ai/test-matrix.yml) for isolated command examples.

## Actor control

`require("ccb").services.actor_control` provides the bounded `enable`, `bind`,
`chat`, `status`, `pause`, `cancel` and `stop` surface for the explicitly selected
recruited companion. Binding uses a current typed NPC handle; writable operations
require a writable callback. Snapshots do not expose native pointers. Native
execution, save/load hooks and arbitrary game-state setters are not Lua tools.
The service is dormant until enabled by an active Mod; it does not call a model.
See [ActorControl](../../docs/project/actor-control.md) for the loopback protocol,
native action/knowledge boundaries, lifecycle and independent companion package.
