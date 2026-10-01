// Networking only — no CDDA game headers allowed here (asio conflicts with PCH).
// Follow the same pattern as mp_server.cpp.
#define ASIO_STANDALONE

#include "mp_client_conn.h"

#include <asio.hpp> // IWYU pragma: keep
#include <asio/associated_cancellation_slot.hpp>
#include <asio/async_result.hpp>
#include <asio/buffer.hpp>
#include <asio/completion_condition.hpp>
#include <asio/connect.hpp>
#include <asio/detail/bind_handler.hpp>
#include <asio/detail/handler_invoke_helpers.hpp>
#include <asio/detail/impl/epoll_reactor.hpp>
#include <asio/detail/impl/reactive_socket_service_base.ipp>
#include <asio/detail/impl/resolver_service_base.ipp>
#include <asio/detail/impl/scheduler.ipp>
#include <asio/detail/impl/service_registry.hpp>
#include <asio/error_code.hpp>
#include <asio/execution/context_as.hpp>
#include <asio/execution/prefer_only.hpp>
#include <asio/impl/any_io_executor.ipp>
#include <asio/impl/connect.hpp>
#include <asio/impl/handler_alloc_hook.ipp>
#include <asio/impl/io_context.hpp>
#include <asio/impl/io_context.ipp>
#include <asio/impl/read_until.hpp>
#include <asio/impl/write.hpp>
#include <asio/io_context.hpp>
#include <asio/ip/basic_resolver_iterator.hpp>
#include <asio/ip/tcp.hpp>
#include <asio/post.hpp>
#include <asio/steady_timer.hpp>
#include <asio/streambuf.hpp>
#include <cstddef>
#include <zstd/zstd.h>
#include <chrono>
#include <iostream>
#include <atomic>
#include <algorithm>
#include <condition_variable>
#include <deque>
#include <functional>
#include <limits>
#include <iterator>
#include <cstdlib>
#include <vector>
#include <memory>
#include <mutex>
#include <new>
#include <queue>
#include <string>
#include <thread>
#include <utility>

#include "catacharset.h"   // base64_decode — only pulls std headers, asio-safe

using asio::ip::tcp;

