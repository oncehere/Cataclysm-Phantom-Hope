#include "actor_control_save.h"

#if defined(__linux__) || defined(_WIN32)

#include <filesystem>
#include <algorithm>
#include <fstream>
#include <iterator>
#include <locale>
#include <string>
#include <cstdlib>
#include <cstring>
#include <cwctype>
#include <vector>

#ifdef _WIN32
    #include "platform_win.h"
    #include <aclapi.h>
    #include <sddl.h>
    #include <winioctl.h>
    #include <process.h>
#else
    #include <poll.h>
    #include <sys/stat.h>
    #include <sys/wait.h>
    #include <unistd.h>
#endif

#include "actor_control_bridge.h"
#include "actor_control_files.h"
#include "cata_catch.h"
#include "cata_path.h"
#include "cata_scope_helpers.h"
#include "cata_utility.h"
#include "filesystem.h"
#include "flexbuffer_json.h"
#include "json_loader.h"
#include "mmap_file.h"
#include "ofstream_wrapper.h"
#include "save_snapshot.h"
#include "zzip.h"

namespace
{
namespace transaction = cata::actor_control::save_transaction;
namespace actor_files = cata::actor_control::files;

class grouped_save_numbers : public std::numpunct<char>
{
    private:
        char do_thousands_sep() const override {
            return ',';
        }
        std::string do_grouping() const override {
            return "\3";
        }
};

#ifdef _WIN32
int run_windows_child( const std::filesystem::path &root, const wchar_t *mode )
{
    std::vector<wchar_t> executable( 32768 );
    REQUIRE( GetModuleFileNameW( nullptr, executable.data(),
                                 static_cast<DWORD>( executable.size() ) ) > 0 );
    const auto quote = []( const std::wstring & value ) {
        std::wstring result = L"\"";
        std::size_t slashes = 0;
        for( const wchar_t c : value ) {
            if( c == L'\\' ) {
                ++slashes;
                continue;
            }
            result.append( c == L'\"' ? slashes * 2 + 1 : slashes, L'\\' );
            slashes = 0;
            result += c;
        }
        result.append( slashes * 2, L'\\' );
        return result + L"\"";
    };
    std::wstring command = quote( executable.data() ) +
                           L" actor_control_save_windows_child --rng-seed 424242 --mods ccb --user-dir " +
                           quote( ( root / "child-user" ).native() );
    const wchar_t *old_root = _wgetenv( L"CPH_ACTOR_SAVE_CHILD_ROOT" );
    const wchar_t *old_mode = _wgetenv( L"CPH_ACTOR_SAVE_CHILD_MODE" );
    const std::wstring saved_root = old_root ? old_root : L"";
    const std::wstring saved_mode = old_mode ? old_mode : L"";
    REQUIRE( _wputenv_s( L"CPH_ACTOR_SAVE_CHILD_ROOT", root.c_str() ) == 0 );
    REQUIRE( _wputenv_s( L"CPH_ACTOR_SAVE_CHILD_MODE", mode ) == 0 );
    STARTUPINFOW startup { sizeof( STARTUPINFOW ) };
    PROCESS_INFORMATION process {};
    const BOOL started = CreateProcessW( executable.data(), command.data(), nullptr, nullptr, FALSE,
                                         CREATE_NO_WINDOW, nullptr, nullptr, &startup, &process );
    _wputenv_s( L"CPH_ACTOR_SAVE_CHILD_ROOT", saved_root.c_str() );
    _wputenv_s( L"CPH_ACTOR_SAVE_CHILD_MODE", saved_mode.c_str() );
    REQUIRE( started );
    CloseHandle( process.hThread );
    const DWORD waited = WaitForSingleObject( process.hProcess, 60000 );
    if( waited != WAIT_OBJECT_0 ) {
        TerminateProcess( process.hProcess, 125 );
        WaitForSingleObject( process.hProcess, 5000 );
    }
    DWORD result = 125;
    GetExitCodeProcess( process.hProcess, &result );
    CloseHandle( process.hProcess );
    REQUIRE( waited == WAIT_OBJECT_0 );
    return static_cast<int>( result );
}

void make_junction( const std::filesystem::path &path, const std::filesystem::path &target )
{
    REQUIRE( std::filesystem::create_directory( path ) );
    const HANDLE handle = CreateFileW( path.c_str(), GENERIC_WRITE, 0, nullptr, OPEN_EXISTING,
                                       FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS, nullptr );
    REQUIRE( handle != INVALID_HANDLE_VALUE );
    const std::wstring substitute = L"\\??\\" + target.native();
    const std::wstring names = substitute + L'\0' + target.native() + L'\0';
    std::vector<unsigned char> data( 16 + names.size() * sizeof( wchar_t ), 0 );
    *reinterpret_cast<DWORD *>( data.data() ) = IO_REPARSE_TAG_MOUNT_POINT;
    auto *fields = reinterpret_cast<WORD *>( data.data() + 4 );
    fields[0] = static_cast<WORD>( data.size() - 8 );
    fields[3] = static_cast<WORD>( substitute.size() * sizeof( wchar_t ) );
    fields[4] = static_cast<WORD>( ( substitute.size() + 1 ) * sizeof( wchar_t ) );
    fields[5] = static_cast<WORD>( target.native().size() * sizeof( wchar_t ) );
    std::memcpy( data.data() + 16, names.data(), names.size() * sizeof( wchar_t ) );
    DWORD returned = 0;
    const BOOL created = DeviceIoControl( handle, FSCTL_SET_REPARSE_POINT, data.data(),
                                          static_cast<DWORD>( data.size() ), nullptr, 0, &returned, nullptr );
    CloseHandle( handle );
    REQUIRE( created );
}
#endif

class save_fixture
{
    public:
        save_fixture() {
            root = std::filesystem::temp_directory_path() /
                   ( "cph-actor-save-test-" + cata::actor_control::new_identity() );
            REQUIRE( actor_files::create_private_directory( root ) == 0 );
        }
        ~save_fixture() {
            std::string error;
            transaction::finish( false, error );
            std::error_code ec;
            // Only the freshly created synthetic world owned by this fixture.
            std::filesystem::remove_all( root, ec );
        }
        std::filesystem::path root;
};

void put( const std::filesystem::path &path, const std::string &text )
{
    std::ofstream output( path, std::ios::binary | std::ios::trunc );
    output << text;
    output.close();
    REQUIRE( output.good() );
}

std::string get( const std::filesystem::path &path )
{
    std::ifstream input( path, std::ios::binary );
    REQUIRE( input.good() );
    return std::string( std::istreambuf_iterator<char>( input ), std::istreambuf_iterator<char>() );
}

void expect_private( const std::filesystem::path &path, int mode )
{
#ifdef _WIN32
    actor_files::info value;
    REQUIRE( actor_files::inspect( path, value ) == 0 );
    CHECK( value.private_access );
    CHECK( value.directory == ( mode == 0700 ) );
#else
    struct stat info {};
    REQUIRE( lstat( path.c_str(), &info ) == 0 );
    CHECK( info.st_uid == getuid() );
    CHECK( ( info.st_mode & 0777 ) == mode );
#endif
}

std::filesystem::path first_backup( const save_fixture &fixture, std::size_t index = 0 )
{
    const JsonObject manifest = json_loader::from_string(
                                    get( fixture.root / ".cph-actor-save/manifest.json" ) ).get_object();
    manifest.allow_omitted_members();
    const JsonObject file = manifest.get_array( "files" ).get_object( index );
    file.allow_omitted_members();
    return fixture.root / ".cph-actor-save" / file.get_string( "backup" );
}

void crash_after_inventory_save( const save_fixture &fixture )
{
#ifdef _WIN32
    REQUIRE( run_windows_child( fixture.root, L"inventory" ) == 0 );
#else
    // _exit deliberately abandons the real durable journal and releases its
    // flock through process exit. No production fault-injection branch exists.
    const pid_t child = fork();
    REQUIRE( child >= 0 );
    if( child == 0 ) {
        try {
            std::string error;
            if( !transaction::begin( fixture.root, error ) ) {
                _exit( 2 );
            }
            transaction::before_write( fixture.root / "npc.json" );
            transaction::before_write( fixture.root / "ground.json" );
            transaction::before_write( fixture.root / "master.gsav" );
            std::ofstream output( fixture.root / "npc.json", std::ios::trunc );
            output << "rock=1";
            output.close();
            _exit( output.good() ? 0 : 3 );
        } catch( const std::exception & ) {
            _exit( 4 );
        }
    }
    int status = 0;
    REQUIRE( waitpid( child, &status, 0 ) == child );
    REQUIRE( WIFEXITED( status ) );
    REQUIRE( WEXITSTATUS( status ) == 0 );
#endif
}
} // namespace

