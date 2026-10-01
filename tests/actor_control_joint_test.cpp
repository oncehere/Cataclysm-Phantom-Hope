#if defined(__linux__)

#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <sstream>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include "actor_control.h"
#include "actor_control_bridge.h"
#include "avatar.h"
#include "calendar.h"
#include "cata_catch.h"
#include "character_attire.h"
#include "coordinates.h"
#include "flexbuffer_json.h"
#include "input_context.h"
#include "input_enums.h"
#include "input_replay.h"
#include "item.h"
#include "json.h"
#include "json_loader.h"
#include "map.h"
#include "map_helpers.h"
#include "npc.h"
#include "path_info.h"
#include "player_helpers.h"
#include "type_id.h"

namespace
{
namespace control = cata::actor_control;

JsonObject joint_object( const std::string &text )
{
    JsonObject object = json_loader::from_string( text ).get_object();
    object.allow_omitted_members();
    return object;
}

std::string joint_result_text( const std::filesystem::path &path )
{
    std::ifstream input( path );
    return input.good() ? std::string( std::istreambuf_iterator<char>( input ),
                                       std::istreambuf_iterator<char>() ) : "Joint driver result unavailable";
}

std::string joint_saved_state()
{
    std::ostringstream buffer;
    JsonOut out( buffer );
    control::serialize( out );
    return buffer.str();
}

class joint_fixture
{
    public:
        joint_fixture() : old_user_dir_( PATH_INFO::user_dir() ),
            old_config_dir_( PATH_INFO::config_dir() ), old_save_dir_( PATH_INFO::savedir() ),
            old_turn_( calendar::turn ) {
            const char *runtime = std::getenv( "XDG_RUNTIME_DIR" );
            had_runtime_ = runtime != nullptr;
            old_runtime_ = runtime ? runtime : "";
            directory_ = std::filesystem::temp_directory_path() /
                         ( "cph-actor-joint-test-" + control::new_identity() );
            std::filesystem::create_directory( directory_ );
            REQUIRE( chmod( directory_.c_str(), 0700 ) == 0 );
            for( const char *name : {
                     "runtime", "user", "config", "save", "profile"
                 } ) {
                const std::filesystem::path path = directory_ / name;
                std::filesystem::create_directory( path );
                REQUIRE( chmod( path.c_str(), 0700 ) == 0 );
            }
            REQUIRE( setenv( "XDG_RUNTIME_DIR", ( directory_ / "runtime" ).c_str(), 1 ) == 0 );
            PATH_INFO::init_user_dir( ( directory_ / "user" ).string() );
            PATH_INFO::set_config_dir( ( directory_ / "config" ).string() + "/" );
            PATH_INFO::set_savedir( ( directory_ / "save" ).string() + "/" );
            control::enable( false );
            control::reset();
            clear_map();
            clear_avatar();
            calendar::turn = calendar::turn_zero + 12_hours;
            get_avatar().setpos( get_map(), tripoint_bub_ms( 59, 60, 0 ) );
            control::enable( true );
        }

        ~joint_fixture() {
            input_replay::finish();
            control::enable( false );
            control::reset();
            clear_npcs();
            calendar::turn = old_turn_;
            PATH_INFO::init_user_dir( old_user_dir_ );
            PATH_INFO::set_config_dir( old_config_dir_ );
            PATH_INFO::set_savedir( old_save_dir_ );
            if( had_runtime_ ) {
                setenv( "XDG_RUNTIME_DIR", old_runtime_.c_str(), 1 );
            } else {
                unsetenv( "XDG_RUNTIME_DIR" );
            }
            // This randomly named directory is created and owned by this fixture.
            // No game/user save, pre-existing path, or build cache is removed.
            std::error_code error;
            std::filesystem::remove_all( directory_, error );
        }

        const std::filesystem::path &directory() const {
            return directory_;
        }

    private:
        bool had_runtime_ = false;
        std::string old_runtime_;
        std::string old_user_dir_;
        std::string old_config_dir_;
        std::string old_save_dir_;
        time_point old_turn_;
        std::filesystem::path directory_;
};

class joint_driver_process
{
    public:
        explicit joint_driver_process( std::vector<std::string> arguments ) :
            arguments_( std::move( arguments ) ) {}

        ~joint_driver_process() {
            if( pid_ > 0 && !reaped_ ) {
                // The child's own process group also contains its bounded SDK worker.
                // Never signal the test runner's group or any unrelated process.
                if( getpgid( pid_ ) == pid_ ) {
                    kill( -pid_, SIGKILL );
                } else {
                    kill( pid_, SIGKILL );
                }
                while( waitpid( pid_, &exit_status_, 0 ) < 0 && errno == EINTR ) {
                }
            }
        }