namespace cata_mp
{

// Keep game headers out of this Asio translation unit (enum_traits conflicts
// with Asio's atomic operators).  Welcome adoption is confined to the game
// thread; a reconnect worker never mutates world/character state directly.
void mp_log( const std::string &msg ); // NOLINT(cata-static-declarations)
void mp_set_client_host_world_name( const std::string &name ); // NOLINT(cata-static-declarations)
void mp_set_client_host_player_name( const std::string &name ); // NOLINT(cata-static-declarations)
void mp_store_pending_welcome( const std::string &msg ); // NOLINT(cata-static-declarations)

static std::atomic<bool> client_mode_{ false };
static constexpr int64_t MP_HB_INTERVAL_MS = 1500;
static constexpr int64_t MP_STALL_MS = 8000;
static constexpr size_t MP_MAX_FRAME_BYTES = 64 * 1024 * 1024;
static constexpr int MP_PREAUTH_REDIAL_MAX = 3;

static int64_t mp_now_ms()
{
    return std::chrono::duration_cast<std::chrono::milliseconds>(
               std::chrono::steady_clock::now().time_since_epoch() ).count();
}

class string_queue // NOLINT(misc-use-internal-linkage)
{
    public:
        void push( std::string s ) {
            {
                std::scoped_lock lock( mutex_ );
                queue_.push( std::move( s ) );
            }
            cv_.notify_one();
        }
        bool pop( std::string &out ) {
            std::scoped_lock lock( mutex_ );
            if( queue_.empty() ) {
                return false;
            }
            out = std::move( queue_.front() );
            queue_.pop();
            return true;
        }
        void clear() {
            std::scoped_lock lock( mutex_ );
            std::queue<std::string> empty;
            queue_.swap( empty );
        }
        bool wait_pop( std::string &out, std::chrono::milliseconds timeout ) {
            std::unique_lock<std::mutex> lock( mutex_ );
            if( !cv_.wait_for( lock, timeout, [this] { return !queue_.empty(); } ) ) {
                return false;
            }
            out = std::move( queue_.front() );
            queue_.pop();
            return true;
        }
    private:
        std::queue<std::string> queue_;
        std::mutex mutex_;
        std::condition_variable cv_;
};

static string_queue g_recv_queue;
static std::atomic<bool> g_rc_enabled{ false };
static std::atomic<bool> g_rc_in_progress{ false };
static std::atomic<int> g_hb_rtt_ms{ -1 };

// These fields are protected by g_connect_mutex, which serializes explicit
// connects, pre-JOIN re-dials, and the worker's connect+JOIN transaction.
struct connect_params { // NOLINT(misc-use-internal-linkage)
    std::string host;
    uint16_t port = 0;
    std::string name;
    std::string password;
    std::string version;
};
static std::mutex g_connect_mutex;
static connect_params g_params;
static int g_preauth_redials = 0;
static std::string g_connect_error;
static std::mutex g_error_mutex;

static void set_connect_error( std::string error )
{
    std::scoped_lock lock( g_error_mutex );
    g_connect_error = std::move( error );
}

static std::string mp_json_escape( const std::string &value )
{
    std::string out;
    for( const unsigned char c : value ) {
        switch( c ) {
            case '\"':
                out += "\\\"";
                break;
            case '\\':
                out += "\\\\";
                break;
            case '\n':
                out += "\\n";
                break;
            case '\r':
                out += "\\r";
                break;
            case '\t':
                out += "\\t";
                break;
            default:
                if( c < 0x20 ) {
                    static constexpr char hex[] = "0123456789abcdef";
                    out += "\\u00";
                    out += hex[c >> 4];
                    out += hex[c & 15];
                } else {
                    out += static_cast<char>( c );
                }
                break;
        }
    }
    return out;
}

// The small protocol's string fields are emitted as UTF-8 with JSON escapes.
// Decode escapes so a quoted player name/password round-trips the handshake.
static std::string json_get_str( const std::string &json, const std::string &key )
{
    size_t pos = json.find( "\"" + key + "\"" );
    if( pos == std::string::npos ) {
        return {};
    }
    pos = json.find( ':', pos + key.size() + 2 );
    if( pos == std::string::npos ) {
        return {};
    }
    ++pos;
    while( pos < json.size() && ( json[pos] == ' ' || json[pos] == '\t' ) ) {
        ++pos;
    }
    if( pos >= json.size() || json[pos++] != '\"' ) {
        return {};
    }
    std::string out;
    while( pos < json.size() ) {
        char c = json[pos++];
        if( c == '\"' ) {
            return out;
        }
        if( c == '\\' ) {
            if( pos == json.size() ) {
                return {};
            }
            c = json[pos++];
            switch( c ) {
                case 'n':
                    c = '\n';
                    break;
                case 'r':
                    c = '\r';
                    break;
                case 't':
                    c = '\t';
                    break;
                case 'b':
                    c = '\b';
                    break;
                case 'f':
                    c = '\f';
                    break;
                case 'u': {
                    if( json.size() - pos < 4 ) {
                        return {};
                    }
                    uint32_t codepoint = 0;
                    for( int digit = 0; digit < 4; ++digit ) {
                        const char h = json[pos++];
                        codepoint <<= 4;
                        if( h >= '0' && h <= '9' ) {
                            codepoint += h - '0';
                        } else if( h >= 'a' && h <= 'f' ) {
                            codepoint += h - 'a' + 10;
                        } else if( h >= 'A' && h <= 'F' ) {
                            codepoint += h - 'A' + 10;
                        } else {
                            return {};
                        }
                    }
                    // Protocol producers emit non-ASCII as UTF-8 directly.
                    // Reject isolated surrogates rather than emitting invalid UTF-8.
                    if( codepoint >= 0xd800 && codepoint <= 0xdfff ) {
                        return {};
                    }
                    out += utf32_to_utf8( codepoint );
                    continue;
                }
                case '\"':
                case '\\':
                case '/':
                    break;
                default:
                    return {};
            }
        }
        out += c;
    }
    return {};
}

static std::string mp_decompress_frame( std::string line )
{
    static const std::string prefix = R"({"z":")";
    if( line.size() <= prefix.size() + 2 ||
        line.compare( 0, prefix.size(), prefix ) != 0 ||
        line.compare( line.size() - 2, 2, "\"}" ) != 0 ) {
        return line;
    }
    const std::string encoded = line.substr( prefix.size(), line.size() - prefix.size() - 2 );
    // catacharset's marked base64 decoder expects a nonempty encoded body.
    // A lone '#' otherwise reaches its raw decoder with a zero-length buffer.
    if( !encoded.empty() && encoded.front() == '#' && encoded.size() < 5 ) {
        return {};
    }
    const std::string comp = base64_decode( encoded );
    const unsigned long long orig = ZSTD_getFrameContentSize( comp.data(), comp.size() );
    if( orig == ZSTD_CONTENTSIZE_UNKNOWN || orig == ZSTD_CONTENTSIZE_ERROR ||
        orig == 0 || orig > MP_MAX_FRAME_BYTES ) {
        mp_log( "[cdda-mp] decompress: invalid/oversized zstd frame; dropping" );
        return {};
    }
    std::string out( static_cast<size_t>( orig ), '\0' );
    const size_t n = ZSTD_decompress( out.data(), out.size(), comp.data(), comp.size() );
    if( ZSTD_isError( n ) ) {
        mp_log( std::string( "[cdda-mp] decompress error: " ) + ZSTD_getErrorName( n ) );
        return {};
    }
    out.resize( n );
    return out;
}