TEST_CASE( "actor_control_save_recovers_inventory_ground_and_task_as_one_generation",
           "[actor_control][save][lifecycle]" )
{
    save_fixture fixture;
    put( fixture.root / "npc.json", "rock=0" );
    put( fixture.root / "ground.json", "rock=1" );
    put( fixture.root / "master.gsav", "reward=100;receipt=none" );
    crash_after_inventory_save( fixture );
    REQUIRE( get( fixture.root / "npc.json" ) == "rock=1" );
    REQUIRE( get( fixture.root / "ground.json" ) == "rock=1" );
    expect_private( fixture.root / ".cph-actor-save", 0700 );
    expect_private( fixture.root / ".cph-actor-save/manifest.json", 0600 );
    expect_private( first_backup( fixture ), 0600 );
    std::string error;
    REQUIRE( transaction::recover( fixture.root, error ) );
    CHECK( get( fixture.root / "npc.json" ) == "rock=0" );
    CHECK( get( fixture.root / "ground.json" ) == "rock=1" );
    CHECK( get( fixture.root / "master.gsav" ) == "reward=100;receipt=none" );
    CHECK_FALSE( std::filesystem::exists( fixture.root / ".cph-actor-save/manifest.json" ) );
    REQUIRE( transaction::recover( fixture.root, error ) );
    CHECK( get( fixture.root / "npc.json" ) == "rock=0" );
}

