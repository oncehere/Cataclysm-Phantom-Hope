#include <algorithm>
#include <sstream>
#include <string>
#include <vector>

#include "actor_control_types.h"
#include "avatar.h"
#include "calendar.h"
#include "cata_catch.h"
#include "character_attire.h"
#include "character_id.h"
#include "coordinates.h"
#include "effect.h"
#include "flexbuffer_json.h"
#include "game.h"
#include "inventory.h"
#include "item.h"
#include "item_location.h"
#include "json.h"
#include "json_loader.h"
#include "map.h"
#include "map_helpers.h"
#include "map_helpers_tests.h"
#include "math_parser_diag_value.h"
#include "mission.h"
#include "npc.h"
#include "npc_execution_adapter.h"
#include "player_activity.h"
#include "player_helpers.h"
#include "recipe.h"
#include "recipe_dictionary.h"
#include "type_id.h"

namespace
{
using cata::actor_control::action_step;
using cata::actor_control::execution_result;
using cata::actor_control::execution_state;
using cata::actor_control::NpcExecutionAdapter;

struct native_fixture {
    time_point previous_turn = calendar::turn;
    npc *actor;
    npc *other;

    native_fixture() {
        mission::clear_all();
        clear_map();
        clear_avatar();
        set_time( calendar::turn_zero + 12_hours );
        map &here = get_map();
        get_avatar().setpos( here, tripoint_bub_ms( 59, 60, 0 ) );
        get_avatar().worn.wear_item( get_avatar(), item( itype_id( "debug_backpack" ) ), false, false );
        actor = &spawn_npc( { 60, 60 }, "test_talker" );
        clear_character( *actor, true );
        actor->setpos( here, tripoint_bub_ms( 60, 60, 0 ) );
        actor->set_fac( faction_id( "your_followers" ) );
        actor->set_attitude( NPCATT_FOLLOW );
        actor->worn.wear_item( *actor, item( itype_id( "debug_backpack" ) ), false, false );
        actor->set_moves( 1000 );
        actor->recalc_sight_limits();
        other = &spawn_npc( { 61, 60 }, "test_talker" );
        clear_character( *other, true );
        other->setpos( here, tripoint_bub_ms( 61, 60, 0 ) );
        other->set_fac( faction_id( "free_merchants" ) );
        other->set_attitude( NPCATT_NULL );
        other->worn.wear_item( *other, item( itype_id( "debug_backpack" ) ), false, false );
        other->recalc_sight_limits();
        // Spawning a doctor can drop its generated stock before we clear the
        // character.  Only items explicitly placed by a scenario belong here.
        clear_items( 0 );
    }

    ~native_fixture() {
        mission::clear_all();
        clear_npcs();
        set_time( previous_turn );
    }

    execution_result act( const std::string &action, const std::string &args,
                          const std::string &id = "native-test-step",
                          const std::string &source_operation = {} ) {
        return NpcExecutionAdapter::execute( *actor, { id, action, args, {}, source_operation } );
    }

    std::string position( const tripoint_bub_ms &pos, const std::string &extra = "" ) const {
        const tripoint_abs_ms absolute = get_map().get_abs( pos );
        return "{\"x\":" + std::to_string( absolute.x() ) + ",\"y\":" +
               std::to_string( absolute.y() ) + ",\"z\":" + std::to_string( absolute.z() ) +
               extra + "}";
    }

    std::string speech( const std::string &text = "A character's own decision." ) const {
        return "{\"target\":" + std::to_string( get_avatar().getID().get_value() ) +
               ",\"text\":\"" + text + "\"}";
    }

    mission *offer() {
        mission *task = mission::reserve_new( mission_type_id( "MISSION_GET_ANTIBIOTICS" ),
                                              other->getID() );
        REQUIRE( task );
        other->chatbin.missions.push_back( task );
        return task;
    }
};

std::string stored( const npc &actor, const std::string &key )
{
    const diag_value *v = actor.maybe_get_value( "cph_ai." + key );
    return v ? v->to_string() : std::string();
}

int amount( const Character &actor, const char *id )
{
    const itype_id type( id );
    return item::count_by_charges( type ) ? actor.charges_of( type ) : actor.amount_of( type );
}

void add_owned( Character &actor, const char *id, int count = 1,
                const std::string &source_operation = {} )
{
    item added( itype_id( id ), calendar::turn );
    added.set_owner( actor );
    if( added.count_by_charges() ) {
        added.charges = count;
    }
    if( !source_operation.empty() ) {
        added.set_var( "cph_ai_produced_step", source_operation );
    }
    actor.i_add( std::move( added ) );
}

int sourced_amount( Character &actor, const char *id, const std::string &source_operation )
{
    int count = 0;
    for( const item_location &location : actor.all_items_loc() ) {
        if( location->typeId() == itype_id( id ) &&
            location->get_var( "cph_ai_produced_step", "" ) == source_operation ) {
            count += location->count_by_charges() ? location->charges : 1;
        }
    }
    return count;
}

JsonObject inspected_object( JsonObject object )
{
    // These assertions inspect selected fields of a complete native snapshot.
    object.allow_omitted_members();
    return object;
}

std::string ground_contents( const tripoint_bub_ms &pos )
{
    std::ostringstream serialized;
    JsonOut out( serialized );
    out.start_array();
    for( const item &on_ground : get_map().i_at( pos ) ) {
        on_ground.serialize( out );
    }
    out.end_array();
    return serialized.str();
}

} // namespace

