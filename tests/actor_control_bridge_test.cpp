// Keep Asio's platform headers before native game headers.
#define ASIO_STANDALONE
#include <asio.hpp>

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iterator>
#include <locale>
#include <sstream>
#include <string>
#include <thread>

#ifdef _WIN32
    #include "platform_win.h"
#else
    #include <sys/stat.h>
    #include <unistd.h>
#endif

#include "actor_control.h"
#include "actor_control_bridge.h"
#include "actor_control_files.h"
#include "actor_control_protocol.h"
#include "actor_control_protocol_generated.h"
#include "avatar.h"
#include "calendar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "coordinates.h"
#include "flexbuffer_json.h"
#include "json.h"
#include "json_loader.h"
#include "map.h"
#include "map_helpers.h"
#include "map_helpers_tests.h"
#include "npc.h"
#include "path_info.h"
#include "player_helpers.h"
#include "type_id.h"

namespace
{
using cata::actor_control::loopback_bridge;
using tcp = asio::ip::tcp;

class grouped_integer_punctuation : public std::numpunct<char>
{
    protected:
        char do_thousands_sep() const override {
            return ',';
        }
        std::string do_grouping() const override {
            return "\3";
        }
};

bool is_wire_identity( const std::string &identity )
{
    return identity.size() == 32 && std::all_of( identity.begin(), identity.end(), []( const char ch ) {
        return ( ch >= '0' && ch <= '9' ) || ( ch >= 'a' && ch <= 'f' );
    } );
}

class isolated_actor_runtime
{
    public:
        isolated_actor_runtime() {
#ifdef _WIN32
            const wchar_t *value = _wgetenv( L"LOCALAPPDATA" );
            had_runtime_ = value != nullptr;
            old_runtime_ = value == nullptr ? L"" : value;
#else
            const char *value = std::getenv( "XDG_RUNTIME_DIR" );
            had_runtime_ = value != nullptr;
            old_runtime_ = value == nullptr ? "" : value;
#endif
            directory_ = std::filesystem::temp_directory_path() /
                         ( "cph-actor-bridge-test-" + cata::actor_control::new_identity() );
            REQUIRE( cata::actor_control::files::create_private_directory( directory_ ) == 0 );
#ifdef _WIN32
            REQUIRE( _wputenv_s( L"LOCALAPPDATA", directory_.c_str() ) == 0 );
#else
            REQUIRE( setenv( "XDG_RUNTIME_DIR", directory_.c_str(), 1 ) == 0 );
#endif
        }

        ~isolated_actor_runtime() {
#ifdef _WIN32
            _wputenv_s( L"LOCALAPPDATA", had_runtime_ ? old_runtime_.c_str() : L"" );
#else
            if( had_runtime_ ) {
                setenv( "XDG_RUNTIME_DIR", old_runtime_.c_str(), 1 );
            } else {
                unsetenv( "XDG_RUNTIME_DIR" );
            }
#endif
            std::error_code error;
            // This class owns a newly created test fixture, never a user path.
            std::filesystem::remove_all( directory_, error );
        }