        void start() {
            std::vector<char *> argv;
            for( std::string &argument : arguments_ ) {
                argv.push_back( argument.data() );
            }
            argv.push_back( nullptr );
            pid_ = fork();
            REQUIRE( pid_ >= 0 );
            if( pid_ == 0 ) {
                if( setpgid( 0, 0 ) != 0 ) {
                    _exit( 126 );
                }
                execv( argv.front(), argv.data() );
                _exit( 127 );
            }
            // Either parent or child can win this race; the child always sets its
            // group before exec, so EACCES here simply means exec already happened.
            const int group_result = setpgid( pid_, pid_ );
            REQUIRE( ( group_result == 0 || errno == EACCES ) );
            REQUIRE( getpgid( pid_ ) == pid_ );
        }

        bool finished() {
            if( reaped_ ) {
                return true;
            }
            const pid_t waited = waitpid( pid_, &exit_status_, WNOHANG );
            REQUIRE( ( waited >= 0 || errno == EINTR ) );
            reaped_ = waited == pid_;
            return reaped_;
        }

        int exit_code() const {
            return WIFEXITED( exit_status_ ) ? WEXITSTATUS( exit_status_ ) : -1;
        }

    private:
        std::vector<std::string> arguments_;
        pid_t pid_ = -1;
        int exit_status_ = 0;
        bool reaped_ = false;
};
} // namespace

