#include <sstream>
#include <string>

#include "avatar.h"
#include "calendar.h"
#include "cata_catch.h"
#include "character.h"
#include "coordinates.h"
#include "field_type.h"
#include "flexbuffer_json.h"
#include "game.h"
#include "json.h"
#include "json_loader.h"
#include "map.h"
#include "map_helpers.h"
#include "map_helpers_tests.h"
#include "math_parser_diag_value.h"
#include "npc.h"
#include "player_helpers.h"
#include "type_id.h"

namespace
{
struct stamina_fixture {
    time_point previous_turn = calendar::turn;
    npc *actor;

    stamina_fixture() {
        clear_map();
        clear_avatar();
        set_time( calendar::turn_zero + 12_hours + 1_turns );
        actor = &spawn_npc( { 60, 60 }, "test_talker" );
        clear_character( *actor );
        actor->setpos( get_map(), tripoint_bub_ms( 60, 60, 0 ) );
        get_avatar().setpos( get_map(), tripoint_bub_ms( 58, 60, 0 ) );
        actor->set_fac( faction_id( "your_followers" ) );
        actor->set_attitude( NPCATT_FOLLOW );
        actor->set_value( "cph_ai.real_stamina", "true" );
        actor->set_stamina( actor->get_stamina_max() );
        actor->set_moves( 1000 );
    }

    ~stamina_fixture() {
        clear_npcs();
        set_time( previous_turn );
    }
};
} // namespace

TEST_CASE( "actor_control_stamina_reuses_finite_character_rules",
           "[actor_control][stamina]" )
{
    stamina_fixture fixture;
    npc &actor = *fixture.actor;
    REQUIRE( actor.uses_stamina() );
    REQUIRE( get_avatar().uses_stamina() );
    actor.set_stamina( 1000 );
    actor.mod_stamina( -125 );
    CHECK( actor.get_stamina() == 875 );

    SECTION( "ordinary_NPCs_keep_the_existing_unlimited_rule" ) {
        actor.remove_value( "cph_ai.real_stamina" );
        CHECK_FALSE( actor.uses_stamina() );
        CHECK( actor.get_stamina() == 10000 );
        actor.mod_stamina( -500 );
        actor.set_value( "cph_ai.real_stamina", "true" );
        CHECK( actor.get_stamina() == 875 );
    }
    SECTION( "fitness_changes_use_the_same_formula_as_the_avatar" ) {
        Character &player = get_avatar();
        actor.set_cardio_acc( 1400 );
        player.set_cardio_acc( 1400 );
        CHECK( actor.get_cardiofit() == player.get_cardiofit() );
        CHECK( actor.get_stamina_max() == player.get_stamina_max() );
        actor.set_cardio_acc( 1800 );
        CHECK( actor.get_stamina_max() > player.get_stamina_max() );
        CHECK( actor.get_stamina() == 875 );
    }
    SECTION( "minute_turn_does_not_grant_a_full_refill" ) {
        set_time( calendar::turn_zero + 12_hours + 1_minutes );
        actor.process_turn();
        CHECK( actor.get_stamina() == 875 );
    }
}

TEST_CASE( "actor_control_stamina_recovers_once_per_elapsed_turn",
           "[actor_control][stamina][regen]" )
{
    stamina_fixture fixture;
    npc &actor = *fixture.actor;
    actor.set_stamina( 1000 );
    actor.update_stamina( 1 );
    const int one_turn = actor.get_stamina() - 1000;
    REQUIRE( one_turn > 0 );
    actor.update_stamina( 3 );
    const int after_four_turns = actor.get_stamina();
    actor.set_stamina( 1000 );
    actor.set_moves( -25 );

    actor.npc_update_body();
    CHECK( actor.get_stamina() == 1000 );
    set_time( calendar::turn + 1_turns );
    actor.npc_update_body();
    CHECK( actor.get_stamina() == 1000 + one_turn );
    actor.npc_update_body();
    CHECK( actor.get_stamina() == 1000 + one_turn );
    set_time( calendar::turn + 3_turns );
    actor.npc_update_body();
    CHECK( actor.get_stamina() == after_four_turns );
    actor.update_body( calendar::turn - 2_turns, calendar::turn - 1_turns );
    actor.npc_update_body();
    CHECK( actor.get_stamina() == after_four_turns );
    CHECK( actor.get_moves() == -25 );
}

TEST_CASE( "actor_control_stamina_movement_debits_actual_moves",
           "[actor_control][stamina][move]" )
{
    stamina_fixture fixture;
    npc &actor = *fixture.actor;
    map &here = get_map();
    const tripoint_bub_ms origin = actor.pos_bub();
    tripoint_bub_ms destination = origin + tripoint( 1, 0, 0 );
    SECTION( "walking" ) {
        actor.set_movement_mode( move_mode_id( "walk" ) );
    }
    SECTION( "running" ) {
        actor.set_movement_mode( move_mode_id( "run" ) );
    }
    SECTION( "slower_terrain" ) {
        here.ter_set( destination, ter_id( "t_grass_long" ) );
    }
    SECTION( "vertical_step" ) {
        destination = origin + tripoint( 0, 0, 1 );
        here.ter_set( destination, ter_id( "t_floor" ) );
    }
    const int initial_stamina = actor.get_stamina();
    const int initial_moves = actor.get_moves();
    actor.move_to( destination, true );
    REQUIRE( actor.pos_bub() == destination );
    const int spent_moves = initial_moves - actor.get_moves();
    const int spent_stamina = initial_stamina - actor.get_stamina();
    REQUIRE( spent_moves > 0 );
    REQUIRE( spent_stamina > 0 );
    actor.setpos( here, origin );
    actor.set_stamina( initial_stamina );
    actor.burn_move_stamina( spent_moves );
    CHECK( actor.get_stamina() == initial_stamina - spent_stamina );
}

