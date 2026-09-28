#include <filesystem>
#include <fstream>
#include <optional>
#include <set>
#include <sstream>
#include <string>

#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "character.h"
#include "debug.h"
#include "json.h"
#include "json_loader.h"
#include "world_advanced_options.h"
#include "worldfactory.h"

namespace
{
class scoped_world_advanced_options
{
    public:
        explicit scoped_world_advanced_options( const world_advanced_options &options ) :
            previous_( active_world_advanced_options() ) {
            set_active_world_advanced_options( &options );
        }
        ~scoped_world_advanced_options() {
            set_active_world_advanced_options( previous_ );
        }
    private:
        const world_advanced_options *previous_;
};

std::string advanced_json( const world_advanced_options &options )
{
    std::ostringstream output;
    JsonOut json( output );
    options.serialize( json );
    return output.str();
}
} // namespace

TEST_CASE( "advanced_world_definitions_are_complete_and_valid", "[option][world_advanced]" )
{
    std::set<std::string> ids;
    int external = 0;
    int regional = 0;
    int climate = 0;
    for( const world_advanced_definition &definition : world_advanced_definitions() ) {
        CAPTURE( definition.id );
        CHECK( ids.insert( definition.id ).second );
        CHECK_FALSE( definition.name.empty() );
        CHECK_FALSE( definition.help.empty() );
        std::string error;
        CHECK( validate_world_advanced_scalar( definition.id, definition.default_value, error ) );
        CHECK( error.empty() );
        options_manager::cOpt option = definition.make_copt();
        CHECK( option.getName() == definition.id );
        CHECK_FALSE( option.is_hidden() );
        if( definition.target == world_advanced_target::external ) {
            ++external;
        } else if( definition.target == world_advanced_target::region ) {
            ++regional;
        } else {
            ++climate;
        }
    }
    CHECK( external == 59 );
    CHECK( regional == 27 );
    CHECK( climate == 3 );
    CHECK( find_world_advanced_definition( "DISABLE_ANIMAL_CLASH" ) == nullptr );
    CHECK( find_world_advanced_definition( "DISABLE_ROBOT_RESPONSE" ) == nullptr );
}

TEST_CASE( "advanced_world_roundtrip_preserves_sparse_typed_choices", "[option][world_advanced]" )
{
    world_advanced_options original;
    std::string error;
    REQUIRE( original.set( "SPAWN_ANIMAL_DENSITY", "1", error ) );
    REQUIRE( original.set( "CITY_SIZE", "0", error ) );
    REQUIRE( original.set( "PLAYER_MAX_STAMINA_BASE", "1e5", error ) );
    REQUIRE( original.set( "REGION_FORESTS", "false", error ) );
    REQUIRE( original.set( "WORLD_TEMPERATURE_OFFSET", "-12.5", error ) );
    REQUIRE( original.set( "ETERNAL_WEATHER", "mod_weather", error ) );
    const JsonObject saved = json_loader::from_string( advanced_json( original ) ).get_object();
    CHECK( saved.get_int( "version" ) == 1 );
    const JsonObject external = saved.get_object( "external" );
    CHECK( external.get_float( "SPAWN_ANIMAL_DENSITY" ) == 1.0 );
    CHECK( external.get_int( "PLAYER_MAX_STAMINA_BASE" ) == 100000 );
    CHECK( external.get_string( "ETERNAL_WEATHER" ) == "mod_weather" );
    const JsonObject region = saved.get_object( "region" );
    CHECK_FALSE( region.get_bool( "REGION_FORESTS" ) );
    CHECK( region.get_int( "CITY_SIZE" ) == 0 );
    CHECK( saved.get_object( "climate" ).get_float( "WORLD_TEMPERATURE_OFFSET" ) == -12.5 );
    world_advanced_options restored;
    restored.deserialize( saved );
    CHECK( restored.values() == original.values() );
    CHECK( restored.find( "SPAWN_ANIMAL_DENSITY" ) == std::optional<std::string>( "1" ) );
    CHECK_FALSE( restored.find( "NPC_HEALING_RATE" ).has_value() );
    restored.erase( "SPAWN_ANIMAL_DENSITY" );
    CHECK_FALSE( restored.find( "SPAWN_ANIMAL_DENSITY" ).has_value() );
}

