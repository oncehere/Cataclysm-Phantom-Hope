#include "actor_control.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <deque>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "actor_control_bridge.h"
#include "actor_control_protocol.h"
#include "actor_control_protocol_generated.h"
#include "avatar.h"
#include "calendar.h"
#include "cata_utility.h"
#include "character_id.h"
#include "flexbuffer_json.h"
#include "game.h"
#include "json.h"
#include "json_loader.h"
#include "math_parser_diag_value.h"
#include "mod_manager.h"
#include "mp_gamestate.h"
#include "npc.h"
#include "npc_execution_adapter.h"
#include "path_info.h"
#include "player_activity.h"
#include "type_id.h"
#include "worldfactory.h"

namespace cata::actor_control
{
namespace
{
using clock_type = std::chrono::steady_clock;
constexpr std::size_t maximum_history = 512;
constexpr std::size_t maximum_events = 4096;
constexpr std::size_t maximum_transcript = 128;
constexpr std::size_t maximum_message = 1048576;
constexpr std::size_t envelope_headroom = 4096;
constexpr std::size_t maximum_event_bytes = 16 * maximum_message;
const char default_policy[] =
    R"({"schema_version":1,"applies_to":"bound_companion_only","expression_policy":"natural_with_intent_checks","traits":{"honesty":0.45,"self_interest":0.65,"commitment":0.55,"caution":0.6},"social_behavior":{"refuse":true,"argue":true,"propose_own_goals":true,"deception":{"enabled":true,"lie_in_dialogue":true,"conceal_information":true,"false_promise":true,"transaction_fraud":false},"betrayal":{"enabled":true,"break_commitment":true,"aid_conflicting_party":true,"disclose_known_information":true,"leave_group":false,"misappropriate_items":false,"sabotage":false,"attack_player":false,"attack_allies":false}}})";

struct requirement_decision {
    std::int64_t source_sequence = 0;
    std::string decision = "pending";
    std::string operation_id;
    std::string text;
};

struct pending_step {
    action_step step;
    std::string from_step;
    bool started = false;
    bool restored = false;
};

// Constant-initialized, trivially destructible: this flag remains safe to read
// after controller's destructor when the global game tears down in another TU.
bool controller_alive = false;

struct controller {
    controller() {
        controller_alive = true;
    }
    ~controller() {
        controller_alive = false;
    }
    bool enabled = false;
    bool paused = false;
    bool authenticated = false;
    bool was_connected = false;
    bool cognition_stale = true;
    bool debug = false;
    bool decision_trigger = false;
    bool chat_trigger = false;
    bool checkpoint_requested = false;
    bool save_commit_prepared = false;
    bool save_commit_attempted = false;
    int actor_id = -1;
    int max_steps = 5;
    int cooldown = 10;
    std::string profile_id;
    std::string world_id = new_identity();
    std::string branch_id = new_identity();
    std::string load_epoch = new_identity();
    std::string request_id = new_identity();
    std::string request_context;
    std::string request_payload;
    std::string policy_version = new_identity();
    std::string memory_version;
    std::string personality = default_policy;
    std::string cognition = "{}";
    std::string control_state = "unbound";
    std::string detach_state = "detached";
    std::string saved_checkpoint = "null";
    std::string saved_memory_context = "null";
    std::string checkpoint_context;
    std::string pending_checkpoint = "null";
    std::string save_nonce;
    std::string future_payload;
    std::string last_error;
    std::string observation_signature;
    std::int64_t event_watermark = 0;
    std::int64_t acknowledged = 0;
    std::deque<std::string> events;
    // ACK only retires the planning delivery. Until a complete game save
    // confirms an external memory checkpoint, keep its replay delta as well.
    std::deque<std::string> checkpoint_delta;
    std::size_t event_bytes = 0;
    std::deque<pending_step> queue;
    std::map<std::string, requirement_decision> requirement_decisions;
    std::map<std::string, std::string> receipts;
    std::map<std::string, std::string> accepted_plans;
    std::deque<std::string> receipt_order;
    std::deque<std::string> transcript;
    clock_type::time_point accepted_at {};
    clock_type::time_point connection_at {};
    loopback_bridge bridge;
};

controller state;

JsonObject read_object( const std::string &text )
{
    JsonObject object = json_loader::from_string( text ).get_object();
    // These are wire/state snapshots, not authored game definitions. Report
    // only bounded error codes; the loader's omitted-member diagnostics would
    // otherwise print entire private dialogue/memory or credentials.
    object.allow_omitted_members();
    return object;
}

JsonObject subobject( const JsonObject &parent, const std::string &key )
{
    JsonObject object = parent.get_object( key );
    object.allow_omitted_members();
    return object;
}

void write_value( JsonOut &out, const JsonValue &value )
{
    if( value.test_object() ) {
        out.start_object();
        for( const JsonMember &member : value.get_object() ) {
            out.member( member.name() );
            write_value( out, member );
        }
        out.end_object();
    } else if( value.test_array() ) {
        out.start_array();
        for( const JsonValue &entry : value.get_array() ) {
            write_value( out, entry );
        }
        out.end_array();
    } else if( value.test_null() ) {
        out.write_null();
    } else if( value.test_string() ) {
        out.write( value.get_string() );
    } else if( value.test_bool() ) {
        out.write( value.get_bool() );
    } else if( value.test_int() ) {
        out.write( value.get_int64() );
    } else {
        out.write( value.get_float() );
    }
}

void write_raw( JsonOut &out, const std::string &text )
{
    write_value( out, json_loader::from_string( text ) );
}

std::string canonical( const JsonValue &value )
{
    if( value.test_object() ) {
        std::map<std::string, std::string> members;
        for( const JsonMember &member : value.get_object() ) {
            members[member.name()] = canonical( member );
        }
        std::string output = "{";
        for( const auto &entry : members ) {
            output += ( output.size() == 1 ? "" : "," ) + quote( entry.first ) + ":" + entry.second;
        }
        return output + "}";
    }
    if( value.test_array() ) {
        std::string output = "[";
        for( const JsonValue &entry : value.get_array() ) {
            output += ( output.size() == 1 ? "" : "," ) + canonical( entry );
        }
        return output + "]";
    }
    return stringify( value );
}

bool valid_identity( const std::string &value )
{
    return value.size() == 32 && std::all_of( value.begin(), value.end(), []( const char ch ) {
        return ( ch >= '0' && ch <= '9' ) || ( ch >= 'a' && ch <= 'f' );
    } );
}

cata_path checkpoint_marker()
{
    return PATH_INFO::world_base_save_path() / (
               ".cph-ai-checkpoint-" + state.world_id + "-" + state.branch_id + "-" +
               std::to_string( state.actor_id ) + "-" + state.save_nonce + ".json" );
}

bool multiplayer_proxy( const npc &candidate )
{
    // The live predicate covers both host and client proxies. The existing
    // durable tag also covers disconnects, reloads and orphaned proxies.
    return candidate.maybe_get_value( "mp_proxy" ) ||
           cata_mp::is_partner_npc( candidate.getID() );
}

npc *actor()
{
    if( !g || state.actor_id < 0 ) {
        return nullptr;
    }
    // Do not load an off-bubble NPC merely to answer an external query.
    for( npc &candidate : g->all_npcs() ) {
        if( candidate.getID().get_value() == state.actor_id && !candidate.is_dead() &&
            !multiplayer_proxy( candidate ) ) {
            return &candidate;
        }
    }
    return nullptr;
}

npc *actor_for_handoff( bool *unsupported_proxy = nullptr )
{
    // Unlike observations, cleanup may use an existing off-bubble object.
    // find_npc scans already loaded overmaps only; it does not load a region.
    npc *candidate = g && state.actor_id >= 0 ?
                     g->find_npc( character_id( state.actor_id ) ) : nullptr;
    if( candidate && multiplayer_proxy( *candidate ) ) {
        if( unsupported_proxy ) {
            *unsupported_proxy = true;
        }
        return nullptr;
    }
    return candidate;
}

std::int64_t game_time()
{
    return std::max<std::int64_t>( 0, to_seconds<std::int64_t>(
                                       calendar::turn - calendar::turn_zero ) );
}

std::string context()
{
    std::ostringstream buffer;
    JsonOut out( buffer );
    out.start_object();
    out.member( "world_id", state.world_id );
    out.member( "branch_id", state.branch_id );
    out.member( "actor_id", std::max( 0, state.actor_id ) );
    out.member( "load_epoch", state.load_epoch );
    out.member( "request_id", state.request_id );
    out.member( "event_watermark", state.event_watermark );
    out.member( "policy_version", state.policy_version );
    out.member( "memory_version", state.memory_version );
    out.member( "game_time", game_time() );
    out.end_object();
    return buffer.str();
}

void invalidate_request()
{
    state.request_id = new_identity();
    state.request_context.clear();
    state.request_payload.clear();
}

std::string context_with_watermark( const std::string &original, std::int64_t watermark )
{
    const JsonObject object = read_object( original );
    std::ostringstream buffer;
    JsonOut out( buffer );
    out.start_object();
    for( const JsonMember &member : object ) {
        out.member( member.name() );
        if( member.name() == "event_watermark" ) {
            out.write( watermark );
        } else {
            write_value( out, member );
        }
    }
    out.end_object();
    return buffer.str();
}

std::string normalized_json( const std::string &original )
{
    std::ostringstream buffer;
    JsonOut out( buffer );
    write_raw( out, original );
    return buffer.str();
}

bool same_context( const JsonObject &candidate, const JsonObject &expected )
{
    candidate.allow_omitted_members();
    expected.allow_omitted_members();
    for( const char *key : {
             "world_id", "branch_id", "actor_id", "load_epoch", "request_id",
             "policy_version", "memory_version"
         } ) {
        if( !candidate.has_member( key ) || !expected.has_member( key ) ||
            canonical( candidate.get_member( key ) ) != canonical( expected.get_member( key ) ) ) {
            return false;
        }
    }
    return candidate.has_int( "event_watermark" ) &&
           candidate.get_int64( "event_watermark" ) == expected.get_int64( "event_watermark" );
}

bool event( const std::string &kind, const std::string &text, const std::string &data = "{}" )
{
    if( state.events.size() + state.checkpoint_delta.size() >= maximum_events ) {
        // Never silently ACK or discard an unprocessed event. Back-pressure
        // pauses additional plans until the external consumer catches up.
        state.last_error = "event_backpressure";
        return false;
    }
    const std::int64_t sequence = state.event_watermark + 1;
    std::ostringstream buffer;
    JsonOut out( buffer );
    out.start_object();
    const JsonObject actual = read_object( data );
    const std::string operation = actual.get_string( "operation_id", "" );
    out.member( "id", kind == "receipt" && !operation.empty() ? "receipt." + operation :
                state.load_epoch + "." + std::to_string( sequence ) );
    out.member( "sequence", sequence );
    out.member( "kind", kind );
    out.member( "text", text );
    out.member( "game_time", game_time() );
    if( ( kind == "goal" || kind == "commitment" ) && data != "{}" ) {
        const std::string action = actual.get_string( "action", "" );
        if( kind == "goal" && action == "propose_own_goals" ) {
            out.member( "status", "active" );
        } else if( kind == "commitment" && action == "false_promise" ) {
            out.member( "status", "accepted" );
        } else if( kind == "commitment" && action == "break_commitment" ) {
            out.member( "status", "cancelled" );
        }
        if( !state.events.empty() ) {
            out.member( "source_ids", std::vector<std::string> {
                read_object( state.events.back() ).get_string( "id" )
            } );
        }
    }
    out.member( "data" );
    write_raw( out, data );
    out.end_object();
    const std::string encoded = buffer.str();
    if( encoded.size() > maximum_event_bytes - state.event_bytes ) {
        state.last_error = "event_backpressure";
        return false;
    }
    state.event_watermark = sequence;
    state.event_bytes += encoded.size();
    state.events.push_back( encoded );
    if( kind != "receipt" ) {
        state.decision_trigger = true;
    } else {
        if( actual.get_string( "state", "" ) == "failed" ||
            actual.get_string( "action", "" ) != "wait" ) {
            state.decision_trigger = true;
        }
    }
    return true;
}

bool valid_text( const std::string &text )
{
    if( text.empty() || text.size() > 16384 ) {
        return false;
    }
    std::size_t length = 0;
    for( const unsigned char ch : text ) {
        if( ch < 32 && ch != '\n' && ch != '\t' ) {
            return false;
        }
        if( ch == 127 ) {
            return false;
        }
        length += ( ch & 0xc0 ) != 0x80;
    }
    return length <= 4096;
}

bool allows( const std::string &behavior )
{
    if( !is_behavior( behavior ) ) {
        return false;
    }
    const JsonObject social = subobject( read_object( state.personality ), "social_behavior" );
    if( social.has_bool( behavior ) ) {
        return social.get_bool( behavior );
    }
    for( const char *parent : {
             "deception", "betrayal"
         } ) {
        const JsonObject group = subobject( social, parent );
        if( group.has_bool( behavior ) ) {
            return group.get_bool( "enabled", false ) && group.get_bool( behavior );
        }
    }
    return false;
}

bool validate_policy( const JsonObject &policy )
{
    policy.allow_omitted_members();
    if( policy.get_int( "schema_version", 1 ) != 1 ||
        policy.get_string( "applies_to", "bound_companion_only" ) != "bound_companion_only" ||
        policy.get_string( "expression_policy", "natural_with_intent_checks" ) !=
        "natural_with_intent_checks" || !policy.has_object( "social_behavior" ) ) {
        return false;
    }
    const JsonObject defaults = read_object( default_policy );
    const JsonObject social = subobject( policy, "social_behavior" );
    const JsonObject expected = subobject( defaults, "social_behavior" );
    for( const JsonMember &entry : expected ) {
        if( entry.test_object() ) {
            if( !social.has_object( entry.name() ) ) {
                return false;
            }
            const JsonObject group = subobject( social, entry.name() );
            const JsonObject expected_group = subobject( expected, entry.name() );
            for( const JsonMember &leaf : expected_group ) {
                if( !group.has_bool( leaf.name() ) ) {
                    return false;
                }
            }
            for( const JsonMember &leaf : group ) {
                if( !expected_group.has_member( leaf.name() ) ) {
                    return false;
                }
            }
        } else if( !social.has_bool( entry.name() ) ) {
            return false;
        }
    }
    for( const JsonMember &entry : social ) {
        if( !expected.has_member( entry.name() ) ) {
            return false;
        }
    }
    if( policy.has_object( "traits" ) ) {
        const JsonObject expected_traits = subobject( defaults, "traits" );
        for( const JsonMember &trait : subobject( policy, "traits" ) ) {
            if( !expected_traits.has_member( trait.name() ) || !trait.test_float() ||
                trait.test_bool() || trait.get_float() < 0 || trait.get_float() > 1 ) {
                return false;
            }
        }
    }
    return true;
}

void write_requirement( JsonOut &out, const std::string &id,
                        const requirement_decision &decision, bool include_text = false )
{
    out.start_object();
    out.member( "requirement_id", id );
    out.member( "source_event_id", id );
    out.member( "source_sequence", decision.source_sequence );
    out.member( "decision", decision.decision );
    out.member( "operation_id", decision.operation_id );
    if( decision.decision == "pending" && include_text ) {
        out.member( "text", decision.text );
    }
    out.end_object();
}

void write_requirements( JsonOut &out, bool persistence = false )
{
    out.member( "requirement_decisions" );
    out.start_array();
    for( const std::pair<const std::string, requirement_decision> &entry :
         state.requirement_decisions ) {
        write_requirement( out, entry.first, entry.second,
                           persistence || entry.second.source_sequence <= state.acknowledged );
    }
    out.end_array();
}

bool matches_actor_scope( const JsonObject &scope )
{
    return ( scope.has_int( "actor_id" ) && scope.get_int( "actor_id" ) == state.actor_id ) ||
           ( scope.has_string( "actor_id" ) &&
             scope.get_string( "actor_id" ) == std::to_string( state.actor_id ) );
}

std::string render_request( const std::string &window_context, const std::string &observed,
                            const std::string &action_catalog,
                            const std::vector<std::string> &window )
{
    std::ostringstream buffer;
    JsonOut out( buffer );
    out.start_object();
    out.member( "context" );
    write_raw( out, window_context );
    out.member( "observations" );
    write_raw( out, observed );
    out.member( "events" );
    out.start_array();
    for( const std::string &entry : window ) {
        write_raw( out, entry );
    }
    out.end_array();
    out.member( "action_catalog" );
    write_raw( out, action_catalog );
    write_requirements( out );
    out.end_object();
    return buffer.str();
}

bool step_allowed( const action_step &step, std::string &error, bool enforce_association = true )
{
    if( ( is_behavior( step.action ) && !allows( step.action ) ) ||
        ( !step.intent.empty() && ( !is_behavior( step.intent ) || !allows( step.intent ) ) ) ) {
        error = "behavior_disabled";
        return false;
    }
    if( step.action == "refuse" && step.requirement_id.empty() ) {
        error = "refusal_requires_requirement";
        return false;
    }
    if( step.action != "refuse" && step.intent == "refuse" ) {
        error = "refusal_requires_requirement";
        return false;
    }
    if( enforce_association && step.requirement_id.empty() && step.action != "propose_own_goals" &&
        step.intent != "propose_own_goals" &&
        std::any_of( state.requirement_decisions.begin(), state.requirement_decisions.end(),
    []( const std::pair<const std::string, requirement_decision> &incoming ) {
    return incoming.second.decision == "pending" || incoming.second.decision == "refused";
} ) ) {
        error = "requirement_association_required";
        return false;
    }
    if( !step.requirement_id.empty() ) {
        const auto decision = state.requirement_decisions.find( step.requirement_id );
        if( decision == state.requirement_decisions.end() ) {
            error = "unknown_requirement";
            return false;
        }
        if( decision->second.decision == "refused" && step.action != "refuse" ) {
            error = "requirement_refused";
            return false;
        }
    }
    const JsonObject args = read_object( step.args_json );
    if( args.has_member( "text" ) && ( !args.has_string( "text" ) ||
                                       !valid_text( args.get_string( "text" ) ) ) ) {
        error = "invalid_dialogue_text";
        return false;
    }
    // A generic attack is never a bypass for the explicit player/ally switches.
    if( step.action == "attack" && args.has_int( "target" ) ) {
        const int target = args.get_int( "target" );
        if( target == get_avatar().getID().get_value() && !allows( "attack_player" ) ) {
            error = "behavior_disabled";
            return false;
        }
        npc *bound = actor();
        if( bound ) {
            for( npc &other : g->all_npcs() ) {
                if( other.getID().get_value() == target && bound->is_ally( other ) &&
                    !allows( "attack_allies" ) ) {
                    error = "behavior_disabled";
                    return false;
                }
            }
        }
    }
    return true;
}

std::string catalog()
{
    const npc *bound = actor();
    std::ostringstream buffer;
    JsonOut out( buffer );
    out.start_array();
    for( const JsonObject &definition : json_loader::from_string( capability_catalog() ).get_array() ) {
        definition.allow_omitted_members();
        out.start_object();
        for( const JsonMember &member : definition ) {
            out.member( member.name() );
            write_value( out, member );
        }
        const bool allowed = !definition.has_string( "permission" ) ||
                             allows( definition.get_string( "permission" ) );
        out.member( "implemented", true );
        out.member( "allowed", allowed );
        out.member( "available", allowed && bound && state.enabled &&
                    !state.paused && state.detach_state == "attached" &&
                    NpcExecutionAdapter::available( *bound, definition.get_string( "name" ) ) );
        out.end_object();
    }
    out.end_array();
    return buffer.str();
}

std::string receipt( const action_step &step, const execution_result &result )
{
    std::ostringstream buffer;
    JsonOut out( buffer );
    out.start_object();
    out.member( "operation_id", step.id );
    out.member( "action", step.action );
    out.member( "intent", step.intent );
    out.member( "requirement_id", step.requirement_id );
    out.member( "origin", !step.requirement_id.empty() ? "incoming_message" :
                step.action == "propose_own_goals" || step.intent == "propose_own_goals" ?
                "own_goal" : "autonomous" );
    out.member( "state", result.state == execution_state::running ? "running" :
                result.state == execution_state::succeeded ? "succeeded" : "failed" );
    out.member( "code", result.code );
    out.member( "game_time", game_time() );
    out.member( "detail" );
    write_raw( out, result.detail_json );
    out.end_object();
    return buffer.str();
}

void record_result( const action_step &step, const execution_result &result )
{
    const auto incoming = state.requirement_decisions.find( step.requirement_id );
    const bool performs_requirement = step.action == "craft" || step.action == "gather" ||
                                      step.action == "trade" || step.action == "accept_mission" ||
                                      step.action == "complete_mission" || step.action == "claim_reward";
    if( incoming != state.requirement_decisions.end() && result.state != execution_state::failed &&
        result.code != "queued" && ( performs_requirement ||
                                     ( step.action == "refuse" && result.state == execution_state::succeeded ) ) ) {
        requirement_decision &decision = incoming->second;
        const std::string next = step.action == "refuse" ? "refused" : "accepted";
        if( decision.decision != next ) {
            decision.decision = next;
            decision.operation_id = step.id;
            decision.text.clear();
            std::ostringstream detail;
            JsonOut out( detail );
            write_requirement( out, incoming->first, decision );
            event( "requirement_decision", next, detail.str() );
        }
    }
    if( state.receipts.count( step.id ) == 0 ) {
        state.receipt_order.push_back( step.id );
    }
    const std::string previous = state.receipts.count( step.id ) ? state.receipts[step.id] : "";
    state.receipts[step.id] = receipt( step, result );
    if( result.state != execution_state::running && previous != state.receipts[step.id] ) {
        event( "receipt", result.code, state.receipts[step.id] );
        if( is_behavior( step.action ) && result.state == execution_state::succeeded ) {
            const JsonObject args = read_object( step.args_json );
            std::string kind = "observation";
            if( step.action == "propose_own_goals" ) {
                kind = "goal";
            } else if( step.action == "false_promise" || step.action == "break_commitment" ) {
                kind = "commitment";
            } else if( step.action == "lie_in_dialogue" || step.action == "argue" ) {
                kind = "statement";
            }
            event( kind, args.get_string( "text", result.code ), state.receipts[step.id] );
        }
    }
    while( state.receipt_order.size() > maximum_history ) {
        state.receipts.erase( state.receipt_order.front() );
        state.receipt_order.pop_front();
    }
}

void cancel_unstarted( const std::string &reason )
{
    for( auto entry = state.queue.begin(); entry != state.queue.end(); ) {
        if( !entry->started ) {
            record_result( entry->step, { execution_state::failed, reason, "{}", false } );
            entry = state.queue.erase( entry );
        } else {
            ++entry;
        }
    }
}

bool owns_native_activity( const npc &candidate )
{
    if( state.queue.empty() || !state.queue.front().started ||
        state.queue.front().step.action != "craft" ) {
        return false;
    }
    const std::string &operation = state.queue.front().step.id;
    const diag_value *active = candidate.maybe_get_value( "cph_ai.craft_step" );
    const diag_value *completed = candidate.maybe_get_value( "cph_ai.craft_completed_step" );
    return active && active->to_string() == operation &&
           ( !completed || completed->to_string() != operation );
}

void finish_cancelled_step( npc *bound, const pending_step &entry, const std::string &reason )
{
    const diag_value *completed = bound ? bound->maybe_get_value( "cph_ai.craft_completed_step" ) :
                                  nullptr;
    if( bound && entry.started && entry.step.action == "craft" && completed &&
        completed->to_string() == entry.step.id ) {
        record_result( entry.step, NpcExecutionAdapter::execute( *bound, entry.step ) );
    } else {
        record_result( entry.step, { execution_state::failed, reason, "{}", false } );
    }
}

void complete_detach()
{
    if( state.control_state == "dead" ) {
        return;
    }
    bool unsupported_proxy = false;
    npc *bound = actor_for_handoff( &unsupported_proxy );
    if( has_binding() && !bound && !unsupported_proxy ) {
        state.control_state = "detach_pending";
        state.detach_state = "detach_pending";
        return;
    }
    if( bound && bound->is_dead() ) {
        // Zero HP is not yet a confirmed death: native EOC/Lua handlers may
        // prevent it. Only npc::die's final lifecycle hook marks control dead.
        state.control_state = "detach_pending";
        state.detach_state = "detach_pending";
        return;
    }
    if( bound && bound->activity && owns_native_activity( *bound ) ) {
        if( !bound->activity.is_interruptible() ) {
            state.control_state = "detach_pending";
            state.detach_state = "detach_pending";
            return;
        }
        bound->cancel_activity();
    }
    for( const pending_step &entry : state.queue ) {
        finish_cancelled_step( bound, entry, "control_stopped" );
    }
    state.queue.clear();
    if( bound ) {
        bound->remove_value( "cph_ai.bound" );
        bound->remove_value( "cph_ai.pending_trade" );
        bound->remove_value( "cph_ai.pending_trade_id" );
        bound->remove_value( "cph_ai.pending_trade_source_operation" );
    }
    state.control_state = "detached";
    state.detach_state = "detached";
}

std::string plan_result( const std::string &request )
{
    std::ostringstream buffer;
    JsonOut out( buffer );
    out.start_object();
    out.member( "accepted", true );
    out.member( "request_id", request );
    out.member( "receipts" );
    out.start_array();
    for( const auto &entry : state.receipts ) {
        if( entry.first.compare( 0, request.size() + 1, request + "." ) == 0 ) {
            write_raw( out, entry.second );
        }
    }
    out.end_array();
    out.end_object();
    return buffer.str();
}

std::string remove_mod_check()
{
    const mod_id companion( "cph_ai_companion" );
    std::vector<std::string> blockers;
    if( state.detach_state != "detached" || !state.queue.empty() ) {
        blockers.emplace_back( "control_not_detached" );
    }
    WORLD *world = world_generator ? world_generator->active_world : nullptr;
    if( !world ) {
        blockers.emplace_back( "no_active_world" );
    } else {
        for( const mod_id &loaded : world->active_mod_order ) {
            if( loaded != companion && loaded.is_valid() &&
                std::find( loaded->dependencies.begin(), loaded->dependencies.end(), companion ) !=
                loaded->dependencies.end() ) {
                blockers.push_back( "dependent_mod:" + loaded.str() );
            }
        }
        for( const std::string &name : world_generator->all_worldnames() ) {
            const WORLD *other = world_generator->get_world( name );
            if( other != world && other ) {
                for( const mod_id &loaded : other->active_mod_order ) {
                    if( loaded == companion || ( loaded.is_valid() &&
                                                 std::find( loaded->dependencies.begin(), loaded->dependencies.end(), companion ) !=
                                                 loaded->dependencies.end() ) ) {
                        blockers.push_back( "dependent_world:" + name );
                        break;
                    }
                }
            }
        }
    }
    if( blockers.empty() ) {
        const std::vector<mod_id> previous = world->active_mod_order;
        world->active_mod_order.erase( std::remove( world->active_mod_order.begin(),
                                       world->active_mod_order.end(), companion ), world->active_mod_order.end() );
        if( !world->save() ) {
            world->active_mod_order = previous;
            blockers.emplace_back( "world_dependency_save_failed" );
        }
    }
    std::ostringstream buffer;
    JsonOut out( buffer );
    out.start_object();
    out.member( "safe_to_remove", blockers.empty() );
    out.member( "world_dependencies", blockers );
    out.end_object();
    return buffer.str();
}

std::string packet( const std::string &text )
{
    std::string id = "null";
    std::string error;
    std::string result;
    try {
        const JsonObject request = read_object( text );
        if( request.has_member( "id" ) ) {
            const JsonValue value = request.get_member( "id" );
            if( ( value.test_string() && value.get_string().size() <= 256 ) || value.test_int() ) {
                id = stringify( value );
            }
        }
        if( !request.has_string( "method" ) || !request.has_object( "params" ) ) {
            error = "invalid_envelope";
        } else if( request.get_string( "method" ) == "hello" ) {
            const JsonObject params = subobject( request, "params" );
            if( state.authenticated ) {
                error = "already_authenticated";
            } else if( params.get_string( "credential", "" ) != state.bridge.credential() ) {
                error = "authentication_failed";
            } else if( params.get_string( "protocol_version", "" ) != protocol_version ||
                       params.get_string( "schema_digest", "" ) != protocol_digest ) {
                error = "protocol_mismatch";
            } else {
                state.authenticated = true;
                state.cognition_stale = true;
                result = "{\"protocol_version\":" + quote( protocol_version ) +
                         ",\"schema_digest\":" + quote( protocol_digest ) +
                         ",\"session_id\":" + quote( state.bridge.session_id() ) + "}";
            }
        } else if( !state.authenticated ) {
            error = "authentication_required";
        } else {
            result = dispatch( request.get_string( "method" ), subobject( request, "params" ).str(), error );
        }
    } catch( const std::exception & ) {
        error = "invalid_json";
    }
    if( error.empty() && result.size() + id.size() + 64 > maximum_message ) {
        error = "oversized_context";
    }
    if( !error.empty() ) {
        return "{\"id\":" + id + ",\"ok\":false,\"error\":{\"code\":" + quote( error ) +
               ",\"message\":" + quote( error ) + "}}";
    }
    return "{\"id\":" + id + ",\"ok\":true,\"result\":" + result + "}";
}
} // namespace

bool is_initialized()
{
    return controller_alive;
}

void enable( bool value )
{
    if( !is_initialized() ) {
        return;
    }
    state.enabled = value;
    if( !value ) {
        stop();
        state.bridge.close();
        state.authenticated = false;
        state.was_connected = false;
    } else if( state.future_payload.empty() && !state.bridge.listening() ) {
        state.bridge.start( state.last_error );
    }
}

bool enabled()
{
    return state.enabled;
}

bool has_binding()
{
    return state.actor_id >= 0;
}

bool is_bound( const npc &candidate )
{
    return has_binding() && candidate.getID().get_value() == state.actor_id;
}

bool permits_item_aid( const npc &candidate, const Character &recipient )
{
    const npc *beneficiary = recipient.as_npc();
    return !is_initialized() || !is_bound( candidate ) || !beneficiary ||
           !beneficiary->is_enemy() || allows( "aid_conflicting_party" );
}

bool pauses_offline_work( npc &candidate )
{
    if( multiplayer_proxy( candidate ) ) {
        return false;
    }
    if( !is_initialized() || !is_bound( candidate ) ) {
        return candidate.get_value( "cph_ai.bound" ) == "true";
    }
    if( state.detach_state == "detached" ) {
        candidate.remove_value( "cph_ai.bound" );
        return false;
    }
    return true;
}

void on_actor_death( npc &candidate )
{
    if( !is_initialized() || !is_bound( candidate ) || !candidate.is_dead() ||
        multiplayer_proxy( candidate ) ) {
        return;
    }
    invalidate_request();
    for( const pending_step &entry : state.queue ) {
        record_result( entry.step, { execution_state::failed, "actor_dead", "{}", false } );
    }
    state.queue.clear();
    candidate.remove_value( "cph_ai.bound" );
    candidate.remove_value( "cph_ai.pending_trade" );
    candidate.remove_value( "cph_ai.pending_trade_id" );
    candidate.remove_value( "cph_ai.pending_trade_source_operation" );
    state.control_state = "dead";
    state.detach_state = "detached";
    state.cognition_stale = true;
    state.checkpoint_requested = false;
    state.last_error = "actor_dead";
}

bool listening()
{
    return state.bridge.listening();
}

bool bind( npc &candidate, const std::string &profile_id, std::string &error )
{
    error.clear();
    if( !state.enabled || !state.future_payload.empty() ) {
        error = "control_disabled";
        return false;
    }
    if( multiplayer_proxy( candidate ) ) {
        error = "multiplayer_proxy_not_supported";
        return false;
    }
    if( candidate.is_dead() || !candidate.is_active() ||
        ( !is_bound( candidate ) && !candidate.is_player_ally() ) ) {
        error = "living_recruited_npc_required";
        return false;
    }
    if( profile_id.empty() || profile_id.size() > 256 || !valid_text( profile_id ) ) {
        error = "invalid_profile_id";
        return false;
    }
    if( has_binding() && ( !is_bound( candidate ) || state.profile_id != profile_id ) ) {
        error = "fixed_binding_conflict";
        return false;
    }
    const bool initial = !has_binding();
    state.actor_id = candidate.getID().get_value();
    state.profile_id = profile_id;
    state.control_state = "active";
    state.detach_state = "attached";
    state.paused = false;
    candidate.set_value( "cph_ai.bound", "true" );
    invalidate_request();
    if( initial ) {
        event( "observation", "companion_bound" );
    }
    return true;
}

bool chat( const std::string &text, std::string &error )
{
    error.clear();
    npc *bound = actor();
    if( !state.enabled || !bound || state.detach_state != "attached" ) {
        error = "actor_unavailable";
        return false;
    }
    if( !valid_text( text ) ||
        state.events.size() + state.checkpoint_delta.size() >= maximum_events ||
        state.requirement_decisions.size() >= maximum_events ) {
        error = "invalid_dialogue_text";
        return false;
    }
    if( !bound->can_hear( get_avatar().pos_bub(), get_avatar().get_shout_volume() ) ) {
        error = "actor_cannot_hear";
        return false;
    }
    const std::string incoming_id = state.load_epoch + "." +
                                    std::to_string( state.event_watermark + 1 );
    if( !event( "statement", text, "{\"speaker_id\":" + std::to_string(
                    get_avatar().getID().get_value() ) + ",\"requirement_id\":" +
                quote( incoming_id ) + "}" ) ) {
        error = "event_backpressure";
        return false;
    }
    state.requirement_decisions.emplace( incoming_id,
                                         requirement_decision { state.event_watermark, "pending", {}, text } );
    invalidate_request();
    state.chat_trigger = true;
    state.transcript.push_back( "{\"speaker\":\"player\",\"text\":" + quote( text ) + "}" );
    while( state.transcript.size() > maximum_transcript ) {
        state.transcript.pop_front();
    }
    return true;
}

void pause( bool value )
{
    state.paused = value;
    invalidate_request();
}

void cancel()
{
    invalidate_request();
    cancel_unstarted( "plan_cancelled" );
    bool unsupported_proxy = false;
    npc *bound = actor_for_handoff( &unsupported_proxy );
    if( has_binding() && !bound && !unsupported_proxy ) {
        state.control_state = "cancel_pending";
        state.last_error = "cancel_waiting_for_actor";
        return;
    }
    if( bound && bound->is_dead() ) {
        state.control_state = "cancel_pending";
        state.last_error = "cancel_waiting_for_native_death_resolution";
        return;
    }
    if( bound && bound->activity && owns_native_activity( *bound ) &&
        bound->activity.is_interruptible() ) {
        bound->cancel_activity();
    }
    if( !bound || !bound->activity || !owns_native_activity( *bound ) ) {
        for( const pending_step &entry : state.queue ) {
            finish_cancelled_step( bound, entry, "plan_cancelled" );
        }
        state.queue.clear();
        if( state.detach_state == "attached" && state.control_state == "cancel_pending" ) {
            state.control_state = "active";
        }
    } else {
        state.control_state = "cancel_pending";
        state.last_error = "cancel_waiting_for_native_activity";
    }
    if( bound ) {
        bound->remove_value( "cph_ai.pending_trade" );
        bound->remove_value( "cph_ai.pending_trade_id" );
        bound->remove_value( "cph_ai.pending_trade_source_operation" );
    }
}

void stop()
{
    invalidate_request();
    state.cognition_stale = true;
    state.checkpoint_requested = false;
    if( npc *bound = actor_for_handoff() ) {
        bound->remove_value( "cph_ai.pending_trade" );
        bound->remove_value( "cph_ai.pending_trade_id" );
        bound->remove_value( "cph_ai.pending_trade_source_operation" );
    }
    cancel_unstarted( "control_stopped" );
    complete_detach();
}

void on_scene_change()
{
    // This is a new planning generation, not a load: changing load_epoch
    // would incorrectly restore an older external memory checkpoint.
    invalidate_request();
    state.observation_signature.clear();
    cancel_unstarted( "scene_changed" );
    for( auto entry = state.queue.begin(); entry != state.queue.end(); ) {
        if( entry->started && entry->step.action == "craft" ) {
            // The native activity and its real inputs travel with the actor,
            // or remain paused in the source dimension when it stays behind.
            ++entry;
        } else {
            record_result( entry->step, { execution_state::failed, "scene_changed", "{}", false } );
            entry = state.queue.erase( entry );
        }
    }
    if( npc *bound = actor_for_handoff() ) {
        bound->remove_value( "cph_ai.pending_trade" );
        bound->remove_value( "cph_ai.pending_trade_id" );
        bound->remove_value( "cph_ai.pending_trade_source_operation" );
    }
    state.decision_trigger = true;
}

void reset()
{
    if( !is_initialized() ) {
        return;
    }
    const bool module_enabled = state.enabled;
    state.bridge.close();
    // loopback_bridge is deliberately non-movable; reset game state fields.
    state.enabled = module_enabled;
    state.paused = false;
    state.authenticated = false;
    state.was_connected = false;
    state.cognition_stale = true;
    state.debug = false;
    state.decision_trigger = false;
    state.chat_trigger = false;
    state.checkpoint_requested = false;
    state.save_commit_prepared = false;
    state.save_commit_attempted = false;
    state.actor_id = -1;
    state.max_steps = 5;
    state.cooldown = 10;
    state.profile_id.clear();
    state.world_id = new_identity();
    state.branch_id = new_identity();
    state.load_epoch = new_identity();
    state.policy_version = new_identity();
    state.memory_version.clear();
    state.personality = default_policy;
    state.cognition = "{}";
    state.control_state = "unbound";
    state.detach_state = "detached";
    state.saved_checkpoint = "null";
    state.saved_memory_context = "null";
    state.checkpoint_context.clear();
    state.pending_checkpoint = "null";
    state.save_nonce.clear();
    state.future_payload.clear();
    state.last_error.clear();
    state.observation_signature.clear();
    state.event_watermark = 0;
    state.acknowledged = 0;
    state.events.clear();
    state.checkpoint_delta.clear();
    state.event_bytes = 0;
    state.queue.clear();
    state.receipts.clear();
    state.accepted_plans.clear();
    state.receipt_order.clear();
    state.transcript.clear();
    state.accepted_at = clock_type::time_point{};
    state.connection_at = clock_type::time_point{};
    invalidate_request();
}

void pump_incoming()
{
    npc *pending = state.control_state == "cancel_pending" ? actor_for_handoff() : nullptr;
    if( pending && ( !pending->activity || !owns_native_activity( *pending ) ||
                     pending->activity.is_interruptible() ) ) {
        cancel();
    }
    if( state.detach_state == "detach_pending" ) {
        complete_detach();
    }
    if( !state.enabled || !state.future_payload.empty() ) {
        return;
    }
    if( !state.bridge.listening() && !state.bridge.start( state.last_error ) ) {
        return;
    }
    state.bridge.pump( []( const std::string & message ) {
        if( !state.was_connected ) {
            state.was_connected = true;
            state.authenticated = false;
            state.connection_at = clock_type::now();
        }
        return packet( message );
    } );
    if( state.bridge.connected() && !state.was_connected ) {
        state.was_connected = true;
        state.authenticated = false;
        state.connection_at = clock_type::now();
    }
    if( state.bridge.connected() && !state.authenticated &&
        clock_type::now() - state.connection_at > std::chrono::seconds( 5 ) ) {
        state.bridge.disconnect();
    }
    if( !state.bridge.connected() && state.was_connected ) {
        state.was_connected = false;
        state.authenticated = false;
        state.cognition_stale = true;
        // Unexpected disconnect keeps accepted native work and the fixed binding.
        invalidate_request();
    }
}

bool act( npc &candidate, bool urgent )
{
    if( !is_bound( candidate ) || multiplayer_proxy( candidate ) || !state.future_payload.empty() ) {
        return false;
    }
    if( state.detach_state == "detach_pending" ) {
        complete_detach();
        return false;
    }
    if( state.detach_state == "detached" ) {
        candidate.remove_value( "cph_ai.bound" );
    }
    if( state.control_state == "cancel_pending" ) {
        return false;
    }
    if( !state.enabled ) {
        return false;
    }
    if( urgent || state.paused || state.detach_state != "attached" || state.queue.empty() ||
        candidate.get_moves() <= 0 ||
        state.events.size() + state.checkpoint_delta.size() > maximum_events - 16 ||
        state.event_bytes > maximum_event_bytes - maximum_message ) {
        return false;
    }
    pending_step &current = state.queue.front();
    if( candidate.activity ) {
        // The original activity owns its progress and scheduling, even when
        // it was started by us. Do not occupy another activity's execution slot.
        return false;
    }
    std::string permission_error;
    if( !step_allowed( current.step, permission_error, !current.started ) ) {
        record_result( current.step, { execution_state::failed, permission_error, "{}", false } );
        state.queue.pop_front();
        cancel_unstarted( "dependency_failed" );
        return false;
    }
    if( current.restored ) {
        const std::string key = current.step.action == "craft" ? "cph_ai.craft_step" :
                                "cph_ai.wait." + current.step.id;
        const diag_value *native = candidate.maybe_get_value( key );
        const diag_value *completed = candidate.maybe_get_value( "cph_ai.craft_completed_step" );
        const bool known = current.step.action == "move" ||
                           ( current.step.action == "wait" && native ) ||
                           ( current.step.action == "craft" && ( ( native && native->to_string() == current.step.id ) ||
                                   ( completed && completed->to_string() == current.step.id ) ) );
        if( !known ) {
            state.control_state = "reconcile_required";
            state.last_error = "unknown_restored_operation";
            return false;
        }
        current.restored = false;
    }
    current.step.source_operation.clear();
    if( !current.from_step.empty() ) {
        const auto predecessor = state.receipts.find( current.from_step );
        if( predecessor == state.receipts.end() ||
            read_object( predecessor->second ).get_string( "state" ) != "succeeded" ) {
            record_result( current.step, { execution_state::failed, "dependency_failed", "{}", false } );
            state.queue.pop_front();
            cancel_unstarted( "dependency_failed" );
            return false;
        }
        const std::string action = read_object( predecessor->second ).get_string( "action" );
        current.step.source_operation = action == "craft" || action == "gather" || action == "trade" ?
                                        current.from_step : std::string();
    }
    current.started = true;
    const execution_result result = NpcExecutionAdapter::execute( candidate, current.step );
    record_result( current.step, result );
    if( result.state != execution_state::running ) {
        const action_step completed = current.step;
        state.queue.pop_front();
        if( result.state == execution_state::failed ) {
            cancel_unstarted( "dependency_failed" );
        } else {
            const JsonObject args = read_object( completed.args_json );
            if( args.has_string( "text" ) ) {
                state.transcript.push_back( "{\"speaker\":\"companion\",\"text\":" +
                                            quote( args.get_string( "text" ) ) + "}" );
                while( state.transcript.size() > maximum_transcript ) {
                    state.transcript.pop_front();
                }
            }
        }
    }
    return result.consumed_moves || candidate.activity;
}

int following_distance( const npc &candidate, int native_distance )
{
    if( !state.enabled || !is_bound( candidate ) || multiplayer_proxy( candidate ) ||
        state.detach_state != "attached" ||
        !state.queue.empty() || native_distance <= 2 || !state.future_payload.empty() ) {
        // Preserve stairs, explicit close-follow and loss-of-vision constraints.
        return native_distance;
    }
    const JsonObject policy = read_object( state.personality );
    const double base = policy.has_object( "traits" ) ?
                        subobject( policy, "traits" ).get_float( "caution", 0.6 ) : 0.6;
    double weighted = base;
    double weight = 1.0;
    const JsonObject cognition = read_object( state.cognition );
    if( cognition.has_array( "records" ) ) {
        for( const JsonObject &record : cognition.get_array( "records" ) ) {
            record.allow_omitted_members();
            const std::string kind = record.get_string( "kind", "" );
            if( ( kind != "growth" && kind != "relationship" ) ||
                !record.has_object( "preferences" ) || !record.has_array( "source_ids" ) ||
                record.get_array( "source_ids" ).empty() ) {
                continue;
            }
            const JsonObject preferences = subobject( record, "preferences" );
            if( !preferences.has_number( "caution" ) || !record.has_number( "confidence" ) ) {
                continue;
            }
            const double caution = preferences.get_float( "caution" );
            const double confidence = record.get_float( "confidence" );
            if( !std::isfinite( caution ) || !std::isfinite( confidence ) || caution < 0 ||
                caution > 1 || confidence < 0 || confidence > 1 ) {
                continue;
            }
            weighted += caution * confidence;
            weight += confidence;
        }
    }
    const double effective = weighted / weight;
    const int offset = std::clamp( static_cast<int>( std::lround( ( effective - 0.5 ) * 4 ) ), -2, 2 );
    return std::clamp( native_distance + offset, 2, 6 );
}

static std::size_t write_recent( JsonOut &out, const std::deque<std::string> &entries,
                                 std::size_t byte_budget )
{
    std::vector<std::string> selected;
    std::size_t used = 0;
    for( auto entry = entries.rbegin(); entry != entries.rend(); ++entry ) {
        const std::string wire = normalized_json( *entry );
        if( wire.size() + 1 > byte_budget - used ) {
            break;
        }
        used += wire.size() + 1;
        selected.push_back( wire );
    }
    out.start_array();
    for( auto entry = selected.rbegin(); entry != selected.rend(); ++entry ) {
        write_raw( out, *entry );
    }
    out.end_array();
    return entries.size() - selected.size();
}

static void write_cognition_debug( JsonOut &out )
{
    const JsonObject cognition = read_object( state.cognition );
    out.start_object();
    out.member( "revision", cognition.get_string( "revision", "" ) );
    out.member( "records" );
    out.start_array();
    std::size_t used = 0;
    std::size_t included = 0;
    const JsonArray records = cognition.has_array( "records" ) ?
                              cognition.get_array( "records" ) : JsonArray();
    for( const JsonValue &record : records ) {
        const std::string wire = normalized_json( stringify( record ) );
        if( wire.size() + 1 > 131072 - used ) {
            break;
        }
        used += wire.size() + 1;
        ++included;
        write_raw( out, wire );
    }
    out.end_array();
    out.member( "omitted_records", records.size() - included );
    out.end_object();
}

std::string status( bool include_debug, const std::string &operation_id )
{
    if( !is_initialized() ) {
        return "{\"state\":\"unavailable\",\"enabled\":false}";
    }
    if( state.detach_state == "detach_pending" ) {
        complete_detach();
    }
    std::ostringstream buffer;
    JsonOut out( buffer );
    out.start_object();
    out.member( "context" );
    if( has_binding() ) {
        write_raw( out, state.request_context.empty() ? context() : state.request_context );
    } else {
        out.write_null();
    }
    out.member( "state", !state.future_payload.empty() ? "unsupported_schema" :
                state.control_state == "dead" || state.detach_state == "detach_pending" ||
                state.control_state == "detached" ? state.control_state :
                state.paused ? "paused" : !actor() && has_binding() ? "off_bubble" : state.control_state );
    out.member( "control_state", state.control_state );
    out.member( "detach_state", state.detach_state );
    out.member( "enabled", state.enabled );
    out.member( "descriptor_path", state.bridge.descriptor_path() );
    out.member( "profile_id", state.profile_id );
    out.member( "actor_id" );
    if( has_binding() ) {
        out.write( state.actor_id );
    } else {
        out.write_null();
    }
    out.member( "connected", state.authenticated && state.bridge.connected() );
    out.member( "cognition_stale", state.cognition_stale );
    out.member( "checkpoint_requested", state.checkpoint_requested );
    out.member( "checkpoint_context" );
    write_raw( out, state.checkpoint_context.empty() ? "null" : state.checkpoint_context );
    out.member( "saved_checkpoint" );
    write_raw( out, state.saved_checkpoint );
    out.member( "saved_memory_context" );
    write_raw( out, state.saved_memory_context );
    out.member( "queue_length", state.queue.size() );
    write_requirements( out );
    out.member( "receipts" );
    std::deque<std::string> receipt_view;
    for( const std::string &id : state.receipt_order ) {
        if( operation_id.empty() || id == operation_id ) {
            receipt_view.push_back( state.receipts.at( id ) );
        }
    }
    const std::size_t receipts_omitted = write_recent( out, receipt_view,
                                         operation_id.empty() ? 262144 : 786432 );
    out.member( "receipts_omitted", receipts_omitted );
    out.member( "transcript" );
    const std::size_t transcript_omitted = write_recent( out, state.transcript, 131072 );
    out.member( "transcript_omitted", transcript_omitted );
    if( include_debug && state.debug ) {
        out.member( "debug" );
        out.start_object();
        out.member( "personality" );
        write_raw( out, state.personality );
        out.member( "cognition" );
        write_cognition_debug( out );
        out.member( "last_error", state.last_error );
        out.member( "unacknowledged_events", state.events.size() );
        out.member( "current_queue" );
        out.start_array();
        const npc *bound = actor();
        for( const pending_step &entry : state.queue ) {
            out.start_object();
            out.member( "id", entry.step.id );
            out.member( "action", entry.step.action );
            out.member( "intent", entry.step.intent );
            out.member( "requirement_id", entry.step.requirement_id );
            out.member( "args" );
            write_raw( out, entry.step.args_json );
            out.member( "from_step", entry.from_step );
            out.member( "source_operation", entry.step.source_operation );
            out.member( "started", entry.started );
            out.member( "phase", entry.restored ? "reconcile_required" :
                        !entry.started ? "queued" :
                        bound && bound->activity && owns_native_activity( *bound ) ?
                        "native_activity" : "running" );
            out.end_object();
        }
        out.end_array();
        out.member( "social_state" );
        if( bound ) {
            out.start_object();
            for( const char *key : {
                     "last_social_action", "goal", "goal_state", "commitment",
                     "commitment_state", "concealed_information"
                 } ) {
                const diag_value *stored = bound->maybe_get_value( std::string( "cph_ai." ) + key );
                out.member( key, stored ? stored->to_string() : std::string() );
            }
            out.end_object();
        } else {
            out.write_null();
        }
        out.member( "pending_player_trade" );
        const diag_value *offer_value = bound ? bound->maybe_get_value( "cph_ai.pending_trade" ) : nullptr;
        const diag_value *offer_id = bound ? bound->maybe_get_value( "cph_ai.pending_trade_id" ) : nullptr;
        if( offer_value && !offer_value->to_string().empty() ) {
            std::string offer_summary;
            try {
                const JsonObject offer = read_object( offer_value->to_string() );
                std::ostringstream summary;
                JsonOut summary_out( summary );
                summary_out.start_object();
                summary_out.member( "operation_id", offer_id ? offer_id->to_string() : std::string() );
                summary_out.member( "target", offer.get_int( "target", -1 ) );
                for( const char *side : {
                         "give", "take"
                     } ) {
                    int items = 0;
                    if( offer.has_array( side ) ) {
                        for( const JsonObject &requested : offer.get_array( side ) ) {
                            requested.allow_omitted_members();
                            items += std::clamp( requested.get_int( "count", 1 ), 0, 1000 );
                        }
                    }
                    summary_out.member( std::string( side ) + "_count", items );
                }
                summary_out.end_object();
                offer_summary = summary.str();
            } catch( const std::exception & ) {
                offer_summary = "{\"state\":\"invalid_offer\"}";
            }
            write_raw( out, offer_summary );
        } else {
            out.write_null();
        }
        out.end_object();
    }
    out.end_object();
    return buffer.str();
}

std::string dispatch( const std::string &method, const std::string &params_text,
                      std::string &error )
{
    error.clear();
    try {
        const JsonObject params = read_object( params_text );
        params.allow_omitted_members();
        if( method == "capabilities" ) {
            return "{\"protocol_version\":" + quote( protocol_version ) +
                   ",\"schema_digest\":" + quote( protocol_digest ) + ",\"actions\":" + catalog() + "}";
        }
        if( method == "status" ) {
            return status( params.get_bool( "include_debug", false ),
                           params.get_string( "operation_id", "" ) );
        }
        if( !state.future_payload.empty() ) {
            error = "unsupported_state_schema";
        } else if( method == "stop" ) {
            stop();
            return status();
        } else if( method == "cancel" ) {
            cancel();
            return status();
        } else if( method == "remove_mod_check" ) {
            return remove_mod_check();
        } else if( method == "configure" ) {
            if( state.control_state == "dead" ) {
                error = "actor_dead";
                return "null";
            }
            if( !state.enabled || !params.has_string( "profile_id" ) ||
                !params.has_object( "personality" ) || !params.has_object( "limits" ) ||
                !validate_policy( subobject( params, "personality" ) ) ) {
                error = "invalid_configuration";
                return "null";
            }
            const JsonObject limits = subobject( params, "limits" );
            const int max_steps = limits.get_int( "max_steps", 5 );
            const int cooldown = limits.get_int( "cooldown", 10 );
            if( max_steps < 1 || max_steps > 5 || cooldown < 0 || cooldown > 3600 ) {
                error = "invalid_limits";
                return "null";
            }
            const std::string profile = params.get_string( "profile_id" );
            if( !has_binding() ) {
                if( !params.has_int( "actor_id" ) ) {
                    error = "actor_binding_required";
                    return "null";
                }
                npc *candidate = nullptr;
                for( npc &entry : g->all_npcs() ) {
                    if( entry.getID().get_value() == params.get_int( "actor_id" ) ) {
                        candidate = &entry;
                    }
                }
                if( !candidate || !bind( *candidate, profile, error ) ) {
                    if( error.empty() ) {
                        error = "actor_unavailable";
                    }
                    return "null";
                }
            } else if( profile != state.profile_id ||
                       ( params.has_int( "actor_id" ) && params.get_int( "actor_id" ) != state.actor_id ) ) {
                error = "fixed_binding_conflict";
                return "null";
            }
            const std::string policy = canonical( params.get_member( "personality" ) );
            if( policy != canonical( json_loader::from_string( state.personality ) ) ) {
                state.personality = policy;
                state.policy_version = new_identity();
                invalidate_request();
            }
            state.max_steps = max_steps;
            state.cooldown = cooldown;
            state.debug = params.has_object( "debug" ) &&
                          subobject( params, "debug" ).get_bool( "enabled", false );
            if( state.detach_state == "detached" ) {
                state.detach_state = "attached";
                state.control_state = "active";
                invalidate_request();
            }
            return status();
        } else if( method == "sync_memory" ) {
            npc *bound = actor();
            if( !has_binding() || !params.has_string( "version" ) ||
                !params.has_object( "snapshot" ) ) {
                error = "invalid_memory_snapshot";
                return "null";
            }
            const JsonObject snapshot = subobject( params, "snapshot" );
            const std::string version = params.get_string( "version" );
            if( version.empty() || version.size() > 256 ||
                snapshot.get_string( "revision", "" ) != version ||
                !snapshot.has_array( "records" ) || snapshot.get_array( "records" ).size() > 1000 ) {
                error = "invalid_memory_snapshot";
                return "null";
            }
            const bool has_root_scope = snapshot.has_object( "context" );
            if( snapshot.has_member( "context" ) ) {
                if( !has_root_scope ) {
                    error = "invalid_memory_snapshot";
                    return "null";
                }
                const JsonObject scope = subobject( snapshot, "context" );
                if( scope.get_string( "world_id", "" ) != state.world_id ||
                    scope.get_string( "branch_id", "" ) != state.branch_id ||
                    scope.get_string( "load_epoch", "" ) != state.load_epoch || !matches_actor_scope( scope ) ) {
                    error = "memory_scope_mismatch";
                    return "null";
                }
            }
            std::string known = "[";
            std::string goal;
            for( const JsonObject &record : snapshot.get_array( "records" ) ) {
                record.allow_omitted_members();
                if( !record.has_object( "context" ) || !record.has_string( "kind" ) ||
                    !record.has_string( "text" ) || record.get_string( "text" ).size() > 65536 ) {
                    error = "invalid_memory_record";
                    return "null";
                }
                const JsonObject scope = record.get_object( "context" );
                scope.allow_omitted_members();
                if( !matches_actor_scope( scope ) ) {
                    error = "memory_actor_mismatch";
                    return "null";
                }
                const std::string kind = record.get_string( "kind" );
                const std::set<std::string> kinds { "observation", "statement", "belief", "commitment", "receipt",
                                                    "relationship", "growth", "summary", "goal" };
                if( kinds.count( kind ) == 0 ) {
                    error = "invalid_memory_kind";
                    return "null";
                }
                const bool imported = record.get_bool( "imported", false );
                if( imported ) {
                    const std::set<std::string> subjective { "belief", "relationship", "growth", "summary" };
                    if( !has_root_scope || subjective.count( kind ) == 0 ||
                        record.get_string( "continuity", "" ) !=
                        "imported_experience_not_current_world_fact" ||
                        !record.has_object( "origin_context" ) ||
                        scope.get_string( "world_id", "" ) != state.world_id ||
                        scope.get_string( "branch_id", "" ) != state.branch_id ||
                        scope.get_string( "load_epoch", "" ) != state.load_epoch ) {
                        error = "invalid_memory_import";
                        return "null";
                    }
                    const JsonObject origin = record.get_object( "origin_context" );
                    origin.allow_omitted_members();
                    if( origin.get_string( "world_id", "" ).empty() ||
                        !( ( origin.has_int( "actor_id" ) && origin.get_int( "actor_id" ) >= 0 ) ||
                           ( origin.has_string( "actor_id" ) && !origin.get_string( "actor_id" ).empty() ) ) ) {
                        error = "invalid_memory_import";
                        return "null";
                    }
                } else if( record.get_string( "continuity", "" ) ==
                           "imported_experience_not_current_world_fact" ||
                           ( scope.has_member( "world_id" ) &&
                             scope.get_string( "world_id", "" ) != state.world_id ) ||
                           ( scope.has_member( "branch_id" ) &&
                             scope.get_string( "branch_id", "" ) != state.branch_id ) ) {
                    error = "memory_scope_mismatch";
                    return "null";
                }
                if( kind == "statement" || kind == "belief" ) {
                    known += ( known.size() == 1 ? "" : "," ) + record.str();
                }
                if( kind == "goal" && record.get_string( "status", "" ) == "active" && goal.empty() ) {
                    goal = record.get_string( "text" );
                }
            }
            known += "]";
            if( state.memory_version != version ) {
                state.memory_version = version;
                invalidate_request();
                state.decision_trigger = true;
            }
            state.cognition = snapshot.str();
            state.cognition_stale = false;
            if( state.observation_signature.empty() ) {
                state.decision_trigger = true;
            }
            if( bound ) {
                bound->set_value( "cph_ai.cognition", stringify( snapshot.get_member( "records" ) ) );
                bound->set_value( "cph_ai.known_information", known );
                bound->set_value( "cph_ai.goal", goal );
            }
            return "{\"version\":" + quote( version ) + "}";
        } else if( method == "take_request" ) {
            npc *bound = actor();
            if( !state.enabled || !bound || state.paused || state.detach_state != "attached" ||
                !state.queue.empty() || state.cognition_stale ) {
                return "null";
            }
            const std::string observed = NpcExecutionAdapter::observe( *bound );
            const JsonObject observation = read_object( observed );
            observation.allow_omitted_members();
            std::ostringstream relevant;
            JsonOut relevant_out( relevant );
            relevant_out.start_object();
            for( const JsonMember &member : observation ) {
                relevant_out.member( member.name() );
                if( member.name() == "actor" && member.test_object() ) {
                    relevant_out.start_object();
                    const JsonObject self = member.get_object();
                    self.allow_omitted_members();
                    for( const JsonMember &field : self ) {
                        if( field.name() != "moves" && field.name() != "known_information" &&
                            field.name() != "concealed_information" && field.name() != "commitment" &&
                            field.name() != "commitment_state" ) {
                            relevant_out.member( field.name() );
                            write_value( relevant_out, field );
                        }
                    }
                    relevant_out.end_object();
                } else {
                    write_value( relevant_out, member );
                }
            }
            relevant_out.end_object();
            const std::string signature = canonical( json_loader::from_string( relevant.str() ) );
            if( signature != state.observation_signature ) {
                invalidate_request();
                state.observation_signature = signature;
                state.decision_trigger = true;
                event( "observation", "perceived_environment_changed", observed );
            }
            if( !state.request_payload.empty() ) {
                return state.request_payload;
            }
            if( state.request_context.empty() ) {
                if( !state.decision_trigger || ( !state.chat_trigger &&
                                                 clock_type::now() - state.accepted_at < std::chrono::seconds( state.cooldown ) ) ) {
                    return "null";
                }
            }
            const std::string original_context = context();
            const std::string observed_wire = normalized_json( observed );
            const std::string catalog_wire = normalized_json( catalog() );
            const std::size_t limit = maximum_message - envelope_headroom;
            std::vector<std::string> window;
            std::int64_t watermark = state.acknowledged;
            // Measure the exact serialized base, then admit a prefix by its
            // normalized wire bytes. The 128 byte margin covers watermark digits.
            const std::size_t base_size = render_request( original_context, observed_wire, catalog_wire,
                                          window ).size();
            if( base_size + 128 > limit ) {
                state.last_error = error = "oversized_context";
                return "null";
            }
            std::size_t used = base_size + 128;
            for( const std::string &entry : state.events ) {
                if( window.size() >= 256 ) {
                    break;
                }
                const std::string encoded = normalized_json( entry );
                if( encoded.size() + 1 > limit - used ) {
                    if( window.empty() ) {
                        state.last_error = error = "oversized_context";
                        return "null";
                    }
                    break;
                }
                used += encoded.size() + 1;
                window.push_back( encoded );
                watermark = read_object( entry ).get_int64( "sequence" );
            }
            const std::string window_context = context_with_watermark( original_context, watermark );
            const std::string payload = render_request( window_context, observed_wire, catalog_wire, window );
            if( payload.size() > limit ) {
                state.last_error = error = "oversized_context";
                return "null";
            }
            state.request_context = window_context;
            state.request_payload = payload;
            return payload;
        } else if( method == "offer_plan" ) {
            std::vector<action_step> candidate;
            if( !parse_plan( params_text, candidate, error ) ) {
                return "null";
            }
            const JsonObject offered = subobject( params, "context" );
            const std::string request = offered.get_string( "request_id" );
            if( offered.get_string( "world_id" ) != state.world_id ||
                offered.get_string( "branch_id" ) != state.branch_id ||
                offered.get_int( "actor_id" ) != state.actor_id ||
                offered.get_string( "load_epoch" ) != state.load_epoch ) {
                error = "stale_request";
                return "null";
            }
            const std::string fingerprint = canonical( json_loader::from_string( params_text ) );
            const auto previous = state.accepted_plans.find( request );
            if( previous != state.accepted_plans.end() ) {
                if( previous->second != fingerprint ) {
                    error = "operation_payload_conflict";
                    return "null";
                }
                return plan_result( request );
            }
            if( !state.enabled || !actor() || state.paused || state.detach_state != "attached" ||
                state.request_context.empty() || !state.queue.empty() || state.cognition_stale ||
                !same_context( offered, read_object( state.request_context ) ) ) {
                error = "stale_request";
                return "null";
            }
            if( candidate.size() > static_cast<std::size_t>( state.max_steps ) ||
                ( params.has_string( "intent" ) && !allows( params.get_string( "intent" ) ) ) ) {
                error = "plan_not_allowed";
                return "null";
            }
            for( const action_step &step : candidate ) {
                if( !step_allowed( step, error ) ) {
                    return "null";
                }
            }
            if( params.has_string( "speech" ) ) {
                if( !valid_text( params.get_string( "speech" ) ) ) {
                    error = "invalid_dialogue_text";
                    return "null";
                }
                if( std::any_of( candidate.begin(), candidate.end(), []( const action_step & step ) {
                return step.id == "__speech";
            } ) ) {
                    error = "reserved_step_id";
                    return "null";
                }
                candidate.push_back( { "__speech", "talk", "{\"target\":" +
                                       std::to_string( get_avatar().getID().get_value() ) + ",\"text\":" +
                                       quote( params.get_string( "speech" ) ) + "}", params.get_string( "intent", "" ) } );
            }
            if( candidate.size() > static_cast<std::size_t>( state.max_steps ) ) {
                error = "plan_not_allowed";
                return "null";
            }
            for( const action_step &step : candidate ) {
                if( !step_allowed( step, error ) ) {
                    return "null";
                }
            }
            std::map<std::string, std::string> dependencies;
            for( const JsonObject &step : params.get_array( "steps" ) ) {
                step.allow_omitted_members();
                if( step.has_string( "from_step" ) ) {
                    dependencies[step.get_string( "id" )] = request + "." + step.get_string( "from_step" );
                }
            }
            for( action_step &step : candidate ) {
                const std::string dependency = dependencies[step.id];
                step.id = request + "." + step.id;
                state.queue.push_back( { step, dependency, false, false } );
                record_result( step, { execution_state::running, "queued", "{}", false } );
            }
            state.accepted_plans[request] = fingerprint;
            if( state.accepted_plans.size() > maximum_history ) {
                state.accepted_plans.erase( state.accepted_plans.begin() );
            }
            state.acknowledged = offered.get_int64( "event_watermark" );
            for( const std::pair<const std::string, requirement_decision> &incoming :
                 state.requirement_decisions ) {
                if( incoming.second.decision != "pending" ||
                    incoming.second.source_sequence > state.acknowledged ) {
                    continue;
                }
                const bool addressed = std::any_of( candidate.begin(), candidate.end(),
                [&incoming]( const action_step & step ) {
                    return step.requirement_id == incoming.first;
                } );
                if( !addressed ) {
                    state.acknowledged = std::min( state.acknowledged, incoming.second.source_sequence - 1 );
                }
            }
            while( !state.events.empty() && read_object( state.events.front() ).get_int64(
                       "sequence" ) <= state.acknowledged ) {
                state.checkpoint_delta.push_back( state.events.front() );
                state.events.pop_front();
            }
            state.accepted_at = clock_type::now();
            state.decision_trigger = state.events.size() > 0;
            state.chat_trigger = false;
            invalidate_request();
            return plan_result( request );
        } else if( method == "checkpoint" ) {
            if( !state.checkpoint_requested || !params.has_object( "reference" ) ||
                !params.has_object( "context" ) ||
                params.get_string( "version", "" ) != state.memory_version ||
                !same_context( subobject( params, "context" ),
                               read_object( state.checkpoint_context ) ) ) {
                error = "stale_checkpoint";
                return "null";
            }
            const JsonObject reference = subobject( params, "reference" );
            if( reference.get_string( "id", "" ).empty() ||
                reference.get_string( "revision", "" ) != state.memory_version ) {
                error = "invalid_checkpoint";
                return "null";
            }
            state.pending_checkpoint = reference.str();
            state.checkpoint_requested = false;
            return "{\"accepted\":true}";
        } else {
            error = "unknown_method";
        }
    } catch( const std::exception & ) {
        error = "invalid_params";
    }
    return "null";
}

void before_save()
{
    state.save_nonce = new_identity();
    state.save_commit_prepared = false;
    state.save_commit_attempted = false;
    state.pending_checkpoint = "null";
    state.checkpoint_context = context();
    state.checkpoint_requested = state.enabled && state.authenticated && state.bridge.connected() &&
                                 has_binding();
    const auto deadline = clock_type::now() + std::chrono::milliseconds( 250 );
    while( state.checkpoint_requested && clock_type::now() < deadline ) {
        pump_incoming();
        std::this_thread::sleep_for( std::chrono::milliseconds( 1 ) );
    }
    state.checkpoint_requested = false;
}

bool prepare_save_commit()
{
    if( state.save_commit_attempted ) {
        return state.save_commit_prepared;
    }
    state.save_commit_attempted = true;
    if( has_binding() && !state.save_nonce.empty() && world_generator &&
        world_generator->active_world ) {
        const std::string checkpoint = state.pending_checkpoint == "null" ?
                                       state.saved_checkpoint : state.pending_checkpoint;
        const cata_path marker = checkpoint_marker();
        const bool committed = write_to_file( marker, [&checkpoint]( std::ostream & stream ) {
            JsonOut out( stream );
            out.start_object();
            out.member( "schema_version", 1 );
            out.member( "save_nonce", state.save_nonce );
            out.member( "checkpoint" );
            write_raw( out, checkpoint );
            out.end_object();
        }, "companion save checkpoint" );
        if( !committed ) {
            state.last_error = "checkpoint_commit_failed";
            return false;
        }
    }
    state.save_commit_prepared = true;
    return true;
}

void after_save( bool success )
{
    // Staging the marker is not a confirmation. The transaction owner calls
    // this only after all native world files and the journal commit are durable.
    // Retain the direct-call fallback for engine integrations without a lease.
    if( success && prepare_save_commit() && state.pending_checkpoint != "null" ) {
        state.saved_checkpoint = state.pending_checkpoint;
        state.saved_memory_context = state.checkpoint_context;
        const std::int64_t watermark = read_object( state.checkpoint_context ).get_int64(
                                           "event_watermark" );
        while( !state.checkpoint_delta.empty() &&
               read_object( state.checkpoint_delta.front() ).get_int64( "sequence" ) <= watermark ) {
            state.event_bytes -= state.checkpoint_delta.front().size();
            state.checkpoint_delta.pop_front();
        }
    }
    state.save_commit_prepared = false;
    state.save_commit_attempted = false;
    state.pending_checkpoint = "null";
    state.checkpoint_requested = false;
}

void serialize( JsonOut &out )
{
    if( !state.future_payload.empty() ) {
        write_raw( out, state.future_payload );
        return;
    }
    out.start_object();
    out.member( "schema_version", 1 );
    out.member( "world_id", state.world_id );
    out.member( "branch_id", state.branch_id );
    out.member( "actor_id", state.actor_id );
    out.member( "profile_id", state.profile_id );
    out.member( "policy_version", state.policy_version );
    out.member( "memory_version", state.memory_version );
    out.member( "personality" );
    write_raw( out, state.personality );
    out.member( "cognition" );
    write_raw( out, state.cognition );
    out.member( "control_state", state.control_state );
    out.member( "detach_state", state.detach_state );
    out.member( "paused", state.paused );
    out.member( "max_steps", state.max_steps );
    out.member( "cooldown", state.cooldown );
    out.member( "debug", state.debug );
    out.member( "decision_trigger", state.decision_trigger );
    out.member( "observation_signature", state.observation_signature );
    out.member( "save_nonce", state.save_nonce );
    out.member( "event_watermark", state.event_watermark );
    out.member( "acknowledged", state.acknowledged );
    out.member( "saved_checkpoint" );
    write_raw( out, state.pending_checkpoint == "null" ? state.saved_checkpoint :
               state.pending_checkpoint );
    out.member( "saved_memory_context" );
    write_raw( out, state.pending_checkpoint == "null" ? state.saved_memory_context :
               state.checkpoint_context );
    write_requirements( out, true );
    out.member( "events" );
    out.start_array();
    for( const std::string &entry : state.events ) {
        write_raw( out, entry );
    }
    out.end_array();
    out.member( "checkpoint_delta" );
    out.start_array();
    for( const std::string &entry : state.checkpoint_delta ) {
        write_raw( out, entry );
    }
    out.end_array();
    out.member( "queue" );
    out.start_array();
    for( const pending_step &entry : state.queue ) {
        out.start_object();
        out.member( "id", entry.step.id );
        out.member( "action", entry.step.action );
        out.member( "args" );
        write_raw( out, entry.step.args_json );
        out.member( "intent", entry.step.intent );
        out.member( "requirement_id", entry.step.requirement_id );
        out.member( "from_step", entry.from_step );
        out.member( "source_operation", entry.step.source_operation );
        out.member( "started", entry.started );
        out.end_object();
    }
    out.end_array();
    out.member( "receipts" );
    out.start_array();
    for( const auto &entry : state.receipts ) {
        write_raw( out, entry.second );
    }
    out.end_array();
    out.member( "accepted_plans", state.accepted_plans );
    out.member( "transcript" );
    out.start_array();
    for( const std::string &entry : state.transcript ) {
        write_raw( out, entry );
    }
    out.end_array();
    out.end_object();
}

void deserialize( const JsonObject &object )
{
    object.allow_omitted_members();
    reset();
    if( object.get_int( "schema_version", 0 ) != 1 ) {
        state.future_payload = object.str();
        state.control_state = "unsupported_schema";
        return;
    }
    try {
        state.world_id = object.get_string( "world_id" );
        state.branch_id = object.get_string( "branch_id" );
        if( !valid_identity( state.world_id ) || !valid_identity( state.branch_id ) ) {
            throw std::runtime_error( "invalid_saved_identity" );
        }
        state.actor_id = object.get_int( "actor_id", -1 );
        state.profile_id = object.get_string( "profile_id", "" );
        state.policy_version = object.get_string( "policy_version" );
        state.memory_version = object.get_string( "memory_version", "" );
        const JsonObject policy = subobject( object, "personality" );
        if( !validate_policy( policy ) ) {
            throw std::runtime_error( "invalid_saved_policy" );
        }
        state.personality = policy.str();
        state.cognition = subobject( object, "cognition" ).str();
        state.control_state = object.get_string( "control_state", "active" );
        state.detach_state = object.get_string( "detach_state", "attached" );
        state.paused = object.get_bool( "paused", false );
        state.debug = object.get_bool( "debug", false );
        state.decision_trigger = object.get_bool( "decision_trigger", false );
        state.observation_signature = object.get_string( "observation_signature", "" );
        state.max_steps = std::clamp( object.get_int( "max_steps", 5 ), 1, 5 );
        state.cooldown = std::clamp( object.get_int( "cooldown", 10 ), 0, 3600 );
        state.event_watermark = object.get_int64( "event_watermark" );
        state.acknowledged = object.get_int64( "acknowledged" );
        state.saved_checkpoint = stringify( object.get_member( "saved_checkpoint" ) );
        state.saved_memory_context = stringify( object.get_member( "saved_memory_context" ) );
        state.save_nonce = object.get_string( "save_nonce", "" );
        if( !state.save_nonce.empty() && !valid_identity( state.save_nonce ) ) {
            throw std::runtime_error( "invalid_save_nonce" );
        }
        if( has_binding() && !state.save_nonce.empty() ) {
            bool confirmed = false;
            const cata_path marker = checkpoint_marker();
            try {
                read_from_file_optional_json( marker, [&confirmed]( const JsonValue & value ) {
                    const JsonObject commit = value.get_object();
                    commit.allow_omitted_members();
                    confirmed = commit.get_int( "schema_version", 0 ) == 1 &&
                                commit.get_string( "save_nonce", "" ) == state.save_nonce &&
                                canonical( commit.get_member( "checkpoint" ) ) == canonical(
                                    json_loader::from_string( state.saved_checkpoint ) );
                } );
            } catch( const std::exception & ) {
                confirmed = false;
            }
            if( !confirmed ) {
                state.saved_checkpoint = "null";
                state.saved_memory_context = "null";
                state.last_error = "unconfirmed_save_checkpoint";
                state.paused = true;
                state.control_state = "reconcile_required";
            }
        }
        const JsonObject memory_context = state.saved_memory_context == "null" ? JsonObject() :
                                          read_object( state.saved_memory_context );
        const std::int64_t checkpoint_watermark = state.saved_checkpoint != "null" &&
                memory_context.has_int( "event_watermark" ) ?
                memory_context.get_int64( "event_watermark" ) : -1;
        if( object.has_array( "checkpoint_delta" ) ) {
            if( object.get_array( "checkpoint_delta" ).size() > maximum_events ) {
                throw std::runtime_error( "saved_event_limit" );
            }
            for( const JsonObject &entry : object.get_array( "checkpoint_delta" ) ) {
                entry.allow_omitted_members();
                if( state.events.size() >= maximum_events ) {
                    throw std::runtime_error( "saved_event_limit" );
                }
                if( entry.get_int64( "sequence" ) > checkpoint_watermark ) {
                    const std::string encoded = entry.str();
                    if( encoded.size() > maximum_event_bytes - state.event_bytes ) {
                        throw std::runtime_error( "saved_event_byte_limit" );
                    }
                    state.event_bytes += encoded.size();
                    state.events.push_back( encoded );
                }
            }
        }
        for( const JsonValue &entry : object.get_array( "events" ) ) {
            if( state.events.size() >= maximum_events ) {
                throw std::runtime_error( "saved_event_limit" );
            }
            const std::string encoded = stringify( entry );
            if( encoded.size() > maximum_event_bytes - state.event_bytes ) {
                throw std::runtime_error( "saved_event_byte_limit" );
            }
            state.event_bytes += encoded.size();
            state.events.push_back( encoded );
        }
        if( !state.events.empty() ) {
            // Redeliver the preserved delta with its original IDs. AgentMemory
            // deduplicates delivery and honors durable deletion tombstones.
            state.acknowledged = std::min( state.acknowledged,
                                           read_object( state.events.front() ).get_int64( "sequence" ) - 1 );
            state.decision_trigger = true;
        }
        if( object.has_array( "requirement_decisions" ) ) {
            for( const JsonObject &entry : object.get_array( "requirement_decisions" ) ) {
                entry.allow_omitted_members();
                const std::string id = entry.get_string( "requirement_id" );
                const std::string decision = entry.get_string( "decision" );
                const std::int64_t sequence = entry.get_int64( "source_sequence" );
                if( id.empty() || id.size() > 256 || sequence < 1 || sequence > state.event_watermark ||
                    state.requirement_decisions.size() >= maximum_events ||
                    ( decision != "pending" && decision != "accepted" && decision != "refused" ) ||
                    entry.get_string( "source_event_id" ) != id || state.requirement_decisions.count( id ) ) {
                    throw std::runtime_error( "invalid_saved_requirement" );
                }
                state.requirement_decisions.emplace( id, requirement_decision {
                    sequence, decision, entry.get_string( "operation_id", "" ), entry.get_string( "text", "" )
                } );
            }
        }
        for( const JsonObject &entry : object.get_array( "queue" ) ) {
            entry.allow_omitted_members();
            if( state.queue.size() >= 6 ) {
                throw std::runtime_error( "saved_queue_limit" );
            }
            const bool started = entry.get_bool( "started", false );
            state.queue.push_back( { {
                    entry.get_string( "id" ), entry.get_string( "action" ),
                    subobject( entry, "args" ).str(), entry.get_string( "intent", "" ),
                    entry.get_string( "source_operation", "" ), entry.get_string( "requirement_id", "" )
                },
                entry.get_string( "from_step", "" ), started, started } );
        }
        for( const JsonObject &entry : object.get_array( "receipts" ) ) {
            entry.allow_omitted_members();
            if( state.receipts.size() >= maximum_history ) {
                throw std::runtime_error( "saved_receipt_limit" );
            }
            const std::string operation = entry.get_string( "operation_id" );
            state.receipts[operation] = entry.str();
            state.receipt_order.push_back( operation );
        }
        if( object.has_object( "accepted_plans" ) ) {
            for( const JsonMember &entry : object.get_object( "accepted_plans" ) ) {
                if( state.accepted_plans.size() >= maximum_history || !entry.test_string() ) {
                    throw std::runtime_error( "saved_plan_limit" );
                }
                state.accepted_plans[entry.name()] = entry.get_string();
            }
        }
        for( const JsonValue &entry : object.get_array( "transcript" ) ) {
            if( state.transcript.size() >= maximum_transcript ) {
                break;
            }
            state.transcript.push_back( stringify( entry ) );
        }
        state.cognition_stale = true;
        invalidate_request();
    } catch( const std::exception & ) {
        // Retain unsupported/corrupt extension data without taking control or
        // replacing it with a guessed migration on the next native save.
        reset();
        state.future_payload = object.str();
        state.control_state = "unsupported_schema";
        state.last_error = "invalid_saved_control_state";
    }
}
} // namespace cata::actor_control