TEST_CASE( "actor_control_stamina_blocked_move_has_no_movement_debit",
           "[actor_control][stamina][move]" )
{
    stamina_fixture fixture;
    npc &actor = *fixture.actor;
    map &here = get_map();
    const tripoint_bub_ms origin = actor.pos_bub();
    const tripoint_bub_ms destination = origin + tripoint( 1, 0, 0 );
    SECTION( "wall" ) {
        here.ter_set( destination, ter_id( "t_wall" ) );
    }
    SECTION( "opening_a_door_is_not_a_step" ) {
        here.ter_set( destination, ter_id( "t_door_c" ) );
    }
    const int initial_stamina = actor.get_stamina();
    actor.move_to( destination, true );
    CHECK( actor.pos_bub() == origin );
    CHECK( actor.get_stamina() == initial_stamina );
}

TEST_CASE( "actor_control_stamina_exhausted_running_returns_to_walk",
           "[actor_control][stamina][move]" )
{
    stamina_fixture fixture;
    npc &actor = *fixture.actor;
    actor.set_stamina( 1 );
    actor.set_movement_mode( move_mode_id( "run" ) );
    const tripoint_bub_ms destination = actor.pos_bub() + tripoint( 1, 0, 0 );
    actor.move_to( destination, true );
    REQUIRE( actor.pos_bub() == destination );
    CHECK( actor.get_stamina() == 0 );
    CHECK( actor.is_walking() );
    CHECK_FALSE( actor.can_run() );
}

TEST_CASE( "actor_control_stamina_persists_and_load_catchup_is_not_replayed",
           "[actor_control][stamina][save]" )
{
    stamina_fixture fixture;
    npc &actor = *fixture.actor;
    actor.set_stamina( 1000 );
    // The fixture's debug nutrition records a synthetic uint64 component hash
    // outside this JSON reader's integer range; it is unrelated to stamina.
    actor.consumption_history.clear();
    std::ostringstream stream;
    JsonOut output( stream );
    actor.serialize( output );
    npc restored;
    restored.deserialize( json_loader::from_string( stream.str() ).get_object() );
    CHECK( restored.uses_stamina() );
    CHECK( restored.get_stamina() == 1000 );
    CHECK( restored.get_cardio_acc() == actor.get_cardio_acc() );

    actor.update_stamina( 1 );
    const int one_turn = actor.get_stamina() - 1000;
    actor.set_stamina( 1000 );
    set_time( calendar::turn + 3_turns );
    actor.on_load( &get_map() );
    CHECK( actor.get_stamina() == 1000 + 3 * one_turn );
    actor.on_load( &get_map() );
    actor.npc_update_body();
    CHECK( actor.get_stamina() == 1000 + 3 * one_turn );
}

TEST_CASE( "actor_control_stamina_rest_uses_only_existing_moves_and_yields_to_danger",
           "[actor_control][stamina]" )
{
    stamina_fixture fixture;
    npc &actor = *fixture.actor;
    actor.set_stamina( 1000 );
    REQUIRE( actor.get_stamina() < actor.get_stamina_max() / 4 );
    actor.set_moves( 100 );
    const tripoint_bub_ms origin = actor.pos_bub();
    SECTION( "safe_local_rest" ) {
        actor.move();
        CHECK( actor.pos_bub() == origin );
        CHECK( actor.get_moves() == 0 );
        CHECK( actor.get_stamina() == 1000 );
    }
    SECTION( "native_danger_response_precedes_rest" ) {
        REQUIRE( get_map().add_field( origin, field_type_id( "fd_fire" ), 1 ) );
        REQUIRE( actor.is_dangerous_fields( get_map().field_at( origin ) ) );
        actor.move();
        CHECK( actor.pos_bub() != origin );
        CHECK( actor.get_moves() < 100 );
    }
}

TEST_CASE( "actor_control_stamina_migrates_existing_companions_without_refill",
           "[actor_control][stamina][save]" )
{
    stamina_fixture fixture;
    npc &actor = *fixture.actor;
    actor.set_stamina( 1000 );
    actor.remove_value( "cph_ai.real_stamina" );
    actor.set_value( "cph_ai.bound", "true" );
    SECTION( "bound_companion" ) {
        actor.on_load( &get_map() );
        CHECK( actor.uses_stamina() );
        CHECK( actor.get_stamina() == 1000 );
    }
    SECTION( "proxy_is_not_opted_in" ) {
        actor.set_value( "mp_proxy", "true" );
        actor.on_load( &get_map() );
        CHECK( actor.get_value( "cph_ai.real_stamina" ) != "true" );
        CHECK_FALSE( actor.uses_stamina() );
    }
}
