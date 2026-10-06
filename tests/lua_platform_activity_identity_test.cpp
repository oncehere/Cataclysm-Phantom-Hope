#if defined(CATA_ENABLE_LUA_PLATFORM) && CATA_ENABLE_LUA_PLATFORM

#include <cstdint>
#include <string>
#include <utility>

#include "avatar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "lua_platform_runtime.h"
#include "lua_platform_runtime_internal.h"
#include "lua_platform_sol.h"
#include "player_activity.h"
#include "player_helpers.h"
#include "type_id.h"

TEST_CASE( "lua_platform_same_id_activity_replacement_retires_old_callbacks",
           "[lua][platform][activity][lifecycle]" )
{
    namespace platform = cata::lua_platform;
    platform::clear_active_runtimes();
    clear_avatar();
    avatar &player = get_avatar();
    const activity_id activity_type( "ACT_LUA_ACTIVITY_IDENTITY_TEST" );

    sol::state lua;
    lua.open_libraries( sol::lib::base );
    sol::table ccb = lua.create_table();
    const auto owner = platform::make_runtime( "activity_identity_test", 7201, lua );
    const on_out_of_scope cleanup( [&]() {
        player.activity = player_activity();
        platform::clear_active_runtimes();
        platform::rollback_runtime_content( owner );
        clear_avatar();
    } );
    platform::install_runtime_api( owner, lua, ccb );
    lua["ccb"] = ccb;

    int replacements = 0;
    lua.set_function( "replace_activity", [&]() {
        ++replacements;
        player.activity = player_activity( activity_type, 987, 43, 44, "replacement" );
        // Completion-ready replacements expose accidental continuation of the old turn.
        player.activity.moves_left = 0;
    } );
    const sol::protected_function_result registered = lua.safe_script( R"lua(
turn_calls = 0
finish_calls = 0
local function stale_result(payload)
    if payload.phase == replacement_phase then
        replace_activity()
        return { moves_total = 1, moves_left = -1, index = -2,
                 position = -3, name = "old callback", cancel = true }
    end
end
ccb.runtime.handler("turn", function(payload)
    turn_calls = turn_calls + 1
    return stale_result(payload)
end)
ccb.runtime.handler("finish", function(payload)
    finish_calls = finish_calls + 1
    return stale_result(payload)
end)
local activity = ccb.content.ActivityType {
    id = "ACT_LUA_ACTIVITY_IDENTITY_TEST", verb = "testing activity identity",
    based_on = "neither"
}
activity:on_turn("turn")
activity:on_finish("finish")
ccb.content.add(activity)
)lua", sol::script_pass_on_error );
    if( !registered.valid() ) {
        const sol::error error = registered;
        INFO( error.what() );
    }
    REQUIRE( registered.valid() );
    std::string error;
    INFO( error );
    REQUIRE( platform::validate_runtime( owner, true, error ) );
    REQUIRE( platform::apply_runtime_content( owner, error ) );
    platform::set_active_runtimes( { owner } );
    owner->world_is_ready = true;

    SECTION( "copy, move, assignment and reset create distinct activity instances" ) {
        const player_activity original( activity_type, 321, 12, 13, "original" );
        player_activity copied( original );
        CHECK( copied.id() == original.id() );
        CHECK( copied.moves_left == original.moves_left );
        CHECK( copied.name == original.name );
        CHECK( copied.identity_generation() != original.identity_generation() );

        const std::uint64_t copied_identity = copied.identity_generation();
        player_activity moved( std::move( copied ) );
        CHECK( moved.id() == original.id() );
        CHECK( moved.name == original.name );
        CHECK( moved.identity_generation() != copied_identity );

        const std::uint64_t before_copy_assignment = moved.identity_generation();
        moved = original;
        CHECK( moved.id() == original.id() );
        CHECK( moved.identity_generation() != before_copy_assignment );
        CHECK( moved.identity_generation() != original.identity_generation() );

        player_activity destination( activity_type, 100 );
        const std::uint64_t before_move_assignment = destination.identity_generation();
        const std::uint64_t moved_identity = moved.identity_generation();
        destination = std::move( moved );
        CHECK( destination.id() == original.id() );
        CHECK( destination.name == original.name );
        CHECK( destination.identity_generation() != before_move_assignment );
        CHECK( destination.identity_generation() != moved_identity );

        const std::uint64_t before_reset = destination.identity_generation();
        destination.set_to_null();
        CHECK_FALSE( destination );
        CHECK( destination.identity_generation() != before_reset );
    }

    SECTION( "turn callback cannot write to or finish its same-id replacement" ) {
        lua["replacement_phase"] = "do_turn";
        player.activity = player_activity( activity_type, 400 );
        const std::uint64_t original_identity = player.activity.identity_generation();
        player.activity.do_turn( player );
        CHECK( player.activity.identity_generation() != original_identity );
        CHECK( lua["turn_calls"].get<int>() == 1 );
        CHECK( lua["finish_calls"].get<int>() == 0 );
        CHECK( replacements == 1 );
        REQUIRE( player.activity );
        CHECK( player.activity.id() == activity_type );
        CHECK( player.activity.moves_total == 987 );
        CHECK( player.activity.moves_left == 0 );
        CHECK( player.activity.index == 43 );
        CHECK( player.activity.position == 44 );
        CHECK( player.activity.name == "replacement" );
    }

    SECTION( "completion callback cannot write to or clear its same-id replacement" ) {
        lua["replacement_phase"] = "completion";
        player.activity = player_activity( activity_type, 0 );
        const std::uint64_t original_identity = player.activity.identity_generation();
        player.activity.do_turn( player );
        CHECK( player.activity.identity_generation() != original_identity );
        CHECK( lua["turn_calls"].get<int>() == 1 );
        CHECK( lua["finish_calls"].get<int>() == 1 );
        CHECK( replacements == 1 );
        REQUIRE( player.activity );
        CHECK( player.activity.id() == activity_type );
        CHECK( player.activity.moves_total == 987 );
        CHECK( player.activity.moves_left == 0 );
        CHECK( player.activity.index == 43 );
        CHECK( player.activity.position == 44 );
        CHECK( player.activity.name == "replacement" );
    }
}

#endif // CATA_ENABLE_LUA_PLATFORM
