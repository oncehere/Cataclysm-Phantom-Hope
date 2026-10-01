#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "action.h"
#include "avatar.h"
#include "calendar.h"
#include "cata_catch.h"
#include "coordinates.h"
#include "game.h"
#include "map.h"
#include "mp_client_conn.h"
#include "mp_gamestate.h"
#include "mp_intent.h"
#include "mp_queue.h"
#include "mp_server.h"
#include "npc.h"
#include "options.h"
#include "point.h"
#include "type_id.h"

namespace
{

using namespace std::chrono_literals;
const std::string probe_version = "a1b2c3d4e5f+SDL3";
const efftype_id effect_sleep( "sleep" );

// The Python launcher supplies a fresh IPC directory and independent user dirs.
// Files only synchronize checkpoints; every game mutation crosses real sockets.
struct session_probe {
    std::filesystem::path ipc;
    std::chrono::steady_clock::time_point deadline = std::chrono::steady_clock::now() + 20s;
    std::thread listener;
    std::atomic<bool> listener_done{ false };

    explicit session_probe( const char *directory ) : ipc( directory ) {}

    ~session_probe() {
        cata_mp::set_client_mode( false );
        if( listener.joinable() ) {
            // An abort can arrive before run_server publishes its pointer.
            // Wait for startup or failure before stopping and joining; joining
            // immediately after a null lookup could leave a live listener.
            // The Python launcher remains the final whole-process deadline.
            while( !listener_done.load() ) {
                if( cata_mp::server *srv = cata_mp::get_active_server() ) {
                    srv->stop();
                    break;
                }
                std::this_thread::sleep_for( 2ms );
            }
            listener.join();
        }
        cata_mp::set_host_mode( false );
        cata_mp::mp_reset_intent_state();
        cata_mp::mp_on_world_exit();
    }

    bool wait_for( const std::function<bool()> &predicate,
                   const std::function<void()> &pump = {} ) const {
        while( std::chrono::steady_clock::now() < deadline ) {
            if( pump ) {
                pump();
            }
            if( predicate() ) {
                return true;
            }
            if( std::filesystem::exists( ipc / "abort" ) ) {
                return false;
            }
            std::this_thread::sleep_for( 2ms );
        }
        return false;
    }

    bool has( const std::string &name ) const {
        return std::filesystem::exists( ipc / name );
    }

    void publish( const std::string &name, const std::string &value = "ready" ) const {
        const std::filesystem::path temporary = ipc / ( name + ".tmp" );
        {
            std::ofstream stream( temporary );
            REQUIRE( stream.good() );
            stream << value << '\n';
        }
        std::filesystem::rename( temporary, ipc / name );
    }

    std::string read( const std::string &name ) const {
        std::ifstream stream( ipc / name );
        std::string value;
        std::getline( stream, value );
        return value;
    }

