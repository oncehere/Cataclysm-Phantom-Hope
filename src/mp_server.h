#pragma once
#ifndef CATA_SRC_MP_SERVER_H
#define CATA_SRC_MP_SERVER_H

#include <stdint.h>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace cata_mp
{

struct client_session;

class server
{
    public:
        server( uint16_t port, std::string password, std::string version = "" );
        ~server();

        // Start listening. Blocks until stop() is called.
        void run();

        // Signal the server to stop accepting connections and shut down.
        void stop();

        // Broadcast a message to all connected clients.
        // Must be called from the Asio io_context thread (e.g. inside a callback).
        void broadcast( const std::string &msg );

        // Thread-safe broadcast: posts the send onto the io_context thread.
        // Use this when calling from the game loop thread.
        void post_broadcast( const std::string &msg );

        uint16_t port() const {
            return port_;
        }

    private:
        void do_accept();
        void arm_heartbeat();
        void on_client_connected( const std::shared_ptr<client_session> &session );
        void on_client_disconnected( const std::shared_ptr<client_session> &session );
        void on_message( const std::shared_ptr<client_session> &session, const std::string &msg );

        uint16_t port_;
        std::string password_;
        std::string version_;

        struct impl;

        std::unique_ptr<impl> impl_;

        std::vector<std::shared_ptr<client_session>> clients_;
        std::mutex clients_mutex_;
        std::weak_ptr<client_session> active_session_;
};

// Start the server on the given port. Called from main() when --server flag is set.
// Does not return until the server shuts down.
void run_server( uint16_t port, const std::string &password,
                 const std::string &version = "" );

// Returns the active server instance, or nullptr if not running.
// The pointer is published atomically.  The game owner must stop and wait for
// the listen thread before destroying a session; sends use post_broadcast().
server *get_active_server();

// True from the moment the (detached) listen thread enters run_server() until
// it fully returns — i.e. until the server object has destructed and its
// listen socket (the port) is released. Session-end waits on this going false
// before allowing a re-host to re-bind the same port, so a second host session
// in one launch can't race the first session's socket teardown.
bool is_server_thread_running();

// Non-loopback IPv4 addresses, with common VPN ranges first, for the host HUD.
std::vector<std::string> mp_local_ipv4s();

// The partner's heartbeat RTT, or -1 before a measurement.
int mp_host_partner_rtt_ms();

// Latest message from the current authenticated partner, including IO-thread
// heartbeats, in steady_clock epoch milliseconds. Zero outside that session.
int64_t mp_host_partner_last_message_ms();

} // namespace cata_mp

#endif // CATA_SRC_MP_SERVER_H