TEST_CASE( "actor_control_save_journal_identity_and_crc_ignore_numeric_locale",
           "[actor_control][save][lifecycle][locale]" )
{
    save_fixture fixture;
    const std::locale previous_locale;
    const on_out_of_scope restore_locale( [previous_locale]() {
        std::locale::global( previous_locale );
    } );
    std::locale::global( std::locale( std::locale::classic(), new grouped_save_numbers ) );
    // This standard CRC-32 vector has the independently known checksum
    // cbf43926, making the grouping regression deterministic.
    put( fixture.root / "npc.json", "123456789" );
    put( fixture.root / "ground.json", "rock=1" );
    put( fixture.root / "master.gsav", "reward=100;receipt=none" );
#ifdef _WIN32
    // A custom C++ facet is process-local, so the existing crash helper must
    // select it in the child as well as in this recovery process.
    REQUIRE( run_windows_child( fixture.root, L"inventory_grouped" ) == 0 );
#else
    crash_after_inventory_save( fixture );
#endif
    REQUIRE( get( fixture.root / "npc.json" ) == "rock=1" );
    const JsonObject manifest = json_loader::from_string(
                                    get( fixture.root / ".cph-actor-save/manifest.json" ) ).get_object();
    manifest.allow_omitted_members();
    const std::string identity = manifest.get_string( "transaction_id" );
    CHECK( identity.size() == 32 );
    CHECK( identity.find_first_not_of( "0123456789abcdef" ) == std::string::npos );
    const JsonObject before_image = manifest.get_array( "files" ).get_object( 0 );
    before_image.allow_omitted_members();
    CHECK( before_image.get_string( "path" ) == "npc.json" );
    CHECK( before_image.get_string( "crc32" ) == "cbf43926" );
    std::string error;
    REQUIRE( transaction::recover( fixture.root, error ) );
    CHECK( get( fixture.root / "npc.json" ) == "123456789" );
    CHECK( get( fixture.root / "ground.json" ) == "rock=1" );
    CHECK( get( fixture.root / "master.gsav" ) == "reward=100;receipt=none" );
    CHECK_FALSE( std::filesystem::exists( fixture.root / ".cph-actor-save/manifest.json" ) );
}

TEST_CASE( "actor_control_save_rollback_is_reentrant_and_preserves_unknown_files",
           "[actor_control][save][lifecycle]" )
{
    save_fixture fixture;
    put( fixture.root / "npc.json", "rock=0" );
    put( fixture.root / "ground.json", "rock=1" );
    put( fixture.root / "master.gsav", "reward=100" );
    crash_after_inventory_save( fixture );
    // Recreate a crash after the first before-image was restored but before
    // the pending journal was retired; the rest still needs restoration.
    std::filesystem::copy_file( first_backup( fixture ), fixture.root / "npc.json",
                                std::filesystem::copy_options::overwrite_existing );
    put( fixture.root / "ground.json", "rock=0" );
    put( fixture.root / "master.gsav", "reward=0" );
    put( fixture.root / ".cph-actor-save/user-note", "keep this" );
    std::string error;
    REQUIRE( transaction::recover( fixture.root, error ) );
    CHECK( get( fixture.root / "npc.json" ) == "rock=0" );
    CHECK( get( fixture.root / "ground.json" ) == "rock=1" );
    CHECK( get( fixture.root / "master.gsav" ) == "reward=100" );
    CHECK( get( fixture.root / ".cph-actor-save/user-note" ) == "keep this" );
}

TEST_CASE( "actor_control_save_keeps_first_beforeimage_and_removes_only_recorded_creations",
           "[actor_control][save]" )
{
    save_fixture fixture;
    put( fixture.root / "npc.json", "initial" );
    std::string error;
    REQUIRE( transaction::begin( fixture.root, error ) );
    transaction::before_write( fixture.root / "npc.json" );
    put( fixture.root / "npc.json", "middle" );
    transaction::before_write( fixture.root / "npc.json" );
    put( fixture.root / "npc.json", "latest" );
    transaction::before_write( fixture.root / "new-receipt.json" );
    put( fixture.root / "new-receipt.json", "transient" );
    put( fixture.root / "user-created.json", "keep" );
    REQUIRE( transaction::finish( false, error ) );
    CHECK( get( fixture.root / "npc.json" ) == "initial" );
    CHECK_FALSE( std::filesystem::exists( fixture.root / "new-receipt.json" ) );
    CHECK( get( fixture.root / "user-created.json" ) == "keep" );
    CHECK_FALSE( transaction::active() );
}

TEST_CASE( "actor_control_save_commits_new_files_and_ignores_external_paths",
           "[actor_control][save]" )
{
    save_fixture fixture;
    save_fixture outside;
    put( fixture.root / "npc.json", "before" );
    put( outside.root / "keep", "outside" );
    std::string error;
    REQUIRE( transaction::begin( fixture.root, error ) );
    transaction::before_write( fixture.root / "npc.json" );
    put( fixture.root / "npc.json", "after" );
    transaction::before_write( outside.root / "keep" );
    transaction::before_write( fixture.root / "new.json" );
    put( fixture.root / "new.json", "new" );
    REQUIRE( transaction::finish( true, error ) );
    CHECK( get( fixture.root / "npc.json" ) == "after" );
    CHECK( get( fixture.root / "new.json" ) == "new" );
    CHECK( get( outside.root / "keep" ) == "outside" );
    REQUIRE( transaction::recover( fixture.root, error ) );
    CHECK( get( fixture.root / "npc.json" ) == "after" );
}

