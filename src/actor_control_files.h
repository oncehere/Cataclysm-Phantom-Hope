#pragma once
#ifndef CATA_SRC_ACTOR_CONTROL_FILES_H
#define CATA_SRC_ACTOR_CONTROL_FILES_H

#include <cstddef>
#include <cstdint>
#include <filesystem>

// The bridge and save journal share the same private-file and lease rules.
// Operations return -1 and set errno on failure, including on Windows.
namespace cata::actor_control::files
{
enum class access { read, read_write, create_new, read_write_create };
struct info {
    bool regular = false;
    bool directory = false;
    bool private_access = false;
    std::int64_t size = 0;
    std::uint64_t links = 0;
};
int inspect( const std::filesystem::path &path, info &result );
int inspect( int fd, info &result );
int open( const std::filesystem::path &path, access mode );
void close( int fd );
std::ptrdiff_t read( int fd, void *data, std::size_t size );
std::ptrdiff_t write( int fd, const void *data, std::size_t size );
int sync( int fd );
int sync_directory( const std::filesystem::path &path );
int lock( int fd );
int replace( const std::filesystem::path &from, const std::filesystem::path &to );
int remove( const std::filesystem::path &path );
// Existing directories must already be private; never repair an untrusted journal.
int create_private_directory( const std::filesystem::path &path );
} // namespace cata::actor_control::files
#endif