TEST_CASE( "advanced_world_rejects_invalid_scalars_and_inconsistent_choices",
           "[option][world_advanced]" )
{
    world_advanced_options options;
    std::string error;
    for( const std::string value : {
             "nan", "inf", "-inf", "1e309", "1x", "", "1,5"
         } ) {
        CAPTURE( value );
        CHECK_FALSE( options.set( "SPAWN_ANIMAL_DENSITY", value, error ) );
        CHECK_FALSE( error.empty() );
    }
    CHECK_FALSE( options.set( "CITY_SIZE", "1.5", error ) );
    CHECK_FALSE( options.set( "GUN_DISPERSION_DIVIDER", "0", error ) );
    CHECK_FALSE( options.set( "SPAWN_CITY_HORDE_SPREAD", "0", error ) );
    CHECK_FALSE( options.set( "HIGHWAY_GRID_VARIANCE", "0", error ) );
    CHECK_FALSE( options.set( "WEARY_THRESH_SCALING", "0", error ) );
    CHECK_FALSE( options.set( "WEARY_RECOVERY_MULT", "1.1", error ) );
    CHECK_FALSE( options.set( "REGION_FORESTS", "yes", error ) );
    CHECK_FALSE( options.set( "UNKNOWN", "1", error ) );
    CHECK( options.empty() );
    REQUIRE( options.set( "REGION_FOREST_THRESHOLD", "0.8", error ) );
    REQUIRE( options.set( "REGION_THICK_FOREST_THRESHOLD", "0.2", error ) );
    CHECK_FALSE( options.validate( error ) );
    REQUIRE( options.set( "REGION_THICK_FOREST_THRESHOLD", "0.9", error ) );
    CHECK( options.validate( error ) );
    REQUIRE( options.set( "MIN_CATCHUP_EXP_PER_POST_CATA_DAY", "200", error ) );
    REQUIRE( options.set( "MAX_CATCHUP_EXP_PER_POST_CATA_DAY", "100", error ) );
    CHECK_FALSE( options.validate( error ) );
    REQUIRE( options.set( "MAX_CATCHUP_EXP_PER_POST_CATA_DAY", "200", error ) );
    REQUIRE( options.set( "HIGHWAY_GRID_ROW_SEPARATION", "4", error ) );
    REQUIRE( options.set( "HIGHWAY_GRID_VARIANCE", "2", error ) );
    CHECK_FALSE( options.validate( error ) );
    REQUIRE( options.set( "HIGHWAY_GRID_VARIANCE", "1", error ) );
    CHECK( options.validate( error ) );
}

TEST_CASE( "advanced_world_deserialization_is_typed_and_transactional", "[option][world_advanced]" )
{
    world_advanced_options options;
    std::string error;
    REQUIRE( options.set( "CITY_SIZE", "5", error ) );
    for( const std::string input : {
             R"({"version":2})",
             R"({"version":1,"region":{"CITY_SIZE":"5"}})",
             R"({"version":1,"region":{"CITY_SIZE":1.5}})",
             R"({"version":1,"region":{"REGION_FORESTS":1}})",
             R"({"version":1,"region":{"UNKNOWN":1}})",
             R"({"version":1,"external":{"CITY_SIZE":5}})",
             R"({"version":1,"external":{"GUN_DISPERSION_DIVIDER":0}})"
         } ) {
        CAPTURE( input );
        CHECK_THROWS( options.deserialize( json_loader::from_string( input ).get_object() ) );
        CHECK( options.find( "CITY_SIZE" ) == std::optional<std::string>( "5" ) );
    }
    options.deserialize( json_loader::from_string( R"({"version":1})" ).get_object() );
    CHECK( options.empty() );
}

TEST_CASE( "advanced_world_context_never_leaks_to_another_world", "[option][world_advanced]" )
{
    world_advanced_options first;
    world_advanced_options second;
    std::string error;
    REQUIRE( first.set( "WORLD_WIND_MULTIPLIER", "2", error ) );
    scoped_world_advanced_options restore( first );
    CHECK( world_advanced_number( "WORLD_WIND_MULTIPLIER", 7 ) == 2 );
    const std::size_t initial_revision = world_advanced_options_revision();
    REQUIRE( first.set( "WORLD_WIND_MULTIPLIER", "3", error ) );
    CHECK( world_advanced_options_revision() > initial_revision );
    CHECK( world_advanced_number( "WORLD_WIND_MULTIPLIER", 7 ) == 3 );
    world_advanced_options replacement;
    REQUIRE( replacement.set( "WORLD_WIND_MULTIPLIER", "4", error ) );
    const std::size_t before_assignment = world_advanced_options_revision();
    first = replacement;
    CHECK( world_advanced_options_revision() > before_assignment );
    CHECK( world_advanced_number( "WORLD_WIND_MULTIPLIER", 7 ) == 4 );
    set_active_world_advanced_options( &second );
    CHECK( world_advanced_number( "WORLD_WIND_MULTIPLIER", 7 ) == 7 );
    CHECK( world_advanced_bool( "REGION_FORESTS", true ) );
    set_active_world_advanced_options( &first );
    CHECK( world_advanced_number( "WORLD_WIND_MULTIPLIER", 7 ) == 4 );
    first.clear();
    CHECK( world_advanced_number( "WORLD_WIND_MULTIPLIER", 7 ) == 7 );
    set_active_world_advanced_options( nullptr );
    CHECK_FALSE( get_world_advanced_value( "WORLD_WIND_MULTIPLIER" ).has_value() );
}

