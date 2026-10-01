#include <cstdlib>
#include <filesystem>
#include <sstream>
#include <string>

#ifndef _WIN32
    #include <sys/stat.h>
#endif

#include "actor_control.h"
#include "actor_control_bridge.h"
#include "actor_control_protocol.h"
#include "actor_control_save.h"
#include "activity_actor_definitions.h"
#include "avatar.h"
#include "calendar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "character_attire.h"
#include "character_id.h"
#include "coordinates.h"
#include "creature_tracker.h"
#include "flexbuffer_json.h"
#include "game.h"
#include "item.h"
#include "item_location.h"
#include "json.h"
#include "json_loader.h"
#include "map.h"
#include "map_helpers.h"
#include "map_helpers_tests.h"
#include "math_parser_diag_value.h"
#include "npc.h"
#include "npc_execution_adapter.h"
#include "overmapbuffer.h"
#include "path_info.h"
#include "player_activity.h"
#include "player_helpers.h"
#include "recipe.h"
#include "recipe_dictionary.h"
#include "type_id.h"
#include "worldfactory.h"

namespace
{
namespace control = cata::actor_control;

const char policy[] =
    R"({"schema_version":1,"applies_to":"bound_companion_only","expression_policy":"natural_with_intent_checks","social_behavior":{"refuse":true,"argue":true,"propose_own_goals":true,"deception":{"enabled":true,"lie_in_dialogue":true,"conceal_information":true,"false_promise":true,"transaction_fraud":false},"betrayal":{"enabled":true,"break_commitment":true,"aid_conflicting_party":true,"disclose_known_information":true,"leave_group":false,"misappropriate_items":false,"sabotage":false,"attack_player":false,"attack_allies":false}}})";

JsonObject snapshot( const std::string &text )
{
    JsonObject result = json_loader::from_string( text ).get_object();
    result.allow_omitted_members();
    return result;
}

JsonObject child( const JsonObject &parent, const std::string &key )
{
    JsonObject result = parent.get_object( key );
    result.allow_omitted_members();
    return result;
}

JsonObject at( const JsonObject &parent, const std::string &key, std::size_t index )
{
    JsonObject result = parent.get_array( key ).get_object( index );
    result.allow_omitted_members();
    return result;
}

class control_fixture
{
    public:
        control_fixture() {
            const char *runtime = std::getenv( "XDG_RUNTIME_DIR" );
            had_runtime = runtime != nullptr;
            old_runtime = runtime ? runtime : "";
            directory = std::filesystem::temp_directory_path() /
                        ( "cph-actor-core-test-" + control::new_identity() );
            std::filesystem::create_directory( directory );
#ifndef _WIN32
            REQUIRE( chmod( directory.c_str(), 0700 ) == 0 );
            REQUIRE( setenv( "XDG_RUNTIME_DIR", directory.c_str(), 1 ) == 0 );
#endif
            control::enable( false );
            control::reset();
            clear_avatar();
            clear_map_without_vision();
            set_time( calendar::turn_zero + 12_hours );
            control::enable( true );
        }
        ~control_fixture() {
            control::enable( false );
            control::reset();
#ifndef _WIN32
            if( had_runtime ) {
                setenv( "XDG_RUNTIME_DIR", old_runtime.c_str(), 1 );
            } else {
                unsetenv( "XDG_RUNTIME_DIR" );
            }
#endif
            std::error_code error;
            // A new isolated fixture owned exclusively by this test.
            std::filesystem::remove_all( directory, error );
        }
        npc &companion() {
            npc &result = spawn_npc( get_avatar().pos_bub().xy() + point( ++companions, 0 ),
                                     "test_talker" );
            const tripoint_bub_ms spawn_position = result.pos_bub();
            clear_character( result );
            // clear_character also moves characters to the avatar's default
            // tile. Keep each real NPC at its distinct native spawn position.
            result.setpos( get_map(), spawn_position );
            result.set_attitude( NPCATT_FOLLOW );
            result.set_fac( faction_id( "your_followers" ) );
            REQUIRE( result.is_player_ally() );
            REQUIRE( result.pos_bub() != get_avatar().pos_bub() );
            REQUIRE( result.is_active() );
            return result;
        }
    private:
        bool had_runtime = false;
        std::string old_runtime;
        std::filesystem::path directory;
        int companions = 0;
};

JsonObject response( const std::string &method, const std::string &params = "{}" )
{
    std::string error;
    const std::string result = control::dispatch( method, params, error );
    INFO( method << ": " << error );
    REQUIRE( error.empty() );
    return snapshot( result );
}

void prepare( npc &actor )
{
    std::string error;
    REQUIRE( control::bind( actor, "test-profile", error ) );
    REQUIRE( error.empty() );
    response( "configure", "{\"profile_id\":\"test-profile\",\"personality\":" +
              std::string( policy ) +
              ",\"limits\":{\"max_steps\":5,\"cooldown\":0},\"debug\":{\"enabled\":true}}" );
    response( "sync_memory",
              "{\"version\":\"test-memory\",\"snapshot\":{\"revision\":\"test-memory\",\"records\":[]}}" );
}

std::string plan( const JsonObject &request, const std::string &steps )
{
    return "{\"context\":" + child( request, "context" ).str() + ",\"steps\":" + steps + "}";
}

int native_amount( const Character &actor, const char *name )
{
    const itype_id id( name );
    return item::count_by_charges( id ) ? actor.charges_of( id ) : actor.amount_of( id );
}

std::string saved()
{
    std::ostringstream buffer;
    JsonOut out( buffer );
    control::serialize( out );
    return buffer.str();
}
} // namespace

TEST_CASE( "actor_control_fixed_binding_preserves_native_character", "[actor_control][npc]" )
{
    control_fixture fixture;
    npc &first = fixture.companion();
    npc &other = fixture.companion();
    REQUIRE( first.pos_bub() != other.pos_bub() );
    REQUIRE( get_creature_tracker().creature_at<npc>( first.pos_bub() ) == &first );
    REQUIRE( get_creature_tracker().creature_at<npc>( other.pos_bub() ) == &other );
    const character_id original = first.getID();
    const int native_moves = first.get_moves();
    const int player_moves = get_avatar().get_moves();
    const time_point original_time = calendar::turn;
    prepare( first );
    std::string error;
    CHECK_FALSE( control::bind( other, "test-profile", error ) );
    CHECK( error == "fixed_binding_conflict" );
    CHECK_FALSE( control::bind( first, "another-profile", error ) );
    CHECK( control::is_bound( first ) );
    CHECK_FALSE( control::is_bound( other ) );
    CHECK( first.getID() == original );
    CHECK( first.get_moves() == native_moves );
    CHECK( get_avatar().get_moves() == player_moves );
    control::pump_incoming();
    CHECK( calendar::turn == original_time );
    CHECK( get_avatar().get_moves() == player_moves );
}