    void start_host() {
        cata_mp::set_host_mode( true );
        // run_server publishes the same active pointer used by production state
        // broadcasts. Direct server::run would only exercise the transport.
        listener = std::thread( [this] {
            cata_mp::run_server( 0, "session-password", probe_version );
            listener_done.store( true );
        } );
        REQUIRE( wait_for( [this] {
            return cata_mp::get_active_server() != nullptr || listener_done.load();
        } ) );
        REQUIRE( cata_mp::get_active_server() != nullptr );
        publish( "port", std::to_string( cata_mp::get_active_server()->port() ) );
    }
};

void prepare_probe_map( const std::string &name )
{
    avatar &av = get_avatar();
    map &here = get_map();
    av.name = name;
    av.activity.set_to_null();
    av.remove_effect( effect_sleep );
    av.set_mutation( trait_id( "DEBUG_CLAIRVOYANCE" ) );
    const tripoint_bub_ms center( 60, 60, 0 );
    for( int y = 35; y <= 85; ++y ) {
        for( int x = 35; x <= 85; ++x ) {
            const tripoint_bub_ms p( x, y, 0 );
            here.ter_set( p, ter_id( "t_floor" ) );
            here.furn_set( p, furn_id( "f_null" ) );
            here.i_clear( p );
        }
    }
    av.setpos( here, center );
    av.set_moves( 0 );
    g->set_seed( 424242 );
    calendar::turn = calendar::turn_zero + 12_hours;
    get_options().get_option( "COOP_PARTNER_INTENT" ).setValue( "true" );
    cata_mp::mp_reset_intent_state();
}

cata_mp::intent_kind partner_hint( point &direction )
{
    tripoint_bub_ms target;
    return cata_mp::mp_partner_intent( get_avatar().pos_bub().z(), target, direction );
}

bool is_action_frame( const cata_mp::mp_event &event, const std::string &member )
{
    return event.evt_type == cata_mp::mp_event::type::action &&
           event.data.find( member ) != std::string::npos;
}

bool is_sleep_wait( const cata_mp::mp_event &event )
{
    return is_action_frame( event, R"("action":"wait")" ) &&
           event.data.find( R"("client_activity":"MP_ASLEEP")" ) != std::string::npos;
}

// Hold only events actually delivered by the real server IO thread. Requeue
// those same objects in their original order to choose the game-thread drain
// boundary deterministically, without constructing protocol snapshots.
void receive_through( session_probe &probe, std::vector<cata_mp::mp_event> &events,
                      const std::function<bool( const cata_mp::mp_event & )> &last_frame )
{
    REQUIRE( probe.wait_for( [&events, &last_frame] {
        cata_mp::mp_event event;
        while( cata_mp::get_mp_queue().pop( event ) )
        {
            events.emplace_back( std::move( event ) );
            if( last_frame( events.back() ) ) {
                return true;
            }
        }
        return false;
    } ) );
}

void restore_received_events( std::vector<cata_mp::mp_event> &events )
{
    for( cata_mp::mp_event &event : events ) {
        cata_mp::get_mp_queue().push( std::move( event ) );
    }
    events.clear();
}

void host_probe( session_probe &probe )
{
    prepare_probe_map( "session-host" );
    // Populate the real welcome metadata before the client probes.
    cata_mp::grant_client_turn();
    CHECK( cata_mp::mp_host_world_seed() == 424242 );
    CHECK( cata_mp::mp_host_active_mods_field().find( "\"ccb\"" ) != std::string::npos );
    CHECK( cata_mp::mp_host_active_mods_field().find( "\"test_data\"" ) != std::string::npos );
    REQUIRE_FALSE( cata_mp::mp_get_host_world_name().empty() );
    probe.publish( "world", cata_mp::mp_get_host_world_name() );
    probe.start_host();
    const auto pump = [] { cata_mp::process_mp_events(); };
    REQUIRE( probe.wait_for( [] { return cata_mp::get_partner_npc() != nullptr; }, pump ) );
    npc *remote = cata_mp::get_partner_npc();
    REQUIRE( remote->getID().is_valid() );
    CHECK( remote->getID() == cata_mp::get_remote_player_npc_character_id() );
    CHECK( remote->name == "session-client" );
    const tripoint_abs_ms initial_remote = remote->pos_abs();
    const tripoint_abs_ms initial_host = get_avatar().pos_abs();
    CHECK( initial_remote != initial_host );
    probe.publish( "host-joined" );
    REQUIRE( probe.wait_for( [&probe] { return probe.has( "client-joined" ); }, pump ) );

    point hint;
    REQUIRE( probe.wait_for( [&hint] {
        return partner_hint( hint ) == cata_mp::intent_kind::move;
    }, pump ) );
    CHECK( hint == point::east );
    cata_mp::mp_reset_intent_state();
    CHECK( partner_hint( hint ) == cata_mp::intent_kind::none );
    probe.publish( "intent-reset" );
    // The peer stages the SAME direction again after its reset. Receiving it
    // proves sender deduplication was cleared as well as our receiver state.
    REQUIRE( probe.wait_for( [&hint] {
        return partner_hint( hint ) == cata_mp::intent_kind::move;
    }, pump ) );
    CHECK( hint == point::east );
    CHECK( remote->pos_abs() == initial_remote );
    CHECK( get_avatar().pos_abs() == initial_host );
    cata_mp::mp_reset_intent_state();
    probe.publish( "intent-complete" );

    REQUIRE( probe.wait_for( [&probe] { return probe.has( "move-ready" ); }, pump ) );
    calendar::turn += 1_turns;
    cata_mp::grant_client_turn();
    REQUIRE( probe.wait_for( [&probe] { return probe.has( "move-pair-sent" ); } ) );
    std::vector<cata_mp::mp_event> move_batch;
    int received_moves = 0;
    receive_through( probe, move_batch, [&received_moves]( const cata_mp::mp_event & event ) {
        if( is_action_frame( event, R"("action":"move")" ) ) {
            CHECK( event.data.find( R"("client_tile_changes":)" ) != std::string::npos );
            return ++received_moves == 2;
        }
        return false;
    } );
    REQUIRE( received_moves == 2 );
    restore_received_events( move_batch );
    // Two genuine enriched moves emulate a retransmit. They must share this
    // single drain's turn slot even though both carry tile-delta metadata.
    cata_mp::process_mp_events();
    REQUIRE( cata_mp::client_acted_this_turn() );
    REQUIRE( remote->pos_abs() == initial_remote + tripoint_rel_ms::east );
    CHECK( get_avatar().pos_abs() == initial_host );
    probe.publish( "move-applied" );
    REQUIRE( probe.wait_for( [&probe] { return probe.has( "move-confirmed" ); }, pump ) );

    int stale_apply_count = 0;
    {
        cata_mp::mp_ui_item_ref_guard held_items;
        cata_mp::mp_defer_item_apply( [&stale_apply_count] { ++stale_apply_count; } );
        probe.publish( "resync-ready" );
        // No game-thread pump before the grant: the peer queues its rollback
        // request first, then the positive sleep grant is sent ahead of the
        // authoritative zero-budget snapshot produced while processing it.
        REQUIRE( probe.wait_for( [&probe] { return probe.has( "sleep-ready" ); } ) );
        calendar::turn += 1_turns;
        cata_mp::grant_client_turn();
        REQUIRE( probe.wait_for( [&probe] { return probe.has( "old-sleep-wait-sent" ); } ) );
        std::vector<cata_mp::mp_event> before_rollback;
        receive_through( probe, before_rollback, is_sleep_wait );
        const auto request_count = std::count_if( before_rollback.begin(), before_rollback.end(),
        []( const cata_mp::mp_event & event ) {
            return is_action_frame( event, R"("type":"item_resync_request")" );
        } );
        REQUIRE( request_count == 1 );
        cata_mp::mp_event old_wait = std::move( before_rollback.back() );
        before_rollback.pop_back();
        // Apply the request while retaining the old grant's real wait. The
        // client is paused at an IPC barrier, so it cannot ACK this snapshot
        // until we explicitly allow its game-thread pump to resume.
        restore_received_events( before_rollback );
        cata_mp::process_mp_events();
        CHECK_FALSE( cata_mp::client_acted_this_turn() );
        probe.publish( "resync-dispatched" );

        std::vector<cata_mp::mp_event> coalesced;
        coalesced.emplace_back( std::move( old_wait ) );
        bool received_epoch_ack = false;
        receive_through( probe, coalesced, [&received_epoch_ack]( const cata_mp::mp_event & event ) {
            if( is_action_frame( event, R"("type":"item_resync_ack")" ) ) {
                received_epoch_ack = true;
            }
            return received_epoch_ack && is_sleep_wait( event );
        } );
        REQUIRE( is_sleep_wait( coalesced.front() ) );
        REQUIRE( is_sleep_wait( coalesced.back() ) );
        CHECK( std::count_if( coalesced.begin(), coalesced.end(), is_sleep_wait ) == 2 );
        CHECK( std::count_if( coalesced.begin(), coalesced.end(),
        []( const cata_mp::mp_event & event ) {
            return is_action_frame( event, R"("type":"item_resync_ack")" );
        } ) == 1 );
        const size_t coalesced_event_count = coalesced.size();
        CAPTURE( coalesced_event_count );
        restore_received_events( coalesced );
        // Exactly one drain sees old wait, epoch ACK, then fresh sleep wait.
        // The stale wait must not consume this drain's valid turn-action slot.
        cata_mp::process_mp_events();
        REQUIRE( cata_mp::client_acted_this_turn() );
        probe.publish( "resync-coalesced", std::to_string( coalesced_event_count ) );
        CHECK( remote->pos_abs() == initial_remote + tripoint_rel_ms::east );
        probe.publish( "sleep-acked" );
        REQUIRE( probe.wait_for( [&probe] { return probe.has( "sleep-confirmed" ); }, pump ) );
    }
    CHECK( stale_apply_count == 0 );
    probe.publish( "host-complete" );
    REQUIRE( probe.wait_for( [] { return cata_mp::get_partner_npc() == nullptr; }, pump ) );
    CHECK( cata_mp::mp_host_partner_last_message_ms() == 0 );
    probe.publish( "host-done",
                   "JOIN proxy, intent reset, duplicate move/state, resync/sleep ACK, disconnect PASS" );
}

void client_probe( session_probe &probe )
{
    prepare_probe_map( "session-client" );
    REQUIRE( probe.wait_for( [&probe] { return probe.has( "port" ); } ) );
    const int port = std::stoi( probe.read( "port" ) );
    REQUIRE( port > 0 );
    REQUIRE( port <= 65535 );
    cata_mp::set_client_mode( true );
    REQUIRE( cata_mp::client_connect( "127.0.0.1", static_cast<uint16_t>( port ),
                                      "session-client", "session-password", probe_version ) );
    CHECK( cata_mp::mp_client_host_world_name() == probe.read( "world" ) );
    CHECK( cata_mp::mp_client_host_player_name() == "session-host" );
    CHECK_FALSE( cata_mp::client_join_is_sent() );
    const auto pump = [] { cata_mp::client_process_incoming(); };
    REQUIRE( probe.wait_for( [&probe] {
        return probe.has( "host-joined" ) && cata_mp::get_partner_npc() != nullptr;
    }, pump ) );
    CHECK( cata_mp::client_join_is_sent() );
    CHECK( cata_mp::get_partner_npc()->name == "session-host" );
    CHECK( cata_mp::get_partner_npc()->getID() == cata_mp::get_host_npc_character_id() );
    const tripoint_abs_ms initial_position = get_avatar().pos_abs();
    CHECK( initial_position != cata_mp::get_partner_npc()->pos_abs() );
    probe.publish( "client-joined" );
    get_avatar().set_moves( 0 );
    cata_mp::mp_stage_intent_action( ACTION_MOVE_RIGHT );
    REQUIRE( probe.wait_for( [&probe] { return probe.has( "intent-reset" ); }, pump ) );
    cata_mp::mp_reset_intent_state();
    cata_mp::mp_stage_intent_action( ACTION_MOVE_RIGHT );
    REQUIRE( probe.wait_for( [&probe] { return probe.has( "intent-complete" ); }, pump ) );
    CHECK( get_avatar().pos_abs() == initial_position );
    cata_mp::mp_clear_intent();

    probe.publish( "move-ready" );
    REQUIRE( probe.wait_for( [] { return get_avatar().get_moves() > 0; }, pump ) );
    cata_mp::client_send( cata_mp::client_enrich_action(
                              R"({"type":"action","action":"move","dir":"e"})" ) );
    cata_mp::client_send( cata_mp::client_enrich_action(
                              R"({"type":"action","action":"move","dir":"e"})" ) );
    get_avatar().set_moves( 0 );
    cata_mp::client_mark_action_sent();
    CHECK( cata_mp::is_client_waiting_for_ack() );
    probe.publish( "move-pair-sent" );
    REQUIRE( probe.wait_for( [&probe, &initial_position] {
        return probe.has( "move-applied" ) && !cata_mp::is_client_waiting_for_ack() &&
        get_avatar().pos_abs() == initial_position + tripoint_rel_ms::east;
    }, pump ) );
    CHECK( get_avatar().get_moves() <= 0 );
    probe.publish( "move-confirmed" );

    REQUIRE( probe.wait_for( [&probe] { return probe.has( "resync-ready" ); }, pump ) );
    get_avatar().add_effect( effect_sleep, 10_minutes );
    get_avatar().set_moves( 0 );
    cata_mp::client_send( R"({"type":"item_resync_request"})" );
    probe.publish( "sleep-ready" );
    REQUIRE( probe.wait_for( [] {
        return cata_mp::is_client_waiting_for_ack() &&
        cata_mp::get_client_turn_activity() == "MP_ASLEEP";
    }, pump ) );
    probe.publish( "old-sleep-wait-sent" );
    REQUIRE( probe.wait_for( [&probe] { return probe.has( "resync-dispatched" ); } ) );
    // apply_one_state_message consumes a sleeping avatar's grant immediately.
    // Observe its synthetic activity and host ACK rather than consuming twice.
    REQUIRE( probe.wait_for( [&probe] {
        return probe.has( "sleep-acked" ) && !cata_mp::is_client_waiting_for_ack() &&
        cata_mp::get_client_turn_activity() == "MP_ASLEEP";
    }, pump ) );
    CHECK( get_avatar().get_moves() == 0 );
    CHECK( get_avatar().has_effect( effect_sleep ) );
    CHECK( get_avatar().pos_abs() == initial_position + tripoint_rel_ms::east );
    probe.publish( "sleep-confirmed" );
    REQUIRE( probe.wait_for( [&probe] { return probe.has( "host-complete" ); }, pump ) );
    cata_mp::client_disable_reconnect();
    cata_mp::client_send( R"({"type":"quit"})" );
    REQUIRE( probe.wait_for( [&probe] { return probe.has( "host-done" ); } ) );
    probe.publish( "client-done",
                   "JOIN proxy, intent sender reset, duplicate move/state, resync/sleep ACK PASS" );
}

} // namespace

TEST_CASE( "mp_native_two_process_session", "[.][multiplayer][session]" )
{
    const char *role = std::getenv( "CPH_MP_PROBE_ROLE" );
    const char *ipc = std::getenv( "CPH_MP_PROBE_IPC" );
    REQUIRE( role != nullptr );
    REQUIRE( ipc != nullptr );
    session_probe probe( ipc );
    const std::string selected_role( role );
    CAPTURE( selected_role );
    if( selected_role == "host" ) {
        host_probe( probe );
    } else {
        REQUIRE( selected_role == "client" );
        client_probe( probe );
    }
}