TEST_CASE( "advanced_world_file_roundtrip_missing_and_invalid_inputs", "[option][world_advanced]" )
{
    const std::string world_name = "Advanced rules persistence test";
    REQUIRE_FALSE( world_generator->has_world( world_name ) );
    WORLD *world = world_generator->make_new_world( world_name, std::vector<mod_id>() );
    REQUIRE( world != nullptr );
    on_out_of_scope cleanup( [&]() {
        world_generator->delete_world( world_name, true );
    } );
    const cata_path path = world->folder_path() / "world_advanced.json";
    world_advanced_options original;
    std::string error;
    REQUIRE( original.set( "PLAYER_HEALING_RATE", "0.00015", error ) );
    REQUIRE( original.set( "SPAWN_ANIMAL_DENSITY", "1", error ) );
    REQUIRE( original.save( path ) );
    world_advanced_options loaded;
    REQUIRE( loaded.load( path ) );
    CHECK( loaded.values() == original.values() );
    REQUIRE( std::filesystem::remove( path.get_unrelative_path() ) );
    REQUIRE( loaded.load( path ) );
    CHECK( loaded.empty() );

    REQUIRE( loaded.set( "CITY_SIZE", "5", error ) );
    {
        std::ofstream invalid( path.get_unrelative_path() );
        REQUIRE( invalid.is_open() );
        invalid << R"({"version":99,"region":{"CITY_SIZE":5}})";
    }
    bool success = true;
    const std::string messages = capture_debugmsg_during( [&]() {
        success = loaded.load( path );
    } );
    CHECK_FALSE( success );
    CHECK_FALSE( messages.empty() );
    CHECK( loaded.empty() );
}

TEST_CASE( "advanced_world_overrides_preserve_loader_values_and_refresh_cached_attributes",
           "[option][world_advanced]" )
{
    options_manager &manager = get_options();
    const options_manager::cOpt original_density = manager.get_option( "SPAWN_ANIMAL_DENSITY" );
    const options_manager::cOpt original_strength = manager.get_option( "PLAYER_MAX_STR_VALUE" );
    on_out_of_scope restore_base( [&]() {
        manager.get_option( "SPAWN_ANIMAL_DENSITY" ) = original_density;
        manager.get_option( "PLAYER_MAX_STR_VALUE" ) = original_strength;
        options_manager::update_options_cache();
    } );
    manager.get_option( "SPAWN_ANIMAL_DENSITY" ).setValue( 2.0f );
    // This is the real unrestricted value supplied by PLAYER_MAX_ATTR_VALUE.
    manager.get_option( "PLAYER_MAX_STR_VALUE" ).setValue( 2147483645 );
    world_advanced_options rules;
    std::string error;
    REQUIRE( rules.set( "SPAWN_ANIMAL_DENSITY", "1", error ) );
    REQUIRE( rules.set( "PLAYER_MAX_STR_VALUE", "100", error ) );
    scoped_world_advanced_options restore_context( rules );
    options_manager::update_options_cache();
    CHECK( get_option<float>( "SPAWN_ANIMAL_DENSITY" ) == 1.0f );
    CHECK( manager.get_option( "SPAWN_ANIMAL_DENSITY" ).value_as<float>() == 2.0f );
    CHECK( character_max_str == 100 );
    load_external_option( json_loader::from_string(
                              R"({"name":"SPAWN_ANIMAL_DENSITY","stype":"float","value":4})" ).get_object() );
    CHECK( get_option<float>( "SPAWN_ANIMAL_DENSITY" ) == 1.0f );
    CHECK( manager.get_option( "SPAWN_ANIMAL_DENSITY" ).value_as<float>() == 4.0f );
    rules.clear();
    options_manager::update_options_cache();
    CHECK( get_option<float>( "SPAWN_ANIMAL_DENSITY" ) == 4.0f );
    CHECK( get_option<int>( "PLAYER_MAX_STR_VALUE" ) == 2147483645 );
    CHECK( character_max_str == 2147483645 );
}