TEST_CASE( "actor_control_final_package_executes_real_npc_gather_and_records_memory",
           "[.actor_control_joint]" )
{
    const char *python = std::getenv( "CPH_COMPANION_PYTHON" );
    const char *driver = std::getenv( "CPH_COMPANION_JOINT_DRIVER" );
    REQUIRE( python != nullptr );
    REQUIRE( driver != nullptr );
    REQUIRE( std::filesystem::is_regular_file( python ) );
    REQUIRE( std::filesystem::is_regular_file( driver ) );
    REQUIRE_FALSE( input_replay::is_recording() );
    REQUIRE_FALSE( input_replay::is_replaying() );

    joint_fixture fixture;
    npc &actor = spawn_npc( { 60, 60 }, "test_talker" );
    clear_character( actor, true );
    actor.setpos( get_map(), tripoint_bub_ms( 60, 60, 0 ) );
    actor.set_fac( faction_id( "your_followers" ) );
    actor.set_attitude( NPCATT_FOLLOW );
    actor.worn.wear_item( actor, item( itype_id( "debug_backpack" ) ), false, false );
    actor.recalc_sight_limits();
    actor.set_moves( 1000 );
    REQUIRE( actor.is_player_ally() );
    REQUIRE( actor.amount_of( itype_id( "rock" ) ) == 0 );
    const tripoint_bub_ms ground( 60, 61, 0 );
    item rock( itype_id( "rock" ), calendar::turn );
    rock.set_owner( actor );
    get_map().add_item_or_charges( ground, rock );
    REQUIRE( actor.sees( get_map(), ground ) );
    std::string error;
    REQUIRE( control::bind( actor, "joint-companion", error ) );
    REQUIRE( error.empty() );
    const std::string descriptor = joint_object( control::status() ).get_string( "descriptor_path" );
    REQUIRE( std::filesystem::is_regular_file( descriptor ) );

    const std::string replay_path = ( fixture.directory() / "waiting-input.replay" ).string();
    REQUIRE( input_replay::begin_record( replay_path ) );
    // The production recorder filters poll-generated timeouts. Record an
    // unbound character instead, then consume it in an isolated ANY_INPUT
    // context. This covers the real input/communication path without a GUI
    // backend or a gameplay action; it does not establish graphical acceptance.
    for( int index = 0; index < 30000; ++index ) {
        input_replay::on_record( input_event( '~', input_event_t::keyboard_char ) );
    }
    input_replay::finish();
    REQUIRE( input_replay::begin_replay( replay_path ) );
    input_context waiting_input( "ACTOR_CONTROL_JOINT" );
    waiting_input.register_action( "ANY_INPUT" );

    const std::filesystem::path result_path = fixture.directory() / "result.json";
    joint_driver_process child( { python, driver, "--session", descriptor,
                                  "--profile", ( fixture.directory() / "profile" ).string(),
                                  "--profile-id", "joint-companion", "--result", result_path.string() } );
    const time_point before = calendar::turn;
    const int npc_moves = actor.get_moves();
    const int player_moves = get_avatar().get_moves();
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds( 60 );
    child.start();
    bool queued = false;
    while( std::chrono::steady_clock::now() < deadline ) {
        REQUIRE( input_replay::replay_remaining() > 0 );
        REQUIRE( waiting_input.handle_input( 10 ) == "ANY_INPUT" );
        queued = joint_object( control::status() ).get_int( "queue_length" ) > 0;
        if( queued || child.finished() ) {
            break;
        }
        std::this_thread::sleep_for( std::chrono::milliseconds( 2 ) );
    }
    INFO( joint_result_text( result_path ) );
    REQUIRE( queued );
    CHECK( calendar::turn == before );
    CHECK( actor.get_moves() == npc_moves );
    CHECK( get_avatar().get_moves() == player_moves );
    CHECK( actor.amount_of( itype_id( "rock" ) ) == 0 );
    input_replay::finish();
    REQUIRE( control::act( actor, false ) );
    CHECK( actor.get_moves() < npc_moves );
    CHECK( calendar::turn == before );
    CHECK( get_avatar().get_moves() == player_moves );
    CHECK( actor.amount_of( itype_id( "rock" ) ) == 1 );
    CHECK( get_map().i_at( ground ).empty() );

    // Exercise the real runtime checkpoint RPC after the native receipt. This
    // prepares the extension only; it does not commit a game/world save.
    std::string prepared_state;
    const int completed_moves = actor.get_moves();
    for( int attempt = 0; attempt < 5; ++attempt ) {
        control::before_save();
        const std::string serialized = joint_saved_state();
        const JsonObject pending = joint_object( serialized );
        if( !pending.get_member( "saved_checkpoint" ).test_null() ) {
            prepared_state = serialized;
            break;
        }
        if( child.finished() ) {
            break;
        }
    }
    INFO( joint_result_text( result_path ) );
    REQUIRE_FALSE( prepared_state.empty() );
    const JsonObject prepared = joint_object( prepared_state );
    const JsonObject reference = prepared.get_object( "saved_checkpoint" );
    reference.allow_omitted_members();
    const JsonObject checkpoint_context = prepared.get_object( "saved_memory_context" );
    checkpoint_context.allow_omitted_members();
    REQUIRE_FALSE( reference.get_string( "revision" ).empty() );
    REQUIRE_FALSE( reference.get_string( "projection_version" ).empty() );
    CHECK( reference.get_string( "projection_version" ) ==
           checkpoint_context.get_string( "memory_version" ) );
    CHECK( reference.get_string( "revision" ) != reference.get_string( "projection_version" ) );
    CHECK( actor.get_moves() == completed_moves );
    CHECK( calendar::turn == before );
    CHECK( get_avatar().get_moves() == player_moves );
    control::after_save( false );

    while( std::chrono::steady_clock::now() < deadline && !child.finished() ) {
        control::pump_incoming();
        std::this_thread::sleep_for( std::chrono::milliseconds( 2 ) );
    }
    REQUIRE( child.finished() );
    const std::string result_text = joint_result_text( result_path );
    INFO( result_text );
    REQUIRE( child.exit_code() == 0 );
    REQUIRE( std::filesystem::is_regular_file( result_path ) );
    const JsonObject result = joint_object( result_text );
    CHECK( result.get_string( "state" ) == "passed" );
    CHECK( result.get_string( "sdk_version" ) == "3.22.1" );
    CHECK( result.get_int( "sdk_calls" ) >= 1 );
    CHECK( result.get_bool( "non_streaming" ) );
    CHECK( result.get_bool( "no_tools" ) );
    CHECK( result.get_string( "receipt_state" ) == "succeeded" );
    CHECK( result.get_int( "memory_receipts" ) >= 1 );
    CHECK( result.get_bool( "checkpoint_prepared" ) );
    CHECK( result.get_string( "checkpoint_projection_version" ) ==
           reference.get_string( "projection_version" ) );
    CHECK( result.get_string( "checkpoint_file_revision" ) == reference.get_string( "revision" ) );
    CHECK( result.get_string( "detach_state" ) == "detached" );
    CHECK( joint_object( control::status() ).get_string( "detach_state" ) == "detached" );
    CHECK( joint_object( control::status() ).get_int( "queue_length" ) == 0 );
    CHECK( actor.amount_of( itype_id( "rock" ) ) == 1 );
    CHECK( get_map().i_at( ground ).empty() );
    CHECK( calendar::turn == before );
    CHECK( get_avatar().get_moves() == player_moves );
}

#endif // defined(__linux__)
