#include <vector>

#include "avatar.h"
#include "calendar.h"
#include "cata_catch.h"
#include "coordinates.h"
#include "enums.h"
#include "faction_camp.h"
#include "game.h"
#include "item.h"
#include "map.h"
#include "map_helpers.h"
#include "memory_fast.h"
#include "npc.h"
#include "player_helpers.h"
#include "point.h"
#include "rng.h"
#include "type_id.h"

static const itype_id rock( "test_rock" );
static const itype_id plank( "2x4" );
static const itype_id water( "water" );

TEST_CASE( "moving_container_swaps_items_with_destination", "[furniture][regression]" )
{
    clear_avatar();
    clear_map_without_vision();
    clear_npcs();
    map &here = get_map();
    npc &who = spawn_npc( point_bub_ms( 30, 30 ), "test_talker" );
    clear_character( who );
    who.set_str_base( 50 );
    const tripoint_bub_ms src = who.pos_bub() + tripoint_rel_ms::east;
    const tripoint_bub_ms dst = src + tripoint_rel_ms::east;
    here.furn_set( src, furn_str_id( "f_crate_o" ) );
    here.i_at( src ).insert( item( rock, calendar::turn ) );
    here.i_at( dst ).insert( item( plank, calendar::turn ) );
    who.grab( object_type::FURNITURE, tripoint_rel_ms::east );
    g->grabbed_furn_move( who, tripoint_rel_ms::east );
    REQUIRE( here.i_at( src ).size() == 1 );
    REQUIRE( here.i_at( dst ).size() == 1 );
    CHECK( here.i_at( src ).only_item().typeId() == plank );
    CHECK( here.i_at( dst ).only_item().typeId() == rock );
}

TEST_CASE( "camp_harvest_preserves_uncollected_items", "[camp][regression]" )
{
    clear_map_without_vision();
    const tripoint_abs_omt target = project_to<coords::omt>(
                                        get_map().get_abs( tripoint_bub_ms( 30, 30, 0 ) ) );
    const tripoint_omt_ms pos( 5, 5, 0 );
    tinymap setup;
    setup.load( target, false );
    for( const tripoint_omt_ms &p : setup.points_in_rectangle( tripoint_omt_ms( 0, 0, 0 ),
            tripoint_omt_ms( 23, 23, 0 ) ) ) {
        setup.i_clear( p );
    }
    setup.i_at( pos ).insert( item( plank, calendar::turn ) );
    setup.i_at( pos ).insert( item( water, calendar::turn, 1 ) );
    setup.save();

    shared_ptr_fast<npc> companion = make_shared_fast<npc>();
    SECTION( "zero chance leaves both items" ) {
        CHECK( talk_function::om_harvest_itm( companion, target, 0, true ).count == 0 );
        CHECK( companion->companion_mission_inv.size() == 0 );
        tinymap result;
        result.load( target, false );
        CHECK( result.i_at( pos ).size() == 2 );
    }
    SECTION( "certain collection leaves liquid" ) {
        CHECK( talk_function::om_harvest_itm( companion, target, 100, true ).count == 1 );
        REQUIRE( companion->companion_mission_inv.size() == 1 );
        CHECK( companion->companion_mission_inv.const_stack( 0 ).front().typeId() == plank );
        tinymap result;
        result.load( target, false );
        REQUIRE( result.i_at( pos ).size() == 1 );
        CHECK( result.i_at( pos ).only_item().typeId() == water );
    }
    SECTION( "estimate does not move items" ) {
        const talk_function::mass_volume estimate = talk_function::om_harvest_itm( companion, target,
                100, false );
        CHECK( estimate.count == 1 );
        CHECK( estimate.wgt == item( plank, calendar::turn ).weight( true ) );
        CHECK( estimate.vol == item( plank, calendar::turn ).volume( true ) );
        CHECK( companion->companion_mission_inv.size() == 0 );
        tinymap result;
        result.load( target, false );
        CHECK( result.i_at( pos ).size() == 2 );
    }
    SECTION( "null companion retains destructive collection semantics" ) {
        CHECK( talk_function::om_harvest_itm( nullptr, target, 100, true ).count == 1 );
        tinymap result;
        result.load( target, false );
        REQUIRE( result.i_at( pos ).size() == 1 );
        CHECK( result.i_at( pos ).only_item().typeId() == water );
    }
    SECTION( "partial collection conserves solid items" ) {
        constexpr int seed = 58163;
        INFO( "RNG seed: " << seed );
        constexpr int extra_planks = 20;
        for( int i = 0; i < extra_planks; ++i ) {
            setup.i_at( tripoint_omt_ms( i, 10, 0 ) ).insert( item( plank, calendar::turn ) );
        }
        setup.save();
        rng_set_engine_seed( seed );
        const talk_function::mass_volume harvested = talk_function::om_harvest_itm( companion, target,
                50, true );
        tinymap result;
        result.load( target, false );
        int remaining_planks = 0;
        int remaining_water = 0;
        for( const tripoint_omt_ms &p : result.points_in_rectangle( tripoint_omt_ms( 0, 0, 0 ),
                tripoint_omt_ms( 23, 23, 0 ) ) ) {
            for( const item &it : result.i_at( p ) ) {
                remaining_planks += it.typeId() == plank;
                remaining_water += it.typeId() == water;
            }
        }
        CHECK( harvested.count > 0 );
        CHECK( remaining_planks > 0 );
        std::vector<const item *> collected;
        companion->companion_mission_inv.dump( collected );
        int collected_count = 0;
        for( const item *it : collected ) {
            collected_count += it->count_by_charges() ? it->charges : 1;
            CHECK( it->typeId() == plank );
        }
        CHECK( harvested.count == collected_count );
        CHECK( harvested.count + remaining_planks == extra_planks + 1 );
        CHECK( remaining_water == 1 );
    }
}