TEST_CASE( "actor_control_ordinary_world_loading_and_writing_create_no_journal",
           "[actor_control][save]" )
{
    save_fixture fixture;
    put( fixture.root / "player.sav", "before" );
    std::string error;
    REQUIRE( transaction::recover( fixture.root, error ) );
    CHECK_FALSE( transaction::active() );
    CHECK_FALSE( std::filesystem::exists( fixture.root / ".cph-actor-save" ) );
    write_to_file( ( fixture.root / "player.sav" ).u8string(), []( std::ostream & output ) {
        output << "ordinary-save";
    } );
    CHECK( get( fixture.root / "player.sav" ) == "ordinary-save" );
    CHECK_FALSE( std::filesystem::exists( fixture.root / ".cph-actor-save" ) );
}

TEST_CASE( "actor_control_save_corrupt_late_backup_restores_nothing_and_retains_evidence",
           "[actor_control][save][lifecycle]" )
{
    save_fixture fixture;
    put( fixture.root / "npc.json", "rock=0" );
    put( fixture.root / "ground.json", "rock=1" );
    put( fixture.root / "master.gsav", "reward=100" );
    crash_after_inventory_save( fixture );
    const auto backup = first_backup( fixture, 2 );
    put( backup, "damaged" );
    std::string error;
    CHECK_FALSE( transaction::recover( fixture.root, error ) );
    CHECK_FALSE( error.empty() );
    CHECK( get( fixture.root / "npc.json" ) == "rock=1" );
    CHECK( std::filesystem::exists( fixture.root / ".cph-actor-save/manifest.json" ) );
    CHECK( std::filesystem::exists( first_backup( fixture ) ) );
}

TEST_CASE( "actor_control_save_committed_cleanup_never_rolls_back_or_removes_unknown_files",
           "[actor_control][save][lifecycle]" )
{
    save_fixture fixture;
    put( fixture.root / "npc.json", "rock=0" );
    put( fixture.root / "ground.json", "rock=1" );
    put( fixture.root / "master.gsav", "reward=100" );
    crash_after_inventory_save( fixture );
    // Model the durable committed manifest surviving a crash before backup
    // retirement. Recovery must clean evidence without replaying old state.
    const auto manifest_path = fixture.root / ".cph-actor-save/manifest.json";
    std::string manifest = get( manifest_path );
    const std::size_t phase = manifest.find( "\"pending\"" );
    REQUIRE( phase != std::string::npos );
    manifest.replace( phase, 9, "\"committed\"" );
    put( manifest_path, manifest );
    const auto backup = first_backup( fixture );
    put( fixture.root / ".cph-actor-save/user-file", "keep" );
    std::string error;
    REQUIRE( transaction::recover( fixture.root, error ) );
    CHECK( get( fixture.root / "npc.json" ) == "rock=1" );
    CHECK_FALSE( std::filesystem::exists( backup ) );
    CHECK_FALSE( std::filesystem::exists( manifest_path ) );
    CHECK( get( fixture.root / ".cph-actor-save/user-file" ) == "keep" );
}

TEST_CASE( "actor_control_save_rejects_unknown_schema_traversal_and_symlink_targets",
           "[actor_control][save]" )
{
    save_fixture fixture;
    put( fixture.root / "npc.json", "before" );
    put( fixture.root / "ground.json", "ground" );
    put( fixture.root / "master.gsav", "master" );
    std::string error;
    SECTION( "future schema preserves every file" ) {
        crash_after_inventory_save( fixture );
        put( fixture.root / ".cph-actor-save/manifest.json", "{\"schema_version\":99}" );
        CHECK_FALSE( transaction::recover( fixture.root, error ) );
        CHECK( get( fixture.root / "npc.json" ) == "rock=1" );
    }
    SECTION( "manifest cannot escape world" ) {
        crash_after_inventory_save( fixture );
        std::string manifest = get( fixture.root / ".cph-actor-save/manifest.json" );
        const std::size_t position = manifest.find( "npc.json" );
        REQUIRE( position != std::string::npos );
        manifest.replace( position, 8, "../escape" );
        put( fixture.root / ".cph-actor-save/manifest.json", manifest );
        CHECK_FALSE( transaction::recover( fixture.root, error ) );
        CHECK( get( fixture.root / "npc.json" ) == "rock=1" );
    }
    SECTION( "file aliases cannot redirect beforeimage" ) {
        REQUIRE( transaction::begin( fixture.root, error ) );
#ifdef _WIN32
        std::filesystem::create_hard_link( fixture.root / "npc.json", fixture.root / "link.json" );
#else
        std::filesystem::create_symlink( fixture.root / "npc.json", fixture.root / "link.json" );
#endif
        CHECK_THROWS_AS( transaction::before_write( fixture.root / "link.json" ), std::ios::failure );
        CHECK_FALSE( transaction::finish( true, error ) );
        CHECK( get( fixture.root / "npc.json" ) == "before" );
        CHECK( std::filesystem::exists( fixture.root / "link.json" ) );
    }
    SECTION( "symlink parent is rejected" ) {
        REQUIRE( transaction::begin( fixture.root, error ) );
#ifdef _WIN32
        make_junction( fixture.root / "alias", fixture.root );
#else
        std::filesystem::create_directory_symlink( fixture.root, fixture.root / "alias" );
#endif
        CHECK_THROWS_AS( transaction::before_write( fixture.root / "alias/npc.json" ), std::ios::failure );
        CHECK_FALSE( transaction::finish( true, error ) );
        CHECK( get( fixture.root / "npc.json" ) == "before" );
#ifdef _WIN32
        REQUIRE( RemoveDirectoryW( ( fixture.root / "alias" ).c_str() ) );
#endif
    }
}