TEST_CASE( "actor_control_rejects_multiplayer_proxy_binding", "[actor_control][multiplayer]" )
{
    control_fixture fixture;
    npc &proxy = fixture.companion();
    proxy.set_value( "mp_proxy", "1" );
    const character_id id = proxy.getID();
    const int moves = proxy.get_moves();
    const int player_moves = get_avatar().get_moves();
    const time_point before = calendar::turn;
    std::string error;
    CHECK_FALSE( control::bind( proxy, "test-profile", error ) );
    CHECK( error == "multiplayer_proxy_not_supported" );
    CHECK_FALSE( control::has_binding() );
    CHECK_FALSE( proxy.maybe_get_value( "cph_ai.bound" ) );
    CHECK( proxy.get_value( "mp_proxy" ) == "1" );
    CHECK( proxy.getID() == id );
    CHECK( proxy.get_moves() == moves );
    CHECK( get_avatar().get_moves() == player_moves );
    CHECK( calendar::turn == before );
}

TEST_CASE( "actor_control_restored_binding_never_controls_multiplayer_proxy",
           "[actor_control][multiplayer][lifecycle]" )
{
    control_fixture fixture;
    npc &proxy = fixture.companion();
    prepare( proxy );
    proxy.i_add( item( itype_id( "bandages" ) ) );
    proxy.set_moves( 100 );
    const character_id id = proxy.getID();
    const int moves = proxy.get_moves();
    const int player_moves = get_avatar().get_moves();
    const std::size_t inventory = proxy.all_items_loc().size();
    const time_point before = calendar::turn;
    const std::string initial_save = saved();

    SECTION( "late plans and subjective preferences cannot control the partner" ) {
        control::deserialize( snapshot( initial_save ) );
        const std::string scope = "{\"actor_id\":" + std::to_string( id.get_value() ) + "}";
        response( "sync_memory",
                  "{\"version\":\"cautious\",\"snapshot\":{\"revision\":\"cautious\",\"records\":["
                  "{\"id\":\"known-event\",\"kind\":\"observation\",\"text\":\"I was hurt.\","
                  "\"context\":" + scope + "},"
                  "{\"id\":\"experience\",\"kind\":\"growth\",\"text\":\"I prefer more space.\","
                  "\"context\":" + scope + ",\"source_ids\":[\"known-event\"],\"confidence\":1,"
                  "\"preferences\":{\"caution\":0.9}}]}}" );
        REQUIRE( control::following_distance( proxy, 4 ) == 5 );
        const JsonObject request = response( "take_request" );
        proxy.set_value( "mp_proxy", "1" );
        std::string error;
        const std::string unavailable = control::dispatch( "take_request", "{}", error );
        CHECK( error.empty() );
        CHECK( json_loader::from_string( unavailable ).test_null() );
        control::dispatch( "offer_plan", plan( request,
                                               R"([{"id":"late","action":"wait","args":{}}])" ), error );
        CHECK( error == "stale_request" );
        CHECK( control::following_distance( proxy, 4 ) == 4 );
    }

    SECTION( "a restored queue cannot use the proxy action budget" ) {
        const JsonObject request = response( "take_request" );
        response( "offer_plan", plan( request,
                                      R"([{"id":"queued","action":"wait","args":{}}])" ) );
        const std::string queued_save = saved();
        proxy.set_value( "mp_proxy", "1" );
        control::deserialize( snapshot( queued_save ) );
        CHECK_FALSE( control::act( proxy, false ) );
        CHECK_FALSE( control::pauses_offline_work( proxy ) );
        CHECK( proxy.get_value( "cph_ai.bound" ) == "true" );
    }

    SECTION( "cancel and stop preserve the partner native activity and markers" ) {
        const JsonObject request = response( "take_request" );
        response( "offer_plan", plan( request,
                                      R"([{"id":"queued","action":"wait","args":{}}])" ) );
        const std::string queued_save = saved();
        proxy.set_value( "mp_proxy", "1" );
        control::deserialize( snapshot( queued_save ) );
        proxy.assign_activity( player_activity( activity_id( "ACT_WAIT" ), 1000 ) );
        proxy.set_value( "cph_ai.pending_trade", "partner-owned-offer" );
        proxy.set_value( "cph_ai.pending_trade_id", "partner-owned-operation" );
        proxy.set_value( "cph_ai.pending_trade_source_operation", "partner-owned-source" );
        control::cancel();
        control::stop();
        control::pump_incoming();
        CHECK( response( "status" ).get_int( "queue_length" ) == 0 );
        CHECK( response( "status" ).get_string( "detach_state" ) == "detached" );
        REQUIRE( proxy.activity );
        CHECK( proxy.activity.id() == activity_id( "ACT_WAIT" ) );
        CHECK( proxy.activity.moves_left == 1000 );
        CHECK( proxy.get_value( "cph_ai.bound" ) == "true" );
        CHECK( proxy.get_value( "cph_ai.pending_trade" ) == "partner-owned-offer" );
        CHECK( proxy.get_value( "cph_ai.pending_trade_id" ) == "partner-owned-operation" );
        CHECK( proxy.get_value( "cph_ai.pending_trade_source_operation" ) == "partner-owned-source" );
        CHECK_FALSE( control::pauses_offline_work( proxy ) );
    }

    CHECK( proxy.get_value( "mp_proxy" ) == "1" );
    CHECK( proxy.getID() == id );
    CHECK( proxy.get_moves() == moves );
    CHECK( get_avatar().get_moves() == player_moves );
    CHECK( proxy.all_items_loc().size() == inventory );
    CHECK( proxy.has_amount( itype_id( "bandages" ), 1 ) );
    CHECK( calendar::turn == before );
}

TEST_CASE( "actor_control_request_ack_covers_only_observed_events", "[actor_control][protocol]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    std::string error;
    REQUIRE( control::chat( "The medicine is north, I think.", error ) );
    const JsonObject request = response( "take_request" );
    const JsonObject repeated = response( "take_request" );
    CHECK( child( request, "context" ).str() == child( repeated, "context" ).str() );
    const std::size_t observed_events = request.get_array( "events" ).size();
    REQUIRE( observed_events >= 2 );
    REQUIRE( control::chat( "Another thing happened while you were thinking.", error ) );
    calendar::turn += 1_turns;
    const std::string offered = plan( request, "[]" );
    control::dispatch( "offer_plan", offered, error );
    CHECK( error == "stale_request" );
    const JsonObject fresh = response( "take_request" );
    response( "offer_plan", plan( fresh, "[]" ) );
    const JsonObject next = response( "take_request" );
    REQUIRE( next.get_array( "events" ).size() >= 2 );
    const JsonObject statement = at( next, "events", 0 );
    CHECK( statement.get_string( "kind" ) == "statement" );
    CHECK( statement.get_string( "text" ) == "The medicine is north, I think." );
    CHECK( next.get_array( "requirement_decisions" ).size() == 2 );
    CHECK( child( next, "context" ).get_string( "request_id" ) !=
           child( request, "context" ).get_string( "request_id" ) );
}

