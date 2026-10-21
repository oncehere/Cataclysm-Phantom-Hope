#include <filesystem>
#include <fstream>
#include <iterator>
#include <locale>
#include <string>

#include "actor_control_bridge.h"
#include "actor_control_files.h"
#include "actor_control_protocol_generated.h"
#include "actor_control_runtime.h"
#include "actor_control_ui.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "debug.h"
#include "flexbuffer_json.h"
#include "json_loader.h"
#include "path_info.h"
#include "translations.h"
#if defined( LOCALIZE )
    #include "translation_manager.h"
#endif

namespace
{
class grouped_numeric_punctuation : public std::numpunct<char>
{
    protected:
        char do_thousands_sep() const override {
            return ',';
        }
        std::string do_grouping() const override {
            return "\3";
        }
};

std::string contents( const std::filesystem::path &path )
{
    std::ifstream input( path );
    return std::string( std::istreambuf_iterator<char>( input ), std::istreambuf_iterator<char>() );
}
} // namespace

TEST_CASE( "actor_control_game_profile_preserves_existing_schema_and_non_ui_settings",
           "[actor_control][runtime][configuration][locale]" )
{
    namespace control = cata::actor_control;
    const std::locale original_locale = std::locale();
    const on_out_of_scope restore_locale( [&]() {
        std::locale::global( original_locale );
    } );
    const auto directory = std::filesystem::temp_directory_path() /
                           ( "cph-runtime-config-" + control::new_identity() );
    REQUIRE( directory.is_absolute() );
    REQUIRE( std::filesystem::create_directory( directory ) );
    const auto old_working_directory = std::filesystem::current_path();
    const auto old_base = PATH_INFO::base_path().get_unrelative_path();
    const std::string old_user = PATH_INFO::user_dir();
    const on_out_of_scope cleanup( [&]() {
        std::filesystem::current_path( old_working_directory );
        PATH_INFO::init_base_path( old_base.u8string() );
        PATH_INFO::init_user_dir( old_user );
        std::filesystem::remove_all( directory );
    } );
    PATH_INFO::init_base_path( directory.u8string() );
    PATH_INFO::init_user_dir( directory.u8string() );
    SECTION( "absolute_game_directories" ) {
    }
    SECTION( "relative_game_directories" ) {
        std::filesystem::current_path( directory );
        PATH_INFO::init_base_path( "./" );
        PATH_INFO::init_user_dir( "./" );
    }
    SECTION( "grouped_numeric_locale" ) {
        std::locale::global( std::locale( std::locale::classic(), new grouped_numeric_punctuation ) );
    }
    const auto bundle = directory / "companion-runtime";
    REQUIRE( std::filesystem::create_directory( bundle ) );
    std::ofstream( bundle / "config.default.json" ) <<
            R"({"schema_version":1,"profile_id":"template","actor_id":null,"llm":{"base_url":"","model":"","max_output_tokens":1024},"personality":{"traits":{"caution":0.7}},"limits":{"session_max_calls":17,"max_input_tokens":32768},"paths":{"background":"background.md","memory":"memory"},"duties":{"allowed_tasks":[],"max_distance":12,"item_types":[],"recipes":[]}})";
    std::ofstream( bundle / "background.default.md" ) << "A synthetic background";
    control::runtime_preferences preferences;
    std::string error;
    REQUIRE( control::read_runtime_preferences( "../same-profile", 7, preferences, error ) );
    preferences.endpoint = "https://example.invalid/v1";
    preferences.model = "synthetic-model";
    preferences.background = "A changed background";
    preferences.duties = { "gather" };
    preferences.item_types = { "rock" };
    const auto profile = control::runtime_profile_directory( preferences.profile_id );
    CHECK( profile.is_absolute() );
    REQUIRE( control::save_runtime_preferences( preferences, error ) );
    CHECK( profile.parent_path() == directory / "ai-companion/profiles" );
    const std::string encoded = contents( profile / "config.json" );
    const JsonObject config = json_loader::from_string( encoded ).get_object();
    config.allow_omitted_members();
    CHECK( config.get_int( "schema_version" ) == 1 );
    CHECK( config.get_string( "profile_id" ) == "../same-profile" );
    CHECK( config.get_int( "actor_id" ) == 7 );
    const JsonObject limits = config.get_object( "limits" );
    CHECK( limits.get_int( "session_max_calls" ) == 17 );
    CHECK( limits.get_int( "max_input_tokens" ) == 32768 );
    CHECK( config.get_object( "personality" ).get_object( "traits" ).get_float( "caution" ) == 0.7 );
    const JsonObject llm = config.get_object( "llm" );
    llm.allow_omitted_members();
    CHECK( llm.get_int( "max_output_tokens" ) == 1024 );
    CHECK( llm.get_string( "api_key_env" ) == "CPH_LLM_API_KEY" );
    CHECK( encoded.find( "api_key\"" ) == std::string::npos );
    CHECK( contents( profile / "background.md" ) == preferences.background );
    control::runtime_preferences loaded;
    REQUIRE( control::read_runtime_preferences( preferences.profile_id, 7, loaded, error ) );
    CHECK( loaded.endpoint == preferences.endpoint );
    CHECK( loaded.duties == preferences.duties );
    CHECK( loaded.item_types == preferences.item_types );
    preferences.max_distance = 61;
    CHECK_FALSE( control::save_runtime_preferences( preferences, error ) );
    CHECK( contents( profile / "config.json" ) == encoded );
    CHECK_FALSE( control::managed_runtime_running() );
}

