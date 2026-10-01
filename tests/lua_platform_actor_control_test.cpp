#if defined(CATA_ENABLE_LUA_PLATFORM) && CATA_ENABLE_LUA_PLATFORM

#include <cstdlib>
#include <filesystem>
#include <functional>
#include <memory>
#include <set>
#include <string>

#include "actor_control.h"
#include "lua_platform_actor_control.h"
#include "lua_platform_runtime_internal.h"
#include "lua_platform_test_support.h"
#include "path_info.h"
#include "worldfactory.h"

TEST_CASE( "lua_platform_actor_control_has_only_bounded_management_operations",
           "[lua][platform][actor_control][contract]" )
{
    namespace platform = cata::lua_platform;
    cata::actor_control::enable( false );
    cata::actor_control::reset();
    const on_out_of_scope cleanup( []() {
        cata::actor_control::enable( false );
        cata::actor_control::reset();
    } );
    sol::state lua;
    sol::table services = lua.create_table();
    int reads = 0;
    int writes = 0;
    platform::install_actor_control_api( services,
    []() {
        return platform::game_handle_runtime();
    }, []() {
        return std::size_t( 1 );
    }, [&]() {
        ++reads;
    }, [&]() {
        ++writes;
        throw std::runtime_error( "write callback required" );
    } );
    const sol::table api = services["actor_control"];
    std::set<std::string> exposed;
    for( const auto &entry : api ) {
        REQUIRE( entry.first.is<std::string>() );
        REQUIRE( entry.second.is<sol::function>() );
        exposed.insert( entry.first.as<std::string>() );
    }
    CHECK( exposed == std::set<std::string> {
        "bind", "cancel", "chat", "enable", "pause", "status", "stop"
    } );
    CHECK_FALSE( lua["actor_control"].valid() );
    CHECK_FALSE( lua["game"].valid() );
    CHECK_FALSE( api["dispatch"].valid() );
    CHECK_FALSE( api["execute"].valid() );
    CHECK_FALSE( api["observe"].valid() );
    const sol::protected_function enable = api["enable"];
    const sol::protected_function bind = api["bind"];
    const sol::protected_function chat = api["chat"];
    const sol::protected_function pause = api["pause"];
    const sol::protected_function cancel = api["cancel"];
    const sol::protected_function stop = api["stop"];
    CHECK_FALSE( enable( true ).valid() );
    CHECK_FALSE( bind( platform::game_handle(), "fixture" ).valid() );
    CHECK_FALSE( chat( "fixture speech" ).valid() );
    CHECK_FALSE( pause( true ).valid() );
    CHECK_FALSE( cancel().valid() );
    CHECK_FALSE( stop().valid() );
    CHECK( writes == 6 );
    CHECK_FALSE( cata::actor_control::enabled() );
    CHECK_FALSE( cata::actor_control::has_binding() );
    const sol::protected_function status = api["status"];
    const sol::protected_function_result first = status();
    REQUIRE( first.valid() );
    sol::table first_result = first;
    REQUIRE( first_result["ok"].get<bool>() );
    sol::table snapshot = first_result["value"];
    CHECK_FALSE( snapshot["enabled"].get<bool>() );
    snapshot["enabled"] = true;
    const sol::protected_function_result second = status( true );
    REQUIRE( second.valid() );
    const sol::table second_result = second;
    CHECK_FALSE( second_result["value"]["enabled"].get<bool>() );
    CHECK_FALSE( second_result["value"]["debug"].valid() );
    CHECK( reads == 2 );
}

TEST_CASE( "lua_platform_actor_control_binding_rejects_stale_typed_handles",
           "[lua][platform][actor_control][handles]" )
{
    namespace platform = cata::lua_platform;
    sol::state lua;
    sol::table services = lua.create_table();
    const auto owner = platform::make_game_handle_runtime_owner();
    const auto other_owner = platform::make_game_handle_runtime_owner();
    const platform::game_handle_runtime original_runtime( owner, 2 );
    platform::game_handle_runtime current_runtime = original_runtime;
    std::size_t world = 4;
    npc subject;
    subject.normalize();
    subject.setID( character_id( 78431 ), true );
    platform::register_npc_handle_identity( subject );
    const on_out_of_scope cleanup( [&]() {
        platform::retire_npc_handle_identity( subject );
    } );
    const auto handle = platform::game_handle::from_creature(
                            subject, { "npc", subject.getID().get_value(), 0, 0, 0, {} },
                            original_runtime, world );
    platform::install_game_handle_api( lua, services, [&]() {
        return current_runtime;
    }, [&]() {
        return world;
    }, []() {} );
    platform::install_actor_control_api( services, [&]() {
        return current_runtime;
    }, [&]() {
        return world;
    }, []() {}, []() {} );
    std::string expected;
    SECTION( "read again after loading another world" ) {
        ++world;
        expected = "stale_world";
    }
    SECTION( "same runtime owner with a different generation" ) {
        current_runtime = platform::game_handle_runtime( owner, 3 );
        expected = "stale_runtime";
    }
    SECTION( "another Mod runtime cannot use this handle" ) {
        current_runtime = platform::game_handle_runtime( other_owner, 2 );
        expected = "stale_runtime";
    }
    SECTION( "retired entity identity" ) {
        platform::retire_npc_handle_identity( subject );
        expected = "stale_identity";
    }
    const sol::protected_function bind = services["actor_control"]["bind"];
    const sol::protected_function_result call = bind( handle, "fixture" );
    REQUIRE( call.valid() );
    const sol::table result = call;
    CHECK_FALSE( result["ok"].get<bool>() );
    CHECK( result["error"]["code"].get<std::string>() == expected );
}