static void schedule_reconnect( const std::string &why );

struct client_impl :
    std::enable_shared_from_this<client_impl> { // NOLINT(misc-use-internal-linkage)
    asio::io_context io_ctx;
    tcp::socket sock{ io_ctx };
    asio::streambuf read_buf{ MP_MAX_FRAME_BYTES };
    asio::steady_timer hb_timer{ io_ctx };
    std::thread io_thread;
    string_queue handshake_queue;
    std::string pending_join;
    std::atomic<bool> alive{ true };
    std::atomic<bool> joined{ false };
    std::atomic<bool> awaiting_probe{ true };
    std::atomic<bool> stopping{ false };
    std::atomic<int> preauth_hb_count{ 0 };
    int64_t connected_ms = 0;
    int64_t last_recv_ms = 0;
    int64_t ping_stamp = -1;
    std::deque<std::string> write_queue;
    bool writing = false;
    bool heartbeat_started = false;

    ~client_impl() {
        shutdown();
    }

    // Always invoked by the connection owner, never from an IO callback.
    // Retain that owner until all callbacks have stopped and the thread joined.
    void shutdown() {
        stopping.store( true );
        io_ctx.stop();
        if( io_thread.joinable() ) {
            io_thread.join();
        }
    }

    void failed( const std::string &reason ) {
        if( stopping.load() || !alive.exchange( false ) ) {
            return;
        }
        asio::error_code ignore;
        hb_timer.cancel( ignore );
        sock.close( ignore );
        mp_log( "[cdda-mp] DISCONNECT: server connection closed (" + reason + ")" );
        if( awaiting_probe.load() ) {
            handshake_queue.push( R"({"type":"link_lost"})" );
        } else if( joined.load() ) {
            if( g_rc_enabled.load() ) {
                schedule_reconnect( reason );
            } else {
                g_recv_queue.push( R"({"type":"state","connected":false})" );
            }
        } else {
            mp_log( "[cdda-mp] HANDSHAKE: link lost during character creation; re-dial at JOIN" );
        }
    }

    // All socket writes, including PROBE/JOIN/heartbeat, use this single queue.
    // The weak capture binds a posted send to this connection, never its successor.
    void send( std::string message ) {
        const std::weak_ptr<client_impl> weak = shared_from_this();
        asio::post( io_ctx, [weak, message = std::move( message )]() {
            const std::shared_ptr<client_impl> self = weak.lock();
            if( !self || !self->alive.load() || self->stopping.load() ) {
                return;
            }
            self->write_queue.push_back( message );
            if( !self->writing ) {
                self->do_write();
            }
        } );
    }

    void do_write() {
        if( write_queue.empty() || !alive.load() ) {
            writing = false;
            return;
        }
        writing = true;
        const std::shared_ptr<std::string> buffer = std::make_shared<std::string>();
        for( const std::string &message : write_queue ) {
            buffer->append( message );
        }
        write_queue.clear();
        const std::weak_ptr<client_impl> weak = shared_from_this();
        asio::async_write( sock, asio::buffer( *buffer ),
        [weak, buffer]( const asio::error_code & ec, size_t ) {
            const std::shared_ptr<client_impl> self = weak.lock();
            if( !self ) {
                return;
            }
            if( ec ) {
                self->failed( ec.message() );
                return;
            }
            self->do_write();
        } );
    }

    void arm_heartbeat() {
        hb_timer.expires_after( std::chrono::milliseconds( MP_HB_INTERVAL_MS ) );
        const std::weak_ptr<client_impl> weak = shared_from_this();
        hb_timer.async_wait( [weak]( const asio::error_code & ec ) {
            const std::shared_ptr<client_impl> self = weak.lock();
            if( ec || !self || !self->alive.load() ) {
                return;
            }
            if( self->joined.load() && self->heartbeat_started ) {
                const int64_t now = mp_now_ms();
                if( now - self->last_recv_ms > MP_STALL_MS ) {
                    self->failed( "host silent >8000ms" );
                    return;
                }
                self->ping_stamp = now;
                self->send( R"({"type":"heartbeat","cp":)" + std::to_string( now ) +
                            R"(,"rtt":)" + std::to_string( g_hb_rtt_ms.load() ) + "}\n" );
            }
            // Pre-JOIN receives host keepalives but sends no heartbeat/JOIN.
            self->arm_heartbeat();
        } );
    }

    void start_read() {
        const std::weak_ptr<client_impl> weak = shared_from_this();
        asio::async_read_until( sock, read_buf, '\n',
        [weak]( const asio::error_code & ec, size_t ) {
            const std::shared_ptr<client_impl> self = weak.lock();
            if( !self ) {
                return;
            }
            if( ec ) {
                self->failed( ec.message() );
                return;
            }
            self->last_recv_ms = mp_now_ms();
            std::istream stream( &self->read_buf );
            std::string line;
            std::getline( stream, line );
            std::string message = mp_decompress_frame( std::move( line ) );
            if( !message.empty() ) {
                const std::string type = json_get_str( message, "type" );
                if( type == "heartbeat" ) {
                    const size_t pos = message.find( "\"pong\":" );
                    if( pos != std::string::npos ) {
                        const int64_t stamp = std::strtoll( message.c_str() + pos + 7, nullptr, 10 );
                        if( stamp == self->ping_stamp && stamp >= 0 ) {
                            const int64_t rtt = mp_now_ms() - stamp;
                            g_hb_rtt_ms.store( static_cast<int>( std::min<int64_t>( rtt,
                                                                 std::numeric_limits<int>::max() ) ) );
                        }
                    }
                    if( !self->joined.load() ) {
                        self->preauth_hb_count.fetch_add( 1 );
                    }
                } else if( self->awaiting_probe.load() && ( type == "welcome" || type == "error" ) ) {
                    // Route at the producer, so a running game loop can never
                    // consume a reconnect worker's handshake response.
                    self->handshake_queue.push( std::move( message ) );
                } else {
                    if( type == "goodbye" || type == "session_ending" ) {
                        g_rc_enabled.store( false );
                    }
                    g_recv_queue.push( std::move( message ) );
                }
            }
            if( self->alive.load() ) {
                self->start_read();
            }
        } );
    }
};