TEST_CASE( "actor_control_player_status_distinguishes_setup_startup_and_connection",
           "[actor_control][runtime][ui]" )
{
    namespace control = cata::actor_control;
#if defined( LOCALIZE )
    const std::string old_language = TranslationManager::GetInstance().GetCurrentLanguage();
    const on_out_of_scope restore_language( [old_language]() {
        set_language( old_language );
    } );
#endif
    set_language( "en" );
    std::string raw;
    std::string expected;
    std::string next_step;
    bool runtime_running = false;
    SECTION( "world_without_mod_explains_how_to_enable_it" ) {
        raw = R"({"enabled":false,"actor_id":null,"state":"unbound"})";
        expected = "not enabled in this world";
        next_step = "Enable the companion Mod";
    }
    SECTION( "first_use_explains_binding_instead_of_reporting_a_disconnect" ) {
        raw = R"({"enabled":true,"actor_id":null,"state":"unbound"})";
        expected = "No companion is bound";
        next_step = "Bind a recruited companion";
    }
    SECTION( "a_started_process_is_not_yet_a_connected_runtime" ) {
        raw = R"({"enabled":true,"actor_id":7,"state":"active",
                   "detach_state":"attached","connected":false})";
        runtime_running = true;
        expected = "Starting the AI runtime";
        next_step = "waiting for the local connection";
    }
    SECTION( "an_authenticated_external_runtime_is_connected_without_a_managed_child" ) {
        raw = R"({"enabled":true,"actor_id":7,"state":"active",
                   "detach_state":"attached","connected":true,"planning_state":"idle"})";
        expected = "AI runtime connected";
    }
    SECTION( "a_pending_decision_does_not_claim_a_live_worker" ) {
        raw = R"({"enabled":true,"actor_id":7,"connected":true,"planning_state":"pending"})";
        expected = "no model request is running";
    }
    SECTION( "quota_exhaustion_explains_that_local_actions_continue" ) {
        raw = R"({"enabled":true,"actor_id":7,"connected":true,"planning_state":"suspended",
                   "planning_reason":"call_budget_exhausted"})";
        expected = "reached its spending limit";
        next_step = "Existing local actions can continue";
    }
    SECTION( "provider_failure_has_an_actionable_public_message" ) {
        raw = R"({"enabled":true,"actor_id":7,"connected":true,"planning_state":"failed",
                   "planning_reason":"provider_failed"})";
        expected = "model service request failed";
        next_step = "check the saved provider settings and session key";
    }
    SECTION( "timeout_is_not_reported_as_still_thinking" ) {
        raw = R"({"enabled":true,"actor_id":7,"connected":true,"planning_state":"failed",
                   "planning_reason":"decision_timeout"})";
        expected = "planning timed out";
    }
    const JsonObject value = json_loader::from_string( raw ).get_object();
    value.allow_omitted_members();
    const std::string text = control::player_status_text( value, runtime_running );
    CHECK( text.find( expected ) != std::string::npos );
    CHECK( text.find( "AI runtime disconnected" ) == std::string::npos );
    CHECK( text.find( "Waiting for an AI decision" ) == std::string::npos );
    if( !next_step.empty() ) {
        CHECK( text.find( next_step ) != std::string::npos );
    }
}