TEST_CASE( "npc_actor_native_gather_uses_actual_stock_and_moves", "[actor_control][native]" )
{
    native_fixture f;
    const tripoint_bub_ms pos( 60, 61, 0 );
    item rock( itype_id( "rock" ), calendar::turn );
    rock.set_owner( *f.actor );
    get_map().add_item_or_charges( pos, rock );
    const int before = f.actor->get_moves();
    const std::string args = f.position( pos, ",\"item_type\":\"rock\",\"count\":1" );
    CHECK( f.act( "gather", args ).state == execution_state::succeeded );
    CHECK( amount( *f.actor, "rock" ) == 1 );
    CHECK( get_map().i_at( pos ).empty() );
    CHECK( f.actor->get_moves() < before );
    const int after_pickup = f.actor->get_moves();
    CHECK( f.act( "gather", args, "another-step" ).code == "gather_target_not_observed" );
    CHECK( f.actor->get_moves() == after_pickup );
    CHECK( amount( *f.actor, "rock" ) == 1 );
}

TEST_CASE( "npc_actor_gather_dependency_selects_only_actual_source_output",
           "[actor_control][native][dependency]" )
{
    native_fixture f;
    const tripoint_bub_ms pos( 60, 61, 0 );
    for( const char *source : {
             "other-craft", "required-craft"
         } ) {
        item rock( itype_id( "rock" ), calendar::turn );
        rock.set_owner( *f.actor );
        rock.set_var( "cph_ai_produced_step", source );
        get_map().add_item_or_charges( pos, rock );
    }
    const std::string args = f.position( pos, ",\"item_type\":\"rock\",\"count\":1" );
    SECTION( "same type from another operation cannot substitute" ) {
        const execution_result gathered = f.act( "gather", args, "required-gather", "required-craft" );
        REQUIRE( gathered.state == execution_state::succeeded );
        CHECK( amount( *f.actor, "rock" ) == 1 );
        CHECK( sourced_amount( *f.actor, "rock", "required-gather" ) == 1 );
        REQUIRE( get_map().i_at( pos ).size() == 1 );
        CHECK( get_map().i_at( pos ).begin()->get_var( "cph_ai_produced_step", "" ) == "other-craft" );
        const JsonObject detail = inspected_object( json_loader::from_string( gathered.detail_json ) );
        const JsonArray produced = detail.get_array( "produced" );
        REQUIRE( produced.size() == 1 );
        const JsonObject output = inspected_object( produced.get_object( 0 ) );
        CHECK( output.get_string( "item_type" ) == "rock" );
        CHECK( output.get_int( "count" ) == 1 );
        CHECK( output.get_string( "location" ) == "actor" );
    }
    SECTION( "missing output neither consumes moves nor takes equivalent stock" ) {
        const int before = f.actor->get_moves();
        CHECK( f.act( "gather", args, "missing-gather",
                      "absent-craft" ).code == "source_output_unavailable" );
        CHECK( f.actor->get_moves() == before );
        CHECK( amount( *f.actor, "rock" ) == 0 );
        CHECK( get_map().i_at( pos ).size() == 2 );
    }
}

