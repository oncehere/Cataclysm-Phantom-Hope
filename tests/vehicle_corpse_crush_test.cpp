#include <algorithm>

#include "avatar.h"
#include "calendar.h"
#include "cata_catch.h"
#include "coordinates.h"
#include "flag.h"
#include "item.h"
#include "map.h"
#include "map_helpers.h"
#include "mtype.h"
#include "player_helpers.h"
#include "type_id.h"
#include "units.h"
#include "vehicle.h"

TEST_CASE( "vehicle_wheel_crushes_corpse_before_another_item", "[vehicle][corpse][crash]" )
{
    clear_avatar();
    clear_map_without_vision();
    map &here = get_map();
    const tripoint_bub_ms pos = get_avatar().pos_bub() + tripoint::east;
    vehicle *cart = here.add_vehicle( vproto_id( "test_shopping_cart" ), pos,
                                      0_degrees, 0, veh_spawn_status::UNDAMAGED );
    REQUIRE( cart );
    REQUIRE_FALSE( cart->wheelcache.empty() );
    item corpse = item::make_corpse( mtype_id( "mon_zombie" ) );
    REQUIRE( corpse.can_revive() );
    here.add_item( pos, corpse );
    const bool another_item = GENERATE( false, true );
    if( another_item ) {
        here.add_item( pos, item( itype_id( "rock" ) ) );
    }
    REQUIRE( here.i_at( pos ).size() == ( another_item ? 2 : 1 ) );

    here.smash_items( pos, 100, "test vehicle wheel", &cart->part( cart->wheelcache.front() ), cart );

    map_stack remaining = here.i_at( pos );
    CHECK( std::none_of( remaining.begin(), remaining.end(), []( const item & it ) {
        return it.is_corpse() && it.can_revive();
    } ) );
    bool found_pulped_corpse = false;
    for( const tripoint_bub_ms &p : here.points_in_radius( pos, 1 ) ) {
        for( const item &it : here.i_at( p ) ) {
            if( it.is_corpse() && it.has_flag( flag_id( "GIBBED" ) ) ) {
                CHECK( it.get_corpse_mon()->id == mtype_id( "mon_zombie" ) );
                CHECK_FALSE( it.can_revive() );
                found_pulped_corpse = true;
            }
        }
    }
    CHECK( found_pulped_corpse );
}

TEST_CASE( "vehicle_movement_over_corpse_and_item", "[vehicle][corpse][crash]" )
{
    clear_avatar();
    clear_map_without_vision();
    map &here = get_map();
    const tripoint_bub_ms pos = get_avatar().pos_bub() + tripoint( 5, 5, 0 );
    vehicle *cart = here.add_vehicle( vproto_id( "car" ), pos,
                                      0_degrees, 0, veh_spawn_status::UNDAMAGED );
    REQUIRE( cart );
    REQUIRE_FALSE( cart->wheelcache.empty() );
    REQUIRE( cart->total_mass( here ) > 500000_gram );
    const int wheel = cart->wheelcache.front();
    const tripoint_bub_ms under_wheel = cart->bub_part_pos( here, wheel ) +
                                        tripoint_rel_ms::east;
    item corpse = item::make_corpse( mtype_id( "mon_zombie" ) );
    REQUIRE( corpse.can_revive() );
    here.add_item( under_wheel, corpse );
    here.add_item( under_wheel, item( itype_id( "rock" ) ) );
    cart->velocity = 1000;

    REQUIRE( here.move_vehicle( *cart, tripoint_rel_ms::east, cart->face ) == cart );

    CHECK( cart->bub_part_pos( here, wheel ) == under_wheel );
    map_stack remaining = here.i_at( under_wheel );
    CHECK( std::none_of( remaining.begin(), remaining.end(), []( const item & it ) {
        return it.is_corpse() && it.can_revive();
    } ) );
}
