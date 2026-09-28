#include <algorithm>
#include <cstddef>
#include <memory>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "city.h"
#include "coordinates.h"
#include "omdata.h"
#include "options_helpers.h"
#include "overmap.h"
#include "overmap_worldgen.h"
#include "overmapbuffer.h"
#include "regional_settings.h"
#include "rng.h"
#include "type_id.h"
#include "world_advanced_options.h"

class world_advanced_region_test_helper
{
    public:
        static void use_region( overmap &om, const region_settings &settings ) {
            om.settings = settings.id;
            om.world_settings = std::make_shared<const region_settings>( settings );
            om.world_settings_revision = world_advanced_options_revision();
            om.init_layers();
        }

        static void generate( overmap &om ) {
            overmap_special_batch specials( om.pos(), {} );
            om.generate( std::vector<const overmap *>( 4, nullptr ), specials );
        }

        static void place_cities( overmap &om ) {
            om.calculate_urbanity();
            om.calculate_forestosity();
            om.place_cities();
        }

        static overmap_special_id pick_building( const overmap &om, int size,
                const std::unordered_set<overmap_special_id> &placed_unique_buildings = {} ) {
            return om.pick_random_building_to_place( 50, size, placed_unique_buildings );
        }
};

namespace
{
class advanced_region_scope
{
    public:
        world_advanced_options options;
        advanced_region_scope() : previous( active_world_advanced_options() ),
            random_state( rng_get_engine() ) {
            set_active_world_advanced_options( &options );
            clear_world_advanced_regions();
        }
        ~advanced_region_scope() {
            set_active_world_advanced_options( previous );
            clear_world_advanced_regions();
            rng_get_engine() = random_state;
        }
        void set( const std::string &id, const std::string &value ) {
            std::string error;
            INFO( id << "=" << value );
            REQUIRE( options.set( id, value, error ) );
        }
    private:
        const world_advanced_options *previous;
        cata_default_random_engine random_state;
};

region_settings forest_only_region()
{
    region_settings settings = *region_settings_id( "default" );
    settings.city_spec = region_settings_city_id( "no_cities" );
    settings.overmap_highway.reset();
    settings.overmap_river.reset();
    settings.overmap_lake.reset();
    settings.overmap_ocean.reset();
    settings.overmap_ravine.reset();
    settings.forest_trail.reset();
    settings.place_roads = false;
    settings.place_railroads = false;
    settings.place_specials = false;
    return settings;
}
} // namespace

TEST_CASE( "world_advanced_regions_inherit_without_mutating_content", "[world_advanced][region]" )
{
    advanced_region_scope scope;
    const region_settings &base = *region_settings_id( "default" );
    const auto inherited = get_world_advanced_region( base.id );
    CHECK( &inherited->get_settings_city() == &base.get_settings_city() );
    CHECK( &inherited->get_settings_forest() == &base.get_settings_forest() );
    CHECK( &inherited->get_settings_lake() == &base.get_settings_lake() );
    CHECK( inherited->place_roads == base.place_roads );
    CHECK( inherited->place_railroads == base.place_railroads );
    CHECK( get_world_advanced_region( base.id ) == inherited );

    scope.set( "CITY_SIZE", "0" );
    scope.set( "REGION_LAKE_DEPTH", "-10" );
    const auto overridden = get_world_advanced_region( base.id );
    CHECK( overridden != inherited );
    CHECK( overridden->get_settings_city().city_size == 0 );
    CHECK( overridden->get_settings_lake().lake_depth == -10 );
    CHECK( inherited->get_settings_city().city_size == base.get_settings_city().city_size );
    CHECK( inherited->get_settings_lake().lake_depth == base.get_settings_lake().lake_depth );
    CHECK( &overridden->get_settings_forest() == &base.get_settings_forest() );
    scope.options.clear();
    CHECK( get_world_advanced_region( base.id )->get_settings_lake().lake_depth ==
           base.get_settings_lake().lake_depth );
}

