#include <filesystem>
#include <fstream>
#include <string>

#include "cata_catch.h"
#include "cata_path.h"
#include "cata_scope_helpers.h"
#include "debug_capture.h"
#include "game.h"
#include "item_factory.h"
#include "itype.h"
#include "mapbuffer.h"
#include "options.h"
#include "overmapbuffer.h"
#include "save_snapshot.h"
#include "vitamin.h"
#include "world_advanced_options.h"
#include "worldfactory.h"

namespace
{
struct content_counts {
    int faults = 0;
    int vitamins = 0;
    int degradation = 0;
};

content_counts count_loaded_content()
{
    content_counts counts;
    for( const itype *type : item_controller->all() ) {
        counts.faults += !type->faults.empty();
        counts.degradation += type->degrade_increments() > 0;
        if( type->comestible ) {
            const nutrients nutrition = type->comestible->default_nutrition_read_only();
            for( const auto &vit : nutrition.vitamins() ) {
                counts.vitamins += vit.first->type() == vitamin_type::VITAMIN && vit.second != 0;
            }
        }
    }
    return counts;
}
} // namespace

// Run separately: this integration test deliberately tears down and reloads all registries.
TEST_CASE( "advanced_world_content_reload_and_failure_cleanup", "[.][world_advanced_loading]" )
{
    WORLD *world = world_generator->active_world;
    REQUIRE( world != nullptr );
    const std::filesystem::path mod_fixture =
        ( world->folder_path() / "mods" / "world_advanced_loading_fixture.json" ).get_unrelative_path();
    REQUIRE_FALSE( std::filesystem::exists( mod_fixture ) );
    const world_advanced_options original = world->advanced_options;
    on_out_of_scope restore( [&]() {
        std::filesystem::remove( mod_fixture );
        world->advanced_options = original;
        world->advanced_options_valid = true;
        world->save();
        world_generator->set_active_world( world );
        MAPBUFFER.clear();
        overmap_buffer.clear();
        g->setup();
    } );
    world->advanced_options.clear();
    world_generator->set_active_world( world );
    REQUIRE( g->setup() );
    const content_counts inherited = count_loaded_content();
    REQUIRE( inherited.faults > 0 );
    REQUIRE( inherited.vitamins > 0 );
    REQUIRE( inherited.degradation > 0 );

    std::filesystem::create_directories( mod_fixture.parent_path() );
    const auto write_mod_fixture = [&]( const std::string & json ) {
        std::ofstream file( mod_fixture );
        REQUIRE( file.is_open() );
        file << json;
        file.close();
        REQUIRE( file.good() );
    };
    write_mod_fixture( R"([
        { "type": "EXTERNAL_OPTION", "name": "NO_FAULTS", "stype": "bool", "value": false },
        { "type": "EXTERNAL_OPTION", "name": "NO_VITAMINS", "stype": "bool", "value": false },
        { "type": "EXTERNAL_OPTION", "name": "VEHICLE_DEGRADATION_WHEN_DAMAGE", "stype": "bool", "value": true },
        { "type": "EXTERNAL_OPTION", "name": "PLAYER_MAX_STR_VALUE", "stype": "int", "value": 27 }
    ])" );
    std::string error;
    REQUIRE( world->advanced_options.set( "NO_FAULTS", "true", error ) );
    REQUIRE( world->advanced_options.set( "NO_VITAMINS", "true", error ) );
    REQUIRE( world->advanced_options.set( "VEHICLE_DEGRADATION_WHEN_DAMAGE", "false", error ) );
    REQUIRE( world->save() );
    REQUIRE( g->setup() );
    CHECK( get_options().get_option( "PLAYER_MAX_STR_VALUE" ).value_as<int>() == 27 );
    CHECK_FALSE( get_options().get_option( "NO_FAULTS" ).value_as<bool>() );
    CHECK( get_option<bool>( "NO_FAULTS" ) );
    const content_counts overridden = count_loaded_content();
    CHECK( overridden.faults == 0 );
    CHECK( overridden.vitamins == 0 );
    CHECK( overridden.degradation == 0 );

    // A restored file changes rules behind the running world's back. Even when the
    // character save cannot be loaded, the reload must rebuild load-time content.
    world_advanced_options followed;
    REQUIRE( followed.save( world->folder_path() / "world_advanced.json" ) );
    capture_debugmsg_during( [&]() {
        CHECK_FALSE( g->reload_active_save( save_t::from_save_id( "no_such_character" ) ) );
    } );
    CHECK( g->uquit == QUIT_NOSAVED );
    CHECK( active_world_advanced_options() == nullptr );
    const content_counts reloaded = count_loaded_content();
    CHECK( reloaded.faults == inherited.faults );
    CHECK( reloaded.vitamins == inherited.vitamins );
    CHECK( reloaded.degradation == inherited.degradation );

    // Keep these failure cases sequential: Catch sections would repeat every
    // expensive full content reload above for each independent failure.
    {
        INFO( "malformed restored JSON" );
        std::ofstream file( ( world->folder_path() / "world_advanced.json" ).get_unrelative_path() );
        file << "{broken";
        file.close();
        world_generator->set_active_world( world );
        capture_debugmsg_during( [&]() {
            CHECK_FALSE( g->reload_active_save( save_t::from_save_id( "no_such_character" ) ) );
        } );
        CHECK_FALSE( world->advanced_options_valid );
        CHECK( g->uquit == QUIT_NOSAVED );
        CHECK( active_world_advanced_options() == nullptr );
    }
    {
        INFO( "unknown weather fails the content reload" );
        world_advanced_options invalid;
        REQUIRE( invalid.set( "ETERNAL_WEATHER", "missing_weather_advanced_test", error ) );
        REQUIRE( invalid.save( world->folder_path() / "world_advanced.json" ) );
        world_generator->set_active_world( world );
        const std::string messages = capture_debugmsg_during( [&]() {
            CHECK_FALSE( g->reload_active_save( save_t::from_save_id( "no_such_character" ) ) );
        } );
        CHECK( messages.find( "missing_weather_advanced_test" ) != std::string::npos );
    }
    CHECK( g->uquit == QUIT_NOSAVED );
    CHECK( active_world_advanced_options() == nullptr );

    // A malformed world-local mod fails before finalization, independently of
    // advanced-rule validation, and must still discard the active override layer.
    world->advanced_options.clear();
    REQUIRE( world->advanced_options.set( "NO_FAULTS", "true", error ) );
    REQUIRE( world->save() );
    write_mod_fixture( "{broken" );
    world_generator->set_active_world( world );
    capture_debugmsg_during( [&]() {
        CHECK_THROWS( g->setup() );
    } );
    CHECK( active_world_advanced_options() == nullptr );
    CHECK_FALSE( get_option<bool>( "NO_FAULTS" ) );
}