TEST_CASE( "actor_control_plan_retry_returns_real_receipts_without_reexecution",
           "[actor_control][protocol][npc]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    const JsonObject request = response( "take_request" );
    const std::string offered = plan( request,
                                      R"([{"id":"rest","action":"wait","args":{"turns":1}}])" );
    response( "offer_plan", offered );
    actor.set_moves( 100 );
    const int player_moves = get_avatar().get_moves();
    const time_point before = calendar::turn;
    REQUIRE( control::act( actor, false ) );
    CHECK( actor.get_moves() == 0 );
    CHECK( calendar::turn == before );
    CHECK( get_avatar().get_moves() == player_moves );
    calendar::turn += 1_turns;
    actor.set_moves( 100 );
    control::act( actor, false );
    const JsonObject duplicate = response( "offer_plan", offered );
    REQUIRE( duplicate.get_array( "receipts" ).size() == 1 );
    CHECK( at( duplicate, "receipts", 0 ).get_string( "state" ) == "succeeded" );
    CHECK( actor.get_moves() == 100 );
    std::string error;
    control::dispatch( "offer_plan", plan( request,
                                           R"([{"id":"rest","action":"wait","args":{"turns":2}}])" ),
                       error );
    CHECK( error == "operation_payload_conflict" );
    CHECK( response( "status" ).get_int( "queue_length" ) == 0 );
}

TEST_CASE( "actor_control_generic_attack_cannot_bypass_personality_switches",
           "[actor_control][social]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    const JsonObject request = response( "take_request" );
    std::string error;
    control::dispatch( "offer_plan", plan( request,
                                           "[{\"id\":\"harm\",\"action\":\"attack\",\"args\":{\"target\":" +
                                           std::to_string( get_avatar().getID().get_value() ) + "}}]" ), error );
    CHECK( error == "behavior_disabled" );
    control::dispatch( "offer_plan", plan( request,
                                           R"([{"id":"cheat","action":"wait","intent":"transaction_fraud","args":{}}])" ), error );
    CHECK( error == "behavior_disabled" );
    CHECK( response( "status" ).get_int( "queue_length" ) == 0 );
}

TEST_CASE( "actor_control_explicit_stop_cancels_queue_and_keeps_binding",
           "[actor_control][lifecycle]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    const JsonObject request = response( "take_request" );
    response( "offer_plan", plan( request, R"([{"id":"rest","action":"wait","args":{}}])" ) );
    actor.set_value( "cph_ai.pending_trade", "{}" );
    actor.set_value( "cph_ai.pending_trade_id", "stale-offer" );
    actor.set_value( "cph_ai.pending_trade_source_operation", "stale-source" );
    control::stop();
    CHECK( control::has_binding() );
    CHECK( control::is_bound( actor ) );
    const JsonObject stopped = response( "status" );
    CHECK( stopped.get_string( "detach_state" ) == "detached" );
    CHECK( stopped.get_int( "queue_length" ) == 0 );
    CHECK( at( stopped, "receipts", 0 ).get_string( "state" ) == "failed" );
    CHECK_FALSE( control::act( actor, false ) );
    CHECK( actor.maybe_get_value( "cph_ai.pending_trade" ) == nullptr );
    CHECK( actor.maybe_get_value( "cph_ai.pending_trade_id" ) == nullptr );
    CHECK( actor.maybe_get_value( "cph_ai.pending_trade_source_operation" ) == nullptr );
}

TEST_CASE( "actor_control_load_epoch_rejects_old_reply_and_unknown_started_work",
           "[actor_control][save]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    const JsonObject old_request = response( "take_request" );
    const std::string old_plan = plan( old_request, "[]" );
    control::deserialize( snapshot( saved() ) );
    std::string error;
    control::dispatch( "offer_plan", old_plan, error );
    CHECK( error == "stale_request" );
    prepare( actor );
    const JsonObject request = response( "take_request" );
    response( "offer_plan", plan( request, R"([{"id":"rest","action":"wait","args":{}}])" ) );
    std::string interrupted = saved();
    const std::size_t start = interrupted.find( "\"started\":false" );
    REQUIRE( start != std::string::npos );
    interrupted.replace( start, std::string( "\"started\":false" ).size(), "\"started\":true" );
    control::deserialize( snapshot( interrupted ) );
    actor.set_moves( 100 );
    CHECK_FALSE( control::act( actor, false ) );
    CHECK( actor.get_moves() == 100 );
    CHECK( response( "status" ).get_string( "control_state" ) == "reconcile_required" );
}

TEST_CASE( "actor_control_future_schema_is_preserved_without_takeover", "[actor_control][save]" )
{
    control_fixture fixture;
    const std::string future =
        R"({"schema_version":7,"new_unknown_field":{"value":"preserve"},"actor_id":51})";
    control::deserialize( snapshot( future ) );
    CHECK_FALSE( control::has_binding() );
    CHECK( child( snapshot( saved() ), "new_unknown_field" ).get_string( "value" ) == "preserve" );
    std::string error;
    control::dispatch( "take_request", "{}", error );
    CHECK( error == "unsupported_state_schema" );
    CHECK( response( "status" ).get_string( "state" ) == "unsupported_schema" );
}

TEST_CASE( "actor_control_native_activity_retains_its_execution_slot", "[actor_control][activity]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    response( "offer_plan", plan( response( "take_request" ),
                                  R"([{"id":"rest","action":"wait","args":{}}])" ) );
    actor.assign_activity( multi_craft_activity_actor() );
    const activity_id original = actor.activity.id();
    actor.set_moves( 100 );
    CHECK_FALSE( control::act( actor, false ) );
    CHECK( actor.activity.id() == original );
    CHECK( actor.get_moves() == 100 );
    CHECK( at( response( "status" ), "receipts", 0 ).get_string( "code" ) == "queued" );
    CHECK_FALSE( control::act( actor, true ) );
    CHECK( actor.activity.id() == original );
    control::stop();
    CHECK( actor.activity.id() == original );
    CHECK( response( "status" ).get_string( "detach_state" ) == "detached" );
}

TEST_CASE( "actor_control_memory_is_subjective_scoped_and_deletable", "[actor_control][memory]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    const std::string actor_id = std::to_string( actor.getID().get_value() );
    response( "sync_memory",
              "{\"version\":\"edited\",\"snapshot\":{\"revision\":\"edited\",\"records\":["
              "{\"id\":\"belief-one\",\"kind\":\"belief\",\"text\":\"There might be medicine north.\","
              "\"context\":{\"actor_id\":" + control::quote( actor_id ) + "}}]}}" );
    REQUIRE( actor.maybe_get_value( "cph_ai.known_information" ) != nullptr );
    const JsonArray known = json_loader::from_string( actor.maybe_get_value(
                                "cph_ai.known_information" )->to_string() ).get_array();
    REQUIRE( known.size() == 1 );
    JsonObject belief = known.get_object( 0 );
    belief.allow_omitted_members();
    CHECK( belief.get_string( "kind" ) == "belief" );
    std::string error;
    control::dispatch( "sync_memory",
                       "{\"version\":\"wrong\",\"snapshot\":{\"revision\":\"wrong\",\"records\":["
                       "{\"id\":\"wrong\",\"kind\":\"belief\",\"text\":\"Not this NPC's knowledge.\","
                       "\"context\":{\"actor_id\":99999999}}]}}", error );
    CHECK( error == "memory_actor_mismatch" );
    response( "sync_memory",
              R"({"version":"deleted","snapshot":{"revision":"deleted","records":[]}})" );
    CHECK( actor.maybe_get_value( "cph_ai.known_information" )->to_string() == "[]" );
    CHECK( actor.maybe_get_value( "cph_ai.cognition" )->to_string() == "[]" );
}

