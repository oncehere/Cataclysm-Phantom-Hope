#include "avatar.h"
#include "avatar_action.h"
#include "calendar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "coordinates.h"
#include "creature.h"
#include "creature_tracker.h"
#include "map.h"
#include "map_helpers.h"
#include "map_helpers_tests.h"
#include "monster.h"
#include "player_helpers.h"
#include "point.h"
#include "type_id.h"

static const efftype_id effect_berserk( "berserk" );
static const efftype_id effect_blind( "blind" );

TEST_CASE( "berserk_movement_checks_visible_hostiles", "[movement][berserk]" )
{
    restore_on_out_of_scope restore_turn( calendar::turn );
    set_time( calendar::turn_zero + 12_hours );
    clear_avatar();
    clear_map();
    avatar &you = get_avatar();
    map &here = get_map();
    const tripoint_bub_ms origin{ 60, 60, 0 };
    you.setpos( here, origin );
    you.add_effect( effect_berserk, 1_hours );
    monster &east = spawn_test_monster( "mon_zombie", origin + tripoint_rel_ms( 3, 0, 0 ) );
    here.build_map_cache( 0 );
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
        you.add_effect( effect_blind, 1_hours );
        REQUIRE_FALSE( you.sees( here, east ) );
        CHECK( avatar_action::move( you, here, tripoint_rel_ms::west ) );
        CHECK( you.pos_bub() == origin + tripoint_rel_ms::west );
    }
}