TEST_CASE( "npc_actor_observation_is_limited_to_own_senses", "[actor_control][native]" )
{
    native_fixture f;
    add_owned( *f.other, "panacea" );
    mission *task = f.offer();
    const JsonObject observation = inspected_object( json_loader::from_string(
                                       NpcExecutionAdapter::observe( *f.actor ) ) );
    const JsonObject actor_state = inspected_object( observation.get_object( "actor" ) );
    const JsonObject nearby = inspected_object( observation.get_object( "nearby" ) );
    CHECK( actor_state.get_array( "inventory" ).size() <= 128 );
    CHECK( actor_state.get_array( "skills" ).size() <= 128 );
    CHECK( actor_state.get_array( "body" ).size() <= 128 );
    CHECK( actor_state.get_int( "hp" ) == f.actor->get_hp() );
    CHECK( actor_state.get_int( "stamina" ) == f.actor->get_stamina() );
    CHECK( nearby.get_array( "characters" ).size() <= 32 );
    CHECK( nearby.get_array( "monsters" ).size() <= 64 );
    CHECK( nearby.get_array( "items" ).size() <= 128 );
    CHECK( actor_state.get_array( "known_recipes" ).size() <= 128 );
    CHECK( actor_state.get_array( "craftable_recipes" ).size() <= 128 );
    CHECK_FALSE( NpcExecutionAdapter::available( *f.actor, "accept_mission" ) );
    CHECK( NpcExecutionAdapter::observe( *f.actor ).find( "panacea" ) == std::string::npos );
    CHECK( NpcExecutionAdapter::observe( *f.actor ).find( "MISSION_GET_ANTIBIOTICS" ) ==
           std::string::npos );
    const std::string target = std::to_string( f.other->getID().get_value() );
    CHECK( f.act( "talk", "{\"target\":" + target +
                  ",\"topic\":\"TALK_MISSION_OFFER\",\"option\":\"ask\"}" ).state ==
           execution_state::succeeded );
    CHECK( NpcExecutionAdapter::observe( *f.actor ).find( "MISSION_GET_ANTIBIOTICS" ) !=
           std::string::npos );
    CHECK( stored( *f.actor, "heard_mission." + std::to_string( task->get_id() ) ) == target );
    CHECK( NpcExecutionAdapter::available( *f.actor, "accept_mission" ) );
    f.actor->add_effect( efftype_id( "blind" ), 1_hours );
    REQUIRE( f.actor->is_blind() );
    f.actor->recalc_sight_limits();
    const JsonObject blind = inspected_object( json_loader::from_string(
                                 NpcExecutionAdapter::observe( *f.actor ) ) );
    const JsonObject blind_nearby = inspected_object( blind.get_object( "nearby" ) );
    CHECK( blind_nearby.get_array( "characters" ).empty() );
    CHECK( blind_nearby.get_array( "items" ).empty() );
    CHECK_FALSE( NpcExecutionAdapter::available( *f.actor, "attack_player" ) );
    const int moves = f.actor->get_moves();
    const int player_hp = get_avatar().get_hp();
    CHECK( f.act( "attack_player", "{\"target\":" +
                  std::to_string( get_avatar().getID().get_value() ) + "}" ).state ==
           execution_state::failed );
    CHECK( f.actor->get_moves() == moves );
    CHECK( get_avatar().get_hp() == player_hp );
}

TEST_CASE( "npc_actor_craft_completion_is_native_and_interruption_does_not_award_output",
           "[actor_control][native][crafting]" )
{
    native_fixture f;
    const recipe_id id( "bandages_makeshift" );
    REQUIRE( id.is_valid() );
    f.actor->learn_recipe( &id.obj() );
    add_owned( *f.actor, "sheet_cotton" );
    const int player_moves = get_avatar().get_moves();
    REQUIRE( NpcExecutionAdapter::available( *f.actor, "craft" ) );
    REQUIRE( f.act( "craft", "{\"recipe\":\"bandages_makeshift\"}", "craft-one" ).state ==
             execution_state::running );
    REQUIRE( f.actor->activity );
    CHECK_FALSE( NpcExecutionAdapter::available( *f.actor, "craft" ) );
    CHECK( amount( *f.actor, "sheet_cotton" ) == 0 );
    CHECK( amount( *f.actor, "bandages_makeshift" ) == 0 );
    SECTION( "native activity finishes" ) {
        process_activity( *f.actor );
        const execution_result finished = f.act( "craft", "{\"recipe\":\"bandages_makeshift\"}",
                                          "craft-one" );
        INFO( finished.code );
        CHECK( finished.state == execution_state::succeeded );
        CHECK( amount( *f.actor, "bandages_makeshift" ) == 2 );
        CHECK( finished.detail_json.find( "bandages_makeshift" ) != std::string::npos );
    }
    SECTION( "cancel leaves actual in-progress craft" ) {
        f.actor->cancel_activity();
        const execution_result cancelled = f.act( "craft", "{\"recipe\":\"bandages_makeshift\"}",
                                           "craft-one" );
        CHECK( cancelled.state == execution_state::failed );
        CHECK( cancelled.code == "craft_interrupted" );
        CHECK( amount( *f.actor, "bandages_makeshift" ) == 0 );
    }
    CHECK( get_avatar().get_moves() == player_moves );
}

TEST_CASE( "npc_actor_player_trade_requires_review_and_deduplicates_real_exchange",
           "[actor_control][native][trade]" )
{
    native_fixture f;
    get_avatar().worn.wear_item( get_avatar(), item( itype_id( "debug_backpack" ) ), false, false );
    add_owned( *f.actor, "rock" );
    add_owned( get_avatar(), "2x4" );
    const std::string args = "{\"target\":" + std::to_string( get_avatar().getID().get_value() ) +
                             ",\"give\":[{\"item_type\":\"rock\"}],\"take\":[{\"item_type\":\"2x4\"}]}";
    REQUIRE( f.act( "trade", args, "exchange-one" ).code == "awaiting_player_trade_confirmation" );
    CHECK( amount( *f.actor, "rock" ) == 1 );
    CHECK( amount( get_avatar(), "2x4" ) == 1 );
    REQUIRE( NpcExecutionAdapter::resolve_player_trade( *f.actor,
             true ).state == execution_state::succeeded );
    CHECK( amount( *f.actor, "rock" ) == 0 );
    CHECK( amount( get_avatar(), "rock" ) == 1 );
    CHECK( amount( *f.actor, "2x4" ) == 1 );
    CHECK( f.act( "trade", args, "exchange-one" ).code == "trade_already_committed" );
    CHECK( amount( *f.actor, "2x4" ) == 1 );
}