TEST_CASE( "world_advanced_regions_apply_scalar_and_generation_overrides",
           "[world_advanced][region]" )
{
    advanced_region_scope scope;
    for( const char *name : {
             "REGION_ROADS", "REGION_HIGHWAYS", "REGION_FORESTS", "REGION_SWAMPS",
             "REGION_FOREST_TRAILS", "REGION_LAKES", "REGION_OCEANS", "REGION_SPECIALS",
             "REGION_NEIGHBOR_CONNECTIONS"
         } ) {
        scope.set( name, "false" );
    }
    scope.set( "REGION_RAILROADS", "true" );
    scope.set( "REGION_MEGACITY", "true" );
    for( const auto &entry : std::vector<std::pair<std::string, std::string>> {
    { "CITY_SIZE", "12" }, { "CITY_SPACING", "7" },
    { "REGION_FOREST_THRESHOLD", "0.3" }, { "REGION_THICK_FOREST_THRESHOLD", "0.4" },
    { "REGION_RIVER_SCALE", "0" }, { "REGION_RIVER_FREQUENCY", "1" },
    { "REGION_LAKE_THRESHOLD", "0.8" }, { "REGION_LAKE_SIZE_MIN", "32400" },
    { "REGION_LAKE_DEPTH", "-10" }, { "REGION_OCEAN_START_NORTH", "0" },
    { "REGION_OCEAN_START_EAST", "-1" }, { "REGION_OCEAN_START_SOUTH", "2" },
    { "REGION_OCEAN_START_WEST", "10000" }, { "REGION_RAVINE_COUNT", "10" },
    { "REGION_RAVINE_WIDTH", "10" }, { "REGION_RAVINE_DEPTH", "-10" }
} ) {
        scope.set( entry.first, entry.second );
    }
    const auto region = get_world_advanced_region( region_settings_id( "default" ) );
    CHECK_FALSE( region->place_roads );
    // Core references local_railroad, but its definition belongs to the optional
    // Railroads mod.  An override must not fabricate that missing component.
    const region_settings &base = *region_settings_id( "default" );
    CHECK( region->place_railroads == ( base.place_railroads ||
                                        base.overmap_connection.rail_connection.is_valid() ) );
    CHECK_FALSE( region->place_swamps );
    CHECK_FALSE( region->place_specials );
    CHECK_FALSE( region->neighbor_connections );
    CHECK_FALSE( region->has_worldgen_forests() );
    CHECK_FALSE( region->has_worldgen_forest_trails() );
    CHECK_FALSE( region->has_worldgen_highways() );
    CHECK_FALSE( region->has_worldgen_lakes() );
    CHECK_FALSE( region->has_worldgen_oceans() );
    // Disabled natural generation still leaves components for special/mapgen terrain.
    CHECK( region->overmap_lake.has_value() );
    CHECK( region->get_settings_city().is_megacity );
    CHECK( region->get_settings_city().city_size == 12 );
    CHECK( region->get_settings_city().city_spacing == 7 );
    CHECK( region->get_settings_forest().noise_threshold_forest == Approx( 0.3 ) );
    CHECK( region->get_settings_forest().noise_threshold_forest_thick == Approx( 0.4 ) );
    CHECK( region->get_settings_river().river_scale == 0 );
    CHECK( region->get_settings_river().river_frequency == 1 );
    CHECK( region->get_settings_lake().noise_threshold_lake == Approx( 0.8 ) );
    CHECK( region->get_settings_lake().lake_size_min == 32400 );
    CHECK( region->get_settings_lake().lake_depth == -10 );
    CHECK( region->get_settings_ocean().ocean_start_north == 0 );
    CHECK_FALSE( region->get_settings_ocean().ocean_start_east.has_value() );
    CHECK( region->get_settings_ocean().ocean_start_south == 2 );
    CHECK( region->get_settings_ocean().ocean_start_west == 10000 );
    CHECK( region->get_settings_ravine().num_ravines == 10 );
    CHECK( region->get_settings_ravine().ravine_width == 10 );
    CHECK( region->get_settings_ravine().ravine_depth == -10 );
}