#ifdef __linux__
TEST_CASE( "actor_control_save_read_lease_excludes_a_second_process_without_journaling",
           "[actor_control][save][lifecycle]" )
{
    save_fixture fixture;
    int ready[2];
    REQUIRE( pipe( ready ) == 0 );
    // Fork before the parent takes its lock, so the child's copied controller
    // state cannot produce an in-process already_active false positive.
    const pid_t child = fork();
    REQUIRE( child >= 0 );
    if( child == 0 ) {
        close( ready[1] );
        char signal = 0;
        pollfd input { ready[0], POLLIN, 0 };
        if( poll( &input, 1, 5000 ) != 1 || read( ready[0], &signal, 1 ) != 1 ) {
            _exit( 2 );
        }
        std::string error;
        const bool acquired = transaction::begin( fixture.root, error, false );
        _exit( acquired || error.empty() ? 3 : 0 );
    }
    close( ready[0] );
    std::string error;
    REQUIRE( transaction::begin( fixture.root, error, false ) );
    CHECK( transaction::active() );
    CHECK_FALSE( transaction::capturing() );
    CHECK( transaction::owns_world( fixture.root / "." ) );
    CHECK( transaction::owns_world( fixture.root / "" ) );
    CHECK( transaction::owns_world( fixture.root / "unused" / ".." ) );
    CHECK_FALSE( transaction::owns_world( fixture.root.parent_path() ) );
    transaction::before_write( fixture.root / "not-captured" );
    CHECK_FALSE( std::filesystem::exists( fixture.root / ".cph-actor-save/manifest.json" ) );
    REQUIRE( write( ready[1], "x", 1 ) == 1 );
    close( ready[1] );
    int status = 0;
    REQUIRE( waitpid( child, &status, 0 ) == child );
    REQUIRE( WIFEXITED( status ) );
    CHECK( WEXITSTATUS( status ) == 0 );
    REQUIRE( transaction::finish( true, error ) );
    REQUIRE( transaction::recover( fixture.root, error ) );
}

TEST_CASE( "actor_control_save_native_writers_are_captured_without_manual_hooks",
           "[actor_control][save][lifecycle]" )
{
    save_fixture fixture;
    put( fixture.root / "player.sav", "old-player" );
    put( fixture.root / "master.gsav", "old-master" );
    put( fixture.root / "mapped", "old-mapped" );
    put( fixture.root / "source.zzip", "old-source" );
    put( fixture.root / "destination.zzip", "old-destination" );
    put( fixture.root / "obsolete-quad.json", "ground-rock=1" );
    {
        std::optional<zzip> archive = zzip::load( fixture.root / "npc.zzip" );
        REQUIRE( archive.has_value() );
        REQUIRE( archive->add_file( "npc.json", "rock=0" ) );
    }
    const pid_t child = fork();
    REQUIRE( child >= 0 );
    if( child == 0 ) {
        try {
            std::string error;
            if( !transaction::begin( fixture.root, error ) ) {
                _exit( 2 );
            }
            write_to_file( ( fixture.root / "player.sav" ).string(), []( std::ostream & output ) {
                output << "new-player";
            } );
            {
                ofstream_wrapper output( fixture.root / "master.gsav", std::ios::binary );
                output.stream() << "new-master";
                output.close();
            }
            {
                auto mapped = mmap_file::map_writeable_file( fixture.root / "mapped" );
                if( !mapped || !mapped->resize_file( 3 ) ) {
                    _exit( 3 );
                }
                auto bytes = static_cast<char *>( mapped->base() );
                bytes[0] = 'n';
                bytes[1] = 'e';
                bytes[2] = 'w';
                mapped->flush();
            }
            {
                auto mapped = mmap_file::map_writeable_file( fixture.root / "new-mapped" );
                if( !mapped || !mapped->resize_file( 1 ) ) {
                    _exit( 4 );
                }
                *static_cast<char *>( mapped->base() ) = 'x';
                mapped->flush();
            }
            {
                std::optional<zzip> archive = zzip::load( fixture.root / "npc.zzip" );
                if( !archive || !archive->add_file( "npc.json", "rock=1" ) ||
                    !archive->compact_to( fixture.root / "npc.zzip.tmp", 0 ) ) {
                    _exit( 5 );
                }
                archive.reset();
                if( !rename_file( fixture.root / "npc.zzip.tmp", fixture.root / "npc.zzip" ) ) {
                    _exit( 6 );
                }
            }
            {
                std::optional<zzip> created = zzip::load( fixture.root / "created-map.zzip" );
                if( !created || !created->add_file( "quad.json", "rock=0" ) ) {
                    _exit( 7 );
                }
            }
            if( !rename_file( fixture.root / "source.zzip", fixture.root / "destination.zzip" ) ||
                !remove_file( fixture.root / "obsolete-quad.json" ) ) {
                _exit( 8 );
            }
            _exit( 0 );
        } catch( const std::exception & ) {
            _exit( 9 );
        }
    }
    int status = 0;
    REQUIRE( waitpid( child, &status, 0 ) == child );
    REQUIRE( WIFEXITED( status ) );
    REQUIRE( WEXITSTATUS( status ) == 0 );
    CHECK( get( fixture.root / "player.sav" ) == "new-player" );
    CHECK( get( fixture.root / "mapped" ) == "new" );
    CHECK_FALSE( std::filesystem::exists( fixture.root / "obsolete-quad.json" ) );
    std::string error;
    REQUIRE( transaction::recover( fixture.root, error ) );
    CHECK( get( fixture.root / "player.sav" ) == "old-player" );
    CHECK( get( fixture.root / "master.gsav" ) == "old-master" );
    CHECK( get( fixture.root / "mapped" ) == "old-mapped" );
    CHECK( get( fixture.root / "source.zzip" ) == "old-source" );
    CHECK( get( fixture.root / "destination.zzip" ) == "old-destination" );
    CHECK( get( fixture.root / "obsolete-quad.json" ) == "ground-rock=1" );
    CHECK_FALSE( std::filesystem::exists( fixture.root / "new-mapped" ) );
    CHECK_FALSE( std::filesystem::exists( fixture.root / "created-map.zzip" ) );
    CHECK_FALSE( std::filesystem::exists( fixture.root / "npc.zzip.tmp" ) );
    {
        const std::optional<zzip> archive = zzip::load( fixture.root / "npc.zzip" );
        REQUIRE( archive.has_value() );
        const std::vector<std::byte> restored = archive->get_file( "npc.json" );
        CHECK( std::string( reinterpret_cast<const char *>( restored.data() ), restored.size() ) ==
               "rock=0" );
    }
}

