#include <filesystem>
#include <string>
#include <vector>

#include "cata_catch.h"
#include "cata_path.h"
#include "cata_scope_helpers.h"
#include "json.h"
#include "json_loader.h"
#include "options.h"
#include "save_snapshot.h"
#include "world_advanced_options.h"
#include "world_advanced_runtime.h"
#include "worldfactory.h"

TEST_CASE( "advanced_world_effective_values_do_not_overwrite_mod_defaults",
           "[world_advanced][option]" )
{
    world_advanced_options rules;
    const world_advanced_options *previous = active_world_advanced_options();
    const options_manager::cOpt strength = get_options().get_option( "PLAYER_MAX_STR_VALUE" );
    const options_manager::cOpt healing = get_options().get_option( "PLAYER_HEALING_RATE" );
    on_out_of_scope restore( [&]() {
        get_options().get_option( "PLAYER_MAX_STR_VALUE" ) = strength;
        get_options().get_option( "PLAYER_HEALING_RATE" ) = healing;
        set_active_world_advanced_options( previous );
        options_manager::update_options_cache();
    } );
    set_active_world_advanced_options( &rules );
    get_options().get_option( "PLAYER_MAX_STR_VALUE" ).setValue( "2147483645" );
    get_options().get_option( "PLAYER_HEALING_RATE" ).setValue( "0.003" );
    CHECK( get_option<int>( "PLAYER_MAX_STR_VALUE" ) == 2147483645 );
    CHECK( get_options().get_option( "PLAYER_MAX_STR_VALUE" ).getValue( true ) == "2147483645" );
    CHECK( std::stod( get_options().get_effective_option( "PLAYER_HEALING_RATE" ).getValue( true ) ) ==
           Approx( 0.003 ) );
    std::string error;
    REQUIRE( rules.set( "PLAYER_MAX_STR_VALUE", "30", error ) );
    REQUIRE( rules.set( "CITY_SIZE", "3", error ) );
    REQUIRE( rules.set( "CITY_SPACING", "7", error ) );
    CHECK( get_option<int>( "CITY_SIZE" ) == 3 );
    CHECK( get_option<int>( "CITY_SPACING" ) == 7 );
    REQUIRE( rules.set( "PLAYER_HEALING_RATE", "0.0001", error ) );
    CHECK( get_option<int>( "PLAYER_MAX_STR_VALUE" ) == 30 );
    CHECK( get_options().get_effective_option( "PLAYER_MAX_STR_VALUE" ).getValue( true ) == "30" );
    CHECK( get_options().get_option( "PLAYER_MAX_STR_VALUE" ).value_as<int>() == 2147483645 );
    CHECK( get_option<float>( "PLAYER_HEALING_RATE" ) == Approx( 0.0001 ) );
    CHECK( std::stod( get_options().get_effective_option( "PLAYER_HEALING_RATE" ).getValue() ) ==
           Approx( 0.0001 ) );

    // Data loaders keep writing the lower layer even while user overrides are active.
    load_external_option( json_loader::from_string(
                              R"({"name":"PLAYER_MAX_STR_VALUE","stype":"int","value":80})" ).get_object() );
    CHECK( get_option<int>( "PLAYER_MAX_STR_VALUE" ) == 30 );
    rules.erase( "PLAYER_MAX_STR_VALUE" );
    CHECK( get_option<int>( "PLAYER_MAX_STR_VALUE" ) == 80 );
    set_active_world_advanced_options( nullptr );
    CHECK( get_option<float>( "PLAYER_HEALING_RATE" ) == Approx( 0.003 ) );
    set_active_world_advanced_options( &rules );
    CHECK( get_option<float>( "PLAYER_HEALING_RATE" ) == Approx( 0.0001 ) );
}