TEST_CASE( "npc_actor_player_confirmation_preserves_output_dependency",
           "[actor_control][native][trade][dependency]" )
{
    native_fixture f;
    add_owned( *f.actor, "rock", 1, "wrong-craft" );
    add_owned( *f.actor, "rock", 1, "required-craft" );
    add_owned( get_avatar(), "2x4" );
    const std::string args = "{\"target\":" + std::to_string( get_avatar().getID().get_value() ) +
                             ",\"give\":[{\"item_type\":\"rock\"}],\"take\":[{\"item_type\":\"2x4\"}]}";
    REQUIRE( f.act( "trade", args, "source-exchange",
                    "required-craft" ).state == execution_state::running );
    CHECK( stored( *f.actor, "pending_trade_source_operation" ) == "required-craft" );
    SECTION( "human confirmation exchanges the required source and tags real output" ) {
        const execution_result exchanged = NpcExecutionAdapter::resolve_player_trade( *f.actor, true );
        REQUIRE( exchanged.state == execution_state::succeeded );
        CHECK( sourced_amount( *f.actor, "rock", "wrong-craft" ) == 1 );
        CHECK( sourced_amount( *f.actor, "rock", "required-craft" ) == 0 );
        CHECK( sourced_amount( get_avatar(), "rock", "required-craft" ) == 1 );
        CHECK( sourced_amount( *f.actor, "2x4", "source-exchange" ) == 1 );
        CHECK( stored( *f.actor, "pending_trade_source_operation" ).empty() );
        const JsonObject detail = inspected_object( json_loader::from_string( exchanged.detail_json ) );
        const JsonArray produced = detail.get_array( "produced" );
        REQUIRE( produced.size() == 1 );
        const JsonObject output = inspected_object( produced.get_object( 0 ) );
        CHECK( output.get_string( "item_type" ) == "2x4" );
        CHECK( output.get_int( "count" ) == 1 );
        CHECK( f.act( "trade", args, "source-exchange",
                      "required-craft" ).detail_json == exchanged.detail_json );
        CHECK( f.act( "trade", args, "source-exchange", "wrong-craft" ).code == "receipt_conflict" );
    }
    SECTION( "consuming required stock before confirmation cannot consume other stock" ) {
        for( item_location loc : f.actor->all_items_loc() ) {
            if( loc->typeId() == itype_id( "rock" ) &&
                loc->get_var( "cph_ai_produced_step", "" ) == "required-craft" ) {
                loc.remove_item();
                break;
            }
        }
        const int before = f.actor->get_moves();
        CHECK( NpcExecutionAdapter::resolve_player_trade( *f.actor,
                true ).code == "source_output_unavailable" );
        CHECK( f.actor->get_moves() == before );
        CHECK( sourced_amount( *f.actor, "rock", "wrong-craft" ) == 1 );
        CHECK( amount( get_avatar(), "rock" ) == 0 );
        CHECK( amount( get_avatar(), "2x4" ) == 1 );
        CHECK( amount( *f.actor, "2x4" ) == 0 );
    }
}

TEST_CASE( "npc_actor_social_speech_and_goal_behaviors_have_effects",
           "[actor_control][native][social]" )
{
    native_fixture f;
    const std::string action = GENERATE( "refuse", "argue", "lie_in_dialogue", "propose_own_goals",
                                         "false_promise" );
    const int before = f.actor->get_moves();
    const int player_moves = get_avatar().get_moves();
    const std::string native_goal = f.actor->get_committed_goal();
    REQUIRE( f.act( action, f.speech() ).state == execution_state::succeeded );
    CHECK( f.actor->get_moves() == before - 100 );
    CHECK( get_avatar().get_moves() == player_moves );
    CHECK( stored( *f.actor, "last_social_action" ) == action );
    if( action == "propose_own_goals" ) {
        CHECK( stored( *f.actor, "goal" ) == "A character's own decision." );
        CHECK( stored( *f.actor, "goal_state" ) == "proposed" );
        CHECK( f.actor->get_committed_goal() == native_goal );
    }
    if( action == "false_promise" ) {
        CHECK( stored( *f.actor, "commitment_state" ) == "false_promise" );
        REQUIRE( f.act( "break_commitment", f.speech() ).state == execution_state::succeeded );
        CHECK( stored( *f.actor, "commitment_state" ) == "broken" );
        CHECK( f.act( "break_commitment", f.speech() ).state == execution_state::failed );
    }
}

