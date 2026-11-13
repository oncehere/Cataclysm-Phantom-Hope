#include <functional>
#include <optional>
#include <sstream>

#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "character.h"
#include "coordinates.h"
#include "item.h"
#include "json.h"
#include "json_loader.h"
#include "map.h"
#include "map_helpers.h"
#include "map_helpers_tests.h"
#include "map_scale_constants.h"
#include "player_helpers.h"
#include "ret_val.h"
#include "safe_reference.h"
#include "type_id.h"
#include "veh_appliance.h"
#include "vehicle.h"
#include "vpart_position.h"

static const itype_id itype_hotplate( "hotplate" );
static const itype_id itype_test_storage_battery( "test_storage_battery" );
static const vpart_id vpart_ap_test_storage_battery( "ap_test_storage_battery" );

TEST_CASE( "cable_length_measured_to_socket_when_grid_origin_leaves_bubble",
           "[vehicle][power][grid]" )
{
    clear_map_without_vision();
    clear_avatar();
    map &here = get_map();
    Character &player_character = get_player_character();
    GIVEN( "hotplate plugged into the far end of a battery grid that straddles a submap edge" ) {
        const int row_y = HALF_MAPSIZE_Y;
        // each new appliance absorbs its neighbor, so the last one placed becomes the origin
        for( int x = SEEX; x >= SEEX - 4; --x ) {
            std::optional<item> battery_item( itype_test_storage_battery );
            REQUIRE( place_appliance( here, tripoint_bub_ms( x, row_y, 0 ),
                                      vpart_ap_test_storage_battery, player_character, battery_item ) );
        }
        const tripoint_bub_ms socket_pos( SEEX, row_y, 0 );
        const optional_vpart_position socket_vp = here.veh_at( socket_pos );
        REQUIRE( socket_vp.has_value() );
        vehicle &grid = socket_vp->vehicle();
        for( int x = SEEX - 4; x < SEEX; ++x ) {
            const optional_vpart_position vp = here.veh_at( tripoint_bub_ms( x, row_y, 0 ) );
            REQUIRE( vp.has_value() );
            REQUIRE( &vp->vehicle() == &grid );
        }
        const tripoint_abs_ms origin_abs = grid.pos_abs();
        CAPTURE( grid.pos_bub( here ).to_string(), socket_vp->mount_pos().to_string() );
        // shift below must drop origin out of the bubble and keep socket in
        REQUIRE( grid.pos_bub( here ).x() < SEEX );
        REQUIRE( socket_vp->mount_pos() != point_rel_ms::zero );

        const tripoint_bub_ms hotplate_pos( SEEX + 1, row_y, 0 );
        item hotplate( itype_hotplate );
        REQUIRE( hotplate.link_to( socket_vp, link_state::vehicle_port ).success() );
        REQUIRE( hotplate.max_link_length() == 3 );
        here.add_item( hotplate_pos, hotplate );
        here.i_at( hotplate_pos ).only_item().process( here, nullptr, hotplate_pos );
        REQUIRE( here.i_at( hotplate_pos ).only_item().link_length() == 1 );
        const tripoint_abs_ms hotplate_abs = here.get_abs( hotplate_pos );

        WHEN( "the map shifts one submap east" ) {
            here.shift( point_rel_sm::east );
            on_out_of_scope restore_map( [&here]() {
                here.shift( point_rel_sm::west );
            } );
            REQUIRE_FALSE( here.inbounds( origin_abs ) );
            REQUIRE( here.inbounds( hotplate_abs ) );
            const tripoint_bub_ms shifted_pos = here.get_bub( hotplate_abs );
            item &shifted = here.i_at( shifted_pos ).only_item();
            REQUIRE( shifted.link().t_veh );

            AND_WHEN( "hotplate is processed where it lies" ) {
                shifted.process( here, nullptr, shifted_pos );
                THEN( "stays plugged in at its true length" ) {
                    CHECK( shifted.link().target == link_state::vehicle_port );
                    CHECK( shifted.link_length() == 1 );
                }
            }
            AND_WHEN( "hotplate saved and loaded back" ) {
                std::ostringstream os;
                JsonOut jsout( os );
                shifted.serialize( jsout );
                item loaded;
                JsonValue jv = json_loader::from_string( os.str() );
                JsonObject jo = jv;
                loaded.deserialize( jo );
                here.i_clear( shifted_pos );
                here.add_item( shifted_pos, loaded );
                item &reloaded = here.i_at( shifted_pos ).only_item();
                REQUIRE_FALSE( reloaded.link().t_veh );
                reloaded.process( here, nullptr, shifted_pos );
                THEN( "reconnects at its true length" ) {
                    CHECK( reloaded.link().target == link_state::vehicle_port );
                    CHECK( reloaded.link_length() == 1 );
                }
            }
            AND_WHEN( "hotplate is carried one more tile from the socket" ) {
                shifted.process( here, nullptr, shifted_pos + tripoint_rel_ms::east );
                THEN( "stays plugged in at the new length" ) {
                    CHECK( shifted.link().target == link_state::vehicle_port );
                    CHECK( shifted.link_length() == 2 );
                }
            }
            AND_WHEN( "hotplate carried past its maximum length" ) {
                shifted.process( here, nullptr, shifted_pos + tripoint_rel_ms( 3, 0, 0 ) );
                THEN( "cable resets fully rather than needing to be reeled in" ) {
                    CHECK_FALSE( shifted.has_link_data() );
                }
            }
        }
    }
}
TEST_CASE( "cable_length_checked_when_source_moves_with_map_shift", "[vehicle][power][grid]" )
{
    clear_map_without_vision();
    clear_avatar();
    map &here = get_map();
    Character &player_character = get_player_character();
    GIVEN( "hotplate plugged into a battery at the map center" ) {
        const tripoint_bub_ms battery_pos( HALF_MAPSIZE_X, HALF_MAPSIZE_Y, 0 );
        std::optional<item> battery_item( itype_test_storage_battery );
        REQUIRE( place_appliance( here, battery_pos, vpart_ap_test_storage_battery,
                                  player_character, battery_item ) );
        const optional_vpart_position battery_vp = here.veh_at( battery_pos );
        REQUIRE( battery_vp.has_value() );
        const tripoint_abs_ms battery_abs = battery_vp->vehicle().pos_abs();

        const tripoint_bub_ms hotplate_pos = battery_pos + tripoint_rel_ms::east;
        item hotplate( itype_hotplate );
        REQUIRE( hotplate.link_to( battery_vp, link_state::vehicle_port ).success() );
        REQUIRE( hotplate.max_link_length() == 3 );
        here.add_item( hotplate_pos, hotplate );
        item &placed = here.i_at( hotplate_pos ).only_item();
        placed.process( here, nullptr, hotplate_pos );
        REQUIRE( placed.link_length() == 1 );

        WHEN( "hotplate moves one submap east as the map shifts with it" ) {
            // copy stands in for a carried device; original stays behind on its submap
            item carried = placed;
            here.shift( point_rel_sm::east );
            on_out_of_scope restore_map( [&here]() {
                here.shift( point_rel_sm::west );
            } );
            REQUIRE( here.inbounds( battery_abs ) );
            carried.process( here, nullptr, hotplate_pos );
            THEN( "over-extended cable comes loose" ) {
                CHECK( carried.link_length() < 0 );
            }
        }
    }
}

#if defined(TILES)
#include "sdltiles.h"

TEST_CASE( "gpu_backend_hint_respects_environment", "[tiles][renderer]" )
{
    CHECK( gpu_backend_hint( "auto", false ) == std::nullopt );
    CHECK( gpu_backend_hint( "", false ) == std::nullopt );
    CHECK( gpu_backend_hint( "vulkan", false ) == std::optional<std::string>( "vulkan" ) );
    CHECK( gpu_backend_hint( "vulkan", true ) == std::nullopt );
}
#endif