TEST_CASE( "advanced_world_validates_combinations_with_inherited_mod_values",
           "[world_advanced][option]" )
{
    world_advanced_options rules;
    const world_advanced_options *previous = active_world_advanced_options();
    const options_manager::cOpt maximum =
        get_options().get_option( "MAX_CATCHUP_EXP_PER_POST_CATA_DAY" );
    const options_manager::cOpt spacing = get_options().get_option( "HIGHWAY_GRID_COLUMN_SEPARATION" );
    const options_manager::cOpt deviation = get_options().get_option( "HIGHWAY_GRID_VARIANCE" );
    on_out_of_scope restore( [&]() {
        get_options().get_option( "MAX_CATCHUP_EXP_PER_POST_CATA_DAY" ) = maximum;
        get_options().get_option( "HIGHWAY_GRID_COLUMN_SEPARATION" ) = spacing;
        get_options().get_option( "HIGHWAY_GRID_VARIANCE" ) = deviation;
        set_active_world_advanced_options( previous );
        options_manager::update_options_cache();
    } );
    set_active_world_advanced_options( &rules );
    std::string error;
    SECTION( "inherited NPC maximum" ) {
        get_options().get_option( "MAX_CATCHUP_EXP_PER_POST_CATA_DAY" ).setValue( 5 );
        REQUIRE( rules.set( "MIN_CATCHUP_EXP_PER_POST_CATA_DAY", "10", error ) );
        CHECK_FALSE( validate_active_world_advanced_options( error ) );
    }
    SECTION( "inherited highway spacing" ) {
        get_options().get_option( "HIGHWAY_GRID_COLUMN_SEPARATION" ).setValue( 4 );
        REQUIRE( rules.set( "HIGHWAY_GRID_VARIANCE", "2", error ) );
        CHECK_FALSE( validate_active_world_advanced_options( error ) );
    }
    SECTION( "inherited zero highway deviation" ) {
        get_options().get_option( "HIGHWAY_GRID_VARIANCE" ).setValue( 0 );
        REQUIRE( rules.set( "HIGHWAY_GRID_COLUMN_SEPARATION", "10", error ) );
        CHECK_FALSE( validate_active_world_advanced_options( error ) );
    }
    SECTION( "unknown weather" ) {
        REQUIRE( rules.set( "ETERNAL_WEATHER", "not_a_real_weather_for_test", error ) );
        CHECK_FALSE( validate_active_world_advanced_options( error ) );
    }
    CHECK_FALSE( error.empty() );
}

TEST_CASE( "advanced_world_snapshot_copy_reset_and_active_world_lifecycle",
           "[world_advanced][worldfactory]" )
{
    const std::string name = "Advanced rules isolated regression";
    REQUIRE_FALSE( world_generator->has_world( name ) );
    WORLD *previous = world_generator->active_world;
    WORLD *world = world_generator->make_new_world( name, std::vector<mod_id>() );
    REQUIRE( world != nullptr );
    on_out_of_scope cleanup( [&]() {
        world_generator->set_active_world( previous );
        if( world_generator->has_world( name ) ) {
            world_generator->delete_world( name, true );
        }
    } );
    const cata_path folder = world->folder_path();
    REQUIRE( std::filesystem::remove( ( folder / "world_advanced.json" ).get_unrelative_path() ) );
    REQUIRE( save_snapshot::make_snapshot( folder, "legacy", "", 0 ) );
    const std::string legacy_snapshot = save_snapshot::list_snapshots( folder ).front().dir_name;
    std::string error;
    REQUIRE( world->advanced_options.set( "SPAWN_ANIMAL_DENSITY", "1", error ) );
    REQUIRE( world->save() );
    REQUIRE( save_snapshot::make_snapshot( folder, "original", "", 0 ) );
    std::string snapshot;
    for( const auto &entry : save_snapshot::list_snapshots( folder ) ) {
        if( entry.name == "original" ) {
            snapshot = entry.dir_name;
        }
    }
    REQUIRE_FALSE( snapshot.empty() );
    REQUIRE( save_snapshot::restore_snapshot( folder, snapshot ) );
    bool changed = true;
    REQUIRE( world->load_advanced_options( &changed ) );
    CHECK_FALSE( changed );
    REQUIRE( world->advanced_options.set( "SPAWN_ANIMAL_DENSITY", "4", error ) );
    REQUIRE( world->save() );
    REQUIRE( save_snapshot::restore_snapshot( folder, snapshot ) );
    REQUIRE( world->load_advanced_options( &changed ) );
    CHECK( changed );
    CHECK( world->advanced_options.find( "SPAWN_ANIMAL_DENSITY" ) ==
           std::optional<std::string>( "1" ) );

    WORLD copied( name + " copy" );
    copied.COPY_WORLD( world );
    CHECK( copied.advanced_options.values() == world->advanced_options.values() );
    copied.advanced_options.clear();
    CHECK_FALSE( world->advanced_options.empty() );
    world_generator->set_active_world( world );
    CHECK( active_world_advanced_options() == &world->advanced_options );

    // Old snapshots have no supplemental file: restoring them removes all overrides.
    REQUIRE( save_snapshot::restore_snapshot( folder, legacy_snapshot ) );
    REQUIRE( world->load_advanced_options( &changed ) );
    CHECK( changed );
    CHECK( world->advanced_options.empty() );
    REQUIRE( world->advanced_options.set( "SPAWN_ANIMAL_DENSITY", "2", error ) );
    REQUIRE( world->save() );
    REQUIRE( world_generator->delete_world( name, false ) );
    CHECK( std::filesystem::exists( ( folder / "world_advanced.json" ).get_unrelative_path() ) );
    world_generator->remove_world( name );
    CHECK( active_world_advanced_options() == nullptr );
    // The test owns this freshly-created directory; remove it after unregistering it.
    std::filesystem::remove_all( folder.get_unrelative_path() );
}
