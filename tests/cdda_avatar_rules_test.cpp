#include "avatar.h"
#include "avatar_action.h"
#include "calendar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "coordinates.h"
#include "creature.h"
#include "creature_tracker.h"
#include "game.h"
#include "map.h"
#include "map_helpers.h"
#include "map_helpers_tests.h"
#include "monster.h"
#include "player_helpers.h"
#include "point.h"
#include "type_id.h"

static const efftype_id effect_berserk( "berserk" );
static const ter_str_id ter_wall( "t_wall" );

TEST_CASE( "berserk_movement_checks_visible_hostiles", "[movement][berserk]" )
{
    const time_point original_time = calendar::turn;
    on_out_of_scope restore_time( [original_time]() {
        set_time( original_time );
    } );
    const safe_mode_type original_safe_mode = g->safe_mode;
    on_out_of_scope restore_safe_mode( [original_safe_mode]() {
        g->set_safe_mode( original_safe_mode );
    } );
    g->set_safe_mode( SAFE_MODE_OFF );
    clear_avatar();
    clear_map();
    set_time( calendar::turn_zero + 12_hours );
    avatar &you = get_avatar();
    map &here = get_map();
    const tripoint_bub_ms origin{ 60, 60, 0 };
    you.setpos( here, origin );
    you.add_effect( effect_berserk, 1_hours );
    monster &east = spawn_test_monster( "mon_zombie", origin + tripoint_rel_ms( 3, 0, 0 ) );
    here.invalidate_map_cache( 0 );
    here.build_map_cache( 0 );
    here.invalidate_visibility_cache();
    here.update_visibility_cache( 0 );
    get_creature_tracker().invalidate_reachability_cache();
    REQUIRE( east.attitude_to( you ) == Creature::Attitude::HOSTILE );
    REQUIRE( you.sees( here, east ) );

    SECTION( "a single hostile prevents moving away" ) {
        CHECK_FALSE( avatar_action::move( you, here, tripoint_rel_ms::west ) );
        CHECK( you.pos_bub() == origin );
        CHECK( avatar_action::move( you, here, tripoint_rel_ms::east ) );
        CHECK( you.pos_bub() == origin + tripoint_rel_ms::east );
    }
    SECTION( "approaching either of two opposite hostiles is allowed" ) {
        monster &west = spawn_test_monster( "mon_zombie", origin + tripoint_rel_ms( -3, 0, 0 ) );
        REQUIRE( west.attitude_to( you ) == Creature::Attitude::HOSTILE );
        REQUIRE( you.sees( here, west ) );
        get_creature_tracker().invalidate_reachability_cache();
        CHECK( avatar_action::move( you, here, tripoint_rel_ms::west ) );
        CHECK( you.pos_bub() == origin + tripoint_rel_ms::west );
    }
    SECTION( "an unseen hostile does not prevent retreat" ) {
        here.ter_set( origin + tripoint_rel_ms::east, ter_wall );
        here.invalidate_map_cache( 0 );
        here.build_map_cache( 0 );
        here.invalidate_visibility_cache();
        here.update_visibility_cache( 0 );
        get_creature_tracker().invalidate_reachability_cache();
        REQUIRE_FALSE( you.sees( here, east ) );
        CHECK( avatar_action::move( you, here, tripoint_rel_ms::west ) );
        CHECK( you.pos_bub() == origin + tripoint_rel_ms::west );
    }
}