TEST_CASE( "actor_control_idle_world_does_not_trigger_periodic_model_work",
           "[actor_control][runtime]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    response( "offer_plan", plan( response( "take_request" ), "[]" ) );
    calendar::turn += 1_hours;
    std::string error;
    CHECK( control::dispatch( "take_request", "{}", error ) == "null" );
    CHECK( error.empty() );
    for( const char *method : {
             "act", "on_lifecycle", "set_moves", "set_inventory", "advance_time"
         } ) {
        control::dispatch( method, "{}", error );
        CHECK( error == "unknown_method" );
    }
}

TEST_CASE( "actor_control_fallback_preferences_change_spacing_without_world_mutation",
           "[actor_control][memory][npc]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    const npc_attitude attitude = actor.get_attitude();
    const int moves = actor.get_moves();
    const std::string scope = "{\"actor_id\":" + std::to_string( actor.getID().get_value() ) + "}";
    const std::string observed =
        "{\"id\":\"observed\",\"kind\":\"observation\",\"text\":\"I was hurt before.\",\"context\":" + scope
        + "}";
    const std::string growth =
        "{\"id\":\"cautious\",\"kind\":\"growth\",\"text\":\"I prefer more space.\",\"context\":" + scope +
        ",\"source_ids\":[\"observed\"],\"confidence\":1,\"preferences\":{\"caution\":0.9}}";
    response( "sync_memory", "{\"version\":\"grown\",\"snapshot\":{\"revision\":\"grown\",\"records\":["
              + observed + "," + growth + "]}}" );
    CHECK( control::following_distance( actor, 4 ) == 5 );
    CHECK( control::following_distance( actor, 2 ) == 2 );
    CHECK( control::following_distance( actor, 1 ) == 1 );
    CHECK( actor.get_attitude() == attitude );
    CHECK( actor.get_moves() == moves );
    npc &other = fixture.companion();
    CHECK( control::following_distance( other, 4 ) == 4 );
    response( "sync_memory",
              R"({"version":"forgotten","snapshot":{"revision":"forgotten","records":[]}})" );
    CHECK( control::following_distance( actor, 4 ) == 4 );
}

TEST_CASE( "actor_control_wire_window_limits_bytes_and_acknowledges_only_its_prefix",
           "[actor_control][protocol]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    std::string text;
    for( int i = 0; i < 4096; ++i ) {
        text += "\xf0\xa0\x80\x80";
    }
    std::string error;
    for( int i = 0; i < 80; ++i ) {
        REQUIRE( control::chat( text, error ) );
    }
    const std::string wire = control::dispatch( "take_request", "{}", error );
    REQUIRE( error.empty() );
    REQUIRE( wire.size() <= 1048576 - 4096 );
    const JsonObject request = snapshot( wire );
    const JsonArray events = request.get_array( "events" );
    REQUIRE( events.size() > 0 );
    CHECK( events.size() < 80 );
    const JsonObject last = at( request, "events", events.size() - 1 );
    const int64_t watermark = last.get_int64( "sequence" );
    CHECK( child( request, "context" ).get_int64( "event_watermark" ) == watermark );
    REQUIRE( control::chat( "Arrived after the pending request.", error ) );
    const JsonObject fresh = response( "take_request" );
    CHECK( child( fresh, "context" ).get_string( "request_id" ) !=
           child( request, "context" ).get_string( "request_id" ) );
    const std::string status_wire = control::status();
    CHECK( status_wire.size() < 1048576 - 4096 );
    CHECK( snapshot( status_wire ).get_int( "transcript_omitted" ) > 0 );
    response( "offer_plan", plan( fresh, "[]" ) );
    const JsonObject remaining = response( "take_request" );
    REQUIRE( remaining.get_array( "events" ).size() > 0 );
    // An empty plan handles no player messages. Their bounded prefix is kept.
    CHECK( at( remaining, "events", 0 ).get_int64( "sequence" ) == 2 );
    CHECK( snapshot( saved() ).get_array( "checkpoint_delta" ).size() == 1 );
}

TEST_CASE( "actor_control_receipt_event_identity_and_goal_source_match_runtime_journal",
           "[actor_control][memory][social]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    response( "offer_plan", plan( response( "take_request" ),
                                  R"([{"id":"goal","action":"propose_own_goals","args":{"text":"Find medicine safely."}}])" ) );
    actor.set_moves( 100 );
    REQUIRE( control::act( actor, false ) );
    const JsonObject request = response( "take_request" );
    std::string receipt_id;
    std::string receipt_data;
    bool found_goal = false;
    for( const JsonObject &event : request.get_array( "events" ) ) {
        event.allow_omitted_members();
        if( event.get_string( "kind" ) == "receipt" ) {
            receipt_data = child( event, "data" ).str();
            receipt_id = "receipt." + child( event, "data" ).get_string( "operation_id" );
            CHECK( event.get_string( "id" ) == receipt_id );
        } else if( event.get_string( "kind" ) == "goal" ) {
            found_goal = true;
            REQUIRE_FALSE( receipt_id.empty() );
            REQUIRE( event.get_array( "source_ids" ).size() == 1 );
            CHECK( event.get_array( "source_ids" ).get_string( 0 ) == receipt_id );
            CHECK( child( event, "data" ).str() == receipt_data );
        }
    }
    CHECK( found_goal );
    const JsonObject debug = child( response( "status", "{\"include_debug\":true}" ), "debug" );
    CHECK( child( debug, "social_state" ).get_string( "last_social_action" ) ==
           "propose_own_goals" );
    const JsonObject actual_receipt = at( response( "status" ), "receipts", 0 );
    const std::string operation = actual_receipt.get_string( "operation_id" );
    const JsonObject selected = response( "status", "{\"operation_id\":" + control::quote( operation ) +
                                          "}" );
    REQUIRE( selected.get_array( "receipts" ).size() == 1 );
    CHECK( at( selected, "receipts", 0 ).get_string( "operation_id" ) == operation );
}

TEST_CASE( "actor_control_offline_restore_redelivers_acknowledged_checkpoint_delta",
           "[actor_control][save][memory]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    std::string error;
    REQUIRE( control::chat( "Remember this even if the next save has no external checkpoint.",
                            error ) );
    const JsonObject request = response( "take_request" );
    const JsonArray original = request.get_array( "events" );
    response( "offer_plan", plan( request, "[]" ) );
    const std::string stored = saved();
    CHECK( snapshot( stored ).get_array( "events" ).size() == original.size() - 1 );
    CHECK( snapshot( stored ).get_array( "checkpoint_delta" ).size() == 1 );
    control::deserialize( snapshot( stored ) );
    response( "sync_memory",
              R"({"version":"test-memory","snapshot":{"revision":"test-memory","records":[]}})" );
    const JsonArray replay = response( "take_request" ).get_array( "events" );
    REQUIRE( replay.size() == original.size() );
    for( std::size_t i = 0; i < original.size(); ++i ) {
        JsonObject before = original.get_object( i );
        JsonObject after = replay.get_object( i );
        before.allow_omitted_members();
        after.allow_omitted_members();
        CHECK( after.get_string( "id" ) == before.get_string( "id" ) );
        CHECK( after.get_int64( "sequence" ) == before.get_int64( "sequence" ) );
    }
}