static std::shared_ptr<client_impl> g_client;
static std::mutex g_client_mutex;

static std::shared_ptr<client_impl> current_client()
{
    std::scoped_lock lock( g_client_mutex );
    return g_client;
}

static void replace_client( std::shared_ptr<client_impl> next )
{
    std::shared_ptr<client_impl> previous;
    {
        std::scoped_lock lock( g_client_mutex );
        previous = std::move( g_client );
    }
    if( previous ) {
        previous->shutdown();
    }
    {
        std::scoped_lock lock( g_client_mutex );
        g_client = std::move( next );
    }
}

// DNS resolution and TCP establishment share one deadline.  A successful
// connect cancels the timer immediately (the old probe always cost all 3 s).
static bool bounded_connect( asio::io_context &io, tcp::socket &socket,
                             const std::string &host, uint16_t port, int timeout_ms,
                             asio::error_code &result )
{
    tcp::resolver resolver( io );
    asio::steady_timer timer( io );
    bool finished = false;
    bool connected = false;
    timer.expires_after( std::chrono::milliseconds( std::max( 1, timeout_ms ) ) );
    timer.async_wait( [&resolver, &socket, &finished, &result]( const asio::error_code & ec ) {
        if( ec || finished ) {
            return;
        }
        result = asio::error::timed_out;
        resolver.cancel();
        asio::error_code ignore;
        socket.close( ignore );
    } );
    resolver.async_resolve( host, std::to_string( port ),
                            [&socket, &timer, &finished, &connected, &result]( const asio::error_code & ec,
    tcp::resolver::results_type endpoints ) {
        if( result == asio::error::timed_out ) {
            finished = true;
            return;
        }
        if( ec ) {
            result = ec;
            finished = true;
            asio::error_code ignore;
            timer.cancel( ignore );
            return;
        }
        asio::async_connect( socket, endpoints,
                             [&timer, &finished, &connected, &result]( const asio::error_code & connect_ec,
        const tcp::endpoint & ) {
            finished = true;
            connected = !connect_ec;
            if( result != asio::error::timed_out ) {
                result = connect_ec;
            }
            asio::error_code ignore;
            timer.cancel( ignore );
        } );
    } );
    io.run();
    io.restart();
    return connected;
}

