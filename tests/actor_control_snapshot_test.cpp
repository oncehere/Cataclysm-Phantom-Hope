#ifdef __linux__

#include <filesystem>
#include <fstream>
#include <string>

#include <sys/stat.h>

#include "actor_control_bridge.h"
#include "actor_control_save.h"
#include "cata_catch.h"
#include "cata_path.h"
#include "save_snapshot.h"

TEST_CASE( "actor_control_gameplay_snapshots_keep_live_journal_authority",
           "[actor_control][save][snapshot]" )
{
    namespace transaction = cata::actor_control::save_transaction;
    const std::filesystem::path root = std::filesystem::temp_directory_path() /
                                       ( "cph-actor-snapshot-" + cata::actor_control::new_identity() );
    REQUIRE( std::filesystem::create_directory( root ) );
    REQUIRE( chmod( root.c_str(), 0700 ) == 0 );
    const cata_path world( cata_path::root_path::unknown, root );
    struct cleanup {
        std::filesystem::path path;
        ~cleanup() {
            std::string error;
            transaction::finish( false, error );
            std::filesystem::remove_all( path );
        }
    } owned { root };
    std::string error;
    REQUIRE( transaction::begin( root, error, false ) );
    REQUIRE( transaction::finish( true, error ) );
    std::ofstream( root / "player.sav" ) << "saved player";
    std::ofstream( root / ".cph-actor-save/user-note" ) << "live authority note";
    REQUIRE( save_snapshot::make_snapshot( world, "test", "survivor", 1 ) );
    CHECK_FALSE( std::filesystem::exists( root / "snapshots/test/.cph-actor-save" ) );
    // Even a historical snapshot containing this folder cannot overwrite the
    // live lock/journal authority when the player explicitly restores it.
    std::filesystem::create_directory( root / "snapshots/test/.cph-actor-save" );
    std::ofstream( root / "snapshots/test/.cph-actor-save/user-note" ) << "obsolete note";
    std::ofstream( root / "player.sav" ) << "changed player";
    REQUIRE( save_snapshot::restore_snapshot( world, "test" ) );
    std::string note;
    std::getline( std::ifstream( root / ".cph-actor-save/user-note" ), note );
    CHECK( note == "live authority note" );
    REQUIRE( transaction::begin( root, error ) );
    CHECK_FALSE( save_snapshot::make_snapshot( world, "during-save", "survivor", 1 ) );
    CHECK_FALSE( save_snapshot::restore_snapshot( world, "test" ) );
    REQUIRE( transaction::finish( false, error ) );
    CHECK( std::filesystem::exists( root / "player.sav" ) );
}

#endif