TEST_CASE( "actor_control_unconfirmed_native_save_freezes_queue_without_a_memory_checkpoint",
           "[actor_control][save]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    response( "offer_plan", plan( response( "take_request" ),
                                  R"([{"id":"wait","action":"wait","args":{}}])" ) );
    std::string stored = saved();
    const std::string empty_nonce = "\"save_nonce\":\"\"";
    const std::size_t offset = stored.find( empty_nonce );
    REQUIRE( offset != std::string::npos );
    stored.replace( offset, empty_nonce.size(), "\"save_nonce\":" +
                    control::quote( control::new_identity() ) );
    control::deserialize( snapshot( stored ) );
    const JsonObject restored = response( "status" );
    CHECK( restored.get_string( "control_state" ) == "reconcile_required" );
    CHECK( restored.get_string( "state" ) == "paused" );
    CHECK( restored.get_int( "queue_length" ) == 1 );
    CHECK( restored.get_member( "saved_checkpoint" ).test_null() );
    actor.set_moves( 100 );
    CHECK_FALSE( control::act( actor, false ) );
    CHECK( actor.get_moves() == 100 );
}

TEST_CASE( "actor_control_speech_uses_a_plan_slot_and_debug_is_opt_in",
           "[actor_control][protocol][social]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    const JsonObject request = response( "take_request" );
    const std::string steps =
        R"([{"id":"1","action":"wait","args":{}},{"id":"2","action":"wait","args":{}},{"id":"3","action":"wait","args":{}},{"id":"4","action":"wait","args":{}},{"id":"5","action":"wait","args":{}}])";
    std::string offered = plan( request, steps );
    offered.pop_back();
    offered += ",\"speech\":\"I will wait.\"}";
    std::string error;
    control::dispatch( "offer_plan", offered, error );
    CHECK( error == "plan_not_allowed" );
    CHECK( response( "status" ).get_int( "queue_length" ) == 0 );
    CHECK_FALSE( response( "status" ).has_member( "debug" ) );
    response( "offer_plan", plan( request,
                                  R"([{"id":"rest","action":"wait","intent":"argue","args":{}}])" ) );
    const JsonObject debug = child( response( "status", "{\"include_debug\":true}" ), "debug" );
    REQUIRE( debug.get_array( "current_queue" ).size() == 1 );
    const JsonObject current = at( debug, "current_queue", 0 );
    CHECK( current.get_string( "intent" ) == "argue" );
    CHECK( current.get_string( "phase" ) == "queued" );
    CHECK_FALSE( current.get_bool( "started" ) );
}

TEST_CASE( "actor_control_mod_removal_contract_reports_actual_dependency_blockers",
           "[actor_control][lifecycle]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    const JsonObject removal = response( "remove_mod_check" );
    CHECK_FALSE( removal.get_bool( "safe_to_remove" ) );
    REQUIRE( removal.get_array( "world_dependencies" ).size() > 0 );
    CHECK( removal.get_array( "world_dependencies" ).get_string( 0 ) == "control_not_detached" );
}

TEST_CASE( "actor_control_cancel_revokes_pending_native_trade_references",
           "[actor_control][lifecycle][trade]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    actor.set_value( "cph_ai.pending_trade", "{}" );
    actor.set_value( "cph_ai.pending_trade_id", "cancelled-offer" );
    actor.set_value( "cph_ai.pending_trade_source_operation", "cancelled-source" );
    control::cancel();
    CHECK( actor.maybe_get_value( "cph_ai.pending_trade" ) == nullptr );
    CHECK( actor.maybe_get_value( "cph_ai.pending_trade_id" ) == nullptr );
    CHECK( actor.maybe_get_value( "cph_ai.pending_trade_source_operation" ) == nullptr );
    CHECK( response( "status" ).get_string( "detach_state" ) == "attached" );
}

TEST_CASE( "actor_control_stopped_off_bubble_identity_does_not_pause_native_work",
           "[actor_control][lifecycle][npc]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    CHECK( control::pauses_offline_work( actor ) );
    actor.on_unload();
    g->remove_npc( actor.getID() );
    REQUIRE_FALSE( actor.is_active() );
    REQUIRE( g->find_npc( actor.getID() ) == &actor );
    const int original_moves = actor.get_moves();
    control::stop();
    CHECK( response( "status" ).get_string( "detach_state" ) == "detached" );
    CHECK( response( "status" ).get_string( "state" ) == "detached" );
    CHECK( control::is_bound( actor ) );
    CHECK_FALSE( control::pauses_offline_work( actor ) );
    CHECK( actor.maybe_get_value( "cph_ai.bound" ) == nullptr );
    CHECK( actor.get_moves() == original_moves );
    std::string error;
    CHECK_FALSE( control::chat( "This cannot reach an off-bubble actor.", error ) );
    CHECK( error == "actor_unavailable" );
}

TEST_CASE( "actor_control_unknown_off_bubble_activity_waits_for_safe_handoff_even_when_disabled",
           "[actor_control][lifecycle][activity]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    response( "offer_plan", plan( response( "take_request" ),
                                  R"([{"id":"work","action":"craft","args":{"recipe":"bandages","batch":1}}])" ) );
    std::string stored = saved();
    const std::size_t start = stored.find( "\"started\":false" );
    REQUIRE( start != std::string::npos );
    stored.replace( start, std::string( "\"started\":false" ).size(), "\"started\":true" );
    control::deserialize( snapshot( stored ) );
    const std::string operation = at( snapshot( stored ), "queue", 0 ).get_string( "id" );
    actor.set_value( "cph_ai.craft_step", operation );
    actor.assign_activity( multi_craft_activity_actor() );
    const activity_id original = actor.activity.id();
    actor.on_unload();
    g->remove_npc( actor.getID() );
    const shared_ptr_fast<npc> unloaded = overmap_buffer.remove_npc( actor.getID() );
    REQUIRE( unloaded.get() == &actor );
    REQUIRE( g->find_npc( actor.getID() ) == nullptr );
    const int original_moves = actor.get_moves();
    control::enable( false );
    CHECK( response( "status" ).get_string( "detach_state" ) == "detach_pending" );
    CHECK( response( "status" ).get_int( "queue_length" ) == 1 );
    CHECK( control::pauses_offline_work( actor ) );
    CHECK( actor.activity.id() == original );
    CHECK( actor.get_moves() == original_moves );
    overmap_buffer.insert_npc( unloaded );
    control::pump_incoming();
    if( actor.activity ) {
        CHECK( response( "status" ).get_string( "detach_state" ) == "detach_pending" );
        actor.activity.set_to_null();
        control::pump_incoming();
    }
    CHECK( response( "status" ).get_string( "detach_state" ) == "detached" );
    CHECK( response( "status" ).get_int( "queue_length" ) == 0 );
    CHECK_FALSE( control::pauses_offline_work( actor ) );
    CHECK( actor.get_moves() == original_moves );
}