TEST_CASE( "npc_actor_social_information_requires_exact_known_record",
           "[actor_control][native][social]" )
{
    native_fixture f;
    f.actor->set_value( "cph_ai.known_information",
                        R"([{"id":"known-1","kind":"statement","text":"The bridge is broken."}])" );
    const std::string action = GENERATE( "conceal_information", "disclose_known_information" );
    CHECK( f.act( action, f.speech( "bridge" ) ).code == "information_not_known" );
    REQUIRE( f.act( action, f.speech( "The bridge is broken." ) ).state == execution_state::succeeded );
    if( action == "conceal_information" ) {
        CHECK( stored( *f.actor, "concealed_information" ) == "The bridge is broken." );
    } else {
        CHECK( stored( *f.actor, "last_social_action" ) == "known_information_disclosed" );
    }
}

TEST_CASE( "npc_actor_fraud_is_a_real_reviewed_offer", "[actor_control][native][social]" )
{
    native_fixture f;
    add_owned( *f.actor, "rock" );
    const std::string args = "{\"target\":" + std::to_string( get_avatar().getID().get_value() ) +
                             ",\"text\":\"This rock is valuable medicine.\",\"give\":[{\"item_type\":\"rock\"}],\"take\":[]}";
    REQUIRE( f.act( "transaction_fraud", args, "fraud-one" ).state == execution_state::running );
    CHECK( amount( *f.actor, "rock" ) == 1 );
    CHECK( stored( *f.actor, "last_social_action" ) == "transaction_fraud_offer" );
    CHECK( NpcExecutionAdapter::resolve_player_trade( *f.actor,
            false ).code == "player_declined_trade" );
    CHECK( f.act( "transaction_fraud", args, "fraud-one" ).state == execution_state::failed );
    CHECK( amount( *f.actor, "rock" ) == 1 );
}

TEST_CASE( "npc_actor_social_aid_theft_leave_and_sabotage_mutate_native_world",
           "[actor_control][native][social]" )
{
    native_fixture f;
    SECTION( "aid a party hostile to the player" ) {
        f.other->set_attitude( NPCATT_KILL );
        add_owned( *f.actor, "rock" );
        const std::string args = "{\"target\":" + std::to_string( f.other->getID().get_value() ) +
                                 ",\"item_type\":\"rock\"}";
        REQUIRE( f.act( "aid_conflicting_party", args ).state == execution_state::succeeded );
        CHECK( amount( *f.actor, "rock" ) == 0 );
        CHECK( amount( *f.other, "rock" ) == 1 );
    }
    SECTION( "misappropriate another faction's observed ground item" ) {
        const tripoint_bub_ms pos( 60, 61, 0 );
        item rock( itype_id( "rock" ), calendar::turn );
        rock.set_owner( *f.other );
        get_map().add_item_or_charges( pos, rock );
        const std::string args = f.position( pos, ",\"item_type\":\"rock\"" );
        CHECK( f.act( "gather", args ).state == execution_state::failed );
        REQUIRE( f.act( "misappropriate_items", args ).state == execution_state::succeeded );
        CHECK( amount( *f.actor, "rock" ) == 1 );
        CHECK( get_map().i_at( pos ).empty() );
    }
    SECTION( "leave the real player faction" ) {
        REQUIRE( f.actor->is_player_ally() );
        REQUIRE( f.act( "leave_group", "{}" ).state == execution_state::succeeded );
        CHECK_FALSE( f.actor->is_player_ally() );
        CHECK_FALSE( NpcExecutionAdapter::available( *f.actor, "leave_group" ) );
    }
    SECTION( "bash an observed native door" ) {
        const tripoint_bub_ms pos( 60, 61, 0 );
        get_map().ter_set( pos, ter_str_id( "t_door_c" ) );
        f.actor->set_str_base( 20 );
        const int damage_before = get_map().get_map_damage( pos );
        const int before = f.actor->get_moves();
        REQUIRE( f.act( "sabotage", f.position( pos ) ).state == execution_state::succeeded );
        CHECK( f.actor->get_moves() == before - 100 );
        CHECK( get_map().get_map_damage( pos ) > damage_before );
        // A native bash accumulates damage; success records an attempt, rather
        // than forcing a door to disappear on the first hit.
        for( int attempt = 1; attempt < 32 &&
             get_map().ter( pos ) == ter_str_id( "t_door_c" ).id(); ++attempt ) {
            f.actor->set_moves( 100 );
            REQUIRE( f.act( "sabotage", f.position( pos ),
                            "bash-" + std::to_string( attempt ) ).code == "native_sabotage_attempt" );
            CHECK( f.actor->get_moves() == 0 );
        }
        CHECK( get_map().ter( pos ) != ter_str_id( "t_door_c" ).id() );
    }
}

