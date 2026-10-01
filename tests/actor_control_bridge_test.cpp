// Keep Asio's platform headers before native game headers.
#define ASIO_STANDALONE
#include <asio.hpp>

#ifndef _WIN32

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iterator>
#include <string>
#include <thread>

#include <sys/stat.h>
#include <unistd.h>

#include "actor_control_bridge.h"
#include "actor_control_protocol.h"
#include "actor_control_protocol_generated.h"
#include "calendar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "flexbuffer_json.h"
#include "json_loader.h"
#include "path_info.h"

namespace
{
using cata::actor_control::loopback_bridge;
using tcp = asio::ip::tcp;

class isolated_actor_runtime
{
    public:
        isolated_actor_runtime() {
            const char *value = std::getenv( "XDG_RUNTIME_DIR" );
            had_runtime_ = value != nullptr;
            old_runtime_ = value == nullptr ? "" : value;
            directory_ = std::filesystem::temp_directory_path() /
                         ( "cph-actor-bridge-test-" + cata::actor_control::new_identity() );
            std::filesystem::create_directory( directory_ );
            REQUIRE( chmod( directory_.c_str(), 0700 ) == 0 );
            REQUIRE( setenv( "XDG_RUNTIME_DIR", directory_.c_str(), 1 ) == 0 );
        }

        ~isolated_actor_runtime() {
            if( had_runtime_ ) {
                setenv( "XDG_RUNTIME_DIR", old_runtime_.c_str(), 1 );
            } else {
                unsetenv( "XDG_RUNTIME_DIR" );
            }
            std::error_code error;
            // This class owns a newly created test fixture, never a user path.
            std::filesystem::remove_all( directory_, error );
        }

        const std::filesystem::path &directory() const {
            return directory_;
        }
    private:
        bool had_runtime_ = false;
        std::string old_runtime_;
        std::filesystem::path directory_;
};

std::string read_fixture_file( const std::filesystem::path &path )
{
    std::ifstream input( path );
    REQUIRE( input.good() );
    return std::string( std::istreambuf_iterator<char>( input ), std::istreambuf_iterator<char>() );
}

void require_permissions( const std::filesystem::path &path, const mode_t permissions )
{
    struct stat info {};
    REQUIRE( lstat( path.c_str(), &info ) == 0 );
    CHECK( info.st_uid == getuid() );
    CHECK( ( info.st_mode & 0777 ) == permissions );
}

tcp::endpoint bridge_address( const loopback_bridge &bridge )
{
    const JsonObject descriptor = json_loader::from_string(
                                      read_fixture_file( bridge.descriptor_path() ) ).get_object();
    REQUIRE( descriptor.get_string( "host" ) == "127.0.0.1" );
    const int port = descriptor.get_int( "port" );
    REQUIRE( port > 0 );
    REQUIRE( port <= 65535 );
    return tcp::endpoint( asio::ip::address_v4::loopback(), static_cast<unsigned short>( port ) );
}

std::string exchange( loopback_bridge &bridge, tcp::socket &client, const std::string &line,
                      const std::function<std::string( const std::string & )> &handler )
{
    asio::write( client, asio::buffer( line + "\n" ) );
    client.non_blocking( true );
    std::string received;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds( 2 );
    while( std::chrono::steady_clock::now() < deadline && received.find( '\n' ) == std::string::npos ) {
        bridge.pump( handler );
        char buffer[4096];
        asio::error_code error;
        const std::size_t count = client.read_some( asio::buffer( buffer ), error );
        if( error && error != asio::error::would_block && error != asio::error::try_again ) {
            FAIL( "loopback reply connection closed" );
        }
        received.append( buffer, count );
        std::this_thread::sleep_for( std::chrono::milliseconds( 1 ) );
    }
    REQUIRE( received.find( '\n' ) != std::string::npos );
    return received.substr( 0, received.find( '\n' ) );
}

void feed_bounded( loopback_bridge &bridge, tcp::socket &client, const std::string &data,
                   const std::function<std::string( const std::string & )> &handler )
{
    client.non_blocking( true );
    std::size_t offset = 0;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds( 3 );
    while( offset < data.size() && std::chrono::steady_clock::now() < deadline ) {
        asio::error_code error;
        const std::size_t size = std::min<std::size_t>( 16384, data.size() - offset );
        const std::size_t count = client.write_some( asio::buffer( data.data() + offset, size ), error );
        if( error && error != asio::error::would_block && error != asio::error::try_again ) {
            return;
        }
        offset += count;
        bridge.pump( handler );
    }
    REQUIRE( offset == data.size() );
    for( int attempt = 0; attempt < 100 && bridge.connected(); ++attempt ) {
        bridge.pump( handler );
    }
}
} // namespace