TEST_CASE( "actor_control_confirmed_native_death_ends_control_without_replacement",
           "[actor_control][lifecycle][npc]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    const JsonObject request = response( "take_request" );
    response( "offer_plan", plan( request, R"([{"id":"rest","action":"wait","args":{}}])" ) );
    const character_id original = actor.getID();
    actor.die( &get_map(), nullptr );
    REQUIRE( actor.is_dead() );
    const JsonObject dead = response( "status" );
    CHECK( dead.get_string( "state" ) == "dead" );
    CHECK( dead.get_string( "detach_state" ) == "detached" );
    CHECK( dead.get_int( "queue_length" ) == 0 );
    CHECK( control::is_bound( actor ) );
    CHECK_FALSE( control::pauses_offline_work( actor ) );
    CHECK( dead.get_int( "actor_id" ) == original.get_value() );
    npc &other = fixture.companion();
    std::string error;
    CHECK_FALSE( control::bind( other, "test-profile", error ) );
    CHECK( error == "fixed_binding_conflict" );
    control::dispatch( "configure", "{}", error );
    CHECK( error == "actor_dead" );
}

TEST_CASE( "actor_control_scene_change_invalidates_plans_without_restoring_memory",
           "[actor_control][lifecycle][dimension]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    const JsonObject request = response( "take_request" );
    const JsonObject before = child( response( "status" ), "context" );
    const time_point time_before = calendar::turn;
    const int moves_before = actor.get_moves();
    SECTION( "late model reply is rejected" ) {
        control::on_scene_change();
        std::string error;
        control::dispatch( "offer_plan", plan( request,
                                               R"([{"id":"old","action":"wait","args":{}}])" ), error );
        CHECK( error == "stale_request" );
        const JsonObject fresh = response( "take_request" );
        CHECK( child( fresh, "context" ).get_string( "request_id" ) !=
               child( request, "context" ).get_string( "request_id" ) );
    }
    SECTION( "accepted source-scene commands are cancelled" ) {
        response( "offer_plan", plan( request,
                                      R"([{"id":"first","action":"wait","args":{"turns":1}},{"id":"next","action":"wait","args":{}}])" ) );
        actor.set_moves( 100 );
        REQUIRE( control::act( actor, false ) );
        control::on_scene_change();
        const JsonObject result = response( "status" );
        CHECK( result.get_int( "queue_length" ) == 0 );
        REQUIRE( result.get_array( "receipts" ).size() == 2 );
        for( const JsonObject &receipt : result.get_array( "receipts" ) ) {
            receipt.allow_omitted_members();
            CHECK( receipt.get_string( "code" ) == "scene_changed" );
        }
    }
    const JsonObject after = child( response( "status" ), "context" );
    CHECK( after.get_string( "load_epoch" ) == before.get_string( "load_epoch" ) );
    CHECK( after.get_string( "memory_version" ) == before.get_string( "memory_version" ) );
    CHECK( after.get_string( "request_id" ) != before.get_string( "request_id" ) );
    CHECK( calendar::turn == time_before );
    if( response( "status" ).get_array( "receipts" ).empty() ) {
        CHECK( actor.get_moves() == moves_before );
    }
}

TEST_CASE( "actor_control_scene_change_retains_native_craft_progress",
           "[actor_control][lifecycle][dimension][activity]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    response( "offer_plan", plan( response( "take_request" ),
                                  R"([{"id":"work","action":"craft","args":{"recipe":"bandages","batch":1}},{"id":"later","action":"wait","args":{}}])" ) );
    std::string stored = saved();
    const std::size_t start = stored.find( "\"started\":false" );
    REQUIRE( start != std::string::npos );
    stored.replace( start, std::string( "\"started\":false" ).size(), "\"started\":true" );
    control::deserialize( snapshot( stored ) );
    const std::string operation = at( snapshot( stored ), "queue", 0 ).get_string( "id" );
    actor.set_value( "cph_ai.craft_step", operation );
    actor.assign_activity( multi_craft_activity_actor() );
    const activity_id activity_before = actor.activity.id();
    const int moves_before = actor.get_moves();
    control::on_scene_change();
    const JsonObject result = response( "status" );
    CHECK( result.get_int( "queue_length" ) == 1 );
    CHECK( actor.activity.id() == activity_before );
    CHECK( actor.maybe_get_value( "cph_ai.craft_step" )->to_string() == operation );
    CHECK( actor.get_moves() == moves_before );
    CHECK( at( snapshot( saved() ), "queue", 0 ).get_string( "id" ) == operation );
}

#ifdef __linux__
TEST_CASE( "actor_control_prepared_checkpoint_marker_is_rolled_back_without_retiring_events",
           "[actor_control][save][memory]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    response( "offer_plan", plan( response( "take_request" ), "[]" ) );
    const std::size_t delta = snapshot( saved() ).get_array( "checkpoint_delta" ).size();
    REQUIRE( delta > 0 );
    REQUIRE( world_generator );
    REQUIRE( world_generator->active_world );
    const std::filesystem::path root = PATH_INFO::world_base_save_path().get_unrelative_path();
    std::string error;
    REQUIRE( cata::actor_control::save_transaction::begin( root, error ) );
    on_out_of_scope release_transaction( [&error]() {
        cata::actor_control::save_transaction::finish( false, error );
        control::after_save( false );
    } );
    control::before_save();
    const JsonObject stored = snapshot( saved() );
    const std::filesystem::path marker = root /
                                         ( ".cph-ai-checkpoint-" + stored.get_string( "world_id" ) + "-" +
                                           stored.get_string( "branch_id" ) + "-" +
                                           std::to_string( actor.getID().get_value() ) + "-" +
                                           stored.get_string( "save_nonce" ) + ".json" );
    REQUIRE( control::prepare_save_commit() );
    CHECK( control::prepare_save_commit() );
    CHECK( std::filesystem::exists( marker ) );
    CHECK( snapshot( saved() ).get_array( "checkpoint_delta" ).size() == delta );
    CHECK( response( "status" ).get_member( "saved_checkpoint" ).test_null() );
    REQUIRE( cata::actor_control::save_transaction::finish( false, error ) );
    control::after_save( false );
    CHECK_FALSE( std::filesystem::exists( marker ) );
    CHECK( snapshot( saved() ).get_array( "checkpoint_delta" ).size() == delta );
}
#endif