bool tcp_probe( std::string_view host, uint16_t port, int timeout_ms )
{
    try {
        asio::io_context io;
        tcp::socket socket( io );
        asio::error_code result;
        return bounded_connect( io, socket, std::string( host ), port, timeout_ms, result );
    } catch( const std::exception & ) {
        return false;
    }
}

// Caller owns g_connect_mutex.  The per-connection handshake queue and a
// retained owner prevent stale welcomes and connection replacement races.
static bool connect_impl( const connect_params &params, bool reconnect )
{
    replace_client( nullptr );
    set_connect_error( "" );
    g_hb_rtt_ms.store( -1 );
    const std::shared_ptr<client_impl> connection = std::make_shared<client_impl>();
    asio::error_code ec;
    if( !bounded_connect( connection->io_ctx, connection->sock, params.host, params.port, 3000, ec ) ) {
        set_connect_error( "Could not connect: " + ec.message() );
        mp_log( "[cdda-mp] HANDSHAKE: could not connect to " + params.host + ":" +
                std::to_string( params.port ) + " (" + ec.message() + ")" );
        return false;
    }
    connection->sock.set_option( tcp::no_delay( true ), ec );
    mp_log( "[cdda-mp] client TCP_NODELAY ec=" + ec.message() );
    connection->sock.set_option( asio::socket_base::keep_alive( true ), ec );
    connection->connected_ms = mp_now_ms();
    connection->last_recv_ms = connection->connected_ms;
    connection->pending_join = R"({"type":"join","name":")" + mp_json_escape( params.name ) +
                               R"(","password":")" + mp_json_escape( params.password ) +
                               R"(","version":")" + mp_json_escape( params.version ) + "\"}\n";
    replace_client( connection );
    connection->start_read();
    connection->arm_heartbeat();
    client_impl *const owner = connection.get();
    connection->io_thread = std::thread( [owner] { owner->io_ctx.run(); } );
    connection->send( R"({"type":"version_probe","password":")" + mp_json_escape( params.password ) +
                      R"(","version":")" + mp_json_escape( params.version ) + "\"}\n" );
    mp_log( "[cdda-mp] HANDSHAKE: sent version_probe to " + params.host + ":" +
            std::to_string( params.port ) + " (our version='" + params.version + "'" +
            ( params.password.empty() ? "" : ", password set" ) + ")" );
    std::string message;
    if( !connection->handshake_queue.wait_pop( message, std::chrono::seconds( 5 ) ) ) {
        set_connect_error( "Timed out waiting for server response." );
    } else if( json_get_str( message, "type" ) == "error" ) {
        const std::string error = json_get_str( message, "message" );
        set_connect_error( error.empty() ? "Server rejected connection." : error );
    } else if( json_get_str( message, "type" ) == "welcome" && connection->alive.load() ) {
        connection->awaiting_probe.store( false );
        g_params = params;
        // Initial connect runs on the game/menu thread.  The worker only
        // re-admits the existing character; game-state adoption stays on its owner.
        if( !reconnect ) {
            const std::string world = json_get_str( message, "world" );
            if( !world.empty() && world != "default" ) {
                mp_set_client_host_world_name( world );
            }
            const std::string host_name = json_get_str( message, "host_name" );
            if( !host_name.empty() ) {
                mp_set_client_host_player_name( host_name );
            }
            mp_store_pending_welcome( message );
            g_recv_queue.push( std::move( message ) );
        }
        mp_log( "[cdda-mp] HANDSHAKE: host accepted our version — connected to " +
                params.host + ":" + std::to_string( params.port ) + " as '" + params.name + "'" );
        return true;
    } else {
        set_connect_error( "Connection closed during handshake." );
    }
    mp_log( "[cdda-mp] HANDSHAKE FAILED: " + client_connect_error() );
    replace_client( nullptr );
    return false;
}