TEST_CASE( "world_advanced_regions_do_not_create_missing_components", "[world_advanced][region]" )
{
    advanced_region_scope scope;
    region_settings base = forest_only_region();
    base.city_spec.reset();
    base.overmap_forest.reset();
    for( const char *name : {
             "REGION_HIGHWAYS", "REGION_FORESTS", "REGION_FOREST_TRAILS",
             "REGION_LAKES", "REGION_OCEANS", "REGION_MEGACITY"
         } ) {
        scope.set( name, "true" );
    }
    scope.set( "CITY_SIZE", "16" );
    scope.set( "REGION_ROADS", "true" );
    scope.set( "REGION_RAILROADS", "true" );
    scope.set( "REGION_RIVER_SCALE", "10" );
    scope.set( "REGION_RAVINE_COUNT", "10" );
    const region_settings effective = base.with_world_advanced_options();
    CHECK_FALSE( effective.city_spec.has_value() );
    CHECK_FALSE( effective.place_roads );
    CHECK_FALSE( effective.place_railroads );
    CHECK_FALSE( effective.overmap_river.has_value() );
    CHECK_FALSE( effective.overmap_ravine.has_value() );
    CHECK_FALSE( effective.has_worldgen_highways() );
    CHECK_FALSE( effective.has_worldgen_forests() );
    CHECK_FALSE( effective.has_worldgen_forest_trails() );
    CHECK_FALSE( effective.has_worldgen_lakes() );
    CHECK_FALSE( effective.has_worldgen_oceans() );
}

TEST_CASE( "world_advanced_railroads_require_components_in_each_region",
           "[world_advanced][region]" )
{
    advanced_region_scope scope;
    const overmap_connection_id existing_connection( "local_road" );
    REQUIRE( existing_connection.is_valid() );
    for( const char *id : {
             "default", "highlands"
         } ) {
        CAPTURE( id );
        const region_settings_id region_id( id );
        REQUIRE( region_id.is_valid() );
        region_settings base = *region_id;
        base.place_railroads = false;
        base.overmap_connection.rail_connection = overmap_connection_id::NULL_ID();
        scope.set( "REGION_RAILROADS", "true" );
        CHECK_FALSE( base.with_world_advanced_options().place_railroads );

        // Use a real loaded connection to model a mod supplying this component.
        // This fixture only checks the switch, and does not generate road terrain.
        base.overmap_connection.rail_connection = existing_connection;
        CHECK( base.with_world_advanced_options().place_railroads );
        scope.set( "REGION_RAILROADS", "false" );
        CHECK_FALSE( base.with_world_advanced_options().place_railroads );

        // Explicit disabling remains valid even for incomplete inherited data.
        base.place_railroads = true;
        base.overmap_connection.rail_connection = overmap_connection_id::NULL_ID();
        CHECK_FALSE( base.with_world_advanced_options().place_railroads );
        scope.options.erase( "REGION_RAILROADS" );
        CHECK( base.with_world_advanced_options().place_railroads );
    }
}

TEST_CASE( "world_advanced_forest_thresholds_validate_against_inherited_region",
           "[world_advanced][region]" )
{
    advanced_region_scope scope;
    scope.set( "REGION_FOREST_THRESHOLD", "0.9" );
    CHECK_FALSE( validate_world_advanced_regions().empty() );
    scope.set( "REGION_THICK_FOREST_THRESHOLD", "0.95" );
    CHECK( validate_world_advanced_regions().empty() );
}

TEST_CASE( "world_advanced_inheritance_preserves_natural_generation_and_rng",
           "[world_advanced][region][overmap]" )
{
    advanced_region_scope scope;
    restore_on_out_of_scope restore_state( overmap_buffer.global_state );
    region_settings base = forest_only_region();
    SECTION( "forest-only region" ) {}
    SECTION( "complete default region" ) {
        base = *region_settings_id( "default" );
    }
    overmap_buffer.global_state.clear();
    const auto baseline = std::make_unique<overmap>( point_abs_om::zero );
    world_advanced_region_test_helper::use_region( *baseline, base );
    rng_set_engine_seed( 7319 );
    world_advanced_region_test_helper::generate( *baseline );
    const auto baseline_rng = rng_get_engine();

    overmap_buffer.global_state.clear();
    const auto inherited = std::make_unique<overmap>( point_abs_om::zero );
    world_advanced_region_test_helper::use_region( *inherited, base.with_world_advanced_options() );
    rng_set_engine_seed( 7319 );
    world_advanced_region_test_helper::generate( *inherited );
    CHECK( rng_get_engine() == baseline_rng );
    REQUIRE( inherited->cities.size() == baseline->cities.size() );
    for( size_t i = 0; i < baseline->cities.size(); ++i ) {
        CHECK( inherited->cities[i].pos == baseline->cities[i].pos );
        CHECK( inherited->cities[i].size == baseline->cities[i].size );
    }
    for( int x = 0; x < OMAPX; ++x ) {
        for( int y = 0; y < OMAPY; ++y ) {
            const tripoint_om_omt p( x, y, 0 );
            REQUIRE( inherited->ter( p ) == baseline->ter( p ) );
        }
    }
}