#endif // __linux__

#ifdef _WIN32
TEST_CASE( "actor_control_save_windows_child", "[.actor_control_save_child]" )
{
    const wchar_t *root_value = _wgetenv( L"CPH_ACTOR_SAVE_CHILD_ROOT" );
    const wchar_t *mode_value = _wgetenv( L"CPH_ACTOR_SAVE_CHILD_MODE" );
    REQUIRE( root_value != nullptr );
    REQUIRE( mode_value != nullptr );
    const std::filesystem::path root( root_value );
    const std::wstring mode( mode_value );
    REQUIRE( root.filename().u8string().find( "cph-actor-save-test-" ) == 0 );
    const std::locale previous_locale;
    const on_out_of_scope restore_locale( [previous_locale]() {
        std::locale::global( previous_locale );
    } );
    if( mode == L"inventory_grouped" ) {
        std::locale::global( std::locale( std::locale::classic(), new grouped_save_numbers ) );
    }
    try {
        std::string error;
        if( mode == L"lock_refused" ) {
            const bool acquired = transaction::begin( root, error, false );
            _exit( !acquired && !error.empty() ? 0 : 10 );
        }
        if( mode == L"lock_available" ) {
            _exit( transaction::begin( root, error, false ) ? 0 : 11 );
        }
        if( !transaction::begin( root, error ) ) {
            _exit( 12 );
        }
        if( mode == L"inventory" || mode == L"inventory_grouped" ) {
            transaction::before_write( root / "npc.json" );
            transaction::before_write( root / "ground.json" );
            transaction::before_write( root / "master.gsav" );
            put( root / "npc.json", "rock=1" );
        } else if( mode == L"writers" ) {
            write_to_file( ( root / "player.sav" ).u8string(), []( std::ostream & output ) {
                output << "new-player";
            } );
            {
                ofstream_wrapper output( root / "master.gsav", std::ios::binary );
                output.stream() << "new-master";
                output.close();
            }
            {
                auto mapped = mmap_file::map_writeable_file( root / "mapped" );
                if( !mapped || !mapped->resize_file( 3 ) ) {
                    _exit( 13 );
                }
                std::memcpy( mapped->base(), "new", 3 );
                mapped->flush();
            }
            {
                auto mapped = mmap_file::map_writeable_file( root / "new-mapped" );
                if( !mapped || !mapped->resize_file( 1 ) ) {
                    _exit( 14 );
                }
                *static_cast<char *>( mapped->base() ) = 'x';
                mapped->flush();
            }
            {
                auto archive = zzip::load( root / "npc.zzip" );
                if( !archive || !archive->add_file( "npc.json", "rock=1" ) ||
                    !archive->compact_to( root / "npc.zzip.tmp", 0 ) ) {
                    _exit( 15 );
                }
                archive.reset();
                if( !rename_file( root / "npc.zzip.tmp", root / "npc.zzip" ) ) {
                    _exit( 16 );
                }
            }
            if( !rename_file( root / "source.zzip", root / "destination.zzip" ) ||
                !remove_file( root / "obsolete-quad.json" ) ) {
                _exit( 17 );
            }
        } else {
            _exit( 18 );
        }
        // This bypasses every C++ destructor: only OS process termination
        // closes the world lease, leaving the durable pending journal intact.
        _exit( 0 );
    } catch( const std::exception & ) {
        _exit( 19 );
    }
}