TEST_CASE( "actor_control_player_status_does_not_reveal_private_runtime_state",
           "[actor_control][runtime][ui][privacy]" )
{
    namespace control = cata::actor_control;
#if defined( LOCALIZE )
    const std::string old_language = TranslationManager::GetInstance().GetCurrentLanguage();
    const on_out_of_scope restore_language( [old_language]() {
        set_language( old_language );
    } );
#endif
    set_language( "en" );
    const JsonObject value = json_loader::from_string( R"({
        "enabled":true,"actor_id":7,"state":"active","control_state":"active",
        "detach_state":"attached","connected":true,"planning_state":"idle",
        "profile_id":"PRIVATE_UX_SENTINEL",
        "task_summary":[{"id":"PRIVATE_UX_SENTINEL","kind":"guard"}],
        "current_queue":[{"intent":"PRIVATE_UX_SENTINEL"}],
        "personality":{"motivation":"PRIVATE_UX_SENTINEL"},
        "debug":{"tasks":[{"reason":"PRIVATE_UX_SENTINEL"}]},
        "player_progress":[
            {"task_kind":"gather","progress":1,"target":3,"state":"paused"},
            {"task_kind":"craft","progress":0,"target":1,"state":"queued"}
        ],
        "transcript":[{"speaker":"companion","text":"PUBLIC_DIALOGUE"}]
    })" ).get_object();
    value.allow_omitted_members();
    const std::string text = control::player_status_text( value, true );
    CHECK( text.find( "PRIVATE_UX_SENTINEL" ) == std::string::npos );
    CHECK( text.find( "PUBLIC_DIALOGUE" ) != std::string::npos );
    CHECK( text.find( "1/3" ) != std::string::npos );
    CHECK( text.find( "0/1" ) != std::string::npos );
    CHECK( text.find( "Paused" ) != std::string::npos );
    CHECK( text.find( "Queued" ) != std::string::npos );
}

TEST_CASE( "actor_control_diagnostics_require_an_explicit_debug_object",
           "[actor_control][runtime][ui][privacy]" )
{
    namespace control = cata::actor_control;
    std::string raw;
    bool available = false;
    SECTION( "ordinary_status_is_not_diagnostic" ) {
        raw = R"({"actor_id":null,"context":null,"planning_state":"offline",
                   "task_summary":[{"id":"private-task"}]})";
    }
    SECTION( "null_debug_does_not_enable_diagnostics" ) {
        raw = R"({"debug":null})";
    }
    SECTION( "a_boolean_cannot_enable_diagnostics" ) {
        raw = R"({"debug":true})";
    }
    SECTION( "an_array_cannot_enable_diagnostics" ) {
        raw = R"({"debug":[]})";
    }
    SECTION( "native_debug_object_enables_diagnostics" ) {
        raw = R"({"debug":{"current_queue":[]}})";
        available = true;
    }
    const std::string messages = capture_debugmsg_during( [&raw, available]() {
        const JsonObject value = json_loader::from_string( raw ).get_object();
        CHECK( control::diagnostics_available( value ) == available );
    } );
    CHECK( messages.empty() );
}