TEST_CASE( "world_advanced_city_rules_change_actual_city_placement_across_regions",
           "[world_advanced][region][overmap]" )
{
    advanced_region_scope scope;
    restore_on_out_of_scope restore_state( overmap_buffer.global_state );
    REQUIRE( city::get_all().empty() );
    for( const char *id : {
             "default", "highlands"
         } ) {
        CAPTURE( id );
        region_settings base = *region_settings_id( id );
        base.urban_increase.fill( 0 );
        base.max_urban = 1;
        base.overmap_forest.reset();
        const auto generate_cities = [&]( const char *size, const char *spacing, bool megacity ) {
            scope.set( "CITY_SIZE", size );
            scope.set( "CITY_SPACING", spacing );
            scope.set( "REGION_MEGACITY", megacity ? "true" : "false" );
            auto result = std::make_unique<overmap>( point_abs_om::zero );
            world_advanced_region_test_helper::use_region( *result, base.with_world_advanced_options() );
            rng_set_engine_seed( 7319 );
            world_advanced_region_test_helper::place_cities( *result );
            return result;
        };
        const auto disabled = generate_cities( "0", "0", false );
        CHECK( disabled->cities.empty() );
        const auto dense = generate_cities( "8", "0", false );
        const auto sparse = generate_cities( "8", "8", false );
        REQUIRE_FALSE( dense->cities.empty() );
        CHECK( dense->cities.size() > sparse->cities.size() );
        const auto large = generate_cities( "16", "0", false );
        REQUIRE_FALSE( large->cities.empty() );
        CHECK( large->cities.size() < dense->cities.size() );
        int largest = 0;
        for( const city &c : large->cities ) {
            largest = std::max( largest, c.size );
        }
        CHECK( largest > 16 );
        const auto mega = generate_cities( "16", "0", true );
        REQUIRE( mega->cities.size() == 5 );
        for( const city &c : mega->cities ) {
            CHECK( c.size == 40 );
        }
    }
}

TEST_CASE( "world_advanced_city_generation_with_no_eligible_buildings_terminates",
           "[world_advanced][region][overmap]" )
{
    advanced_region_scope scope;
    scope.set( "CITY_SIZE", "16" );
    scope.set( "CITY_SPACING", "0" );
    scope.set( "REGION_MEGACITY", "true" );
    const auto om = std::make_unique<overmap>( point_abs_om::zero );
    region_settings settings = region_settings_id( "default" )->with_world_advanced_options();
    REQUIRE( &settings.get_settings_city() !=
             &region_settings_id( "default" )->get_settings_city() );
    // The explicit city choices created a child owned by this mutable copy.
    // Customize that test copy, leaving factory definitions untouched.
    region_settings_city &city = const_cast<region_settings_city &>( settings.get_settings_city() );
    CHECK( city.city_size == 16 );
    CHECK( city.city_spacing == 0 );
    CHECK( city.is_megacity );
    const auto use_only_building = [&]( const overmap_special_id & candidate ) {
        for( building_bin *bin : {
                 &city.houses, &city.shops, &city.parks
             } ) {
            bin->clear();
            bin->add( candidate, 1 );
            bin->finalize();
            REQUIRE_FALSE( bin->buildings.empty() );
        }
        world_advanced_region_test_helper::use_region( *om, settings );
    };

    SECTION( "empty building bins" ) {
        world_advanced_region_test_helper::use_region( *om,
                forest_only_region().with_world_advanced_options() );
        CHECK( world_advanced_region_test_helper::pick_building( *om, 40 ).is_null() );
    }
    SECTION( "nonempty bins with no building eligible for a giant city" ) {
        const overmap_special_id candidate( "fishing_pond_city" );
        REQUIRE( candidate.is_valid() );
        REQUIRE_FALSE( candidate->get_constraints().city_size.contains( 40 ) );
        REQUIRE( candidate->get_constraints().city_size.contains( 8 ) );
        use_only_building( candidate );
        CHECK( world_advanced_region_test_helper::pick_building( *om, 8 ) == candidate );
        CHECK( world_advanced_region_test_helper::pick_building( *om, 40 ).is_null() );
    }
    SECTION( "nonempty bins with every city unique building exhausted" ) {
        const overmap_special_id candidate( "police_dept" );
        REQUIRE( candidate.is_valid() );
        REQUIRE( candidate->get_constraints().city_size.contains( 40 ) );
        REQUIRE( candidate->has_flag( "CITY_UNIQUE" ) );
        use_only_building( candidate );
        CHECK( world_advanced_region_test_helper::pick_building( *om, 40 ) == candidate );
        CHECK( world_advanced_region_test_helper::pick_building( *om, 40, { candidate } ).is_null() );
    }
}