TEST_CASE( "actor_control_imports_subjective_growth_without_importing_physical_facts",
           "[actor_control][memory]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    const std::string scope = child( response( "status" ), "context" ).str();
    const std::string record =
        "{\"id\":\"prior-growth\",\"kind\":\"growth\",\"text\":\"I learned caution.\",\"context\":" +
        scope + ",\"origin_context\":{\"world_id\":\"previous-world\",\"actor_id\":\"7\"},"
        "\"imported\":true,\"continuity\":\"imported_experience_not_current_world_fact\","
        "\"source_ids\":[\"previous-observation\"],\"preferences\":{\"caution\":0.9},\"confidence\":1}";
    const auto offer = [&scope]( const std::string & entry, bool root_scope ) {
        return "{\"version\":\"imported\",\"snapshot\":{\"revision\":\"imported\"," +
               ( root_scope ? "\"context\":" + scope + "," : std::string() ) +
               "\"records\":[" + entry + "]}}";
    };
    response( "sync_memory", offer( record, true ) );
    CHECK( control::following_distance( actor, 4 ) == 5 );
    const int moves = actor.get_moves();
    std::string forged = record;
    const std::size_t kind = forged.find( "\"kind\":\"growth\"" );
    REQUIRE( kind != std::string::npos );
    forged.replace( kind, std::string( "\"kind\":\"growth\"" ).size(), "\"kind\":\"receipt\"" );
    std::string error;
    control::dispatch( "sync_memory", offer( forged, true ), error );
    CHECK( error == "invalid_memory_import" );
    control::dispatch( "sync_memory", offer( record, false ), error );
    CHECK( error == "invalid_memory_import" );
    control::dispatch( "sync_memory",
                       "{\"version\":\"old\",\"snapshot\":{\"revision\":\"old\","
                       "\"context\":{\"world_id\":\"previous-world\"},\"records\":[]}}", error );
    CHECK( error == "memory_scope_mismatch" );
    CHECK( control::following_distance( actor, 4 ) == 5 );
    CHECK( actor.get_moves() == moves );
}

TEST_CASE( "actor_control_trade_permission_checks_actual_hostile_beneficiary",
           "[actor_control][social][trade]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    npc &other = fixture.companion();
    actor.worn.wear_item( actor, item( itype_id( "debug_backpack" ) ), false, false );
    other.worn.wear_item( other, item( itype_id( "debug_backpack" ) ), false, false );
    actor.rules.set_flag( ally_rule::forbid_engage );
    other.rules.set_flag( ally_rule::forbid_engage );
    item stock( itype_id( "rock" ), calendar::turn );
    stock.set_owner( actor );
    actor.i_add( std::move( stock ) );
    prepare( actor );
    const bool enabled = GENERATE( false, true );
    std::string restricted = policy;
    if( !enabled ) {
        const std::string setting = "\"aid_conflicting_party\":true";
        restricted.replace( restricted.find( setting ), setting.size(),
                            "\"aid_conflicting_party\":false" );
    }
    response( "configure", "{\"profile_id\":\"test-profile\",\"personality\":" + restricted +
              ",\"limits\":{\"max_steps\":5,\"cooldown\":0}}" );
    // Allegiance changes after acceptance must be checked again at execution.
    const JsonObject request = response( "take_request" );
    response( "offer_plan", plan( request,
                                  "[{\"id\":\"gift\",\"action\":\"trade\",\"args\":{\"target\":" +
                                  std::to_string( other.getID().get_value() ) +
                                  ",\"give\":[{\"item_type\":\"rock\",\"count\":1}],\"take\":[]}}]" ) );
    other.set_attitude( NPCATT_KILL );
    REQUIRE( other.is_enemy() );
    actor.set_moves( 100 );
    control::act( actor, false );
    const JsonObject receipt = at( response( "status" ), "receipts", 0 );
    CHECK( receipt.get_string( "code" ) == ( enabled ? "trade_committed" : "behavior_disabled" ) );
    CHECK( actor.amount_of( itype_id( "rock" ) ) == ( enabled ? 0 : 1 ) );
    CHECK( other.amount_of( itype_id( "rock" ) ) == ( enabled ? 1 : 0 ) );
    CHECK( actor.rules.has_flag( ally_rule::forbid_engage ) );
}

TEST_CASE( "actor_control_player_trade_confirmation_rechecks_take_beneficiary_permission",
           "[actor_control][social][trade]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    actor.worn.wear_item( actor, item( itype_id( "debug_backpack" ) ), false, false );
    get_avatar().worn.wear_item( get_avatar(), item( itype_id( "debug_backpack" ) ), false, false );
    item rock( itype_id( "rock" ), calendar::turn );
    rock.set_owner( get_avatar() );
    get_avatar().i_add( std::move( rock ) );
    prepare( actor );
    response( "offer_plan", plan( response( "take_request" ),
                                  "[{\"id\":\"take\",\"action\":\"trade\",\"args\":{\"target\":" +
                                  std::to_string( get_avatar().getID().get_value() ) +
                                  ",\"give\":[],\"take\":[{\"item_type\":\"rock\",\"count\":1}]}}]" ) );
    actor.set_moves( 100 );
    control::act( actor, false );
    REQUIRE( actor.maybe_get_value( "cph_ai.pending_trade" ) );
    std::string restricted = policy;
    const std::string setting = "\"aid_conflicting_party\":true";
    restricted.replace( restricted.find( setting ), setting.size(),
                        "\"aid_conflicting_party\":false" );
    response( "configure", "{\"profile_id\":\"test-profile\",\"personality\":" + restricted +
              ",\"limits\":{\"max_steps\":5,\"cooldown\":0}}" );
    actor.set_attitude( NPCATT_KILL );
    REQUIRE( actor.is_enemy() );
    const int before = actor.get_moves();
    CHECK( control::NpcExecutionAdapter::resolve_player_trade( actor,
            true ).code == "behavior_disabled" );
    CHECK( actor.amount_of( itype_id( "rock" ) ) == 0 );
    CHECK( get_avatar().amount_of( itype_id( "rock" ) ) == 1 );
    CHECK( actor.get_moves() == before );
}

TEST_CASE( "actor_control_refusal_is_durable_and_keeps_unaddressed_messages_pending",
           "[actor_control][social][save]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    std::string error;
    REQUIRE( control::chat( "Gather a rock for me.", error ) );
    REQUIRE( control::chat( "Another independent request.", error ) );
    const JsonObject request = response( "take_request" );
    const std::string requirement = at( request, "requirement_decisions",
                                        0 ).get_string( "requirement_id" );
    const std::string refuse = "{\"id\":\"no\",\"action\":\"refuse\",\"requirement_id\":" +
                               control::quote( requirement ) + ",\"args\":{\"text\":\"I refuse that request.\"}}";
    const tripoint_abs_ms location = actor.pos_abs();
    const std::string gather = "{\"id\":\"get\",\"action\":\"gather\",\"requirement_id\":" +
                               control::quote( requirement ) + ",\"args\":{\"item_type\":\"rock\",\"x\":" +
                               std::to_string( location.x() ) + ",\"y\":" + std::to_string( location.y() ) +
                               ",\"z\":" + std::to_string( location.z() ) + "}}";
    control::dispatch( "offer_plan", plan( request, "[" + refuse + "," + gather + "]" ), error );
    CHECK( error == "contradictory_requirement_decision" );
    CHECK( response( "status" ).get_int( "queue_length" ) == 0 );
    response( "offer_plan", plan( request, "[" + refuse + "]" ) );
    actor.set_moves( 100 );
    REQUIRE( control::act( actor, false ) );
    const JsonObject result = response( "status" );
    CHECK( at( result, "requirement_decisions", 0 ).get_string( "decision" ) == "refused" );
    CHECK( at( result, "requirement_decisions", 1 ).get_string( "decision" ) == "pending" );
    CHECK( snapshot( saved() ).get_array( "events" ).size() > 0 );
    control::deserialize( snapshot( saved() ) );
    response( "sync_memory",
              R"({"version":"restored","snapshot":{"revision":"restored","records":[]}})" );
    const JsonObject restored = response( "take_request" );
    CHECK( at( restored, "requirement_decisions", 0 ).get_string( "decision" ) == "refused" );
    control::dispatch( "offer_plan", plan( restored, "[" + gather + "]" ), error );
    CHECK( error == "requirement_refused" );
    control::dispatch( "offer_plan", plan( restored, R"([{"id":"get","action":"wait","args":{}}])" ),
                       error );
    CHECK( error == "requirement_association_required" );
    control::dispatch( "offer_plan", plan( restored,
                                           R"([{"id":"no","action":"refuse","args":{"text":"No."}}])" ), error );
    CHECK( error == "refusal_requires_requirement" );
    response( "offer_plan", plan( restored,
                                  R"([{"id":"own","action":"wait","intent":"propose_own_goals","args":{}}])" ) );
}

