#include "activity_actor_definitions.h"
#include "avatar.h"
#include "calendar.h"
#include "cata_catch.h"
#include "construction.h"
#include "game.h"
#include "item.h"
#include "map.h"
#include "map_helpers.h"
#include "map_helpers_tests.h"
#include "monster.h"
#include "player_activity.h"
#include "player_helpers.h"
#include "point.h"
#include "requirements.h"
#include "trap.h"
#include "type_id.h"

namespace
{

using pit_trigger = bool ( * )( const tripoint_bub_ms &, Creature *, item * );

void check_corpse_filled_pit( pit_trigger trigger, const ter_id &terrain, int corpse_count )
{
    clear_creatures();
    clear_avatar();
    clear_map_without_vision();

    map &here = get_map();
    const tripoint_bub_ms p = get_avatar().pos_bub() + tripoint::east;
    monster &falling = spawn_test_monster( "mon_zombie_hulk", p );
    here.ter_set( p, terrain );

    const item corpse = item::make_corpse( mtype_id( "mon_zombie" ) );
    REQUIRE( corpse.volume() == 62500_ml );
    for( int i = 0; i < corpse_count; ++i ) {
        here.add_item_or_charges( p, corpse );
    }
    here.add_item_or_charges( p, item( itype_id( "rock" ) ) );

    REQUIRE( trigger( p, &falling, nullptr ) );
    if( corpse_count == 5 ) {
        CHECK( here.ter( p ) == ter_id( "t_pit_corpsed" ) );
        CHECK_FALSE( here.has_flag( ter_furn_flag::TFLAG_SEALED, p ) );
        CHECK( here.can_put_items_ter_furn( p ) );
        CHECK( here.accessible_items( p ) );
        int corpses = 0;
        bool rock_accessible = false;
        for( item &pit_item : here.i_at( p ) ) {
            corpses += pit_item.is_corpse();
            rock_accessible |= pit_item.typeId() == itype_id( "rock" );
        }
        CHECK( corpses == 5 );
        CHECK( rock_accessible );
    } else {
        CHECK( here.ter( p ) != ter_id( "t_pit_corpsed" ) );
    }
}

} // namespace

TEST_CASE( "corpses_fill_pits_after_five_standard_zombies", "[trap][pit][corpse]" )
{
    SECTION( "ordinary pit below 300 liters" ) {
        check_corpse_filled_pit( trapfunc::pit, ter_id( "t_pit" ), 4 );
    }
    SECTION( "ordinary pit above 300 liters" ) {
        check_corpse_filled_pit( trapfunc::pit, ter_id( "t_pit" ), 5 );
    }
    SECTION( "spiked pit above 300 liters" ) {
        check_corpse_filled_pit( trapfunc::pit_spikes, ter_id( "t_pit_spiked" ), 5 );
    }
    SECTION( "glass pit above 300 liters" ) {
        check_corpse_filled_pit( trapfunc::pit_glass, ter_id( "t_pit_glass" ), 5 );
    }
}

TEST_CASE( "corpse_filled_pit_can_be_dug_open", "[construction][pit][corpse]" )
{
    const construction &dig = construction_str_id( "constr_pit_from_corpsefilled" ).obj();
    CHECK( dig.time == to_moves<int>( 30_minutes ) );
    CHECK( dig.pre_terrain.count( "t_pit_corpsed" ) == 1 );
    CHECK( dig.post_terrain == "t_pit" );

    const auto &qualities = dig.requirements.obj().get_qualities();
    REQUIRE( qualities.size() == 1 );
    REQUIRE( qualities.front().size() == 1 );
    CHECK( qualities.front().front().type == quality_id( "DIG" ) );
    CHECK( qualities.front().front().level == 2 );

    clear_map_without_vision();
    map &here = get_map();
    const tripoint_bub_ms p = get_avatar().pos_bub() + tripoint::east;
    here.ter_set( p, ter_id( "t_pit_corpsed" ) );
    CHECK( can_construct( dig, p ) );

    here.add_item_or_charges( p, item::make_corpse( mtype_id( "mon_zombie" ) ) );
    here.add_item_or_charges( p, item( itype_id( "rock" ) ) );
    partial_con site;
    site.id = dig.id;
    here.partial_con_set( p, site );
    player_activity activity;
    build_construction_activity_actor actor( here.get_abs( p ) );
    actor.complete_construction( activity, get_avatar() );

    CHECK( here.ter( p ) == ter_id( "t_pit" ) );
    CHECK_FALSE( can_construct( dig, p ) );
    CHECK( here.i_at( p ).empty() );
    bool found_corpse = false;
    bool found_rock = false;
    for( const tripoint_bub_ms &adjacent : here.points_in_radius( p, 1 ) ) {
        if( adjacent == p ) {
            continue;
        }
        for( item &ground_item : here.i_at( adjacent ) ) {
            found_corpse |= ground_item.is_corpse();
            found_rock |= ground_item.typeId() == itype_id( "rock" );
        }
    }
    CHECK( found_corpse );
    CHECK( found_rock );
}
