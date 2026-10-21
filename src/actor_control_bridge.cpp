// Keep Asio's platform headers before native game headers.
#define ASIO_STANDALONE
#include <asio.hpp>

#include "actor_control_bridge.h"

#include <array>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <locale>
#include <random>
#include <sstream>
#include <system_error>

#ifdef _WIN32
    #include "platform_win.h"
#else
    #include <unistd.h>
#endif

#include "actor_control_files.h"
#include "actor_control_protocol.h"
#include "actor_control_protocol_generated.h"
#include "path_info.h"

namespace cata::actor_control
{
namespace
{
constexpr std::size_t maximum_message = 1048576;
constexpr std::size_t maximum_outgoing = maximum_message * 4;

std::string environment( const char *name )
{
    const char *value = std::getenv( name );
    return value == nullptr ? std::string() : std::string( value );
}

std::string actual_directory( const std::string &path )
{
    return std::filesystem::absolute( std::filesystem::u8path( path ) ).lexically_normal().u8string();
}

bool private_directory( const std::filesystem::path &path )
{
    auto prefix = path.root_path();
    for( const auto &part : path.parent_path().relative_path() ) {
        prefix /= part;
        files::info value;
        if( files::inspect( prefix, value ) != 0 ) {
            if( errno != ENOENT || files::create_private_directory( prefix ) != 0 ) {
                return false;
            }
        } else if( !value.directory ) {
            return false;
        }
    }
    return files::create_private_directory( path ) == 0;
}

bool private_file( const std::filesystem::path &path, const std::string &content )
{
    const int fd = files::open( path, files::access::create_new );
    if( fd < 0 ) {
        return false;
    }
    std::size_t offset = 0;
    while( offset < content.size() ) {
        const auto count = files::write( fd, content.data() + offset, content.size() - offset );
        if( count <= 0 ) {
            files::close( fd );
            return false;
        }
        offset += count;
    }
    const bool saved = files::sync( fd ) == 0;
    files::close( fd );
    return saved;
}

int process_id()
{
#ifdef _WIN32
    return static_cast<int>( GetCurrentProcessId() );
#else
    return getpid();
#endif
}

std::string process_start()
{
#ifdef _WIN32
    FILETIME created, exited, kernel, user;
    if( GetProcessTimes( GetCurrentProcess(), &created, &exited, &kernel, &user ) ) {
        return std::to_string( ( static_cast<std::uint64_t>( created.dwHighDateTime ) << 32 ) |
                               created.dwLowDateTime );
    }
#elif defined(__linux__)
    std::ifstream file( "/proc/self/stat" );
    std::string line;
    std::getline( file, line );
    const std::size_t end = line.rfind( ')' );
    if( end != std::string::npos ) {
        std::istringstream fields( line.substr( end + 2 ) );
        std::string value;
        // The remainder starts at field 3; starttime is field 22.
        for( int index = 3; index <= 22; ++index ) {
            fields >> value;
        }
        return value;
    }
#endif
    return "";
}
} // namespace

std::string new_identity()
{
    std::random_device source;
    std::ostringstream output;
    output.imbue( std::locale::classic() );
    output << std::hex << std::setfill( '0' );
    for( int count = 0; count < 4; ++count ) {
        output << std::setw( 8 ) << source();
    }
    return output.str();
}

struct loopback_bridge::implementation {
    asio::io_context io;
    asio::ip::tcp::acceptor acceptor {io};
    std::unique_ptr<asio::ip::tcp::socket> socket;
    std::filesystem::path directory;
    std::string identity;
    std::string secret;
    std::string descriptor;
    std::string incoming;
    std::string outgoing;
};

loopback_bridge::loopback_bridge() : impl_( std::make_unique<implementation>() )
{
}

loopback_bridge::~loopback_bridge()
{
    close();
}

bool loopback_bridge::start( std::string &error )
{
    close();
    try {
        std::filesystem::path root;
#ifdef _WIN32
        const wchar_t *local = _wgetenv( L"LOCALAPPDATA" );
        if( !local || !*local ) {
            error = "no_private_runtime_directory";
            return false;
        }
        root = std::filesystem::path( local ) / "cph-ai-companion" / "run";
#else
        const std::string runtime = environment( "XDG_RUNTIME_DIR" );
        if( !runtime.empty() ) {
            root = std::filesystem::path( runtime ) / "cph-ai-companion";
        } else {
            const std::string cache = environment( "XDG_CACHE_HOME" );
            const std::string home = environment( "HOME" );
            if( cache.empty() && home.empty() ) {
                error = "no_private_runtime_directory";
                return false;
            }
            root = ( cache.empty() ? std::filesystem::path( home ) / ".cache" :
                     std::filesystem::path( cache ) ) / "cph-ai-companion" / "run";
        }
#endif
        if( !private_directory( root ) ) {
            error = "unsafe_runtime_directory";
            return false;
        }
        impl_->identity = new_identity();
        impl_->secret = new_identity() + new_identity();
        impl_->directory = root / impl_->identity;
        if( !private_directory( impl_->directory ) ) {
            error = "unsafe_session_directory";
            return false;
        }
        const asio::ip::tcp::endpoint address( asio::ip::address_v4::loopback(), 0 );
        impl_->acceptor.open( address.protocol() );
        impl_->acceptor.bind( address );
        impl_->acceptor.listen( 1 );
        impl_->acceptor.non_blocking( true );
        impl_->descriptor = ( impl_->directory / "session.json" ).u8string();
        const std::string json = "{\"session_id\":" + quote( impl_->identity ) +
                                 ",\"host\":\"127.0.0.1\",\"port\":" +
                                 std::to_string( impl_->acceptor.local_endpoint().port() ) +
                                 ",\"credential_file\":\"credential\",\"protocol_version\":" +
                                 quote( protocol_version ) + ",\"schema_digest\":" + quote( protocol_digest ) +
                                 ",\"pid\":" + std::to_string( process_id() ) +
                                 ",\"process_start\":" + quote( process_start() ) +
                                 ",\"user_dir\":" + quote( actual_directory( PATH_INFO::user_dir() ) ) +
                                 ",\"save_dir\":" + quote( actual_directory( PATH_INFO::savedir() ) ) +
                                 ",\"config_dir\":" + quote( actual_directory( PATH_INFO::config_dir() ) ) + "}\n";
        if( !private_file( impl_->directory / "credential", impl_->secret + "\n" ) ||
            !private_file( impl_->directory / "session.json", json ) ) {
            error = "session_descriptor_write_failed";
            close();
            return false;
        }
        return true;
    } catch( const std::exception & ) {
        error = "bridge_start_failed";
        close();
        return false;
    }
}

void loopback_bridge::disconnect()
{
    if( impl_->socket ) {
        asio::error_code ignored;
        impl_->socket->close( ignored );
        impl_->socket.reset();
    }
    impl_->incoming.clear();
    impl_->outgoing.clear();
}

void loopback_bridge::close()
{
    disconnect();
    asio::error_code ignored;
    impl_->acceptor.close( ignored );
    if( !impl_->directory.empty() ) {
        // Only our two freshly created files. Preserve unknown files, including
        // a runtime's liveness record, rather than recursively deleting a tree.
        std::error_code error;
        std::filesystem::remove( impl_->directory / "credential", error );
        std::filesystem::remove( impl_->directory / "session.json", error );
        std::filesystem::remove( impl_->directory, error );
    }
    impl_->directory.clear();
    impl_->descriptor.clear();
    impl_->secret.clear();
    impl_->identity.clear();
}

void loopback_bridge::pump( const std::function<std::string( const std::string & )> &handler )
{
    if( !listening() ) {
        return;
    }
    if( !impl_->socket ) {
        std::unique_ptr<asio::ip::tcp::socket> candidate =
            std::make_unique<asio::ip::tcp::socket>( impl_->io );
        asio::error_code error;
        impl_->acceptor.accept( *candidate, error );
        if( error ) {
            return;
        }
        candidate->non_blocking( true, error );
        if( error ) {
            return;
        }
        impl_->socket = std::move( candidate );
    }
    std::array<char, 16384> bytes;
    asio::error_code error;
    const std::size_t count = impl_->socket->read_some( asio::buffer( bytes ), error );
    if( error && error != asio::error::would_block && error != asio::error::try_again ) {
        disconnect();
        return;
    }
    impl_->incoming.append( bytes.data(), count );
    for( int handled = 0; handled < 16; ++handled ) {
        const std::size_t end = impl_->incoming.find( '\n' );
        if( end == std::string::npos ) {
            break;
        }
        if( end > maximum_message ) {
            disconnect();
            return;
        }
        const std::string message = impl_->incoming.substr( 0, end );
        impl_->incoming.erase( 0, end + 1 );
        const std::string reply = handler( message );
        if( !connected() ) {
            return;
        }
        if( reply.size() > maximum_message || impl_->outgoing.size() + reply.size() > maximum_outgoing ) {
            disconnect();
            return;
        }
        impl_->outgoing += reply + "\n";
    }
    const std::size_t next_end = impl_->incoming.find( '\n' );
    if( next_end == std::string::npos ? impl_->incoming.size() > maximum_message :
        next_end > maximum_message ) {
        disconnect();
        return;
    }
    if( !impl_->outgoing.empty() ) {
        error.clear();
        const std::size_t written = impl_->socket->write_some( asio::buffer( impl_->outgoing ), error );
        if( error && error != asio::error::would_block && error != asio::error::try_again ) {
            disconnect();
            return;
        }
        impl_->outgoing.erase( 0, written );
    }
}

bool loopback_bridge::listening() const
{
    return impl_->acceptor.is_open();
}

bool loopback_bridge::connected() const
{
    return impl_->socket && impl_->socket->is_open();
}

const std::string &loopback_bridge::credential() const
{
    return impl_->secret;
}

const std::string &loopback_bridge::session_id() const
{
    return impl_->identity;
}

const std::string &loopback_bridge::descriptor_path() const
{
    return impl_->descriptor;
}
} // namespace cata::actor_control