TEST_CASE( "actor_control_bridge_advertises_private_loopback_and_preserves_calendar",
           "[actor_control][bridge]" )
{
    isolated_actor_runtime fixture;
    loopback_bridge bridge;
    std::string error;
    REQUIRE( bridge.start( error ) );
    const std::filesystem::path descriptor_path = bridge.descriptor_path();
    require_permissions( fixture.directory() / "cph-ai-companion", 0700 );
    require_permissions( descriptor_path.parent_path(), 0700 );
    require_permissions( descriptor_path, 0600 );
    require_permissions( descriptor_path.parent_path() / "credential", 0600 );
    const JsonObject descriptor = json_loader::from_string( read_fixture_file(
                                      descriptor_path ) ).get_object();
    CHECK( descriptor.get_string( "session_id" ) == bridge.session_id() );
    CHECK( descriptor.get_string( "credential_file" ) == "credential" );
    CHECK( descriptor.get_string( "protocol_version" ) == cata::actor_control::protocol_version );
    CHECK( descriptor.get_string( "schema_digest" ) == cata::actor_control::protocol_digest );
    CHECK( descriptor.get_int( "pid" ) == getpid() );
    CHECK_FALSE( descriptor.get_string( "process_start" ).empty() );
    CHECK( descriptor.get_string( "user_dir" ) == std::filesystem::absolute(
               PATH_INFO::user_dir() ).lexically_normal().string() );
    CHECK( descriptor.get_string( "config_dir" ) == std::filesystem::absolute(
               PATH_INFO::config_dir() ).lexically_normal().string() );
    CHECK( descriptor.get_string( "save_dir" ) == std::filesystem::absolute(
               PATH_INFO::savedir() ).lexically_normal().string() );
    CHECK( bool( read_fixture_file( descriptor_path.parent_path() / "credential" ) ==
                 bridge.credential() + "\n" ) );
    CHECK_FALSE( descriptor.has_member( "credential" ) );

    const time_point before = calendar::turn;
    asio::io_context io;
    tcp::socket client( io );
    client.connect( bridge_address( bridge ) );
    int handled = 0;
    CHECK( exchange( bridge, client, R"({"id":"one","method":"status","params":{}})",
    [&handled]( const std::string & message ) {
        ++handled;
        return message;
    } ) == R"({"id":"one","method":"status","params":{}})" );
    CHECK( handled == 1 );
    CHECK( calendar::turn == before );
    std::ofstream( descriptor_path.parent_path() / "user-note.txt" ) << "keep";
    bridge.close();
    CHECK_FALSE( std::filesystem::exists( descriptor_path ) );
    CHECK_FALSE( std::filesystem::exists( descriptor_path.parent_path() / "credential" ) );
    CHECK( read_fixture_file( descriptor_path.parent_path() / "user-note.txt" ) == "keep" );
}

TEST_CASE( "actor_control_bridge_instances_are_distinct_and_admit_one_active_client",
           "[actor_control][bridge]" )
{
    isolated_actor_runtime fixture;
    loopback_bridge first;
    loopback_bridge second;
    std::string error;
    REQUIRE( first.start( error ) );
    REQUIRE( second.start( error ) );
    CHECK( first.session_id() != second.session_id() );
    CHECK( bool( first.credential() != second.credential() ) );
    CHECK( bridge_address( first ) != bridge_address( second ) );
    asio::io_context io;
    tcp::socket owner( io );
    owner.connect( bridge_address( first ) );
    int handled = 0;
    const auto handler = [&handled]( const std::string & message ) {
        ++handled;
        return message;
    };
    CHECK( exchange( first, owner, "owner", handler ) == "owner" );
    tcp::socket other( io );
    other.connect( bridge_address( first ) );
    asio::write( other, asio::buffer( std::string( "second-client\n" ) ) );
    for( int attempt = 0; attempt < 50; ++attempt ) {
        first.pump( handler );
    }
    CHECK( handled == 1 );
    CHECK( exchange( first, owner, "owner-still-connected", handler ) == "owner-still-connected" );
    CHECK( handled == 2 );
}

TEST_CASE( "actor_control_bridge_rejects_oversized_incoming_and_outgoing_messages",
           "[actor_control][bridge]" )
{
    isolated_actor_runtime fixture;
    loopback_bridge bridge;
    std::string error;
    REQUIRE( bridge.start( error ) );
    asio::io_context io;
    tcp::socket client( io );
    client.connect( bridge_address( bridge ) );
    int handled = 0;
    const auto handler = [&handled]( const std::string & ) {
        ++handled;
        return "ok";
    };
    SECTION( "No delimiter can grow incoming memory without a bound" ) {
        feed_bounded( bridge, client, std::string( 1048577, 'x' ), handler );
        CHECK( handled == 0 );
        CHECK_FALSE( bridge.connected() );
    }
    SECTION( "A delimited oversized message cannot reach the handler" ) {
        feed_bounded( bridge, client, std::string( 1048577, 'x' ) + "\n", handler );
        CHECK( handled == 0 );
        CHECK_FALSE( bridge.connected() );
    }
    SECTION( "An oversized reply drops the connection" ) {
        asio::write( client, asio::buffer( std::string( "query\n" ) ) );
        bridge.pump( []( const std::string & ) {
            return std::string( 1048577, 'x' );
        } );
        CHECK_FALSE( bridge.connected() );
    }
    SECTION( "Exactly the maximum payload excludes its line delimiter" ) {
        feed_bounded( bridge, client, std::string( 1048576, 'x' ) + "\n", handler );
        CHECK( handled == 1 );
        CHECK( bridge.connected() );
    }
}

#endif // !_WIN32