TEST_CASE( "actor_control_save_read_lease_excludes_a_second_process_without_journaling",
           "[actor_control][save][lifecycle][windows]" )
{
    save_fixture fixture;
    std::string error;
    REQUIRE( transaction::begin( fixture.root, error, false ) );
    CHECK( transaction::active() );
    CHECK_FALSE( transaction::capturing() );
    CHECK( transaction::owns_world( fixture.root / "." ) );
    transaction::before_write( fixture.root / "not-captured" );
    CHECK_FALSE( std::filesystem::exists( fixture.root / ".cph-actor-save/manifest.json" ) );
    CHECK( run_windows_child( fixture.root, L"lock_refused" ) == 0 );
    REQUIRE( transaction::finish( true, error ) );
    CHECK( run_windows_child( fixture.root, L"lock_available" ) == 0 );
    REQUIRE( transaction::recover( fixture.root, error ) );
}

TEST_CASE( "actor_control_save_native_writers_are_captured_without_manual_hooks",
           "[actor_control][save][lifecycle][windows]" )
{
    save_fixture fixture;
    put( fixture.root / "player.sav", "old-player" );
    put( fixture.root / "master.gsav", "old-master" );
    put( fixture.root / "mapped", "old-mapped" );
    put( fixture.root / "source.zzip", "old-source" );
    put( fixture.root / "destination.zzip", "old-destination" );
    put( fixture.root / "obsolete-quad.json", "ground-rock=1" );
    {
        auto archive = zzip::load( fixture.root / "npc.zzip" );
        REQUIRE( archive.has_value() );
        REQUIRE( archive->add_file( "npc.json", "rock=0" ) );
    }
    REQUIRE( run_windows_child( fixture.root, L"writers" ) == 0 );
    CHECK( get( fixture.root / "player.sav" ) == "new-player" );
    CHECK( get( fixture.root / "mapped" ) == "new" );
    std::string error;
    REQUIRE( transaction::recover( fixture.root, error ) );
    CHECK( get( fixture.root / "player.sav" ) == "old-player" );
    CHECK( get( fixture.root / "master.gsav" ) == "old-master" );
    CHECK( get( fixture.root / "mapped" ) == "old-mapped" );
    CHECK( get( fixture.root / "source.zzip" ) == "old-source" );
    CHECK( get( fixture.root / "destination.zzip" ) == "old-destination" );
    CHECK( get( fixture.root / "obsolete-quad.json" ) == "ground-rock=1" );
    CHECK_FALSE( std::filesystem::exists( fixture.root / "new-mapped" ) );
    CHECK_FALSE( std::filesystem::exists( fixture.root / "npc.zzip.tmp" ) );
    auto archive = zzip::load( fixture.root / "npc.zzip" );
    REQUIRE( archive.has_value() );
    const auto restored = archive->get_file( "npc.json" );
    CHECK( std::string( reinterpret_cast<const char *>( restored.data() ),
                        restored.size() ) == "rock=0" );
}

