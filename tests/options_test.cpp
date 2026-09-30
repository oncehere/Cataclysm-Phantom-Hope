#include <map>
#include <string>
#include <unordered_map>
#include <utility>

#include "cata_catch.h"
#include "json.h"
#include "json_loader.h"
#include "options.h"
#include "options_helpers.h"
#include "string_formatter.h"
#include "translation.h"
#include "type_id.h"

static const option_slider_id option_slider_test_world_difficulty( "test_world_difficulty" );

TEST_CASE( "core_data_preserves_the_radiation_mutation_world_default", "[option]" )
{
    CHECK( get_option<bool>( "RAD_MUTATION" ) );
}

TEST_CASE( "retired_renderer_options_remain_loadable_but_hidden", "[option][sdl3]" )
{
    options_manager &manager = get_options();
    REQUIRE( manager.has_option( "FRAMEBUFFER_ACCEL" ) );
    REQUIRE( manager.has_option( "USE_COLOR_MODULATED_TEXTURES" ) );
    override_option restore_framebuffer( "FRAMEBUFFER_ACCEL", "false" );
    override_option restore_modulated( "USE_COLOR_MODULATED_TEXTURES", "false" );

    // Existing settings remain recognizable after the renderer becomes automatic.
    manager.deserialize( json_loader::from_string( R"([
        {"name":"FRAMEBUFFER_ACCEL","value":"true"},
        {"name":"USE_COLOR_MODULATED_TEXTURES","value":"true"}
    ])" ).get_array() );

    CHECK( get_option<bool>( "FRAMEBUFFER_ACCEL" ) );
    CHECK( get_option<bool>( "USE_COLOR_MODULATED_TEXTURES" ) );
    CHECK( manager.get_option( "FRAMEBUFFER_ACCEL" ).is_hidden() );
    CHECK( manager.get_option( "USE_COLOR_MODULATED_TEXTURES" ).is_hidden() );
    CHECK_FALSE( manager.has_option( "RENDER_BATCHING" ) );
}

TEST_CASE( "option_slider_test", "[option]" )
{
    options_manager::options_container opts = get_options().get_world_defaults();
    options_manager::options_container old_opts = opts;

    // Simple reused variables, for ease of updating the test.
    const int num_slider_options = 7;
    const int level_of_last_slider = num_slider_options - 1;

    const option_slider &slider = option_slider_test_world_difficulty.obj();
    REQUIRE( slider.count() == num_slider_options );

    // check reordering
    for( int i = 0; i < num_slider_options; i++ ) {
        REQUIRE( slider.level_name( i ).translated() == string_format( "TEST %d", i ) );
    }

    const std::map<std::string, std::string> expected_default_lvl3 {
        { "MONSTER_SPEED", "100%" },
        { "MONSTER_RESILIENCE", "100%" },
        { "SPAWN_DENSITY", "1.00" },
        { "EVOLUTION_INVERSE_MULTIPLIER", "1.00" },
        { "ITEM_SPAWNRATE", "1.00" },
        { "ETERNAL_SEASON", "false" },
        { "ETERNAL_TIME_OF_DAY", "normal" }
    };

    const std::map<std::string, std::string> expected_highest_difficulty_lvl6 {
        { "MONSTER_SPEED", "120%" },
        { "MONSTER_RESILIENCE", "200%" },
        { "SPAWN_DENSITY", "3.00" },
        { "EVOLUTION_INVERSE_MULTIPLIER", "0.75" },
        { "ITEM_SPAWNRATE", "0.50" },
        { "ETERNAL_SEASON", "true" },
        { "ETERNAL_TIME_OF_DAY", "night" }
    };

    // check defaults
    int checked = 0;
    for( const auto &opt : opts ) {
        CHECK( opt.second == old_opts.at( opt.first ) );
        const auto iter = expected_default_lvl3.find( opt.first );
        if( iter != expected_default_lvl3.end() ) {
            CAPTURE( opt.first );
            CAPTURE( opt.second.getType() );
            CHECK( opt.second.getValue() == iter->second );
            checked++;
        }
    }
    CHECK( checked == num_slider_options );

    // check modified
    slider.apply_opts( level_of_last_slider, opts );
    checked = 0;
    for( const auto &opt : opts ) {
        const auto iter = expected_highest_difficulty_lvl6.find( opt.first );
        if( iter != expected_highest_difficulty_lvl6.end() ) {
            CAPTURE( opt.first );
            CAPTURE( opt.second.getType() );
            CHECK( opt.second.getValue() == iter->second );
            checked++;
        }
    }
    CHECK( checked == num_slider_options );

    // check defaults
    slider.apply_opts( 3, opts );
    checked = 0;
    for( const auto &opt : opts ) {
        CHECK( opt.second == old_opts.at( opt.first ) );
        const auto iter = expected_default_lvl3.find( opt.first );
        if( iter != expected_default_lvl3.end() ) {
            CAPTURE( opt.first );
            CAPTURE( opt.second.getType() );
            CHECK( opt.second.getValue() == iter->second );
            checked++;
        }
    }
    CHECK( checked == num_slider_options );
}
