#pragma once
#ifndef CATA_SRC_ACTOR_CONTROL_BRIDGE_H
#define CATA_SRC_ACTOR_CONTROL_BRIDGE_H

#include <functional>
#include <memory>
#include <string>

namespace cata::actor_control
{
/** A bounded, game-thread-only, loopback transport. It never advances the simulation. */
class loopback_bridge
{
    public:
        loopback_bridge();
        ~loopback_bridge();
        loopback_bridge( const loopback_bridge & ) = delete;
        loopback_bridge &operator=( const loopback_bridge & ) = delete;
        bool start( std::string &error );
        void close();
        void disconnect();
        void pump( const std::function<std::string( const std::string & )> &handler );
        bool listening() const;
        bool connected() const;
        const std::string &credential() const;
        const std::string &session_id() const;
        const std::string &descriptor_path() const;
    private:
        struct implementation;
        std::unique_ptr<implementation> impl_;
};

std::string new_identity();
} // namespace cata::actor_control

#endif // CATA_SRC_ACTOR_CONTROL_BRIDGE_H
