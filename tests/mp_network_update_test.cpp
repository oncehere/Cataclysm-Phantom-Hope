#include <chrono>
#include <functional>
#include <memory>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#ifndef ASIO_STANDALONE
    #define ASIO_STANDALONE
#endif
#include <asio.hpp>

#include "cata_catch.h"
#include "mp_client_conn.h"
#include "mp_queue.h"
#include "mp_server.h"

namespace
{

using namespace std::chrono_literals;

bool wait_until( const std::function<bool()> &predicate,
                 std::chrono::milliseconds timeout = 5s )
{
    const std::chrono::steady_clock::time_point deadline = std::chrono::steady_clock::now() + timeout;
    while( std::chrono::steady_clock::now() < deadline ) {
        if( predicate() ) {
            return true;
        }
        std::this_thread::sleep_for( 2ms );
    }
    return predicate();
}

void drain_events()
{
    cata_mp::mp_event event;
    while( cata_mp::get_mp_queue().pop( event ) ) {}
}

struct loopback_server {
    std::unique_ptr<cata_mp::server> instance;
    std::thread thread;
    uint16_t port = 0;
    std::string password;
    const std::string version = "a1b2c3d4e5f-dirty.123456+SDL3";

    explicit loopback_server( std::string password_ = "" )
        : password( std::move( password_ ) ) {
        cata_mp::set_client_mode( false );
        drain_events();
        start();
    }

    ~loopback_server() {
        cata_mp::set_client_mode( false );
        stop();
        drain_events();
    }

    void start() {
        instance = std::make_unique<cata_mp::server>( port, password, version );
        port = instance->port();
        cata_mp::server *const owner = instance.get();
        thread = std::thread( [owner] { owner->run(); } );
    }

    void stop() {
        if( instance ) {
            instance->stop();
            if( thread.joinable() ) {
                thread.join();
            }
            instance.reset();
        }
    }

    bool connect( const std::string &provided_password = "",
                  const std::string &client_version = "a1b2c3d4e5f+SDL3" ) {
        cata_mp::set_client_mode( true );
        return cata_mp::client_connect( "127.0.0.1", port, "quoted \"partner\"",
                                        provided_password, client_version );
    }
};

bool pop_event( cata_mp::mp_event::type type, cata_mp::mp_event &out )
{
    return wait_until( [type, &out] {
        while( cata_mp::get_mp_queue().pop( out ) )
        {
            if( out.evt_type == type ) {
                return true;
            }
        }
        return false;
    } );
}

bool pop_client_message( const std::string &needle, std::string &out )
{
    return wait_until( [&needle, &out] {
        while( cata_mp::client_recv_pop( out ) )
        {
            if( out.find( needle ) != std::string::npos ) {
                return true;
            }
        }
        return false;
    } );
}

// An independent second real socket leaves the production client's connection
// alive. Reads are bounded and cancellation keeps the socket open for PROBE.
struct raw_peer {
    asio::io_context io;
    asio::ip::tcp::socket socket{ io };
    asio::streambuf buffer;

    explicit raw_peer( uint16_t port ) {
        socket.connect( asio::ip::tcp::endpoint( asio::ip::address_v4::loopback(), port ) );
    }

    void send( const std::string &message ) {
        asio::write( socket, asio::buffer( message ) );
    }

    bool read_line( std::string &message, std::chrono::milliseconds timeout ) {
        io.restart();
        asio::steady_timer timer( io );
        timer.expires_after( timeout );
        bool received = false;
        timer.async_wait( [this]( const std::error_code & error ) {
            if( !error ) {
                socket.cancel();
            }
        } );
        asio::async_read_until( socket, buffer, '\n',
        [&timer, &received]( const std::error_code & error, std::size_t ) {
            received = !error;
            timer.cancel();
        } );
        io.run();
        if( received ) {
            std::istream input( &buffer );
            std::getline( input, message );
        }
        return received;
    }

    bool receive_matching( const std::string &needle, std::string &message,
                           std::chrono::milliseconds timeout = 3s ) {
        const auto deadline = std::chrono::steady_clock::now() + timeout;
        while( std::chrono::steady_clock::now() < deadline ) {
            const auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(
                                       deadline - std::chrono::steady_clock::now() );
            if( !read_line( message, remaining ) ) {
                return false;
            }
            if( message.find( needle ) != std::string::npos ) {
                return true;
            }
        }
        return false;
    }
};

} // namespace