static bool send_join_impl( bool enable_reconnect = true )
{
    const std::shared_ptr<client_impl> connection = current_client();
    if( !connection || !connection->alive.load() || connection->pending_join.empty() ) {
        return false;
    }
    if( connection->joined.exchange( true ) ) {
        return true;
    }
    // Reset liveness on the IO thread before enabling the watchdog.  Minutes
    // spent in character creation must not count as post-JOIN peer silence.
    const std::weak_ptr<client_impl> weak = connection;
    asio::post( connection->io_ctx, [weak]() {
        const std::shared_ptr<client_impl> self = weak.lock();
        if( self ) {
            self->last_recv_ms = mp_now_ms();
            self->heartbeat_started = true;
        }
    } );
    const int64_t window = mp_now_ms() - connection->connected_ms;
    mp_log( "[cdda-mp] PREAUTH-KEEPALIVE: " + std::to_string( connection->preauth_hb_count.load() ) +
            " host beats over " + std::to_string( window / 1000 ) + "s of pre-JOIN" +
            ( window >= 5000 ? " — 0 means the path went cold" : " — immediate join" ) );
    if( enable_reconnect ) {
        g_rc_enabled.store( true );
    }
    connection->send( connection->pending_join );
    mp_log( "[cdda-mp] Join queued — now in-game" );
    return true;
}

// One lazily started, owned worker handles reconnect sweeps.  Its request and
// delay waits are cancellable, and teardown joins it before another menu join
// may change connection parameters.  No detached thread outlives its session.
class reconnect_controller // NOLINT(misc-use-internal-linkage)
{
    public:
        ~reconnect_controller() {
            g_rc_enabled.store( false );
            {
                std::scoped_lock lock( mutex_ );
                stopping_ = true;
            }
            cv_.notify_all();
            if( thread_.joinable() ) {
                thread_.join();
            }
        }
        bool request() {
            {
                std::scoped_lock lock( mutex_ );
                if( !g_rc_enabled.load() || g_rc_in_progress.exchange( true ) ) {
                    return false;
                }
                requested_ = true;
                if( !thread_.joinable() ) {
                    thread_ = std::thread( [this] { run(); } );
                }
            }
            cv_.notify_all();
            return true;
        }
        void cancel_and_wait() {
            std::unique_lock<std::mutex> lock( mutex_ );
            g_rc_enabled.store( false );
            cv_.notify_all();
            cv_.wait( lock, [] { return !g_rc_in_progress.load(); } );
        }
    private:
        std::mutex mutex_;
        std::condition_variable cv_;
        std::thread thread_;
        bool requested_ = false;
        bool stopping_ = false;

        void run() {
            std::unique_lock<std::mutex> lock( mutex_ );
            while( !stopping_ ) {
                cv_.wait( lock, [this] { return requested_ || stopping_; } );
                if( stopping_ ) {
                    break;
                }
                requested_ = false;
                lock.unlock();
                const bool reconnected = sweep();
                lock.lock();
                g_rc_in_progress.store( false );
                if( reconnected && g_rc_enabled.load() ) {
                    g_recv_queue.push( R"({"type":"state","reconnected":true})" );
                }
                cv_.notify_all();
            }
            g_rc_in_progress.store( false );
            cv_.notify_all();
        }