TEST_CASE( "actor_control_windows_rejects_ambiguous_names_and_untrusted_journals",
           "[actor_control][save][windows]" )
{
    save_fixture fixture;
    std::string error;
    SECTION( "Win32 aliases are refused before creating a file" ) {
        for( const char *name : {
                 "npc.json:secret", "npc.json.", "npc.json ", "CON", "NUL.txt", "COM1"
             } ) {
            INFO( name );
            const auto path = fixture.root / name;
            const int fd = actor_files::open( path, actor_files::access::create_new );
            CHECK( fd == -1 );
            if( fd >= 0 ) {
                actor_files::close( fd );
            }
        }
    }
    SECTION( "A public journal ACL is rejected, never repaired" ) {
        const auto journal = fixture.root / ".cph-actor-save";
        REQUIRE( actor_files::create_private_directory( journal ) == 0 );
        put( journal / "sentinel", "keep" );
        PSECURITY_DESCRIPTOR descriptor = nullptr;
        REQUIRE( ConvertStringSecurityDescriptorToSecurityDescriptorW( L"D:P(A;;FA;;;WD)",
                 SDDL_REVISION_1, &descriptor, nullptr ) );
        PACL acl = nullptr;
        BOOL present = FALSE, defaulted = FALSE;
        REQUIRE( GetSecurityDescriptorDacl( descriptor, &present, &acl, &defaulted ) );
        const DWORD result = SetNamedSecurityInfoW( const_cast<wchar_t *>( journal.c_str() ),
                             SE_FILE_OBJECT, DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
                             nullptr, nullptr, acl, nullptr );
        LocalFree( descriptor );
        REQUIRE( result == ERROR_SUCCESS );
        CHECK_FALSE( transaction::begin( fixture.root, error ) );
        actor_files::info value;
        REQUIRE( actor_files::inspect( journal, value ) == 0 );
        CHECK_FALSE( value.private_access );
        CHECK( get( journal / "sentinel" ) == "keep" );
    }
    SECTION( "A hardlinked lock cannot name an outside file" ) {
        save_fixture outside;
        const auto journal = fixture.root / ".cph-actor-save";
        REQUIRE( actor_files::create_private_directory( journal ) == 0 );
        const int fd = actor_files::open( outside.root / "keep", actor_files::access::create_new );
        REQUIRE( fd >= 0 );
        REQUIRE( actor_files::write( fd, "outside", 7 ) == 7 );
        actor_files::close( fd );
        std::filesystem::create_hard_link( outside.root / "keep", journal / "lock" );
        CHECK_FALSE( transaction::begin( fixture.root, error ) );
        CHECK( get( outside.root / "keep" ) == "outside" );
    }
    SECTION( "A junction cannot redirect journal creation" ) {
        save_fixture outside;
        make_junction( fixture.root / ".cph-actor-save", outside.root );
        CHECK_FALSE( transaction::begin( fixture.root, error ) );
        CHECK_FALSE( std::filesystem::exists( outside.root / "lock" ) );
        REQUIRE( RemoveDirectoryW( ( fixture.root / ".cph-actor-save" ).c_str() ) );
    }
    SECTION( "A case alias retains the original beforeimage" ) {
        put( fixture.root / "npc.json", "before" );
        REQUIRE( transaction::begin( fixture.root, error ) );
        auto upper = fixture.root.native();
        std::transform( upper.begin(), upper.end(), upper.begin(), []( wchar_t c ) {
            return static_cast<wchar_t>( std::towupper( c ) );
        } );
        CHECK( transaction::owns_world( std::filesystem::path( upper ) ) );
        transaction::before_write( std::filesystem::path( upper ) / "NPC.JSON" );
        put( fixture.root / "npc.json", "middle" );
        transaction::before_write( fixture.root / "npc.json" );
        put( fixture.root / "npc.json", "after" );
        REQUIRE( transaction::finish( false, error ) );
        CHECK( get( fixture.root / "npc.json" ) == "before" );
    }
    SECTION( "A manifest stream alias restores no earlier files" ) {
        put( fixture.root / "npc.json", "before" );
        put( fixture.root / "ground.json", "ground" );
        put( fixture.root / "master.gsav", "master" );
        crash_after_inventory_save( fixture );
        const auto path = fixture.root / ".cph-actor-save/manifest.json";
        auto manifest = get( path );
        const auto position = manifest.find( "master.gsav" );
        REQUIRE( position != std::string::npos );
        manifest.replace( position, 11, "master.gsav:stream" );
        put( path, manifest );
        CHECK_FALSE( transaction::recover( fixture.root, error ) );
        CHECK( get( fixture.root / "npc.json" ) == "rock=1" );
        CHECK( std::filesystem::exists( path ) );
    }
    SECTION( "Unicode filenames use the same durable transaction" ) {
        const auto target = fixture.root / std::filesystem::u8path( "\u80cc\u5305.json" );
        put( target, "before" );
        REQUIRE( transaction::begin( fixture.root, error ) );
        transaction::before_write( target );
        put( target, "after" );
        REQUIRE( transaction::finish( false, error ) );
        CHECK( get( target ) == "before" );
    }
}
#endif // _WIN32

TEST_CASE( "actor_control_dimension_marker_joins_world_save_transaction",
           "[actor_control][save][dimension]" )
{
    save_fixture fixture;
    const cata_path world_dir( cata_path::root_path::unknown, fixture.root );
    put( fixture.root / "player.sav", "before-travel" );
    REQUIRE( save_snapshot::make_dimension_rollback( world_dir, "survivor", 1 ) );
    REQUIRE( save_snapshot::begin_dimension_transition( world_dir ) );
    put( fixture.root / "player.sav", "destination" );
    std::string error;
    REQUIRE( transaction::begin( fixture.root, error ) );
    REQUIRE( save_snapshot::finish_dimension_transition( world_dir ) );
    CHECK_FALSE( save_snapshot::dimension_transition_pending( world_dir ) );

    SECTION( "failed checkpoint keeps interrupted travel recoverable" ) {
        REQUIRE( transaction::finish( false, error ) );
        REQUIRE( save_snapshot::dimension_transition_pending( world_dir ) );
        REQUIRE( save_snapshot::recover_dimension_transition( world_dir ) );
        CHECK( get( fixture.root / "player.sav" ) == "before-travel" );
        CHECK_FALSE( save_snapshot::dimension_transition_pending( world_dir ) );
    }

    SECTION( "committed checkpoint keeps the destination save" ) {
        REQUIRE( transaction::finish( true, error ) );
        REQUIRE( save_snapshot::recover_dimension_transition( world_dir ) );
        CHECK( get( fixture.root / "player.sav" ) == "destination" );
        CHECK_FALSE( save_snapshot::dimension_transition_pending( world_dir ) );
    }
}

#endif // __linux__ || _WIN32
