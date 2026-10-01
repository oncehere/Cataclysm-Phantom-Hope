#pragma once
#ifndef CATA_SRC_ACTOR_CONTROL_H
#define CATA_SRC_ACTOR_CONTROL_H

#include <string>

class JsonObject;
class JsonOut;
class npc;

namespace cata::actor_control
{
// The engine owns execution. Neither act nor lifecycle callbacks are exposed
// as external RPCs or Lua clock/stat/inventory mutations.
/** Safe during cross-translation-unit startup and teardown. */
bool is_initialized();
void enable( bool value );
bool enabled();
bool has_binding();
bool is_bound( const npc &actor );
/** Identity persists after stop; this checks actual offline-work ownership. */
bool pauses_offline_work( npc &actor );
/** Native death lifecycle only; never exposed over the external protocol. */
void on_actor_death( npc &actor );
/** Scene changes invalidate plans, preserving real native activity progress. */
void on_scene_change();
bool listening();
bool bind( npc &actor, const std::string &profile_id, std::string &error );
bool chat( const std::string &text, std::string &error );
void pause( bool value );
void cancel();
void stop();
void reset();
void pump_incoming();
bool act( npc &actor, bool urgent );
/** Read-only cognition preference for native fallback; never changes follower rules. */
int following_distance( const npc &actor, int native_distance );
void before_save();
/** Stage the checkpoint marker inside the owning world transaction. */
bool prepare_save_commit();
void after_save( bool success );
void serialize( JsonOut &out );
void deserialize( const JsonObject &object );
/** Bounded recent history; operation_id selects one retained receipt. */
std::string status( bool include_debug = false, const std::string &operation_id = "" );
std::string dispatch( const std::string &method, const std::string &params, std::string &error );
} // namespace cata::actor_control

#endif // CATA_SRC_ACTOR_CONTROL_H
