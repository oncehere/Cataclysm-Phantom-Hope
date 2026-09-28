#include "avatar.h"
#include "cata_catch.h"
#include "creature.h"
#include "game.h"
#include "map.h"
#include "map_helpers.h"
#include "map_helpers_tests.h"
#include "monster.h"
#include "npc.h"
#include "player_helpers.h"
#include "point.h"
#include "trap.h"
#include "type_id.h"

namespace
{

using pit_trigger = bool ( * )( const tripoint_bub_ms &, Creature *, item * );

void check_pit_riders( pit_trigger trigger, const ter_id &terrain )
{
    clear_npcs();
    clear_creatures();
    clear_avatar();
    clear_map_without_vision();

    map &here = get_map();
    avatar &player = get_avatar();
    monster &player_mount = spawn_test_monster( "mon_horse_police",
        player.pos_bub() + tripoint::east );
    player_mount.friendly = -1;
    player.mount_creature( player_mount );
    REQUIRE( player.is_mounted() );
    REQUIRE( player_mount.mounted_player == &player );

    npc &other_rider = spawn_npc( player.pos_bub().xy() + point( 4, 0 ), "test_talker" );
    monster &other_mount = spawn_test_monster( "mon_horse_police",
        other_rider.pos_bub() + tripoint::east );
    other_mount.friendly = -1;
    other_rider.mount_creature( other_mount );
    REQUIRE( other_rider.is_mounted() );
    REQUIRE( other_mount.mounted_player == &other_rider );

    here.ter_set( other_mount.pos_bub(), terrain );
    REQUIRE( trigger( other_mount.pos_bub(), &other_mount, nullptr ) );
    CHECK( player.is_mounted() );
    CHECK( player_mount.mounted_player == &player );

    here.ter_set( player_mount.pos_bub(), terrain );
    REQUIRE( trigger( player_mount.pos_bub(), &player_mount, nullptr ) );
    CHECK_FALSE( player.is_mounted() );
    CHECK( player_mount.mounted_player == nullptr );

    if( other_rider.is_mounted() ) {
        other_rider.forced_dismount();
    }
}

} // namespace

TEST_CASE( "pit_traps_only_dismount_their_player_rider", "[trap][mount]" )
{
    SECTION( "ordinary pit" ) {
        check_pit_riders( trapfunc::pit, ter_id( "t_pit" ) );
    }
    SECTION( "spiked pit" ) {
        check_pit_riders( trapfunc::pit_spikes, ter_id( "t_pit_spiked" ) );
    }
    SECTION( "glass pit" ) {
        check_pit_riders( trapfunc::pit_glass, ter_id( "t_pit_glass" ) );
    }
}