        bool sweep() {
            static constexpr int delays_ms[] = { 500, 1000, 2000, 3000, 4000, 5000 };
            const int attempts = static_cast<int>( std::size( delays_ms ) );
            for( int i = 0; i < attempts && g_rc_enabled.load(); ++i ) {
                {
                    std::unique_lock<std::mutex> lock( mutex_ );
                    if( cv_.wait_for( lock, std::chrono::milliseconds( delays_ms[i] ),
                                      [this] { return stopping_ || !g_rc_enabled.load(); } ) ) {
                        return false;
                    }
                }
                g_recv_queue.push( R"({"type":"state","reconnect_attempt":)" +
                                   std::to_string( i + 1 ) + R"(,"reconnect_total":)" +
                                   std::to_string( attempts ) + "}" );
                std::scoped_lock connect_lock( g_connect_mutex );
                mp_log( "[cdda-mp] RECONNECT: attempt " + std::to_string( i + 1 ) + "/" +
                        std::to_string( attempts ) + " -> " + g_params.host + ":" +
                        std::to_string( g_params.port ) );
                const connect_params params = g_params;
                if( connect_impl( params, true ) && g_rc_enabled.load() && send_join_impl( false ) ) {
                    mp_log( "[cdda-mp] RECONNECT: success on attempt " + std::to_string( i + 1 ) );
                    return true;
                }
            }
            if( g_rc_enabled.exchange( false ) ) {
                mp_log( "[cdda-mp] RECONNECT: giving up — surfacing disconnect" );
                g_recv_queue.push( R"({"type":"state","reconnect_failed":true})" );
                g_recv_queue.push( R"({"type":"state","connected":false})" );
            }
            return false;
        }
};

static reconnect_controller g_reconnector;

static void schedule_reconnect( const std::string &why )
{
    if( g_reconnector.request() ) {
        mp_log( "[cdda-mp] RECONNECT: " + why + " — starting reconnect sweep" );
        g_recv_queue.push( R"({"type":"state","reconnecting":true})" );
    }
}

bool is_client_mode()
{
    return client_mode_.load();
}

void set_client_mode( bool enabled )
{
    client_mode_.store( enabled );
    if( !enabled ) {
        client_disable_reconnect();
        std::scoped_lock lock( g_connect_mutex );
        replace_client( nullptr );
        g_recv_queue.clear();
    }
    mp_log( "[cdda-mp] set_client_mode -> " + std::string( enabled ? "true" : "false" ) );
}

bool client_connect( const std::string &host, uint16_t port, const std::string &name,
                     const std::string &password, const std::string &version )
{
    client_disable_reconnect();
    std::scoped_lock lock( g_connect_mutex );
    g_preauth_redials = 0;
    replace_client( nullptr );
    g_recv_queue.clear();
    return connect_impl( { host, port, name, password, version }, false );
}

std::string client_connect_error()
{
    std::scoped_lock lock( g_error_mutex );
    return g_connect_error;
}

void client_send_join()
{
    // A worker owns re-PROBE+JOIN as one transaction; the game loop must not
    // prematurely JOIN its socket or block waiting on the worker's handshake.
    if( g_rc_in_progress.load() ) {
        return;
    }
    std::unique_lock<std::mutex> lock( g_connect_mutex, std::try_to_lock );
    if( !lock.owns_lock() ) {
        return;
    }
    const std::shared_ptr<client_impl> connection = current_client();
    if( connection && connection->joined.load() ) {
        return;
    }
    if( !connection || !connection->alive.load() ) {
        if( g_params.host.empty() ) {
            return;
        }
        if( g_preauth_redials >= MP_PREAUTH_REDIAL_MAX ) {
            return;
        }
        ++g_preauth_redials;
        const connect_params params = g_params;
        mp_log( "[cdda-mp] JOIN: pre-auth re-dial " + std::to_string( g_preauth_redials ) + "/3" );
        if( !connect_impl( params, false ) ) {
            if( g_preauth_redials == MP_PREAUTH_REDIAL_MAX ) {
                g_recv_queue.push( R"({"type":"state","join_failed":true})" );
                g_recv_queue.push( R"({"type":"state","connected":false})" );
            }
            return;
        }
    }
    send_join_impl();
}

bool client_join_is_sent()
{
    const std::shared_ptr<client_impl> connection = current_client();
    return connection && connection->joined.load();
}

bool client_recv_pop( std::string &out )
{
    return g_recv_queue.pop( out );
}

void client_send( const std::string &json )
{
    const std::shared_ptr<client_impl> connection = current_client();
    if( connection && connection->alive.load() && connection->joined.load() &&
        !g_rc_in_progress.load() ) {
        connection->send( json + "\n" );
    }
}

bool client_is_reconnecting()
{
    return g_rc_in_progress.load();
}

void client_disable_reconnect()
{
    g_reconnector.cancel_and_wait();
}

int mp_client_measured_rtt_ms()
{
    return g_hb_rtt_ms.load();
}

} // namespace cata_mp