        const std::filesystem::path &directory() const {
            return directory_;
        }
        std::filesystem::path runtime_root() const {
#ifdef _WIN32
            return directory_ / "cph-ai-companion" / "run";
#else
            return directory_ / "cph-ai-companion";
#endif
        }
    private:
        bool had_runtime_ = false;
#ifdef _WIN32
        std::wstring old_runtime_;
#else
        std::string old_runtime_;
#endif
        std::filesystem::path directory_;
};

std::string read_fixture_file( const std::filesystem::path &path )
{
    std::ifstream input( path );
    REQUIRE( input.good() );
    return std::string( std::istreambuf_iterator<char>( input ), std::istreambuf_iterator<char>() );
}

void require_permissions( const std::filesystem::path &path, const int permissions )
{
#ifdef _WIN32
    cata::actor_control::files::info value;
    REQUIRE( cata::actor_control::files::inspect( path, value ) == 0 );
    CHECK( value.private_access );
    CHECK( value.directory == ( permissions == 0700 ) );
#else
    struct stat info {};
    REQUIRE( lstat( path.c_str(), &info ) == 0 );
    CHECK( info.st_uid == getuid() );
    CHECK( ( info.st_mode & 0777 ) == permissions );
#endif
}

tcp::endpoint bridge_address( const loopback_bridge &bridge )
{
    const JsonObject descriptor = json_loader::from_string(
                                      read_fixture_file( std::filesystem::u8path( bridge.descriptor_path() ) ) ).get_object();
    descriptor.allow_omitted_members();
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

JsonObject controller_exchange( tcp::socket &client, const std::string &method,
                                const std::string &params = "{}" )
{
    const std::string packet = "{\"id\":1,\"method\":" + cata::actor_control::quote( method ) +
                               ",\"params\":" + params + "}\n";
    asio::write( client, asio::buffer( packet ) );
    client.non_blocking( true );
    std::string received;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds( 2 );
    while( std::chrono::steady_clock::now() < deadline && received.find( '\n' ) == std::string::npos ) {
        cata::actor_control::pump_incoming();
        char buffer[4096];
        asio::error_code error;
        const std::size_t count = client.read_some( asio::buffer( buffer ), error );
        if( error && error != asio::error::would_block && error != asio::error::try_again ) {
            FAIL( "controller reply connection closed" );
        }
        received.append( buffer, count );
        std::this_thread::sleep_for( std::chrono::milliseconds( 1 ) );
    }
    REQUIRE( received.find( '\n' ) != std::string::npos );
    JsonObject result = json_loader::from_string( received.substr( 0,
                        received.find( '\n' ) ) ).get_object();
    result.allow_omitted_members();
    return result;
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

TEST_CASE( "actor_control_worker_reports_are_transient_and_bound_to_the_current_request",
           "[actor_control][bridge][runtime][planning]" )
{
    namespace control = cata::actor_control;
    isolated_actor_runtime isolated;
    control::enable( false );
    control::reset();
    clear_avatar();
    clear_map_without_vision();
    control::enable( true );
    const on_out_of_scope cleanup( []() {
        control::enable( false );
        control::reset();
        clear_npcs();
    } );
    npc &actor = spawn_npc( get_avatar().pos_bub().xy() + point( 1, 0 ), "test_talker" );
    actor.set_fac( faction_id( "your_followers" ) );
    actor.set_attitude( NPCATT_FOLLOW );
    std::string error;
    REQUIRE( control::bind( actor, "planning-report-test", error ) );
    const JsonObject status = json_loader::from_string( control::status() ).get_object();
    status.allow_omitted_members();
    const std::filesystem::path path = std::filesystem::u8path(
                                           status.get_string( "descriptor_path" ) );
    const JsonObject descriptor = json_loader::from_string( read_fixture_file( path ) ).get_object();
    descriptor.allow_omitted_members();
    std::string credential = read_fixture_file( path.parent_path() / "credential" );
    credential.pop_back();
    asio::io_context io;
    tcp::socket client( io );
    client.connect( tcp::endpoint( asio::ip::address_v4::loopback(),
                                   static_cast<unsigned short>( descriptor.get_int( "port" ) ) ) );
    REQUIRE( controller_exchange( client, "hello", "{\"credential\":" + control::quote( credential ) +
                                  ",\"protocol_version\":" + control::quote( control::protocol_version ) +
                                  ",\"schema_digest\":" + control::quote( control::protocol_digest ) + "}" ).get_bool( "ok" ) );
    REQUIRE( controller_exchange( client, "sync_memory",
                                  R"({"version":"memory","snapshot":{"revision":"memory","records":[]}})" ).get_bool( "ok" ) );
    const auto member = []( const JsonObject & parent, const char *key ) {
        JsonObject value = parent.get_object( key );
        value.allow_omitted_members();
        return value;
    };
    const JsonObject request = member( controller_exchange( client, "take_request" ), "result" );
    const std::string prefix = "{\"planning_report\":{\"decision_id\":" +
                               control::quote( request.get_string( "decision_id" ) ) + ",\"request_id\":" +
                               control::quote( member( request, "context" ).get_string( "request_id" ) );
    const std::string thinking = prefix + R"(,"state":"thinking","reason":""}})";
    CHECK( member( controller_exchange( client, "status" ),
                   "result" ).get_string( "planning_state" ) == "pending" );
    CHECK( member( controller_exchange( client, "status", thinking ),
                   "result" ).get_string( "planning_state" ) == "thinking" );
    const JsonObject failed = member( controller_exchange( client, "status",
                                      prefix + R"(,"state":"failed","reason":"provider_failed"}})" ), "result" );
    CHECK( failed.get_string( "planning_state" ) == "failed" );
    CHECK( failed.get_string( "planning_reason" ) == "provider_failed" );
    CHECK( failed.get_string( "decision_id" ) == request.get_string( "decision_id" ) );
    CHECK( member( failed, "context" ).get_int64( "event_watermark" ) ==
           member( request, "context" ).get_int64( "event_watermark" ) );
    CHECK( member( controller_exchange( client, "status",
                                        prefix + R"(,"state":"suspended","reason":"call_budget_exhausted"}})" ),
                   "result" ).get_string( "planning_state" ) == "suspended" );
    const JsonObject rejected = controller_exchange( client, "status", R"({"unknown":"SECRET"})" );
    CHECK_FALSE( rejected.get_bool( "ok" ) );
    CHECK( member( rejected, "error" ).get_string( "code" ) == "unknown_field" );
    REQUIRE( control::chat( "A new decision", error ) );
    REQUIRE( controller_exchange( client, "take_request" ).get_bool( "ok" ) );
    const JsonObject stale = controller_exchange( client, "status", thinking );
    CHECK_FALSE( stale.get_bool( "ok" ) );
    CHECK( member( stale, "error" ).get_string( "code" ) == "stale_request" );
    CHECK( member( controller_exchange( client, "status" ),
                   "result" ).get_string( "planning_state" ) == "pending" );
    std::ostringstream saved;
    JsonOut out( saved );
    control::serialize( out );
    CHECK( saved.str().find( "planning_state" ) == std::string::npos );
    control::deserialize( json_loader::from_string( saved.str() ).get_object() );
    CHECK( control::status().find( "\"planning_state\":\"offline\"" ) != std::string::npos );
    control::dispatch( "status", thinking, error );
    CHECK( error == "stale_request" );
}

TEST_CASE( "actor_control_identity_ignores_global_numeric_locale",
           "[actor_control][bridge][locale]" )
{
    const std::locale original = std::locale();
    const on_out_of_scope restore_locale( [&]() {
        std::locale::global( original );
    } );
    std::locale::global( std::locale( std::locale::classic(), new grouped_integer_punctuation ) );
    std::ostringstream grouped;
    grouped << 1234567;
    REQUIRE( grouped.str() == "1,234,567" );
    const std::string identity = cata::actor_control::new_identity();
    INFO( "Identity under grouped numeric locale: " << identity );
    CHECK( is_wire_identity( identity ) );
}

TEST_CASE( "actor_control_binding_and_withdrawal_restore_under_grouped_numeric_locale",
           "[actor_control][bridge][locale][save]" )
{
    namespace control = cata::actor_control;
    isolated_actor_runtime fixture;
    const std::locale original = std::locale();
    const time_point old_turn = calendar::turn;
    const on_out_of_scope cleanup( [&]() {
        std::locale::global( original );
        control::enable( false );
        control::reset();
        clear_npcs();
        set_time( old_turn );
    } );
    control::enable( false );
    control::reset();
    clear_avatar();
    clear_map_without_vision();
    clear_npcs();
    set_time( calendar::turn_zero );
    get_avatar().setpos( get_map(), tripoint_bub_ms( 59, 60, 0 ) );
    npc &actor = spawn_npc( { 60, 60 }, "test_talker" );
    clear_character( actor, true );
    actor.setpos( get_map(), tripoint_bub_ms( 60, 60, 0 ) );
    actor.set_attitude( NPCATT_FOLLOW );
    actor.set_fac( faction_id( "your_followers" ) );
    actor.recalc_sight_limits();

    std::locale::global( std::locale( std::locale::classic(), new grouped_integer_punctuation ) );
    control::reset(); // Match the GUI: all new world/request identities inherit the user locale.
    control::enable( true );
    std::string error;
    REQUIRE( control::bind( actor, "locale-restore", error ) );
    REQUIRE( control::chat( "Withdraw this request.", error ) );
    const std::string withdrawn = control::player_requirements().back().id;
    REQUIRE( control::chat( "Keep this request.", error ) );
    const std::string retained = control::player_requirements().back().id;
    REQUIRE( control::withdraw_requirement( withdrawn, error ) );
    std::ostringstream saved;
    saved.imbue( std::locale::classic() );
    JsonOut out( saved );
    control::serialize( out );
    const JsonObject snapshot = json_loader::from_string( saved.str() ).get_object();
    snapshot.allow_omitted_members();
    const std::string world = snapshot.get_string( "world_id" );
    const std::string branch = snapshot.get_string( "branch_id" );
    CHECK( is_wire_identity( world ) );
    CHECK( is_wire_identity( branch ) );
    control::reset();
    control::deserialize( snapshot );
    CHECK( control::has_binding() );
    CHECK( control::is_bound( actor ) );
    const auto restored = control::player_requirements();
    REQUIRE( restored.size() == 2 );
    CHECK( restored[0].id == withdrawn );
    CHECK( restored[0].withdrawn );
    CHECK( restored[1].id == retained );
    CHECK_FALSE( restored[1].withdrawn );
    std::ostringstream again;
    again.imbue( std::locale::classic() );
    JsonOut again_out( again );
    control::serialize( again_out );
    const JsonObject reloaded = json_loader::from_string( again.str() ).get_object();
    reloaded.allow_omitted_members();
    CHECK( reloaded.get_string( "world_id" ) == world );
    CHECK( reloaded.get_string( "branch_id" ) == branch );
}

TEST_CASE( "actor_control_bridge_advertises_private_loopback_and_preserves_calendar",
           "[actor_control][bridge]" )
{
    isolated_actor_runtime fixture;
    loopback_bridge bridge;
    std::string error;
    REQUIRE( bridge.start( error ) );
    const std::filesystem::path descriptor_path = std::filesystem::u8path( bridge.descriptor_path() );
    require_permissions( fixture.runtime_root(), 0700 );
    require_permissions( descriptor_path.parent_path(), 0700 );
    require_permissions( descriptor_path, 0600 );
    require_permissions( descriptor_path.parent_path() / "credential", 0600 );
    const JsonObject descriptor = json_loader::from_string( read_fixture_file(
                                      descriptor_path ) ).get_object();
    descriptor.allow_omitted_members();
    CHECK( descriptor.get_string( "session_id" ) == bridge.session_id() );
    CHECK( descriptor.get_string( "credential_file" ) == "credential" );
    CHECK( descriptor.get_string( "protocol_version" ) == cata::actor_control::protocol_version );
    CHECK( descriptor.get_string( "schema_digest" ) == cata::actor_control::protocol_digest );
#ifdef _WIN32
    CHECK( descriptor.get_int( "pid" ) == static_cast<int>( GetCurrentProcessId() ) );
#else
    CHECK( descriptor.get_int( "pid" ) == getpid() );
#endif
    CHECK_FALSE( descriptor.get_string( "process_start" ).empty() );
    CHECK( descriptor.get_string( "user_dir" ) == std::filesystem::absolute(
               std::filesystem::u8path( PATH_INFO::user_dir() ) ).lexically_normal().u8string() );
    CHECK( descriptor.get_string( "config_dir" ) == std::filesystem::absolute(
               std::filesystem::u8path( PATH_INFO::config_dir() ) ).lexically_normal().u8string() );
    CHECK( descriptor.get_string( "save_dir" ) == std::filesystem::absolute(
               std::filesystem::u8path( PATH_INFO::savedir() ) ).lexically_normal().u8string() );
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
