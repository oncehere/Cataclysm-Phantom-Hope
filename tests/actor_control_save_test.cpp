#include "actor_control_save.h"

#ifdef __linux__

#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>

#include <poll.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

#include "actor_control_bridge.h"
#include "cata_catch.h"
#include "cata_utility.h"
#include "filesystem.h"
#include "flexbuffer_json.h"
#include "json_loader.h"
#include "mmap_file.h"
#include "ofstream_wrapper.h"
#include "zzip.h"

namespace
{
namespace transaction = cata::actor_control::save_transaction;

class save_fixture
{
    public:
        save_fixture() {
            root = std::filesystem::temp_directory_path() /
                   ( "cph-actor-save-test-" + cata::actor_control::new_identity() );
            REQUIRE( std::filesystem::create_directory( root ) );
            REQUIRE( chmod( root.c_str(), 0700 ) == 0 );
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

void expect_private( const std::filesystem::path &path, mode_t mode )
{
    struct stat info {};
    REQUIRE( lstat( path.c_str(), &info ) == 0 );
    CHECK( info.st_uid == getuid() );
    CHECK( ( info.st_mode & 0777 ) == mode );
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
    SECTION( "symlink cannot redirect beforeimage" ) {
        REQUIRE( transaction::begin( fixture.root, error ) );
        std::filesystem::create_symlink( fixture.root / "npc.json", fixture.root / "link.json" );
        CHECK_THROWS_AS( transaction::before_write( fixture.root / "link.json" ), std::ios::failure );
        CHECK_FALSE( transaction::finish( true, error ) );
        CHECK( get( fixture.root / "npc.json" ) == "before" );
        CHECK( std::filesystem::is_symlink( fixture.root / "link.json" ) );
    }
    SECTION( "symlink parent is rejected" ) {
        REQUIRE( transaction::begin( fixture.root, error ) );
        std::filesystem::create_directory_symlink( fixture.root, fixture.root / "alias" );
        CHECK_THROWS_AS( transaction::before_write( fixture.root / "alias/npc.json" ), std::ios::failure );
        CHECK_FALSE( transaction::finish( true, error ) );
        CHECK( get( fixture.root / "npc.json" ) == "before" );
    }
}

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