TEST_CASE( "npc_actor_social_attacks_use_native_combat_and_target_constraints",
           "[actor_control][native][social][combat]" )
{
    native_fixture f;
    const std::string action = GENERATE( "attack_player", "attack_allies" );
    Character *target = &get_avatar();
    if( action == "attack_allies" ) {
        f.other->set_fac( faction_id( "your_followers" ) );
        f.other->set_attitude( NPCATT_FOLLOW );
        target = f.other;
    }
    const std::string args = "{\"target\":" + std::to_string( target->getID().get_value() ) + "}";
    const int before = f.actor->get_moves();
    REQUIRE( f.act( action, args ).code == "native_attack" );
    CHECK( f.actor->get_moves() < before );
    const std::string mismatch = "{\"target\":" + std::to_string( f.other->getID().get_value() ) + "}";
    if( action == "attack_player" ) {
        CHECK( f.act( action, mismatch ).code == "social_attack_target_mismatch" );
    }
}

TEST_CASE( "npc_assigned_antibiotics_task_consumes_only_claimant_medicine_and_preserves_reward",
           "[actor_control][native][mission]" )
{
    native_fixture f;
    const char *medicine = GENERATE( "antibiotics", "strong_antibiotic", "panacea" );
    mission *task = f.offer();
    add_owned( get_avatar(), medicine );
    const int player_debt = f.other->op_of_u.owed;
    REQUIRE( task->assign( *f.actor ) );
    CHECK( task->get_assigned_npc_id() == f.actor->getID() );
    CHECK_FALSE( task->get_assigned_player_id().is_valid() );
    REQUIRE( f.other->has_effect( efftype_id( "infection" ) ) );
    CHECK_FALSE( task->wrap_up( *f.actor ) );
    add_owned( *f.actor, medicine );
    REQUIRE( task->wrap_up( *f.actor ) );
    CHECK( amount( *f.actor, medicine ) == 0 );
    CHECK( amount( get_avatar(), medicine ) == 1 );
    CHECK_FALSE( f.other->has_effect( efftype_id( "infection" ) ) );
    CHECK( task->npc_reward_remaining() == task->get_value() );
    CHECK( f.other->op_of_u.owed == player_debt );
    std::string error;
    const int credit_before = task->npc_reward_remaining();
    const std::string reward_receipt = std::string( 32, 'a' ) + "." + std::string( 128, 'b' );
    CHECK_FALSE( task->claim_npc_reward( *f.actor, itype_id( "rock" ), 1, reward_receipt, error ) );
    CHECK( error == "reward_stock_shortage" );
    CHECK( task->npc_reward_remaining() == credit_before );
    add_owned( *f.other, "rock" );
    REQUIRE( task->claim_npc_reward( *f.actor, itype_id( "rock" ), 1, reward_receipt, error ) );
    CHECK( amount( *f.actor, "rock" ) == 1 );
    CHECK( amount( *f.other, "rock" ) == 0 );
    CHECK( task->npc_reward_remaining() < credit_before );
    const int remaining = task->npc_reward_remaining();
    REQUIRE( task->claim_npc_reward( *f.actor, itype_id( "rock" ), 1, reward_receipt, error ) );
    CHECK( amount( *f.actor, "rock" ) == 1 );
    CHECK( task->npc_reward_remaining() == remaining );
    CHECK_FALSE( task->claim_npc_reward( *f.actor, itype_id( "rock" ), 2, reward_receipt, error ) );
    CHECK( error == "receipt_conflict" );
    CHECK( NpcExecutionAdapter::has_native_management( *f.actor ) );
    std::ostringstream data;
    JsonOut out( data );
    task->serialize( out );
    mission restored;
    restored.deserialize( json_loader::from_string( data.str() ) );
    CHECK( restored.get_assigned_npc_id() == f.actor->getID() );
    CHECK( restored.npc_reward_remaining() == remaining );
    REQUIRE( restored.claim_npc_reward( *f.actor, itype_id( "rock" ), 1, reward_receipt, error ) );
    CHECK( amount( *f.actor, "rock" ) == 1 );
    CHECK( f.other->op_of_u.owed == player_debt );
}

TEST_CASE( "npc_assigned_task_deadline_failure_retains_claimant_and_never_uses_player_inventory",
           "[actor_control][native][mission]" )
{
    native_fixture f;
    mission *task = f.offer();
    REQUIRE( task->assign( *f.actor ) );
    add_owned( *f.actor, "antibiotics" );
    task->set_deadline( calendar::turn - 1_turns );
    task->process();
    CHECK( task->get_status() == mission::mission_status::failure );
    CHECK( task->get_assigned_npc_id() == f.actor->getID() );
    CHECK_FALSE( task->get_assigned_player_id().is_valid() );
    CHECK( task->npc_reward_remaining() == 0 );
    CHECK_FALSE( task->wrap_up( *f.actor ) );
    CHECK( amount( *f.actor, "antibiotics" ) == 1 );
}