TEST_CASE( "world_advanced_regions_apply_to_other_dimensions_without_adding_components",
           "[world_advanced][region]" )
{
    advanced_region_scope scope;
    const region_settings_id highlands( "highlands" );
    REQUIRE( highlands.is_valid() );
    scope.set( "REGION_RAVINE_DEPTH", "-10" );
    scope.set( "REGION_LAKES", "true" );
    const auto effective = get_world_advanced_region( highlands );
    CHECK( effective->get_settings_ravine().ravine_depth == -10 );
    CHECK_FALSE( effective->has_worldgen_lakes() );
    CHECK( highlands->get_settings_ravine().ravine_depth != -10 );
}

TEST_CASE( "world_advanced_terrain_rules_leave_pregenerated_layouts_unchanged",
           "[world_advanced][region]" )
{
    advanced_region_scope scope;
    const override_option pregenerated( "OVERMAP_PREGENERATED_PATH", "world_advanced_fixture" );
    scope.set( "CITY_SIZE", "0" );
    scope.set( "REGION_LAKE_DEPTH", "-10" );
    scope.set( "REGION_FORESTS", "false" );
    const region_settings_id id( "default" );
    const auto effective = get_world_advanced_region( id );
    CHECK( effective->get_settings_city().city_size == id->get_settings_city().city_size );
    CHECK( effective->get_settings_lake().lake_depth == id->get_settings_lake().lake_depth );
    CHECK( effective->has_worldgen_forests() );
}

TEST_CASE( "world_advanced_character_region_preview_does_not_generate_maps",
           "[world_advanced][region]" )
{
    advanced_region_scope scope;
    const auto before_rng = rng_get_engine();
    const auto before_regions = overmap_buffer.global_state.placed_regions;
    const dimension_id starting_dimension( "default" );
    const region_settings_id region = starting_dimension->get_region_layout()->get_generator()->
                                      get_initial_region();
    REQUIRE( region.is_valid() );
    CHECK( rng_get_engine() == before_rng );
    CHECK( overmap_buffer.global_state.placed_regions == before_regions );
    scope.set( "CITY_SIZE", "0" );
    CHECK( get_world_advanced_region( region )->get_settings_city().city_size == 0 );
}

TEST_CASE( "world_advanced_lake_heavy_highway_junction_search_is_bounded",
           "[world_advanced][region][overmap]" )
{
    advanced_region_scope scope;
    restore_on_out_of_scope restore_regions( overmap_buffer.global_state.placed_regions );
    const override_option variance( "HIGHWAY_GRID_VARIANCE", "1" );
    scope.set( "REGION_LAKE_THRESHOLD", "0" );
    scope.set( "REGION_LAKE_SIZE_MIN", "1" );
    highway_intersection_grid grid;
    grid.set_options();
    overmap_feature_grid_node node( point_abs_om::zero );
    rng_set_engine_seed( 7319 );
    const auto before_rng = rng_get_engine();
    grid.generate_offset( node );
    CHECK( node.get_offset_pos() == point_abs_om( 1, 0 ) );
    CHECK( rng_get_engine() == before_rng );

    // Cached lake predictions must be refreshed for another world's rules.
    scope.set( "REGION_LAKE_THRESHOLD", "1" );
    grid.generate_offset( node );
    CHECK_FALSE( node.get_offset_pos().is_invalid() );
    CHECK( node.get_offset_pos() != point_abs_om::zero );
    CHECK( rng_get_engine() != before_rng );
}
