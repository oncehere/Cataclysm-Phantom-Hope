#include <initializer_list>
#include <string>

#include "calendar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "coordinates.h"
#include "enums.h"
#include "game.h"
#include "item.h"
#include "map.h"
#include "map_helpers.h"
#include "rng.h"
#include "type_id.h"
#include "units.h"
#include "weather.h"
#include "weather_gen.h"
#include "world_advanced_options.h"

namespace
{

class scoped_climate_options
{
    public:
        scoped_climate_options() : previous( active_world_advanced_options() ) {
            set_active_world_advanced_options( &options );
            get_weather().clear_temp_cache();
        }

        ~scoped_climate_options() {
            set_active_world_advanced_options( previous );
            get_weather().clear_temp_cache();
        }

        void set( const std::string &id, const std::string &value ) {
            std::string error;
            const bool accepted = options.set( id, value, error );
            INFO( error );
            REQUIRE( accepted );
            get_weather().clear_temp_cache();
        }

    private:
        const world_advanced_options *previous;
        world_advanced_options options;
};

weather_generator climate_fixture()
{
    weather_generator result;
    result.base_temperature = 11.1;
    result.base_humidity = 50.0;
    result.base_pressure = 1015.0;
    result.base_wind = 3.4;
    result.base_wind_distrib_peaks = 80;
    result.summer_temp_manual_mod = 5;
    return result;
}

w_point seeded_weather( const weather_generator &generator )
{
    constexpr unsigned seed = 20260928;
    rng_set_engine_seed( seed );
    weather_generator::current_winddir = 1000;
    return generator.get_weather( tripoint_abs_ms::zero, calendar::turn_zero + 60_days + 8_hours,
                                  seed );
}

} // namespace

TEST_CASE( "world_advanced_climate_neutral_values_preserve_weather_and_rng",
           "[world_advanced][weather]" )
{
    restore_on_out_of_scope restore_rng( rng_get_engine() );
    restore_on_out_of_scope restore_wind( weather_generator::current_winddir );
    scoped_climate_options options;
    const weather_generator generator = climate_fixture();
    const w_point original = seeded_weather( generator );
    const cata_default_random_engine original_rng = rng_get_engine();

    options.set( "WORLD_TEMPERATURE_OFFSET", "0" );
    options.set( "WORLD_HUMIDITY_OFFSET", "0" );
    options.set( "WORLD_WIND_MULTIPLIER", "1" );
    const w_point neutral = seeded_weather( generator );

    CHECK( neutral.temperature == original.temperature );
    CHECK( neutral.humidity == original.humidity );
    CHECK( neutral.pressure == original.pressure );
    CHECK( neutral.windpower == original.windpower );
    CHECK( neutral.winddirection == original.winddirection );
    CHECK( neutral.wind_desc == original.wind_desc );
    CHECK( rng_get_engine() == original_rng );
}

TEST_CASE( "world_advanced_temperature_preserves_regional_differences_and_water_temperature",
           "[world_advanced][weather]" )
{
    scoped_climate_options options;
    weather_generator generator = climate_fixture();
    const time_point sample_time = calendar::turn_zero + 60_days + 8_hours;
    const units::temperature water_temperature = generator.get_water_temperature();

    for( const double regional_temperature : {
             -50.0, 11.1, 26.0
             } ) {
        generator.base_temperature = regional_temperature;
        options.set( "WORLD_TEMPERATURE_OFFSET", "0" );
        const units::temperature original = generator.get_weather_temperature(
                                                tripoint_abs_ms::zero, sample_time, 20260928 );

        for( const int offset : {
                 -100, 0, 100
                 } ) {
            CAPTURE( regional_temperature, offset );
            options.set( "WORLD_TEMPERATURE_OFFSET", std::to_string( offset ) );
            const units::temperature modified = generator.get_weather_temperature(
                                                    tripoint_abs_ms::zero, sample_time, 20260928 );
            CHECK( units::to_celsius( modified ) == Approx( units::to_celsius( original ) + offset ) );
            CHECK( generator.get_base_temperature_celsius() == Approx( regional_temperature + offset ) );
            CHECK( generator.base_temperature == regional_temperature );
            CHECK( generator.get_water_temperature() == water_temperature );
        }
    }
}