TEST_CASE( "npc_actor_npc_dialogue_and_trade_use_real_stock_and_options",
           "[actor_control][native][trade][dialogue]" )
{
    native_fixture f;
    // Ally trade consent is native and allows these deliberately simple test goods.
    f.other->set_fac( faction_id( "your_followers" ) );
    f.other->set_attitude( NPCATT_FOLLOW );
    add_owned( *f.actor, "2x4" );
    add_owned( *f.other, "rock" );
    const std::string target = std::to_string( f.other->getID().get_value() );
    CHECK( f.act( "talk", "{\"target\":" + target +
                  ",\"topic\":\"TALK_TRADE\",\"option\":\"invented-effect\"}" ).code ==
           "native_option_unavailable" );
    REQUIRE( f.act( "talk", "{\"target\":" + target +
                    ",\"topic\":\"TALK_TRADE\",\"option\":\"ask\"}" ).state == execution_state::succeeded );
    CHECK( stored( *f.actor, "heard_trade." + target ) == "true" );
    CHECK( NpcExecutionAdapter::observe( *f.actor ).find( "trade_offers" ) != std::string::npos );
    const int player_debt = f.other->op_of_u.owed;
    const std::string args = "{\"target\":" + target +
                             ",\"give\":[{\"item_type\":\"2x4\"}],\"take\":[{\"item_type\":\"rock\"}]}";
    REQUIRE( f.act( "trade", args, "npc-exchange" ).state == execution_state::succeeded );
    CHECK( amount( *f.actor, "rock" ) == 1 );
    CHECK( amount( *f.actor, "2x4" ) == 0 );
    CHECK( amount( *f.other, "rock" ) == 0 );
    CHECK( amount( *f.other, "2x4" ) == 1 );
    CHECK( f.other->op_of_u.owed == player_debt );
    CHECK( f.act( "trade", args, "npc-exchange" ).code == "trade_already_committed" );
    CHECK( amount( *f.actor, "rock" ) == 1 );
}

TEST_CASE( "npc_actor_npc_trade_uses_required_output_and_receipts_real_received_stock",
           "[actor_control][native][trade][dependency]" )
{
    native_fixture f;
    f.other->set_fac( faction_id( "your_followers" ) );
    f.other->set_attitude( NPCATT_FOLLOW );
    add_owned( *f.actor, "2x4", 1, "other-output" );
    add_owned( *f.actor, "2x4", 1, "required-output" );
    add_owned( *f.other, "rock" );
    const std::string target = std::to_string( f.other->getID().get_value() );
    REQUIRE( f.act( "talk", "{\"target\":" + target +
                    ",\"topic\":\"TALK_TRADE\",\"option\":\"ask\"}" ).state == execution_state::succeeded );
    const std::string args = "{\"target\":" + target +
                             ",\"give\":[{\"item_type\":\"2x4\"}],\"take\":[{\"item_type\":\"rock\"}]}";
    const execution_result exchanged = f.act( "trade", args, "dependent-trade", "required-output" );
    REQUIRE( exchanged.state == execution_state::succeeded );
    CHECK( sourced_amount( *f.actor, "2x4", "other-output" ) == 1 );
    CHECK( sourced_amount( *f.actor, "2x4", "required-output" ) == 0 );
    CHECK( sourced_amount( *f.other, "2x4", "required-output" ) == 1 );
    CHECK( sourced_amount( *f.actor, "rock", "dependent-trade" ) == 1 );
    const JsonObject detail = inspected_object( json_loader::from_string( exchanged.detail_json ) );
    const JsonArray produced = detail.get_array( "produced" );
    REQUIRE( produced.size() == 1 );
    const JsonObject output = inspected_object( produced.get_object( 0 ) );
    CHECK( output.get_string( "item_type" ) == "rock" );
    CHECK( output.get_int( "count" ) == 1 );
    const int before = f.actor->get_moves();
    CHECK( f.act( "trade", args, "missing-output-trade",
                  "absent-output" ).code == "source_output_unavailable" );
    CHECK( f.actor->get_moves() == before );
    CHECK( amount( *f.other, "2x4" ) == 1 );
    CHECK( amount( *f.actor, "2x4" ) == 1 );
    CHECK( amount( *f.actor, "rock" ) == 1 );
}

TEST_CASE( "npc_actor_guessing_mission_id_cannot_assign_without_hearing_offer",
           "[actor_control][native][mission]" )
{
    native_fixture f;
    mission *task = f.offer();
    const std::string args = "{\"mission_id\":" + std::to_string( task->get_id() ) + "}";
    CHECK( f.act( "accept_mission", args ).state == execution_state::failed );
    CHECK_FALSE( task->is_assigned() );
    const std::string target = std::to_string( f.other->getID().get_value() );
    REQUIRE( f.act( "talk", "{\"target\":" + target +
                    ",\"topic\":\"TALK_MISSION_OFFER\",\"option\":\"ask\"}" ).state ==
             execution_state::succeeded );
    REQUIRE( f.act( "talk", "{\"target\":" + target +
                    ",\"topic\":\"TALK_MISSION_OFFER\",\"option\":\"accept\",\"mission_id\":" +
                    std::to_string( task->get_id() ) + "}" ).state == execution_state::succeeded );
    CHECK( task->get_assigned_npc_id() == f.actor->getID() );
    CHECK( f.other->chatbin.mission_selected == nullptr );
    CHECK_FALSE( f.act( "accept_mission", args ).state == execution_state::succeeded );
    const character_id claimant = task->get_assigned_npc_id();
    task->update_world_missions_character( character_id( -1 ), get_avatar().getID() );
    CHECK( task->get_assigned_npc_id() == claimant );
    CHECK_FALSE( task->get_assigned_player_id().is_valid() );
}