// Real loopback sockets and wall-clock keepalives are deliberately opt-in.
TEST_CASE( "mp_network_probe_returns_without_waiting_for_its_deadline",
           "[.][multiplayer][network]" )
{
    loopback_server host;
    const std::chrono::steady_clock::time_point start = std::chrono::steady_clock::now();
    REQUIRE( cata_mp::tcp_probe( "127.0.0.1", host.port, 3000 ) );
    CHECK( std::chrono::steady_clock::now() - start < 2500ms );
    CHECK_FALSE( cata_mp::tcp_probe( "127.0.0.1", 0, 100 ) );
}

TEST_CASE( "mp_network_rejections_flush_and_handshake_fields_round_trip",
           "[.][multiplayer][network]" )
{
    loopback_server host( "quoted \"password\"\\with\nnewline" );
    SECTION( "wrong password returns the host's reason" ) {
        REQUIRE_FALSE( host.connect( "wrong" ) );
        CHECK( cata_mp::client_connect_error() == "Wrong password" );
    }
    SECTION( "version prefixes must be plausible commit hashes" ) {
        REQUIRE_FALSE( host.connect( host.password, "a" ) );
        CHECK( cata_mp::client_connect_error().find( "Version mismatch" ) != std::string::npos );
    }
    SECTION( "commit abbreviations and quoted passwords are accepted" ) {
        REQUIRE( host.connect( host.password, "a1b2c3d+SDL3" ) );
        CHECK_FALSE( cata_mp::client_join_is_sent() );
        CHECK( cata_mp::get_mp_queue().empty() );
        cata_mp::client_send_join();
        cata_mp::mp_event event;
        REQUIRE( pop_event( cata_mp::mp_event::type::connect, event ) );
        CHECK( event.session_id == "quoted \"partner\"" );
    }
}

TEST_CASE( "mp_network_prejoin_keepalive_does_not_spawn_or_queue_heartbeats",
           "[.][multiplayer][network]" )
{
    loopback_server host;
    REQUIRE( host.connect() );
    std::string message;
    while( cata_mp::client_recv_pop( message ) ) {}
    // The host IO thread keeps the socket warm while the game thread is idle.
    std::this_thread::sleep_for( 1700ms );
    CHECK_FALSE( cata_mp::client_recv_pop( message ) );
    CHECK_FALSE( cata_mp::client_join_is_sent() );
    CHECK_FALSE( cata_mp::client_is_reconnecting() );
    CHECK( cata_mp::get_mp_queue().empty() );
    CHECK( cata_mp::mp_host_partner_last_message_ms() == 0 );
    cata_mp::client_send_join();
    cata_mp::mp_event event;
    REQUIRE( pop_event( cata_mp::mp_event::type::connect, event ) );
    REQUIRE( wait_until( [] { return cata_mp::mp_client_measured_rtt_ms() >= 0; } ) );
    CHECK( cata_mp::mp_client_measured_rtt_ms() < 1000 );
    const int64_t last_message = cata_mp::mp_host_partner_last_message_ms();
    REQUIRE( last_message > 0 );
    REQUIRE( wait_until( [last_message] {
        return cata_mp::mp_host_partner_last_message_ms() > last_message;
    } ) );
    cata_mp::client_disable_reconnect();
    cata_mp::client_send( R"({"type":"quit"})" );
    REQUIRE( pop_event( cata_mp::mp_event::type::disconnect, event ) );
    CHECK( cata_mp::mp_host_partner_last_message_ms() == 0 );
    cata_mp::set_client_mode( false );
    REQUIRE( host.connect() );
    CHECK( cata_mp::mp_host_partner_last_message_ms() == 0 );
}

TEST_CASE( "mp_network_compressed_frames_and_queued_actions_preserve_order",
           "[.][multiplayer][network]" )
{
    loopback_server host;
    REQUIRE( host.connect() );
    cata_mp::client_send_join();
    cata_mp::mp_event event;
    REQUIRE( pop_event( cata_mp::mp_event::type::connect, event ) );
    const std::string payload = R"({"type":"state","network_payload":")" +
                                std::string( 12000, 'x' ) + "\"}";
    host.instance->post_broadcast( payload + "\n" );
    std::string message;
    REQUIRE( pop_client_message( "network_payload", message ) );
    CHECK( message == payload );
    host.instance->post_broadcast( R"({"z":"not-a-zstd-frame"})" "\n" );
    host.instance->post_broadcast( R"({"z":"#"})" "\n" );
    host.instance->post_broadcast( R"({"type":"state","after_invalid_frame":true})" "\n" );
    REQUIRE( pop_client_message( "after_invalid_frame", message ) );
    CHECK( message == R"({"type":"state","after_invalid_frame":true})" );

    for( int i = 0; i < 20; ++i ) {
        cata_mp::client_send( R"({"type":"action","network_sequence":)" + std::to_string( i ) + "}" );
    }
    for( int i = 0; i < 20; ++i ) {
        REQUIRE( pop_event( cata_mp::mp_event::type::action, event ) );
        CHECK( event.data == R"({"type":"action","network_sequence":)" + std::to_string( i ) + "}" );
    }
    cata_mp::client_disable_reconnect();
    cata_mp::client_send( R"({"type":"quit"})" );
    REQUIRE( pop_event( cata_mp::mp_event::type::disconnect, event ) );
    std::this_thread::sleep_for( 50ms );
    CHECK( cata_mp::get_mp_queue().empty() );
    CHECK_FALSE( cata_mp::client_is_reconnecting() );
}