TEST_CASE( "actor_control_linked_casual_speech_does_not_accept_message_contents",
           "[actor_control][social]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    std::string error;
    REQUIRE( control::chat( "This is a belief, not an instruction.", error ) );
    const JsonObject request = response( "take_request" );
    const std::string requirement = at( request, "requirement_decisions",
                                        0 ).get_string( "requirement_id" );
    response( "offer_plan", plan( request,
                                  "[{\"id\":\"reply\",\"action\":\"talk\",\"requirement_id\":" +
                                  control::quote( requirement ) + ",\"args\":{\"target\":" +
                                  std::to_string( get_avatar().getID().get_value() ) +
                                  ",\"text\":\"I heard you.\"}}]" ) );
    actor.set_moves( 100 );
    REQUIRE( control::act( actor, false ) );
    CHECK( at( response( "status" ), "requirement_decisions",
               0 ).get_string( "decision" ) == "pending" );
    CHECK_FALSE( actor.maybe_get_value( "cph_ai.commitment" ) );
}

TEST_CASE( "actor_control_cancel_retains_completed_native_craft_output_receipt",
           "[actor_control][lifecycle][crafting]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    actor.worn.wear_item( actor, item( itype_id( "debug_backpack" ) ), false, false );
    const recipe_id recipe( "bandages_makeshift" );
    actor.learn_recipe( &recipe.obj() );
    item sheet( itype_id( "sheet_cotton" ), calendar::turn );
    sheet.set_owner( actor );
    actor.i_add( std::move( sheet ) );
    prepare( actor );
    response( "offer_plan", plan( response( "take_request" ),
                                  R"([{"id":"craft","action":"craft","args":{"recipe":"bandages_makeshift"}}])" ) );
    actor.set_moves( 100 );
    REQUIRE( control::act( actor, false ) );
    REQUIRE( actor.activity );
    process_activity( actor );
    REQUIRE_FALSE( actor.activity );
    REQUIRE( native_amount( actor, "bandages_makeshift" ) == 2 );
    actor.set_moves( 0 );
    control::cancel();
    const JsonObject result = response( "status" );
    CHECK( result.get_int( "queue_length" ) == 0 );
    const JsonObject receipt = at( result, "receipts", 0 );
    CHECK( receipt.get_string( "state" ) == "succeeded" );
    CHECK( receipt.get_string( "code" ) == "crafted" );
    REQUIRE( child( receipt, "detail" ).get_array( "produced" ).size() > 0 );
    CHECK( native_amount( actor, "bandages_makeshift" ) == 2 );
}

TEST_CASE( "actor_control_new_chat_during_native_craft_retains_completed_work",
           "[actor_control][lifecycle][crafting][social]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    actor.worn.wear_item( actor, item( itype_id( "debug_backpack" ) ), false, false );
    const recipe_id recipe( "bandages_makeshift" );
    actor.learn_recipe( &recipe.obj() );
    item sheet( itype_id( "sheet_cotton" ), calendar::turn );
    sheet.set_owner( actor );
    actor.i_add( std::move( sheet ) );
    prepare( actor );
    response( "offer_plan", plan( response( "take_request" ),
                                  R"([{"id":"craft","action":"craft","args":{"recipe":"bandages_makeshift"}}])" ) );
    actor.set_moves( 100 );
    REQUIRE( control::act( actor, false ) );
    REQUIRE( actor.activity );
    std::string error;
    REQUIRE( control::chat( "Another question while you work.", error ) );
    process_activity( actor );
    REQUIRE_FALSE( actor.activity );
    REQUIRE( native_amount( actor, "bandages_makeshift" ) == 2 );
    actor.set_moves( 100 );
    control::act( actor, false );
    const JsonObject result = response( "status" );
    CHECK( result.get_int( "queue_length" ) == 0 );
    CHECK( at( result, "receipts", 0 ).get_string( "state" ) == "succeeded" );
    CHECK( at( result, "receipts", 0 ).get_string( "code" ) == "crafted" );
    CHECK( at( result, "requirement_decisions", 0 ).get_string( "decision" ) == "pending" );
    CHECK( native_amount( actor, "bandages_makeshift" ) == 2 );
}

TEST_CASE( "actor_control_reset_discards_previous_world_requirement_decisions",
           "[actor_control][social][save]" )
{
    control_fixture fixture;
    npc &actor = fixture.companion();
    prepare( actor );
    std::string error;
    REQUIRE( control::chat( "Gather a rock in this world.", error ) );
    const JsonObject original = response( "take_request" );
    const std::string requirement = at( original, "requirement_decisions",
                                        0 ).get_string( "requirement_id" );
    const std::string refusal = "[{\"id\":\"no\",\"action\":\"refuse\",\"requirement_id\":" +
                                control::quote( requirement ) + ",\"args\":{\"text\":\"I refuse.\"}}]";
    response( "offer_plan", plan( original, refusal ) );
    actor.set_moves( 100 );
    REQUIRE( control::act( actor, false ) );
    CHECK( at( response( "status" ), "requirement_decisions",
               0 ).get_string( "decision" ) == "refused" );
    const std::string previous_world = child( original, "context" ).get_string( "world_id" );
    control::reset();
    control::enable( true );
    prepare( actor );
    const JsonObject fresh = response( "take_request" );
    CHECK( child( fresh, "context" ).get_string( "world_id" ) != previous_world );
    CHECK( fresh.get_array( "requirement_decisions" ).empty() );
    CHECK( snapshot( saved() ).get_array( "requirement_decisions" ).empty() );
    control::dispatch( "offer_plan", plan( fresh, refusal ), error );
    CHECK( error == "unknown_requirement" );
    response( "offer_plan", plan( fresh, R"([{"id":"new-world","action":"wait","args":{}}])" ) );
    CHECK( response( "status" ).get_int( "queue_length" ) == 1 );
}