TEST_CASE( "npc_actor_batch_capacity_projection_does_not_mutate_inventory",
           "[actor_control][native][inventory]" )
{
    native_fixture f;
    const int before = amount( *f.actor, "2x4" );
    get_map().add_item_or_charges( f.actor->pos_bub(), item( itype_id( "rock" ), calendar::turn ) );
    const std::string ground_before = ground_contents( f.actor->pos_bub() );
    std::vector<item> goods;
    for( int i = 0; i < 1000; ++i ) {
        goods.emplace_back( itype_id( "2x4" ), calendar::turn );
    }
    CHECK_FALSE( NpcExecutionAdapter::can_receive_items( *f.actor, goods ) );
    CHECK( amount( *f.actor, "2x4" ) == before );
    CHECK( ground_contents( f.actor->pos_bub() ) == ground_before );
}

TEST_CASE( "npc_actor_dialogue_limits_count_unicode_characters_and_keep_percent_literal",
           "[actor_control][native][dialogue]" )
{
    native_fixture f;
    std::string text;
    for( int i = 0; i < 4096; ++i ) {
        text += "药";
    }
    CHECK( f.act( "talk", f.speech( text ) ).state == execution_state::succeeded );
    text += "药";
    CHECK( f.act( "talk", f.speech( text ) ).code == "invalid_dialogue_text" );
    CHECK( f.act( "talk", f.speech( "100% medicine, literal %s and %n." ) ).state ==
           execution_state::succeeded );
    CHECK( f.act( "talk", "{\"text\":\"bad\\u0001line\"}" ).code == "invalid_dialogue_text" );
}

TEST_CASE( "npc_actor_native_enquiries_require_real_two_way_hearing",
           "[actor_control][native][dialogue][knowledge]" )
{
    native_fixture f;
    f.other->chatbin.first_topic = "TALK_TEST_PRIVATE_UNHEARD_STATE";
    add_owned( *f.other, "rock" );
    mission *task = mission::reserve_new( mission_type_id( "MISSION_GET_ANTIBIOTICS" ),
                                          f.other->getID() );
    REQUIRE( task );
    f.other->chatbin.missions.push_back( task );
    SECTION( "companion cannot hear" ) {
        // Native int_dur_factor overrides an explicitly supplied intensity.
        f.actor->add_effect( efftype_id( "deaf" ), 5_minutes );
        REQUIRE( f.actor->get_effect_int( efftype_id( "deaf" ) ) == 3 );
        REQUIRE( f.actor->is_deaf() );
    }
    SECTION( "partner cannot hear" ) {
        f.other->add_effect( efftype_id( "deaf" ), 5_minutes );
        REQUIRE( f.other->get_effect_int( efftype_id( "deaf" ) ) == 3 );
        REQUIRE( f.other->is_deaf() );
    }
    const std::string target = std::to_string( f.other->getID().get_value() );
    const int moves = f.actor->get_moves();
    for( const char *topic : {
             "TALK_TRADE", "TALK_MISSION_OFFER"
         } ) {
        const execution_result enquiry = f.act( "talk", "{\"target\":" + target +
                                                ",\"topic\":\"" + topic + "\",\"option\":\"ask\"}" );
        CHECK( enquiry.state == execution_state::failed );
        CHECK( enquiry.code == "listener_unavailable" );
    }
    CHECK( f.actor->get_moves() == moves );
    CHECK( stored( *f.actor, "heard_trade." + target ).empty() );
    CHECK( stored( *f.actor, "heard_mission." + std::to_string( task->get_id() ) ).empty() );
    const std::string observation = NpcExecutionAdapter::observe( *f.actor );
    CHECK( observation.find( "TALK_TEST_PRIVATE_UNHEARD_STATE" ) == std::string::npos );
    const JsonObject observed = inspected_object( json_loader::from_string( observation ) );
    const JsonObject nearby = inspected_object( observed.get_object( "nearby" ) );
    for( const JsonObject &person : nearby.get_array( "characters" ) ) {
        person.allow_omitted_members();
        if( person.get_int( "id" ) == f.other->getID().get_value() ) {
            CHECK( person.get_string( "topic" ) == "TALK_FIRST_TOPIC" );
            CHECK( person.get_array( "available_missions" ).size() == 0 );
            CHECK( person.get_array( "trade_offers" ).size() == 0 );
        }
    }
}