TEST_CASE( "world_advanced_humidity_and_wind_keep_their_physical_bounds",
           "[world_advanced][weather]" )
{
    restore_on_out_of_scope restore_rng( rng_get_engine() );
    restore_on_out_of_scope restore_wind( weather_generator::current_winddir );
    scoped_climate_options options;
    const weather_generator generator = climate_fixture();
    const w_point original = seeded_weather( generator );
    REQUIRE( original.windpower > 0 );

    options.set( "WORLD_HUMIDITY_OFFSET", "-100" );
    options.set( "WORLD_WIND_MULTIPLIER", "0" );
    const w_point dry_calm = seeded_weather( generator );
    CHECK( dry_calm.humidity == 0 );
    CHECK( dry_calm.windpower == 0 );
    CHECK( dry_calm.temperature == original.temperature );
    CHECK( dry_calm.pressure == original.pressure );

    options.set( "WORLD_HUMIDITY_OFFSET", "100" );
    options.set( "WORLD_WIND_MULTIPLIER", "10" );
    const w_point wet_windy = seeded_weather( generator );
    CHECK( wet_windy.humidity == 100 );
    CHECK( wet_windy.windpower == Approx( original.windpower * 10 ) );
    CHECK( wet_windy.temperature == original.temperature );
    CHECK( wet_windy.pressure == original.pressure );
}

TEST_CASE( "world_advanced_temperature_reaches_underground_and_offline_root_cellars",
           "[world_advanced][weather][temperature][rot]" )
{
    restore_on_out_of_scope restore_time( calendar::turn );
    restore_on_out_of_scope restore_new_game( g->new_game );
    restore_on_out_of_scope restore_forced_temperature( get_weather().forced_temperature );
    scoped_climate_options options;
    g->new_game = true;
    get_weather().forced_temperature.reset();
    calendar::turn = calendar::start_of_cataclysm + 1_minutes;

    options.set( "WORLD_TEMPERATURE_OFFSET", "20" );
    const double expected = get_weather().get_cur_weather_gen().base_temperature + 20.0;
    CHECK( units::to_celsius( get_weather().get_temperature( tripoint_bub_ms( 0, 0, -1 ) ) ) ==
           Approx( expected ) );
    CHECK( units::to_celsius( get_weather().get_area_temperature( tripoint_abs_omt( 0, 0, -1 ) ) ) ==
           Approx( expected ) );

    item water( itype_id( "water" ) );
    water.process_temperature_rot( 1, tripoint_bub_ms::zero, get_map(), nullptr,
                                   temperature_flag::ROOT_CELLAR );
    CHECK( units::to_celsius( water.temperature ) == Approx( expected ) );
    calendar::turn += 3_hours;
    water.process_temperature_rot( 1, tripoint_bub_ms::zero, get_map(), nullptr,
                                   temperature_flag::ROOT_CELLAR );
    CHECK( units::to_celsius( water.temperature ) == Approx( expected ) );

    const time_point comparison_start = calendar::turn;
    time_duration original_rot = 0_turns;
    for( const int offset : {
             0, 20
         } ) {
        calendar::turn = comparison_start;
        options.set( "WORLD_TEMPERATURE_OFFSET", std::to_string( offset ) );
        item food( itype_id( "meat_cooked" ) );
        food.process_temperature_rot( 1, tripoint_bub_ms::zero, get_map(), nullptr,
                                      temperature_flag::ROOT_CELLAR );
        calendar::turn += 3_hours;
        food.process_temperature_rot( 1, tripoint_bub_ms::zero, get_map(), nullptr,
                                      temperature_flag::ROOT_CELLAR );
        if( offset == 0 ) {
            original_rot = food.get_rot();
        } else {
            CHECK( food.get_rot() > original_rot );
        }
    }
}

TEST_CASE( "world_advanced_temperature_changes_water_terrain_freezing",
           "[world_advanced][weather][mapgen]" )
{
    clear_map();
    scoped_climate_options options;
    const weather_generator generator = climate_fixture();
    map &here = get_map();
    const tripoint_bub_ms point( 60, 60, 0 );
    const ter_str_id water( "t_water_sh" );
    here.ter_set( point, water );

    options.set( "WORLD_TEMPERATURE_OFFSET", "-100" );
    here.temp_based_phase_change_at( point, generator );
    CHECK( here.ter( point ) != water );
    REQUIRE( here.has_original_terrain_at( point ) );

    options.set( "WORLD_TEMPERATURE_OFFSET", "100" );
    here.temp_based_phase_change_at( point, generator );
    CHECK( here.ter( point ) == water );
}
