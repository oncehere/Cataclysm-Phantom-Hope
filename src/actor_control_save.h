#pragma once
#ifndef CATA_SRC_ACTOR_CONTROL_SAVE_H
#define CATA_SRC_ACTOR_CONTROL_SAVE_H

#include <filesystem>
#include <string>

namespace cata::actor_control::save_transaction
{
/** Lock one world and start a durable, lazy before-image journal. */
bool begin( const std::filesystem::path &world_root, std::string &error, bool capture = true );
/** Call before replacing, modifying, creating or removing a world file.
 * Outside-world paths are ignored. Failure throws std::ios::failure before mutation.
 */
void before_write( const std::filesystem::path &path );
/** Commit all durable writes, or restore their original files. */
bool finish( bool success, std::string &error );
/** Recover before loading any world data. Unknown/corrupt journals stop loading. */
bool recover( const std::filesystem::path &world_root, std::string &error );
bool active();
/** True only for a lease which captures mutations; read-only leases do not. */
bool capturing();
/** Joined operations must belong to the same normalized world directory. */
bool owns_world( const std::filesystem::path &world_root );
} // namespace cata::actor_control::save_transaction

#endif // CATA_SRC_ACTOR_CONTROL_SAVE_H
