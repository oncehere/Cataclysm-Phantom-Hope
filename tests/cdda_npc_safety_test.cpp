#include "activity_actor_definitions.h"
#include "avatar.h"
#include "calendar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "character.h"
#include "character_attire.h"
#include "craft_reservation.h"
#include "field_type.h"
#include "item.h"
#include "item_location.h"
#include "item_uid.h"
#include "map.h"
#include "map_helpers.h"
#include "npc.h"
#include "player_activity.h"
#include "player_helpers.h"
#include "pocket_type.h"
#include "point.h"
#include "test_data.h"
#include "type_id.h"

TEST_CASE( "cdda_npc_consume_uses_the_npc", "[npc][cdda_safety]" )
{
    clear_map();
    clear_avatar();
    npc &guy = spawn_npc( { 50, 50 }, "test_talker" );
    clear_character( guy, true );
    avatar &player = get_avatar();
    guy.set_thirst( 200 );
    player.set_thirst( 0 );
    guy.assign_activity( consume_activity_actor( item( itype_id( "water_clean" ) ) ) );
    REQUIRE( guy.activity );
    for( int turn = 0; turn < 100 && guy.activity; ++turn ) {
        guy.set_moves( 100 );
        guy.activity.do_turn( guy );
    }
    CHECK_FALSE( guy.activity );
    CHECK( guy.get_thirst() < 200 );
    CHECK( player.get_thirst() == 0 );
}

TEST_CASE( "cdda_npc_fire_requires_safe_hearth", "[npc][cdda_safety]" )
{
    clear_map();
    clear_avatar();
    npc &guy = spawn_npc( { 50, 50 }, "test_talker" );
    clear_character( guy, true );
    map &here = get_map();
    const tripoint_bub_ms east = guy.pos_bub() + point::east;
    guy.worn.wear_item( guy, item( itype_id( "backpack" ) ), false, false );
    const item_location wood = guy.i_add( item( itype_id( "2x4" ) ) );
    REQUIRE( wood );
    REQUIRE( wood.carrier() == &guy );
    REQUIRE( wood != guy.get_wielded_item() );
    CHECK_FALSE( guy.check_fire_spot( east ).usable() );
    here.furn_set( east, furn_str_id( "f_firering" ) );
    CHECK( guy.check_fire_spot( east ).check == npc::fire_spot_check::own_fuel );
    here.add_item_or_charges( east, item( itype_id( "cudgel" ) ) );
    CHECK_FALSE( guy.check_fire_spot( east ).usable() );
}

TEST_CASE( "cdda_npc_hearth_rechecks_reserved_and_new_items", "[npc][cdda_safety]" )
{
    clear_map();
    clear_avatar();
    get_craft_reservations().clear();
    on_out_of_scope cleanup( [] { get_craft_reservations().clear(); } );
    npc &guy = spawn_npc( { 50, 50 }, "test_talker" );
    clear_character( guy, true );
    map &here = get_map();
    const tripoint_bub_ms east = guy.pos_bub() + point::east;
    here.furn_set( east, furn_str_id( "f_firering" ) );
    item &wood = here.add_item( east, item( itype_id( "2x4" ) ) );
    craft_reservation_index::record claim;
    claim.craft_uid = 4242;
    claim.provider_item_uids.push_back( wood.uid().get_value() );
    claim.expires_at = calendar::turn + 1_hours;
    get_craft_reservations().set( claim );
    REQUIRE( craft_reservation::contains_reserved( wood ) );
    CHECK_FALSE( guy.check_fire_spot( east ).usable() );
    get_craft_reservations().clear();
    REQUIRE( guy.check_fire_spot( east ).usable() );

    item_location lighter = guy.i_add( tool_with_ammo( itype_id( "lighter" ), 20 ) );
    fire_start_activity_actor actor( here.get_abs( east ), lighter, 0, 100 );
    player_activity act( actor );
    here.add_item_or_charges( east, item( itype_id( "cudgel" ) ) );
    actor.finish( act, guy );
    CHECK_FALSE( act );
    CHECK_FALSE( here.get_field( east, fd_fire ) );
    CHECK( here.i_at( east ).size() == 2 );
}

TEST_CASE( "cdda_npc_liquid_pickup_preserves_remainder", "[npc][cdda_safety]" )
{
    clear_map();
    clear_avatar();
    npc &guy = spawn_npc( { 50, 50 }, "test_talker" );
    clear_character( guy, true );
    guy.set_thirst( 0 );
    map &here = get_map();
    const itype_id jug( "test_watertight_open_sealed_container_250ml" );
    const itype_id water( "test_liquid_1ml" );
    item destination( itype_id( "bottle_plastic" ) );
    item filler( water );
    filler.charges = 499;
    REQUIRE( destination.put_in( filler, pocket_type::CONTAINER ).success() );
    item_location carried = guy.i_add( destination );
    item bucket( jug );
    item liquid( water );
    liquid.charges = 5;
    REQUIRE( bucket.put_in( liquid, pocket_type::CONTAINER ).success() );
    bucket.on_pickup( guy );
    REQUIRE( carried );
    CHECK( carried->only_item().charges == 500 );
    int spilled = 0;
    for( const item &it : here.i_at( guy.pos_bub() ) ) {
        if( it.typeId() == water ) {
            spilled += it.charges;
        }
    }
    CHECK( spilled == 4 );
}
