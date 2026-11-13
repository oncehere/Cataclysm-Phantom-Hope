#include <tuple>
#include <vector>

#include "activity_actor_definitions.h"
#include "activity_item_handling.h"
#include "avatar.h"
#include "calendar.h"
#include "cata_catch.h"
#include "clzones.h"
#include "craft_reservation.h"
#include "faction.h"
#include "item.h"
#include "item_uid.h"
#include "map.h"
#include "map_helpers.h"
#include "player_activity.h"
#include "player_helpers.h"
#include "pocket_type.h"
#include "point.h"
#include "requirements.h"
#include "ret_val.h"
#include "type_id.h"

static const activity_id ACT_FETCH_REQUIRED( "ACT_FETCH_REQUIRED" );
static const itype_id itype_nail( "nail" );
static const itype_id itype_box_small( "box_small" );
static const itype_id itype_pockknife( "pockknife" );
static const itype_id itype_sealed_jug( "test_watertight_open_sealed_container_1L" );
static const zone_type_id zone_type_LOOT_UNSORTED( "LOOT_UNSORTED" );

TEST_CASE( "construction_fetch_splits_contained_charges_and_preserves_reservations",
           "[activities][zones][fetch][construction]" )
{
    clear_map();
    clear_avatar();
    get_craft_reservations().clear();
    zone_manager::get_manager().clear();
    avatar &u = get_avatar();
    map &here = get_map();
    const tripoint_bub_ms work = u.pos_bub();
    const tripoint_bub_ms loot = work + tripoint( 8, 0, 0 );
    zone_manager::get_manager().add( "loot", zone_type_LOOT_UNSORTED, u.get_faction()->id,
                                     false, true, here.get_abs( loot ), here.get_abs( loot ) );
    item reserved_box( itype_box_small );
    REQUIRE( reserved_box.put_in( item( itype_nail, calendar::turn, 30 ),
                                  pocket_type::CONTAINER ).success() );
    const item &reserved = here.add_item( loot, reserved_box ).only_item();
    craft_reservation_index::record claim;
    claim.craft_uid = 4242;
    claim.provider_item_uids.push_back( reserved.uid().get_value() );
    claim.expires_at = calendar::turn + 1_days;
    get_craft_reservations().set( claim );
    REQUIRE( craft_reservation::contains_reserved( reserved ) );

    item free_box( itype_box_small );
    REQUIRE( free_box.put_in( item( itype_nail, calendar::turn, 30 ),
                              pocket_type::CONTAINER ).success() );
    const item &stored = here.add_item( loot, free_box );
    const requirement_id req = multi_activity_actor::synthesize_requirements(
    { { item_comp( itype_nail, 12 ) } }, {}, {} );
    u.backlog.push_front( player_activity( multi_build_construction_activity_actor() ) );
    fetch_required_activity_actor fetch( req, do_activity_reason::NO_COMPONENTS,
                                         here.get_abs( work ), here.get_abs( work ) );
    const auto plan = fetch.requirements_map( u );
    REQUIRE( plan.size() == 1 );
    CHECK( std::get<0>( plan.front() ) == loot );
    CHECK( std::get<1>( plan.front() ) == itype_nail );
    CHECK( std::get<2>( plan.front() ) == 12 );
    REQUIRE( fetch.fetch_activity( u, loot, ACT_FETCH_REQUIRED ) );
    CHECK( stored.only_item().charges == 18 );
    CHECK( reserved.charges == 30 );
    CHECK( here.i_at( loot ).size() == 2 );
    REQUIRE( here.i_at( work ).size() == 1 );
    CHECK( here.i_at( work ).only_item().typeId() == itype_nail );
    CHECK( here.i_at( work ).only_item().charges == 12 );
    get_craft_reservations().clear();
}

TEST_CASE( "construction_fetch_unseals_source_pocket",
           "[activities][zones][fetch][construction]" )
{
    clear_map();
    clear_avatar();
    get_craft_reservations().clear();
    zone_manager::get_manager().clear();
    avatar &u = get_avatar();
    map &here = get_map();
    const tripoint_bub_ms work = u.pos_bub();
    const tripoint_bub_ms loot = work + tripoint( 8, 0, 0 );
    zone_manager::get_manager().add( "loot", zone_type_LOOT_UNSORTED, u.get_faction()->id,
                                     false, true, here.get_abs( loot ), here.get_abs( loot ) );
    item jug( itype_sealed_jug );
    REQUIRE( jug.put_in( item( itype_pockknife ), pocket_type::CONTAINER ).success() );
    REQUIRE( jug.put_in( item( itype_nail, calendar::turn, 10 ),
                         pocket_type::CONTAINER ).success() );
    REQUIRE( jug.seal() );
    const bool nested = GENERATE( false, true );
    item outer( itype_id( "backpack" ) );
    if( nested ) {
        REQUIRE( outer.put_in( jug, pocket_type::CONTAINER ).success() );
    }
    const item &placed = here.add_item( loot, nested ? outer : jug );
    const item &stored = nested ? placed.only_item() : placed;
    REQUIRE( stored.all_pockets_sealed() );
    const requirement_id req = multi_activity_actor::synthesize_requirements(
    { { item_comp( itype_pockknife, 1 ) } }, {}, {} );
    u.backlog.push_front( player_activity( multi_build_construction_activity_actor() ) );
    fetch_required_activity_actor fetch( req, do_activity_reason::NO_COMPONENTS,
                                         here.get_abs( work ), here.get_abs( work ) );
    REQUIRE( fetch.fetch_activity( u, loot, ACT_FETCH_REQUIRED ) );
    CHECK_FALSE( stored.any_pockets_sealed() );
    CHECK( stored.only_item().typeId() == itype_nail );
    CHECK( here.i_at( loot ).size() == 1 );
    CHECK( placed.typeId() == ( nested ? itype_id( "backpack" ) : itype_sealed_jug ) );
    REQUIRE( here.i_at( work ).size() == 1 );
    CHECK( here.i_at( work ).only_item().typeId() == itype_pockknife );
    get_craft_reservations().clear();
}
