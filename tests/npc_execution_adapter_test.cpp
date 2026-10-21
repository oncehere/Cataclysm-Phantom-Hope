#include <algorithm>
#include <sstream>
#include <string>
#include <vector>

#include "actor_control_types.h"
#include "avatar.h"
#include "calendar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "character_attire.h"
#include "character_id.h"
#include "coordinates.h"
#include "craft_reservation.h"
#include "effect.h"
#include "effect_on_condition.h"
#include "enum_bitset.h"
#include "event.h"
#include "flexbuffer_json.h"
#include "game.h"
#include "inventory.h"
#include "item.h"
#include "item_location.h"
#include "json.h"
#include "json_loader.h"
#include "magic.h"
#include "magic_type.h"
#include "map.h"
#include "map_helpers.h"
#include "map_helpers_tests.h"
#include "math_parser_diag_value.h"
#include "mission.h"
#include "monster.h"
#include "native_item_transfer.h"
#include "npc.h"
#include "npc_execution_adapter.h"
#include "pimpl.h"
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
                          const std::string &source_operation = {}, const std::string &requirement_id = {} ) {
        return NpcExecutionAdapter::execute( *actor, { id, action, args, {}, source_operation, requirement_id } );
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

spell_id native_test_spell( const std::string &suffix, const std::string &overrides = {} )
{
    const spell_id id( "test_actor_control_" + suffix );
    if( !id.is_valid() ) {
        const std::string definition = "{\"id\":\"" + id.str() +
                                      "\",\"name\":\"Test native ability\","
                                      "\"description\":\"Deterministic native ability regression.\","
                                      "\"valid_targets\":[\"self\",\"ally\",\"hostile\",\"ground\"],"
                                      "\"flags\":[\"NO_FAIL\",\"SILENT\",\"NO_HANDS\",\"NO_LEGS\"],"
                                      "\"shape\":\"blast\",\"max_level\":1,\"min_range\":6,\"max_range\":6,"
                                      "\"base_casting_time\":200,\"base_energy_cost\":50," +
                                      ( overrides.empty() ?
                                        "\"effect\":\"attack\",\"min_damage\":-7,\"max_damage\":-7,"
                                        "\"energy_source\":\"MANA\"" : overrides ) + "}";
        spell_type::load_spell( json_loader::from_string( definition ), "" );
    }
    return id;
}

void teach_native_spell( Character &actor, const spell_id &id )
{
    actor.magic->learn_spell( id, actor, true );
    actor.magic->set_spell_level( id, 1, &actor );
    actor.magic->set_mana( actor.magic->max_mana( actor ) );
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

TEST_CASE( "npc_actor_gather_preserves_reserved_providers_and_live_crafts",
           "[actor_control][native][crafting][reservation]" )
{
    native_fixture f;
    map &here = get_map();
    const tripoint_bub_ms pos( 60, 61, 0 );
    item stock( itype_id( "rock" ), calendar::turn );
    bool reserved_provider = false;
    SECTION( "reserved provider becomes available only after release" ) {
        reserved_provider = true;
    }
    SECTION( "a live craft without bindings must not be copied" ) {
        const recipe_id recipe( "cudgel_test_unattended_simple" );
        REQUIRE( recipe.is_valid() );
        item ingredient( itype_id( "2x4" ), calendar::turn );
        stock = item( &recipe.obj(), 1, ingredient );
        stock.set_passive_started_at( calendar::turn );
        stock.set_ready_at( calendar::turn + 10_minutes );
        REQUIRE_FALSE( craft_reservation::contains_reserved( stock ) );
        REQUIRE( craft_reservation::contains_live_craft( stock ) );
    }
    stock.set_owner( *f.actor );
    here.add_item_or_charges( pos, stock );
    REQUIRE( here.i_at( pos ).size() == 1 );
    if( reserved_provider ) {
        craft_reservation_index::record claim;
        claim.craft_uid = 991019;
        claim.provider_item_uids = { here.i_at( pos ).begin()->uid().get_value() };
        claim.expires_at = calendar::turn + 10_minutes;
        get_craft_reservations().set( claim );
    }
    const std::string before_stock = ground_contents( pos );
    const int before_moves = f.actor->get_moves();
    const std::string args = f.position( pos, ",\"item_type\":\"" + stock.typeId().str() +
                                         "\",\"count\":1" );
    CHECK_FALSE( NpcExecutionAdapter::available( *f.actor, "gather" ) );
    CHECK( f.act( "gather", args ).state == execution_state::failed );
    CHECK( ground_contents( pos ) == before_stock );
    CHECK( f.actor->get_moves() == before_moves );
    if( reserved_provider ) {
        get_craft_reservations().erase( 991019 );
        REQUIRE( NpcExecutionAdapter::available( *f.actor, "gather" ) );
        CHECK( f.act( "gather", args ).state == execution_state::succeeded );
        CHECK( here.i_at( pos ).empty() );
        CHECK( amount( *f.actor, "rock" ) == 1 );
    }
}

TEST_CASE( "native_item_transfer_preserves_reserved_stock",
           "[actor_control][native][inventory][trade][reservation]" )
{
    native_fixture f;
    item rock( itype_id( "rock" ), calendar::turn );
    rock.set_owner( *f.actor );
    const item_location stock = f.actor->i_add( std::move( rock ) );
    craft_reservation_index::record claim;
    claim.craft_uid = 991020;
    claim.provider_item_uids = { stock->uid().get_value() };
    claim.expires_at = calendar::turn + 10_minutes;
    get_craft_reservations().set( claim );
    std::vector<cata::native_item_transfer::selection> selected;
    int price = 73;
    std::string error;
    CHECK_FALSE( cata::native_item_transfer::select( *f.actor, *f.other,
    { { itype_id( "rock" ), 1 } }, selected, price, error, {} ) );
    CHECK( selected.empty() );
    CHECK( price == 73 );
    CHECK( amount( *f.actor, "rock" ) == 1 );
    CHECK( amount( *f.other, "rock" ) == 0 );
    get_craft_reservations().erase( 991020 );
    REQUIRE( cata::native_item_transfer::select( *f.actor, *f.other,
    { { itype_id( "rock" ), 1 } }, selected, price, error, {} ) );
    CHECK( selected.size() == 1 );
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
    REQUIRE( f.act( action, f.speech(), "native-test-step", {},
                    action == "refuse" ? "native-incoming-message" : std::string() ).state ==
             execution_state::succeeded );
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

TEST_CASE( "native_item_transfer_selects_partial_native_stock_and_commits_provenance",
           "[actor_control][native][inventory][trade]" )
{
    native_fixture f;
    add_owned( *f.actor, "antibiotics", 10, "required-stock" );
    const int before = amount( *f.actor, "antibiotics" );
    std::vector<cata::native_item_transfer::selection> selected;
    int price = 0;
    std::string error;
    REQUIRE( cata::native_item_transfer::select( *f.actor, *f.other,
    { { itype_id( "antibiotics" ), 3 } }, selected, price, error, { true, true },
    { "cph_ai_produced_step", "required-stock" } ) );
    REQUIRE( selected.size() == 1 );
    CHECK( selected.front().count == 3 );
    CHECK( amount( *f.actor, "antibiotics" ) == before );
    REQUIRE( price > 0 );
    const std::vector<cata::native_item_transfer::selection> placed =
        cata::native_item_transfer::commit( selected, *f.other,
    { "cph_ai_produced_step", "committed-output" } );
    REQUIRE( placed.size() == 1 );
    CHECK( placed.front().location->is_owned_by( *f.other ) );
    CHECK( amount( *f.actor, "antibiotics" ) == before - 3 );
    CHECK( amount( *f.other, "antibiotics" ) == 3 );
    CHECK( sourced_amount( *f.other, "antibiotics", "committed-output" ) == 3 );
}

TEST_CASE( "native_item_transfer_failed_batch_keeps_stock_and_selection_uncommitted",
           "[actor_control][native][inventory][trade]" )
{
    native_fixture f;
    add_owned( *f.actor, "rock" );
    std::vector<cata::native_item_transfer::selection> selected;
    int price = 73;
    std::string error;
    CHECK_FALSE( cata::native_item_transfer::select( *f.actor, *f.other,
    { { itype_id( "rock" ), 1 }, { itype_id( "2x4" ), 1 } }, selected,
    price, error, { true, true } ) );
    CHECK( error == "inventory_or_consent_changed" );
    CHECK( selected.empty() );
    CHECK( price == 73 );
    CHECK( amount( *f.actor, "rock" ) == 1 );
    CHECK( amount( *f.other, "rock" ) == 0 );
    std::vector<item> too_large( 1000, item( itype_id( "2x4" ), calendar::turn ) );
    CHECK_FALSE( cata::native_item_transfer::can_receive( *f.other, too_large ) );
    CHECK( amount( *f.other, "2x4" ) == 0 );
}

TEST_CASE( "npc_actor_abilities_report_only_own_knowledge_and_bound_the_snapshot",
           "[actor_control][native][magic]" )
{
    native_fixture f;
    const spell_id private_spell = native_test_spell( "other_private" );
    teach_native_spell( *f.other, private_spell );
    teach_native_spell( get_avatar(), private_spell );
    CHECK( NpcExecutionAdapter::observe( *f.actor ).find( private_spell.str() ) == std::string::npos );
    for( int i = 0; i < 66; ++i ) {
        teach_native_spell( *f.actor, native_test_spell( "bounded_" + std::to_string( i ) ) );
    }
    const JsonObject observation = inspected_object( json_loader::from_string(
                                       NpcExecutionAdapter::observe( *f.actor ) ) );
    const JsonObject actor = inspected_object( observation.get_object( "actor" ) );
    const JsonArray abilities = actor.get_array( "abilities" );
    CHECK( actor.get_int( "ability_count" ) == 66 );
    CHECK( actor.get_bool( "abilities_truncated" ) );
    CHECK( abilities.size() == 64 );
    CHECK( actor.get_int( "mana" ) == f.actor->magic->available_mana() );
    CHECK( actor.get_int( "mana_max" ) == f.actor->magic->max_mana( *f.actor ) );
    for( const JsonValue value : abilities ) {
        const JsonObject ability = inspected_object( value.get_object() );
        CHECK( f.actor->magic->knows_spell( ability.get_string( "id" ) ) );
        CHECK( ability.get_bool( "supported" ) );
        CHECK( ability.get_string( "energy_source" ) == "MANA" );
        CHECK( ability.get_int( "energy_cost" ) == 50 );
        CHECK( ability.get_int( "casting_time_moves" ) >= 200 );
        CHECK( ability.get_bool( "castable" ) );
    }
    CHECK( NpcExecutionAdapter::observe( *f.actor ).find( private_spell.str() ) == std::string::npos );
}

TEST_CASE( "npc_actor_checked_cast_spends_native_time_resources_and_never_replays",
           "[actor_control][native][magic][save]" )
{
    native_fixture f;
    const spell_id healing = native_test_spell( "heal" );
    teach_native_spell( *f.actor, healing );
    f.actor->set_part_hp_cur( bodypart_id( "torso" ), 10 );
    const int mana = f.actor->magic->available_mana();
    const int player_moves = get_avatar().get_moves();
    const std::string args = f.position( f.actor->pos_bub(),
                                       ",\"spell\":\"" + healing.str() + "\"" );
    REQUIRE( f.act( "cast_spell", args, "heal-once" ).state == execution_state::running );
    REQUIRE( f.actor->activity );
    CHECK( f.actor->activity.moves_total >= 200 );
    CHECK( f.actor->get_part_hp_cur( bodypart_id( "torso" ) ) == 10 );
    CHECK( f.actor->magic->available_mana() == mana );
    CHECK( f.act( "cast_spell", args, "heal-once" ).state == execution_state::running );

    SECTION( "finishing and saving preserve the real receipt" ) {
        REQUIRE( process_activity_bounded( *f.actor, 20, 100 ) );
        const execution_result finished = f.act( "cast_spell", args, "heal-once" );
        INFO( finished.code );
        REQUIRE( finished.state == execution_state::succeeded );
        CHECK( f.actor->get_part_hp_cur( bodypart_id( "torso" ) ) == 17 );
        CHECK( f.actor->magic->available_mana() == mana - 50 );
        std::ostringstream data;
        JsonOut out( data );
        f.actor->serialize( out );
        f.actor->setID( character_id(), true );
        f.actor->deserialize( json_loader::from_string( data.str() ) );
        CHECK( f.act( "cast_spell", args, "heal-once" ).state == execution_state::succeeded );
        CHECK_FALSE( f.actor->activity );
        CHECK( f.actor->get_part_hp_cur( bodypart_id( "torso" ) ) == 17 );
        CHECK( f.actor->magic->available_mana() == mana - 50 );
    }
    SECTION( "cancelled activity cannot report success or restart" ) {
        f.actor->cancel_activity();
        CHECK( f.act( "cast_spell", args, "heal-once" ).state == execution_state::failed );
        CHECK_FALSE( f.actor->activity );
        CHECK( f.actor->get_part_hp_cur( bodypart_id( "torso" ) ) == 10 );
        CHECK( f.actor->magic->available_mana() == mana );
    }
    SECTION( "resources are rechecked before the delayed effect" ) {
        f.actor->magic->set_mana( 0 );
        REQUIRE( process_activity_bounded( *f.actor, 20, 100 ) );
        const execution_result rejected = f.act( "cast_spell", args, "heal-once" );
        CHECK( rejected.state == execution_state::failed );
        CHECK( rejected.code == "insufficient_spell_energy" );
        CHECK( f.actor->get_part_hp_cur( bodypart_id( "torso" ) ) == 10 );
        CHECK( f.actor->magic->available_mana() == 0 );
    }
    SECTION( "an in-flight saved activity resumes once" ) {
        f.actor->set_moves( 50 );
        f.actor->activity.do_turn( *f.actor );
        REQUIRE( f.actor->activity );
        std::ostringstream data;
        JsonOut out( data );
        f.actor->serialize( out );
        f.actor->setID( character_id(), true );
        f.actor->deserialize( json_loader::from_string( data.str() ) );
        REQUIRE( f.actor->activity );
        REQUIRE( process_activity_bounded( *f.actor, 20, 100 ) );
        REQUIRE( f.act( "cast_spell", args, "heal-once" ).state == execution_state::succeeded );
        CHECK( f.actor->get_part_hp_cur( bodypart_id( "torso" ) ) == 17 );
        CHECK( f.actor->magic->available_mana() == mana - 50 );
        CHECK( f.act( "cast_spell", args, "heal-once" ).state == execution_state::succeeded );
        CHECK_FALSE( f.actor->activity );
        CHECK( f.actor->magic->available_mana() == mana - 50 );
    }
    CHECK( get_avatar().get_moves() == player_moves );
}

TEST_CASE( "npc_actor_owned_spell_activity_refuses_missing_or_corrupt_saved_context",
           "[actor_control][native][magic][save]" )
{
    native_fixture f;
    const spell_id healing = native_test_spell( "heal" );
    teach_native_spell( *f.actor, healing );
    f.actor->set_part_hp_cur( bodypart_id( "torso" ), 10 );
    const int mana = f.actor->magic->available_mana();
    const std::string args = f.position( f.actor->pos_bub(),
                                       ",\"spell\":\"" + healing.str() + "\"" );
    REQUIRE( f.act( "cast_spell", args, "owned-context" ).state == execution_state::running );
    REQUIRE( f.actor->activity );
    const std::vector<std::string> ownership = { "cph_ai.cast_spell", "owned-context" };
    REQUIRE( f.actor->activity.str_values == ownership );
    const std::string damage = GENERATE( "missing_step", "missing_args", "bad_args", "different_args",
                                        "missing_target" );
    if( damage == "missing_step" ) {
        f.actor->remove_value( "cph_ai.spell_step" );
    } else if( damage == "missing_args" ) {
        f.actor->remove_value( "cph_ai.spell_args" );
    } else if( damage == "bad_args" ) {
        f.actor->set_value( "cph_ai.spell_args", "{broken" );
    } else if( damage == "missing_target" ) {
        f.actor->remove_value( "cph_ai.spell_target" );
    } else {
        f.actor->set_value( "cph_ai.spell_args", f.position( f.other->pos_bub(),
                          ",\"spell\":\"" + healing.str() + "\"" ) );
    }
    std::ostringstream data;
    JsonOut out( data );
    f.actor->serialize( out );
    f.actor->setID( character_id(), true );
    f.actor->deserialize( json_loader::from_string( data.str() ) );
    REQUIRE( f.actor->activity );
    REQUIRE( process_activity_bounded( *f.actor, 20, 100 ) );
    CHECK( f.actor->get_part_hp_cur( bodypart_id( "torso" ) ) == 10 );
    CHECK( f.actor->magic->available_mana() == mana );
    CHECK( stored( *f.actor, "spell_completed_step" ) == "owned-context" );
    const JsonObject receipt = inspected_object( json_loader::from_string(
                                   stored( *f.actor, "spell_result" ) ) );
    CHECK( receipt.get_string( "state" ) == "failed" );
    CHECK( receipt.get_string( "code" ) == "spell_context_changed" );
}

TEST_CASE( "npc_ordinary_native_spell_ignores_unrelated_companion_markers",
           "[actor_control][native][magic]" )
{
    native_fixture f;
    const spell_id healing = native_test_spell( "heal" );
    teach_native_spell( *f.actor, healing );
    f.actor->set_part_hp_cur( bodypart_id( "torso" ), 10 );
    const int mana = f.actor->magic->available_mana();
    SECTION( "without companion markers" ) {}
    SECTION( "with corrupt markers from an unrelated old operation" ) {
        f.actor->set_value( "cph_ai.spell_step", "old-unrelated-step" );
        f.actor->set_value( "cph_ai.spell_args", "{broken" );
    }
    REQUIRE( f.actor->cast_spell( f.actor->magic->get_spell( healing ), false, f.actor->pos_bub() ) );
    REQUIRE( f.actor->activity );
    REQUIRE( f.actor->activity.str_values.empty() );
    REQUIRE( process_activity_bounded( *f.actor, 20, 100 ) );
    CHECK( f.actor->get_part_hp_cur( bodypart_id( "torso" ) ) == 17 );
    CHECK( f.actor->magic->available_mana() == mana - 50 );
    CHECK( stored( *f.actor, "spell_completed_step" ).empty() );
    CHECK( stored( *f.actor, "spell_result" ).empty() );
}

TEST_CASE( "npc_actor_checked_cast_rejects_unsupported_or_unavailable_without_effects",
           "[actor_control][native][magic]" )
{
    native_fixture f;
    const std::string variant = GENERATE( "unknown", "mana", "hp", "eoc", "extra", "field", "dot",
                                        "random_target", "status", "stamina_unsupported", "stamina_recovery",
                                        "components", "failure_eoc", "damage_eoc" );
    spell_id selected;
    if( variant == "hp" ) {
        selected = native_test_spell( "reject_hp_source",
                                     "\"effect\":\"attack\",\"min_damage\":-7,\"max_damage\":-7,\"energy_source\":\"HP\"" );
    } else if( variant == "eoc" ) {
        selected = native_test_spell( "reject_eoc_effect",
                                     "\"effect\":\"effect_on_condition\",\"effect_str\":\"EOC_teleport_test\",\"energy_source\":\"MANA\"" );
    } else if( variant == "extra" ) {
        selected = native_test_spell( "reject_extra_effect",
                                     "\"effect\":\"attack\",\"extra_effects\":[{\"id\":\"test_spell_pew\"}],\"energy_source\":\"MANA\"" );
    } else if( variant == "field" ) {
        selected = native_test_spell( "reject_field_effect",
                                     "\"effect\":\"attack\",\"field_id\":\"fd_fire\",\"min_field_intensity\":1,\"max_field_intensity\":1,\"energy_source\":\"MANA\"" );
    } else if( variant == "dot" ) {
        selected = native_test_spell( "reject_dot_effect",
                                     "\"effect\":\"attack\",\"min_dot\":1,\"max_dot\":1,\"energy_source\":\"MANA\"" );
    } else if( variant == "status" ) {
        selected = native_test_spell( "reject_status_effect",
                                     "\"effect\":\"attack\",\"effect_str\":\"blind\",\"energy_source\":\"MANA\"" );
    } else if( variant == "stamina_unsupported" ) {
        selected = native_test_spell( "reject_stamina_unsupported",
                                     "\"effect\":\"attack\",\"min_damage\":-7,\"max_damage\":-7,\"energy_source\":\"STAMINA\"" );
    } else if( variant == "stamina_recovery" ) {
        selected = native_test_spell( "reject_stamina_recovery",
                                     "\"effect\":\"recover_energy\",\"effect_str\":\"STAMINA\",\"min_damage\":50,\"max_damage\":50,\"energy_source\":\"NONE\"" );
    } else if( variant == "components" ) {
        selected = native_test_spell( "reject_components",
                                     "\"effect\":\"attack\",\"components\":\"test_components\",\"energy_source\":\"MANA\"" );
        add_owned( *f.actor, "test_rag" );
    } else if( variant == "damage_eoc" ) {
        selected = native_test_spell( "reject_damage_eoc",
                                     "\"effect\":\"attack\",\"min_damage\":-7,\"max_damage\":-7,\"damage_type\":\"test_fire\",\"energy_source\":\"MANA\"" );
    } else if( variant == "failure_eoc" ) {
        const magic_type_id failure_type( "test_actor_control_failure_type" );
        if( !failure_type.is_valid() ) {
            magic_type::load_magic_type( json_loader::from_string( R"({
                "id":"test_actor_control_failure_type","energy_source":"MANA",
                "failure_eocs":["EOC_teleport_test"]
            })" ), "" );
        }
        selected = native_test_spell( "reject_failure_eoc",
                                     "\"effect\":\"attack\",\"magic_type\":\"test_actor_control_failure_type\",\"energy_source\":\"MANA\"" );
    } else if( variant == "random_target" ) {
        const spell_id random( "test_actor_control_random_target" );
        if( !random.is_valid() ) {
            spell_type::load_spell( json_loader::from_string( R"({
                "id":"test_actor_control_random_target","name":"Random target",
                "description":"Reject uncontrolled target selection.",
                "valid_targets":["self"],"flags":["RANDOM_TARGET","NO_FAIL"],
                "effect":"attack","shape":"blast","max_level":1,
                "min_damage":-7,"max_damage":-7,"energy_source":"MANA"
            })" ), "" );
        }
        selected = random;
    }
    if( variant == "unknown" || variant == "mana" ) {
        selected = native_test_spell( "reject_" + variant );
    }
    if( variant != "unknown" ) {
        teach_native_spell( *f.actor, selected );
    }
    if( variant == "mana" ) {
        f.actor->magic->set_mana( 0 );
    }
    const int mana = f.actor->magic->available_mana();
    const int hp = f.actor->get_hp();
    const int moves = f.actor->get_moves();
    const int player_hp = get_avatar().get_hp();
    const int stamina = f.actor->get_stamina();
    const std::string args = f.position( f.actor->pos_bub(),
                                       ",\"spell\":\"" + selected.str() + "\"" );
    const execution_result rejected = f.act( "cast_spell", args, "rejected-cast" );
    INFO( variant );
    INFO( rejected.code );
    CHECK( rejected.state == execution_state::failed );
    if( variant == "damage_eoc" ) {
        CHECK( rejected.code == "npc_unsupported_damage_effect" );
    }
    if( variant == "stamina_unsupported" || variant == "stamina_recovery" ) {
        CHECK( rejected.code == "npc_unsupported_energy_source" );
    }
    CHECK_FALSE( f.actor->activity );
    CHECK( f.actor->magic->available_mana() == mana );
    CHECK( f.actor->get_hp() == hp );
    CHECK( f.actor->get_moves() == moves );
    CHECK( f.actor->get_stamina() == stamina );
    if( variant == "components" ) {
        CHECK( amount( *f.actor, "test_rag" ) == 1 );
    }
    CHECK( get_avatar().get_hp() == player_hp );
}

TEST_CASE( "npc_actor_checked_cast_requires_its_own_perception_and_range",
           "[actor_control][native][magic]" )
{
    native_fixture f;
    const spell_id attack = native_test_spell( "attack",
                            "\"effect\":\"attack\",\"min_damage\":7,\"max_damage\":7,\"damage_type\":\"pure\",\"energy_source\":\"MANA\"" );
    teach_native_spell( *f.actor, attack );
    const bool blind = GENERATE( false, true );
    const tripoint_bub_ms target = blind ? tripoint_bub_ms( 60, 62, 0 ) :
                                  tripoint_bub_ms( 60, 70, 0 );
    monster &foe = spawn_test_monster( "mon_zombie", target );
    if( blind ) {
        f.actor->add_effect( efftype_id( "blind" ), 1_hours );
        f.actor->recalc_sight_limits();
        REQUIRE( f.actor->is_blind() );
    }
    const int hp = foe.get_hp();
    const int mana = f.actor->magic->available_mana();
    const int moves = f.actor->get_moves();
    const execution_result result = f.act( "cast_spell", f.position( target,
                                   ",\"spell\":\"" + attack.str() + "\"" ) );
    INFO( result.code );
    CHECK( result.state == execution_state::failed );
    CHECK_FALSE( f.actor->activity );
    CHECK( foe.get_hp() == hp );
    CHECK( f.actor->magic->available_mana() == mana );
    CHECK( f.actor->get_moves() == moves );
}

TEST_CASE( "npc_actor_checked_cast_damages_only_the_actual_observed_target_once",
           "[actor_control][native][magic]" )
{
    native_fixture f;
    const spell_id attack = native_test_spell( "attack",
                            "\"effect\":\"attack\",\"min_damage\":7,\"max_damage\":7,\"damage_type\":\"pure\",\"energy_source\":\"MANA\"" );
    teach_native_spell( *f.actor, attack );
    monster &foe = spawn_test_monster( "mon_zombie", tripoint_bub_ms( 60, 62, 0 ) );
    const int hp = foe.get_hp();
    const int mana = f.actor->magic->available_mana();
    const int player_hp = get_avatar().get_hp();
    const std::string args = f.position( foe.pos_bub(), ",\"spell\":\"" + attack.str() + "\"" );
    REQUIRE( f.act( "cast_spell", args, "strike-once" ).state == execution_state::running );
    CHECK( foe.get_hp() == hp );
    SECTION( "the chosen creature receives the effect" ) {
        REQUIRE( process_activity_bounded( *f.actor, 20, 100 ) );
        REQUIRE( f.act( "cast_spell", args, "strike-once" ).state == execution_state::succeeded );
        CHECK( foe.get_hp() == hp - 7 );
        CHECK( f.actor->magic->available_mana() == mana - 50 );
        CHECK( f.act( "cast_spell", args, "strike-once" ).state == execution_state::succeeded );
        CHECK( foe.get_hp() == hp - 7 );
        const std::string changed = f.position( get_avatar().pos_bub(),
                                    ",\"spell\":\"" + attack.str() + "\"" );
        CHECK( f.act( "cast_spell", changed, "strike-once" ).code == "receipt_conflict" );
        CHECK_FALSE( f.actor->activity );
    }
    SECTION( "a creature replacing the target cannot inherit permission" ) {
        const tripoint_bub_ms target = foe.pos_bub();
        foe.setpos( get_map(), tripoint_bub_ms( 60, 63, 0 ) );
        monster &replacement = spawn_test_monster( "mon_zombie", target );
        const int replacement_hp = replacement.get_hp();
        const bool missing_target = GENERATE( false, true );
        if( missing_target ) {
            f.actor->remove_value( "cph_ai.spell_target" );
        }
        REQUIRE( process_activity_bounded( *f.actor, 20, 100 ) );
        const execution_result rejected = f.act( "cast_spell", args, "strike-once" );
        CHECK( rejected.state == execution_state::failed );
        CHECK( rejected.code == ( missing_target ? "spell_context_changed" : "spell_target_changed" ) );
        CHECK( foe.get_hp() == hp );
        CHECK( replacement.get_hp() == replacement_hp );
        CHECK( f.actor->magic->available_mana() == mana );
    }
    CHECK( get_avatar().get_hp() == player_hp );
}

// Explicitly opt in with --mods magiclysm,mindovermatter,xedra_evolved.
// Fixture knowledge does not claim that progression or learning is supported.
TEST_CASE( "npc_actor_magic_mod_abilities_keep_the_same_native_safety_boundary",
           "[.actor_control_magic_mods][actor_control][native][magic]" )
{
    native_fixture f;
    const std::string id = GENERATE( "point_flare", "classless_specific_concentration_end",
                                    "fire_teleport", "telepathic_blast", "boann_heal" );
    const spell_id selected( id );
    REQUIRE( selected.is_valid() );
    teach_native_spell( *f.actor, selected );
    // Loaded spellbook hooks are gameplay prerequisites. Until audited, even
    // an otherwise pure helper may not bypass that Mod's preparation.
    const bool supported = false;
    const JsonObject observation = inspected_object( json_loader::from_string(
                                       NpcExecutionAdapter::observe( *f.actor ) ) );
    const JsonArray abilities = inspected_object( observation.get_object( "actor" ) ).get_array(
                                   "abilities" );
    REQUIRE( abilities.size() == 1 );
    const JsonObject ability = inspected_object( abilities.get_object( 0 ) );
    CHECK( ability.get_string( "id" ) == id );
    INFO( ability.get_string( "reason" ) );
    CHECK( ability.get_bool( "supported" ) == supported );
    if( id == "boann_heal" ) {
        CHECK( ability.get_string( "reason" ) == "npc_unsupported_spellbook_event" );
    }
    const std::string args = f.position( f.actor->pos_bub(), ",\"spell\":\"" + id + "\"" );
    if( !supported ) {
        const int mana = f.actor->magic->available_mana();
        const int stamina = f.actor->get_stamina();
        CHECK( f.act( "cast_spell", args, "mod-rejected" ).state == execution_state::failed );
        CHECK_FALSE( f.actor->activity );
        CHECK( f.actor->magic->available_mana() == mana );
        CHECK( f.actor->get_stamina() == stamina );
    }
}

TEST_CASE( "npc_actor_checked_stamina_cast_spends_native_energy_once",
           "[actor_control][native][magic][stamina]" )
{
    native_fixture f;
    f.actor->set_value( "cph_ai.real_stamina", "true" );
    f.actor->set_stamina( 1000 );
    const spell_id selected = native_test_spell( "finite_stamina",
                              "\"effect\":\"attack\",\"min_damage\":-7,\"max_damage\":-7,"
                              "\"energy_source\":\"STAMINA\"" );
    teach_native_spell( *f.actor, selected );
    f.actor->set_part_hp_cur( bodypart_id( "torso" ), 10 );
    const int cost = f.actor->magic->get_spell( selected ).energy_cost( *f.actor );
    REQUIRE( cost > 0 );
    const int player_stamina = get_avatar().get_stamina();
    const int mana = f.actor->magic->available_mana();
    const std::string args = f.position( f.actor->pos_bub(),
                                       ",\"spell\":\"" + selected.str() + "\"" );
    SECTION( "success_and_repeated_receipt" ) {
        REQUIRE( f.act( "cast_spell", args, "paid" ).state == execution_state::running );
        CHECK( f.actor->get_stamina() == 1000 );
        REQUIRE( process_activity_bounded( *f.actor, 20, 100 ) );
        REQUIRE( f.act( "cast_spell", args, "paid" ).state == execution_state::succeeded );
        CHECK( f.actor->get_stamina() == 1000 - cost );
        CHECK( f.actor->get_part_hp_cur( bodypart_id( "torso" ) ) == 17 );
        // Exclude the fixture's synthetic nutrition hash from this resource/
        // receipt roundtrip; it is unrelated to the saved casting state.
        f.actor->consumption_history.clear();
        std::ostringstream stream;
        JsonOut output( stream );
        f.actor->serialize( output );
        npc restored;
        restored.deserialize( json_loader::from_string( stream.str() ).get_object() );
        CHECK( NpcExecutionAdapter::execute( restored, { "paid", "cast_spell", args } ).state ==
               execution_state::succeeded );
        CHECK( restored.get_stamina() == 1000 - cost );
        CHECK( restored.get_part_hp_cur( bodypart_id( "torso" ) ) == 17 );
    }
    SECTION( "insufficient_at_start" ) {
        f.actor->set_stamina( cost - 1 );
        CHECK( f.act( "cast_spell", args, "paid" ).code == "insufficient_spell_energy" );
        CHECK_FALSE( f.actor->activity );
        CHECK( f.actor->get_stamina() == cost - 1 );
    }
    SECTION( "energy_changed_while_casting" ) {
        REQUIRE( f.act( "cast_spell", args, "paid" ).state == execution_state::running );
        f.actor->set_stamina( cost - 1 );
        REQUIRE( process_activity_bounded( *f.actor, 20, 100 ) );
        CHECK( f.act( "cast_spell", args, "paid" ).code == "insufficient_spell_energy" );
        CHECK( f.actor->get_stamina() == cost - 1 );
        CHECK( f.actor->get_part_hp_cur( bodypart_id( "torso" ) ) == 10 );
    }
    SECTION( "native_failure_cost_is_spent_once" ) {
        spell_type &definition = const_cast<spell_type &>( selected.obj() );
        restore_on_out_of_scope restore_flags( definition.flags );
        restore_on_out_of_scope restore_tags( definition.spell_tags );
        restore_on_out_of_scope restore_difficulty( definition.difficulty );
        restore_on_out_of_scope restore_school( definition.magic_type );
        definition.flags.erase( "NO_FAIL" );
        definition.spell_tags.reset( spell_flag::NO_FAIL );
        definition.difficulty = 100;
        definition.magic_type = magic_type_id( "test_magic_available" );
        magic_type &school = const_cast<magic_type &>( definition.magic_type->obj() );
        restore_on_out_of_scope restore_cost( school.failure_cost_percent );
        school.failure_cost_percent = 0.5;
        REQUIRE( f.actor->magic->get_spell( selected ).spell_fail( *f.actor ) == 1.0f );
        REQUIRE( f.act( "cast_spell", args, "paid" ).state == execution_state::running );
        REQUIRE( process_activity_bounded( *f.actor, 20, 100 ) );
        CHECK( f.act( "cast_spell", args, "paid" ).code == "spell_failed" );
        CHECK( f.actor->get_stamina() == 1000 - static_cast<int>( cost * 0.5 ) );
        CHECK( f.actor->get_part_hp_cur( bodypart_id( "torso" ) ) == 10 );
        CHECK( f.act( "cast_spell", args, "paid" ).code == "spell_failed" );
        CHECK( f.actor->get_stamina() == 1000 - static_cast<int>( cost * 0.5 ) );
    }
    CHECK( f.actor->magic->available_mana() == mana );
    CHECK( get_avatar().get_stamina() == player_stamina );
}

TEST_CASE( "npc_actor_checked_stamina_recovery_is_self_only_and_clamped",
           "[actor_control][native][magic][stamina]" )
{
    native_fixture f;
    f.actor->set_value( "cph_ai.real_stamina", "true" );
    const spell_id selected = native_test_spell( "finite_recovery",
                              "\"effect\":\"recover_energy\",\"effect_str\":\"STAMINA\","
                              "\"min_damage\":100,\"max_damage\":100,\"energy_source\":\"MANA\"" );
    teach_native_spell( *f.actor, selected );
    f.actor->set_stamina( f.actor->get_stamina_max() - 10 );
    const int mana = f.actor->magic->available_mana();
    const int cost = f.actor->magic->get_spell( selected ).energy_cost( *f.actor );
    SECTION( "self_recovery_is_capped" ) {
        const std::string args = f.position( f.actor->pos_bub(),
                                           ",\"spell\":\"" + selected.str() + "\"" );
        REQUIRE( f.act( "cast_spell", args, "recover" ).state == execution_state::running );
        REQUIRE( process_activity_bounded( *f.actor, 20, 100 ) );
        CHECK( f.act( "cast_spell", args, "recover" ).state == execution_state::succeeded );
        CHECK( f.actor->get_stamina() == f.actor->get_stamina_max() );
        CHECK( f.actor->magic->available_mana() == mana - cost );
        CHECK( f.act( "cast_spell", args, "recover" ).state == execution_state::succeeded );
        CHECK( f.actor->magic->available_mana() == mana - cost );
    }
    SECTION( "other_target_is_rejected" ) {
        CHECK( f.act( "cast_spell", f.position( f.other->pos_bub(),
                                              ",\"spell\":\"" + selected.str() + "\"" ) ).code ==
               "npc_unsupported_spell_target" );
        CHECK( f.actor->magic->available_mana() == mana );
        CHECK( f.actor->get_stamina() == f.actor->get_stamina_max() - 10 );
    }
}

TEST_CASE( "npc_actor_spellbook_scripts_are_rejected_before_side_effects",
           "[actor_control][native][magic]" )
{
    native_fixture f;
    const spell_id selected = native_test_spell( "spellbook_guard" );
    teach_native_spell( *f.actor, selected );
    const std::string args = f.position( f.actor->pos_bub(),
                                       ",\"spell\":\"" + selected.str() + "\"" );
    const bool already_started = GENERATE( false, true );
    if( already_started ) {
        REQUIRE( f.act( "cast_spell", args, "guard" ).state == execution_state::running );
    }
    const auto &eocs = effect_on_conditions::get_all();
    const auto existing_event = std::find_if( eocs.begin(), eocs.end(),
    []( const effect_on_condition & eoc ) {
        return eoc.type == eoc_type::EVENT;
    } );
    REQUIRE( existing_event != eocs.end() );
    effect_on_condition &hook = const_cast<effect_on_condition &>( *existing_event );
    restore_on_out_of_scope restore_event( hook.required_event );
    hook.required_event = event_type::opens_spellbook;
    const int mana = f.actor->magic->available_mana();
    const int hp = f.actor->get_hp();
    const int host_hp = get_avatar().get_hp();
    if( already_started ) {
        REQUIRE( process_activity_bounded( *f.actor, 20, 100 ) );
    }
    CHECK( f.act( "cast_spell", args, "guard" ).code == "npc_unsupported_spellbook_event" );
    CHECK_FALSE( f.actor->activity );
    CHECK( f.actor->magic->available_mana() == mana );
    CHECK( f.actor->get_hp() == hp );
    CHECK( get_avatar().get_hp() == host_hp );
}
