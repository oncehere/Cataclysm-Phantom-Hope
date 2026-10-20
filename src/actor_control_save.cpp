#include "actor_control_save.h"
#include "actor_control_files.h"

#include <array>
#include <cerrno>
#include <cstdint>
#include <filesystem>
#include <iomanip>
#include <ios>
#include <locale>
#include <memory>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#ifdef _WIN32
    #include "platform_win.h"
#endif

#include "flexbuffer_json.h"
#include "json.h"
#include "json_loader.h"


namespace cata::actor_control::save_transaction
{
namespace
{
#if defined(__linux__) || defined(_WIN32)
constexpr std::size_t maximum_files = 16384;
constexpr std::uint64_t maximum_file_bytes = 1024ULL * 1024 * 1024;
constexpr std::uint64_t maximum_total_bytes = 16ULL * 1024 * 1024 * 1024;
constexpr std::size_t maximum_manifest_bytes = 8 * 1024 * 1024;
constexpr const char *journal_name = ".cph-actor-save";

class descriptor
{
    public:
        explicit descriptor( int value = -1 ) : value_( value ) {}
        ~descriptor() {
            if( value_ >= 0 ) {
                files::close( value_ );
            }
        }
        descriptor( const descriptor & ) = delete;
        descriptor &operator=( const descriptor & ) = delete;
        int get() const {
            return value_;
        }
    private:
        int value_;
};

struct saved_file {
    std::filesystem::path relative;
    bool existed = false;
    std::string backup;
    std::uint64_t bytes = 0;
    std::string crc;
};

struct journal {
    std::filesystem::path root;
    std::filesystem::path directory;
    std::unique_ptr<descriptor> lock;
    std::string identity;
    bool committed = false;
    bool poisoned = false;
    bool capture = true;
    std::uint64_t total_bytes = 0;
    std::vector<saved_file> files;
};

std::unique_ptr<journal> current;

[[noreturn]] void fail( const char *code )
{
    throw std::ios::failure( code );
}

struct path_order {
    bool operator()( const std::filesystem::path &left, const std::filesystem::path &right ) const {
#ifdef _WIN32
        const auto a = left.generic_wstring();
        const auto b = right.generic_wstring();
        return CompareStringOrdinal( a.c_str(), -1, b.c_str(), -1, TRUE ) == CSTR_LESS_THAN;
#else
        return left < right;
#endif
    }
};

bool same_path( const std::filesystem::path &left, const std::filesystem::path &right )
{
    return !path_order{}( left, right )&& !path_order{}( right, left );
}

std::filesystem::path absolute_path( const std::filesystem::path &path )
{
    auto result = std::filesystem::absolute( path ).lexically_normal();
    // Lexical normalization preserves a trailing separator from paths such as
    // world/., but the world lease identifies the directory itself.
    if( result != result.root_path() && result.filename().empty() ) {
        result = result.parent_path();
    }
    return result;
}

bool safe_relative( const std::filesystem::path &path )
{
    if( path.empty() || path.is_absolute() || path.has_root_path() ) {
        return false;
    }
    for( const auto &part : path ) {
        if( part.empty() || part == "." || part == ".." ||
            part.u8string().find( '\0' ) != std::string::npos ) {
            return false;
        }
    }
    return path == path.lexically_normal();
}

bool inside( const std::filesystem::path &root, const std::filesystem::path &path )
{
    auto cursor = path.begin();
    for( const auto &part : root ) {
        if( cursor == path.end() || !same_path( *cursor++, part ) ) {
            return false;
        }
    }
    return cursor != path.end();
}

void check_directories( const std::filesystem::path &path, bool allow_missing )
{
    std::filesystem::path prefix = path.root_path();
    bool missing = false;
    for( const auto &part : path.relative_path() ) {
        prefix /= part;
        if( missing ) {
            continue;
        }
        files::info info {};
        if( files::inspect( prefix.c_str(), info ) != 0 ) {
            if( allow_missing && errno == ENOENT ) {
                missing = true;
                continue;
            }
            fail( "save_journal_directory_unavailable" );
        }
        if( !info.directory ) {
            fail( "save_journal_unsafe_path" );
        }
    }
}

void sync_directory( const std::filesystem::path &path )
{
    if( files::sync_directory( path ) != 0 ) {
        fail( "save_journal_directory_sync_failed" );
    }
}

void write_all( int fd, const char *data, std::size_t size )
{
    while( size > 0 ) {
        const std::ptrdiff_t count = files::write( fd, data, size );
        if( count < 0 && errno == EINTR ) {
            continue;
        }
        if( count <= 0 ) {
            fail( "save_journal_write_failed" );
        }
        data += count;
        size -= static_cast<std::size_t>( count );
    }
}

std::uint32_t crc_update( std::uint32_t crc, const char *data, std::size_t size )
{
    static const std::array<std::uint32_t, 256> table = []() {
        std::array<std::uint32_t, 256> values {};
        for( std::size_t index = 0; index < values.size(); ++index ) {
            std::uint32_t value = static_cast<std::uint32_t>( index );
            for( int bit = 0; bit < 8; ++bit ) {
                value = ( value >> 1 ) ^ ( ( value & 1 ) ? 0xedb88320U : 0U );
            }
            values[index] = value;
        }
        return values;
    }
    ();
    for( std::size_t index = 0; index < size; ++index ) {
        crc = ( crc >> 8 ) ^ table[( crc ^ static_cast<unsigned char>( data[index] ) ) & 0xff];
    }
    return crc;
}

std::string crc_string( std::uint32_t crc )
{
    std::ostringstream result;
    result.imbue( std::locale::classic() );
    result << std::hex << std::setw( 8 ) << std::setfill( '0' ) << ( crc ^ 0xffffffffU );
    return result.str();
}

bool hexadecimal( const std::string &value, std::size_t length )
{
    return value.size() == length && value.find_first_not_of( "0123456789abcdef" ) ==
           std::string::npos;
}

std::string new_identity()
{
    std::random_device random;
    std::ostringstream value;
    value.imbue( std::locale::classic() );
    value << std::hex << std::setfill( '0' );
    for( int index = 0; index < 4; ++index ) {
        value << std::setw( 8 ) << static_cast<std::uint32_t>( random() );
    }
    return value.str();
}

void copy_checked( const std::filesystem::path &source, int destination,
                   std::uint64_t &bytes, std::string &checksum )
{
    descriptor input( files::open( source.c_str(), files::access::read ) );
    files::info info {};
    if( input.get() < 0 || files::inspect( input.get(), info ) != 0 || !info.regular ||
        info.size < 0 || static_cast<std::uint64_t>( info.size ) > maximum_file_bytes ) {
        fail( "save_journal_invalid_file" );
    }
    std::array<char, 65536> buffer;
    std::uint32_t crc = 0xffffffffU;
    bytes = 0;
    for( ;; ) {
        const std::ptrdiff_t count = files::read( input.get(), buffer.data(), buffer.size() );
        if( count < 0 && errno == EINTR ) {
            continue;
        }
        if( count < 0 ) {
            fail( "save_journal_read_failed" );
        }
        if( count == 0 ) {
            break;
        }
        bytes += static_cast<std::uint64_t>( count );
        if( bytes > maximum_file_bytes ) {
            fail( "save_journal_file_limit" );
        }
        crc = crc_update( crc, buffer.data(), static_cast<std::size_t>( count ) );
        if( destination >= 0 ) {
            write_all( destination, buffer.data(), static_cast<std::size_t>( count ) );
        }
    }
    checksum = crc_string( crc );
    if( destination >= 0 && files::sync( destination ) != 0 ) {
        fail( "save_journal_backup_sync_failed" );
    }
}

void replace_manifest( const journal &state )
{
    std::ostringstream buffer;
    JsonOut out( buffer );
    out.start_object();
    out.member( "schema_version", 1 );
    out.member( "transaction_id", state.identity );
    out.member( "state", state.committed ? "committed" : "pending" );
    out.member( "files" );
    out.start_array();
    for( const saved_file &file : state.files ) {
        out.start_object();
        out.member( "path", file.relative.generic_u8string() );
        out.member( "existed", file.existed );
        out.member( "backup", file.backup );
        out.member( "bytes", static_cast<std::int64_t>( file.bytes ) );
        out.member( "crc32", file.crc );
        out.end_object();
    }
    out.end_array();
    out.end_object();
    const std::string encoded = buffer.str();
    if( encoded.size() > maximum_manifest_bytes ) {
        fail( "save_journal_manifest_limit" );
    }
    const auto temporary = state.directory / ( "manifest-" + new_identity() + ".tmp" );
    descriptor output( files::open( temporary.c_str(), files::access::create_new ) );
    if( output.get() < 0 ) {
        fail( "save_journal_manifest_open_failed" );
    }
    write_all( output.get(), encoded.data(), encoded.size() );
    if( files::sync( output.get() ) != 0 ||
        files::replace( temporary.c_str(), ( state.directory / "manifest.json" ).c_str() ) != 0 ) {
        fail( "save_journal_manifest_commit_failed" );
    }
    sync_directory( state.directory );
}

bool load_manifest( journal &state )
{
    const auto path = state.directory / "manifest.json";
    files::info info {};
    if( files::inspect( path.c_str(), info ) != 0 ) {
        if( errno == ENOENT ) {
            return false;
        }
        fail( "save_journal_manifest_unavailable" );
    }
    if( !info.regular || !info.private_access || info.links != 1 || info.size < 0 ||
        static_cast<std::uint64_t>( info.size ) > maximum_manifest_bytes ) {
        fail( "save_journal_unsafe_manifest" );
    }
    descriptor input( files::open( path.c_str(), files::access::read ) );
    if( input.get() < 0 ) {
        fail( "save_journal_manifest_unavailable" );
    }
    std::string encoded( static_cast<std::size_t>( info.size ), '\0' );
    std::size_t offset = 0;
    while( offset < encoded.size() ) {
        const std::ptrdiff_t count = files::read( input.get(), encoded.data() + offset,
                                     encoded.size() - offset );
        if( count < 0 && errno == EINTR ) {
            continue;
        }
        if( count <= 0 ) {
            fail( "save_journal_manifest_read_failed" );
        }
        offset += static_cast<std::size_t>( count );
    }
    const JsonObject object = json_loader::from_string( encoded ).get_object();
    object.allow_omitted_members();
    if( object.get_int( "schema_version", 0 ) != 1 ||
        !hexadecimal( object.get_string( "transaction_id", "" ), 32 ) ||
        !object.has_array( "files" ) || object.get_array( "files" ).size() > maximum_files ) {
        fail( "save_journal_unsupported_manifest" );
    }
    const std::set<std::string> keys { "schema_version", "transaction_id", "state", "files" };
    for( const JsonMember &member : object ) {
        if( keys.count( member.name() ) == 0 ) {
            fail( "save_journal_unsupported_manifest" );
        }
    }
    const std::string phase = object.get_string( "state", "" );
    if( phase != "pending" && phase != "committed" ) {
        fail( "save_journal_unsupported_manifest" );
    }
    state.identity = object.get_string( "transaction_id" );
    state.committed = phase == "committed";
    std::set<std::filesystem::path, path_order> paths;
    for( const JsonObject &entry : object.get_array( "files" ) ) {
        entry.allow_omitted_members();
        const std::set<std::string> fields { "path", "existed", "backup", "bytes", "crc32" };
        for( const JsonMember &member : entry ) {
            if( fields.count( member.name() ) == 0 ) {
                fail( "save_journal_unsupported_manifest" );
            }
        }
        saved_file file;
        file.relative = std::filesystem::u8path( entry.get_string( "path" ) );
        file.existed = entry.get_bool( "existed" );
        file.backup = entry.get_string( "backup" );
        const std::int64_t bytes = entry.get_int64( "bytes" );
        file.crc = entry.get_string( "crc32" );
        const std::string expected = "before-" + state.identity + "-" +
                                     std::to_string( state.files.size() ) + ".bin";
        if( !safe_relative( file.relative ) || same_path( *file.relative.begin(), journal_name ) ||
            !paths.insert( file.relative ).second || bytes < 0 ||
            static_cast<std::uint64_t>( bytes ) > maximum_file_bytes ||
            ( file.existed ? file.backup != expected || !hexadecimal( file.crc, 8 ) :
              !file.backup.empty() || bytes != 0 || !file.crc.empty() ) ) {
            fail( "save_journal_invalid_entry" );
        }
        file.bytes = static_cast<std::uint64_t>( bytes );
        state.total_bytes += file.bytes;
        if( state.total_bytes > maximum_total_bytes ) {
            fail( "save_journal_total_limit" );
        }
        state.files.push_back( std::move( file ) );
    }
    return true;
}

std::unique_ptr<journal> lock_world( const std::filesystem::path &world_root )
{
    auto state = std::make_unique<journal>();
    state->root = absolute_path( world_root );
    check_directories( state->root, false );
    state->directory = state->root / journal_name;
    if( files::create_private_directory( state->directory ) != 0 ) {
        fail( "save_journal_directory_create_failed" );
    }
    files::info info {};
    if( files::inspect( state->directory.c_str(), info ) != 0 || !info.directory ||
        !info.private_access ) {
        fail( "save_journal_unsafe_directory" );
    }
    state->lock = std::make_unique<descriptor>( files::open( ( state->directory / "lock" ).c_str(),
                  files::access::read_write_create ) );
    if( state->lock->get() < 0 || files::inspect( state->lock->get(), info ) != 0 ||
        !info.regular || !info.private_access || info.links != 1 ) {
        fail( "save_journal_unsafe_lock" );
    }
    if( files::lock( state->lock->get() ) != 0 ) {
        fail( "save_journal_world_busy" );
    }
    sync_directory( state->root );
    return state;
}

void validate_backups( const journal &state )
{
    // Check the entire rollback before touching any real file. A corrupt late
    // backup must not leave an earlier inventory partially restored.
    for( const saved_file &file : state.files ) {
        check_directories( ( state.root / file.relative ).parent_path(), !file.existed );
        files::info target {};
        if( files::inspect( ( state.root / file.relative ).c_str(), target ) == 0 ) {
            if( !target.regular || target.links != 1 ) {
                fail( "save_journal_unsafe_target" );
            }
        } else if( errno != ENOENT ) {
            fail( "save_journal_target_unavailable" );
        }
        if( !file.existed ) {
            continue;
        }
        const auto backup = state.directory / file.backup;
        files::info info {};
        if( files::inspect( backup.c_str(), info ) != 0 || !info.regular ||
            !info.private_access || info.links != 1 ) {
            fail( "save_journal_unsafe_backup" );
        }
        std::uint64_t bytes = 0;
        std::string crc;
        copy_checked( backup, -1, bytes, crc );
        if( bytes != file.bytes || crc != file.crc ) {
            fail( "save_journal_corrupt_backup" );
        }
    }
}

void cleanup( const journal &state )
{
    for( const saved_file &file : state.files ) {
        if( file.existed && files::remove( ( state.directory / file.backup ).c_str() ) != 0 &&
            errno != ENOENT ) {
            fail( "save_journal_cleanup_failed" );
        }
    }
    // Unknown files and the stable lock inode deliberately survive cleanup.
    if( files::remove( ( state.directory / "manifest.json" ).c_str() ) != 0 && errno != ENOENT ) {
        fail( "save_journal_cleanup_failed" );
    }
    sync_directory( state.directory );
}

void rollback( journal &state )
{
    validate_backups( state );
    for( const saved_file &file : state.files ) {
        const auto target = state.root / file.relative;
        if( !file.existed ) {
            if( files::remove( target.c_str() ) != 0 && errno != ENOENT ) {
                fail( "save_journal_remove_created_failed" );
            }
            // A recorded creation may have failed before its parent was made.
            if( std::filesystem::exists( target.parent_path() ) ) {
                sync_directory( target.parent_path() );
            }
            continue;
        }
        // A crash may leave an unpublished temporary file. Never replace or
        // delete an unknown file to retry: choose a fresh private name instead.
        const auto temporary = state.directory / ( "restore-" + new_identity() + ".tmp" );
        descriptor output( files::open( temporary.c_str(), files::access::create_new ) );
        if( output.get() < 0 ) {
            fail( "save_journal_restore_open_failed" );
        }
        std::uint64_t bytes = 0;
        std::string crc;
        copy_checked( state.directory / file.backup, output.get(), bytes, crc );
        if( bytes != file.bytes || crc != file.crc ||
            files::replace( temporary.c_str(), target.c_str() ) != 0 ) {
            fail( "save_journal_restore_failed" );
        }
        sync_directory( target.parent_path() );
        sync_directory( state.directory );
    }
    // Mark rollback complete before deleting any backups. Recovery after a
    // crash during cleanup then only cleans, and never needs deleted backups.
    state.committed = true;
    replace_manifest( state );
    cleanup( state );
}

void settle_existing( journal &state )
{
    if( load_manifest( state ) ) {
        if( state.committed ) {
            cleanup( state );
        } else {
            rollback( state );
        }
    }
}

void sync_targets( const journal &state )
{
    std::set<std::filesystem::path> directories;
    directories.insert( state.root );
    for( const saved_file &file : state.files ) {
        const auto target = state.root / file.relative;
        check_directories( target.parent_path(), true );
        files::info info {};
        if( files::inspect( target.c_str(), info ) == 0 ) {
            descriptor input( files::open( target.c_str(), files::access::read_write ) );
            if( !info.regular || input.get() < 0 || files::sync( input.get() ) != 0 ) {
                fail( "save_journal_target_sync_failed" );
            }
        } else if( errno != ENOENT ) {
            fail( "save_journal_target_sync_failed" );
        }
        // Persist every newly created parent link, not just the leaf directory.
        for( auto parent = target.parent_path(); parent != state.root; parent = parent.parent_path() ) {
            if( std::filesystem::exists( parent ) ) {
                directories.insert( parent );
            }
        }
    }
    for( const auto &directory : directories ) {
        sync_directory( directory );
    }
}
#endif
} // namespace

bool active()
{
#if defined(__linux__) || defined(_WIN32)
    return current != nullptr;
#else
    return false;
#endif
}

bool capturing()
{
#if defined(__linux__) || defined(_WIN32)
    return current && current->capture;
#else
    return false;
#endif
}

bool owns_world( const std::filesystem::path &world_root )
{
#if defined(__linux__) || defined(_WIN32)
    try {
        return current && same_path( current->root, absolute_path( world_root ) );
    } catch( const std::exception & ) {
        return false;
    }
#else
    ( void )world_root;
    return false;
#endif
}

bool begin( const std::filesystem::path &world_root, std::string &error, bool capture )
{
    error.clear();
#if defined(__linux__) || defined(_WIN32)
    if( current ) {
        error = "save_journal_already_active";
        return false;
    }
    try {
        auto state = lock_world( world_root );
        settle_existing( *state );
        state->files.clear();
        state->total_bytes = 0;
        state->committed = false;
        state->identity = new_identity();
        state->capture = capture;
        if( capture ) {
            replace_manifest( *state );
        }
        current = std::move( state );
        return true;
    } catch( const std::exception & ) {
        error = "save_journal_begin_failed";
        return false;
    }
#else
    ( void )world_root;
    if( !capture ) {
        return true;
    }
    error = "save_journal_unsupported_platform";
    return false;
#endif
}

void before_write( const std::filesystem::path &path )
{
#if defined(__linux__) || defined(_WIN32)
    if( !current || !current->capture ) {
        return;
    }
    try {
        journal &state = *current;
        if( state.poisoned ) {
            fail( "save_journal_poisoned" );
        }
        const auto target = absolute_path( path );
        if( !inside( state.root, target ) ) {
            return;
        }
        auto cursor = target.begin();
        for( const auto &part : state.root ) {
            ( void )part;
            ++cursor;
        }
        std::filesystem::path relative;
        for( ; cursor != target.end(); ++cursor ) {
            relative /= *cursor;
        }
        if( !safe_relative( relative ) || same_path( *relative.begin(), journal_name ) ) {
            fail( "save_journal_reserved_path" );
        }
        check_directories( target.parent_path(), true );
        files::info target_info {};
        if( files::inspect( target.c_str(), target_info ) == 0 ) {
            if( !target_info.regular || target_info.links != 1 ) {
                fail( "save_journal_invalid_target" );
            }
        } else if( errno != ENOENT ) {
            fail( "save_journal_target_unavailable" );
        }
        for( const saved_file &file : state.files ) {
            if( same_path( file.relative, relative ) ) {
                return;
            }
        }
        if( state.files.size() >= maximum_files ) {
            fail( "save_journal_file_count_limit" );
        }
        saved_file file;
        file.relative = relative;
        files::info info {};
        if( files::inspect( target.c_str(), info ) == 0 ) {
            if( !info.regular || info.links != 1 || info.size < 0 ||
                static_cast<std::uint64_t>( info.size ) > maximum_file_bytes ||
                static_cast<std::uint64_t>( info.size ) > maximum_total_bytes - state.total_bytes ) {
                fail( "save_journal_invalid_target" );
            }
            file.existed = true;
            file.backup = "before-" + state.identity + "-" + std::to_string( state.files.size() ) + ".bin";
            descriptor output( files::open( ( state.directory / file.backup ).c_str(),
                                            files::access::create_new ) );
            if( output.get() < 0 ) {
                fail( "save_journal_backup_open_failed" );
            }
            copy_checked( target, output.get(), file.bytes, file.crc );
            if( file.bytes > maximum_total_bytes - state.total_bytes ) {
                fail( "save_journal_total_limit" );
            }
            state.total_bytes += file.bytes;
            sync_directory( state.directory );
        } else if( errno != ENOENT ) {
            fail( "save_journal_target_unavailable" );
        }
        state.files.push_back( std::move( file ) );
        replace_manifest( state );
    } catch( const std::exception & ) {
        current->poisoned = true;
        fail( "save_journal_before_write_failed" );
    }
#else
    ( void )path;
#endif
}

bool finish( bool success, std::string &error )
{
    error.clear();
#if defined(__linux__) || defined(_WIN32)
    if( !current ) {
        return true;
    }
    if( !current->capture ) {
        current.reset();
        return true;
    }
    try {
        if( success && !current->poisoned ) {
            sync_targets( *current );
            current->committed = true;
            replace_manifest( *current );
            cleanup( *current );
        } else {
            rollback( *current );
        }
        const bool poisoned_commit = success && current->poisoned;
        current.reset();
        if( poisoned_commit ) {
            error = "save_journal_poisoned";
            return false;
        }
        return true;
    } catch( const std::exception & ) {
        // The durable manifest remains the recovery authority. Release the
        // lock, but never remove evidence after a failed restore or commit.
        current.reset();
        error = "save_journal_finish_failed";
        return false;
    }
#else
    ( void )success;
    return true;
#endif
}

bool recover( const std::filesystem::path &world_root, std::string &error )
{
    error.clear();
#if defined(__linux__) || defined(_WIN32)
    if( current ) {
        error = "save_journal_already_active";
        return false;
    }
    try {
        const auto root = absolute_path( world_root );
        // Loading ordinary worlds does not create a journal or lock file.
        files::info info {};
        if( files::inspect( ( root / journal_name ).c_str(), info ) != 0 && errno == ENOENT ) {
            return true;
        }
        auto state = lock_world( root );
        settle_existing( *state );
        return true;
    } catch( const std::exception & ) {
        error = "save_journal_recovery_failed";
        return false;
    }
#else
    std::error_code ec;
    if( !std::filesystem::exists( world_root / ".cph-actor-save", ec ) && !ec ) {
        return true;
    }
    error = "save_journal_unsupported_platform";
    return false;
#endif
}
} // namespace cata::actor_control::save_transaction
