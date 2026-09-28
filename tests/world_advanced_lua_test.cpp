#if defined(CATA_ENABLE_LUA_PLATFORM) && CATA_ENABLE_LUA_PLATFORM

#include "lua_platform_test_support.h"

#include <memory>
#include <string>

#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "json_loader.h"
#include "lua_platform_runtime.h"
#include "lua_platform_sol.h"
#include "options.h"
#include "world_advanced_options.h"
#include "worldfactory.h"

TEST_CASE( "world_advanced_lua_reads_effective_options_without_losing_small_rates",
           "[world_advanced][lua][platform][options]" )
{
    namespace platform = cata::lua_platform;
    platform::clear_active_runtimes();
    options_manager &options = get_options();
    REQUIRE( options.has_option( "PLAYER_HEALING_RATE" ) );
    REQUIRE( options.has_option( "PLAYER_HUNGER_RATE" ) );
    const options_manager::cOpt old_healing = options.get_option( "PLAYER_HEALING_RATE" );
    const options_manager::cOpt old_hunger = options.get_option( "PLAYER_HUNGER_RATE" );
    const world_advanced_options *old_rules = active_world_advanced_options();
    world_advanced_options rules;
    sol::state lua;
    sol::table ccb = lua.create_table();
    const std::shared_ptr<platform::runtime> owner = platform::make_runtime(
                "world_advanced_options", 4903, lua );
    const on_out_of_scope cleanup( [&]() {
        platform::clear_active_runtimes();
        set_active_world_advanced_options( old_rules );
        options.get_option( "PLAYER_HEALING_RATE" ) = old_healing;
        options.get_option( "PLAYER_HUNGER_RATE" ) = old_hunger;
        options_manager::update_options_cache();
    } );
    set_active_world_advanced_options( &rules );
    std::string error;
    REQUIRE( rules.set( "PLAYER_HEALING_RATE", "0.00037", error ) );
    REQUIRE( rules.set( "PLAYER_HUNGER_RATE", "2.75", error ) );
    platform::install_runtime_api( owner, lua, ccb );
    platform::set_active_runtimes( { owner } );
    platform::runtime_world_ready( true );
    lua["services"] = ccb["services"];
    sol::protected_function query = lua.load(
                                        "return services.gameplay.options.get(id).value, "
                                        "services.gameplay.options.value(id)" );
    const auto check_lua_value = [&]( const std::string & id, const double expected ) {
        CAPTURE( id, expected );
        lua["id"] = id;
        const sol::protected_function_result result = query();
        REQUIRE( result.valid() );
        CHECK( std::stod( result.get<std::string>( 0 ) ) == Approx( expected ).margin( 1e-10 ) );
        CHECK( std::stod( result.get<std::string>( 1 ) ) == Approx( expected ).margin( 1e-10 ) );
    };
    check_lua_value( "PLAYER_HEALING_RATE", 0.00037 );
    check_lua_value( "PLAYER_HUNGER_RATE", 2.75 );
    REQUIRE( rules.set( "CITY_SIZE", "3", error ) );
    check_lua_value( "CITY_SIZE", 3 );

    // Content loading still owns the base values; an explicit world choice wins.
    load_external_option( json_loader::from_string(
                              R"({"name":"PLAYER_HEALING_RATE","stype":"float","value":0.00081})" ).get_object() );
    load_external_option( json_loader::from_string(
                              R"({"name":"PLAYER_HUNGER_RATE","stype":"float","value":1.5})" ).get_object() );
    CHECK( options.get_option( "PLAYER_HEALING_RATE" ).value_as<float>() ==
           Approx( 0.00081 ).margin( 1e-10 ) );
    CHECK( options.get_option( "PLAYER_HUNGER_RATE" ).value_as<float>() == Approx( 1.5 ) );
    check_lua_value( "PLAYER_HEALING_RATE", 0.00037 );
    check_lua_value( "PLAYER_HUNGER_RATE", 2.75 );

    rules.erase( "PLAYER_HEALING_RATE" );
    check_lua_value( "PLAYER_HEALING_RATE", 0.00081 );
    rules.erase( "PLAYER_HUNGER_RATE" );
    check_lua_value( "PLAYER_HUNGER_RATE", 1.5 );
}

#endif