TEST_CASE( "mp_network_reconnect_handshake_has_one_consumer_and_new_connection_ownership",
           "[.][multiplayer][network]" )
{
    loopback_server host;
    REQUIRE( host.connect() );
    cata_mp::client_send_join();
    cata_mp::mp_event event;
    REQUIRE( pop_event( cata_mp::mp_event::type::connect, event ) );
    host.stop();
    REQUIRE( wait_until( [] { return cata_mp::client_is_reconnecting(); } ) );
    host.start();
    std::string message;
    // Continuously drain incoming game messages while the worker re-PROBEs.
    // An unowned shared recv queue steals its welcome and times out here.
    REQUIRE( pop_client_message( "\"reconnected\":true", message ) );
    REQUIRE( wait_until( [] { return !cata_mp::client_is_reconnecting(); } ) );
    REQUIRE( pop_event( cata_mp::mp_event::type::connect, event ) );
    cata_mp::client_send( R"({"type":"action","new_connection":true})" );
    REQUIRE( pop_event( cata_mp::mp_event::type::action, event ) );
    CHECK( event.data == R"({"type":"action","new_connection":true})" );
    cata_mp::client_disable_reconnect();
    host.stop();
    std::this_thread::sleep_for( 100ms );
    CHECK_FALSE( cata_mp::client_is_reconnecting() );
}

TEST_CASE( "mp_network_only_the_one_authenticated_partner_receives_game_broadcasts",
           "[.][multiplayer][network]" )
{
    loopback_server host;
    REQUIRE( host.connect() );
    cata_mp::client_send_join();
    cata_mp::mp_event event;
    REQUIRE( pop_event( cata_mp::mp_event::type::connect, event ) );

    raw_peer visitor( host.port );
    std::string message;
    // A real IO heartbeat proves ACCEPT ran before the test broadcasts.
    REQUIRE( visitor.receive_matching( "\"heartbeat\"", message ) );
    host.instance->post_broadcast( R"({"type":"state","private_before_probe":true})" "\n" );
    REQUIRE( pop_client_message( "private_before_probe", message ) );
    CHECK_FALSE( visitor.receive_matching( "private_before_probe", message, 250ms ) );

    visitor.send( R"({"type":"version_probe","version":"a1b2c3d4e5f+SDL3"})" "\n" );
    REQUIRE( visitor.receive_matching( "\"welcome\"", message ) );
    host.instance->post_broadcast( R"({"type":"state","private_after_probe":true})" "\n" );
    REQUIRE( pop_client_message( "private_after_probe", message ) );
    CHECK_FALSE( visitor.receive_matching( "private_after_probe", message, 250ms ) );

    visitor.send( R"({"type":"join","name":"different partner","version":"a1b2c3d4e5f+SDL3"})" "\n" );
    REQUIRE( visitor.receive_matching( "\"error\"", message ) );
    CHECK( message.find( "host plus one partner" ) != std::string::npos );
    CHECK( cata_mp::get_mp_queue().empty() );
    cata_mp::client_send( R"({"type":"action","original_partner_alive":true})" );
    REQUIRE( pop_event( cata_mp::mp_event::type::action, event ) );
    CHECK( event.data.find( "original_partner_alive" ) != std::string::npos );

    cata_mp::client_disable_reconnect();
    raw_peer successor( host.port );
    successor.send( R"({"type":"join","name":"quoted \"partner\"","version":"a1b2c3d4e5f+SDL3"})"
                    "\n" );
    REQUIRE( successor.receive_matching( "\"welcome\"", message ) );
    REQUIRE( wait_until( [&event] { return cata_mp::get_mp_queue().pop( event ); } ) );
    CHECK( event.evt_type == cata_mp::mp_event::type::connect );
    CHECK( event.session_id == "quoted \"partner\"" );
    std::this_thread::sleep_for( 50ms );
    CHECK( cata_mp::get_mp_queue().empty() );
    successor.send( R"({"type":"action","successor_alive":true})" "\n" );
    REQUIRE( pop_event( cata_mp::mp_event::type::action, event ) );
    CHECK( event.data.find( "successor_alive" ) != std::string::npos );
}