#ifndef _WIN32
TEST_CASE( "lua_platform_actor_control_world_callbacks_use_the_sole_ccb_surface",
           "[lua][platform][actor_control][lifecycle]" )
{
    namespace platform = cata::lua_platform;
    platform::shutdown();
    cata::actor_control::enable( false );
    cata::actor_control::reset();
    clear_avatar();
    clear_npcs();
    clear_map_without_vision();
    const platform_lua_test_directory files;
    const char *previous = std::getenv( "XDG_RUNTIME_DIR" );
    const bool had_runtime = previous != nullptr;
    const std::string old_runtime = previous == nullptr ? "" : previous;
    const std::string old_savedir = PATH_INFO::savedir();
    REQUIRE( world_generator != nullptr );
    WORLD *old_world = world_generator->active_world;
    const on_out_of_scope cleanup( [&]() {
        platform::shutdown();
        cata::actor_control::enable( false );
        cata::actor_control::reset();
        PATH_INFO::set_savedir( old_savedir );
        world_generator->active_world = old_world;
        if( had_runtime ) {
            setenv( "XDG_RUNTIME_DIR", old_runtime.c_str(), 1 );
        } else {
            unsetenv( "XDG_RUNTIME_DIR" );
        }
        clear_npcs();
        clear_avatar();
    } );
    REQUIRE( setenv( "XDG_RUNTIME_DIR", files.root.c_str(), 1 ) == 0 );
    PATH_INFO::set_savedir( files.root.u8string() + "/" );
    world_generator->active_world = nullptr;
    npc &companion = spawn_npc( get_avatar().pos_bub().xy() + point::south, "thug" );
    talk_function::follow( companion );
    REQUIRE( companion.is_player_ally() );
    files.write( std::filesystem::u8path( "main.lua" ), R"lua(
local ccb = require("ccb")
local api = ccb.services.actor_control
assert(type(api) == "table")
assert(ccb.actor_control == nil and actor_control == nil and game == nil)
assert(api.execute == nil and api.dispatch == nil and api.observe == nil)
assert(not pcall(api.enable, true))
assert(not pcall(api.status))
captured_api = api
ready_calls = 0
shutdown_calls = 0
ccb.runtime.handler("companion_ready", function()
    assert(api.enable(true).ok)
    local result = api.bind(fixture_handle(), "fixture-companion")
    assert(result.ok, result.error and result.error.code)
    assert(api.chat("A statement from the player.").ok)
    assert(api.pause(true).ok)
    assert(api.status().value.state == "paused")
    assert(api.pause(false).ok)
    ready_calls = ready_calls + 1
end)
ccb.runtime.on("world_ready", "companion_ready")
ccb.runtime.handler("companion_shutdown", function()
    assert(api.stop().ok)
    assert(api.enable(false).ok)
    shutdown_calls = shutdown_calls + 1
end)
ccb.runtime.on("shutdown", "companion_shutdown")
)lua" );
    const platform::mod_source source { "actor-control-fixture", files.root,
                                        files.root / std::filesystem::u8path( "main.lua" ) };
    std::string error;
    REQUIRE( platform::prepare_mods( { source }, error ) );
    REQUIRE( platform::apply_prepared_content( error ) );
    REQUIRE( platform::validate_finalized_prepared_content( error ) );
    platform::commit_prepared_mods();
    CHECK_FALSE( cata::actor_control::enabled() );
    const auto runtime = platform::detail::find_active_runtime( source.id );
    REQUIRE( runtime );
    runtime->lua->set_function( "fixture_handle", [&]() {
        return platform::game_handle::from_creature(
                   companion, { "npc", companion.getID().get_value(), 0, 0, 0, {} },
                   runtime->handle_runtime(), platform::runtime_world_generation() );
    } );
    const time_point before = calendar::turn;
    const int before_moves = companion.get_moves();
    platform::runtime_world_ready( true );
    REQUIRE( ( *runtime->lua )["ready_calls"].get<int>() == 1 );
    CHECK( cata::actor_control::is_bound( companion ) );
    CHECK( cata::actor_control::enabled() );
    CHECK( calendar::turn == before );
    CHECK( companion.get_moves() == before_moves );
    const sol::table api = ( *runtime->lua )["captured_api"];
    const sol::protected_function enable = api["enable"];
    const sol::protected_function status = api["status"];
    CHECK_FALSE( enable( false ).valid() );
    REQUIRE( status().valid() );
    CHECK( cata::actor_control::enabled() );
    platform::clear_active_runtimes();
    CHECK( ( *runtime->lua )["shutdown_calls"].get<int>() == 1 );
    CHECK_FALSE( cata::actor_control::enabled() );
    CHECK_FALSE( status().valid() );
}
#endif // !_WIN32

#endif // CATA_ENABLE_LUA_PLATFORM
