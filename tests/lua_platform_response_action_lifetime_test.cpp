#if defined(CATA_ENABLE_LUA_PLATFORM) && CATA_ENABLE_LUA_PLATFORM

#include <cata_scope_helpers.h>
#include <cstdint>
#include <memory>

#include "cata_catch.h"
#include "dialogue.h"
#include "lua_platform_dialogue.h"
#include "lua_platform_handle.h"

namespace platform_dialogue = cata::lua_platform::dialogue;

TEST_CASE( "lua_platform_abandoned_response_actions_release_captures",
           "[lua][platform][dialogue][callbacks][gc]" )
{
    platform_dialogue::clear_response_callbacks();
    const on_out_of_scope cleanup( []() {
        platform_dialogue::clear_response_callbacks();
    } );
    dialogue conversation;
    const cata::lua_platform::game_handle_runtime_owner_ptr owner =
        cata::lua_platform::make_game_handle_runtime_owner();
    const cata::lua_platform::game_handle_runtime runtime( owner, 1 );
    platform_dialogue::begin_session( conversation, runtime, 1 );
    const platform_dialogue::dialogue_session_ptr session = platform_dialogue::session_for(
                conversation, "TALK_ABANDONED_ACTION", runtime, 1 );
    REQUIRE( session );
    std::weak_ptr<int> capture;
    int calls = 0;
    std::uint64_t callback_id = 0;
    {
        const std::shared_ptr<int> lifetime = std::make_shared<int>( 1 );
        capture = lifetime;
        callback_id = platform_dialogue::register_response_action_callback(
                          platform_dialogue::response_callback_origin::platform,
        [lifetime, &calls]( dialogue &, bool ) {
            calls += *lifetime;
        }, session, "TALK_ABANDONED_ACTION" );
    }
    REQUIRE_FALSE( capture.expired() );

    SECTION( "regenerating response lines retires unselected actions" ) {
        platform_dialogue::clear_response_callbacks( conversation );
        CHECK( session->active() );
    }
    SECTION( "ending the dialogue retires unselected actions" ) {
        platform_dialogue::end_session( conversation );
        CHECK_FALSE( session->active() );
    }
    CHECK( capture.expired() );
    platform_dialogue::apply_response_action_callback( conversation, callback_id, true );
    CHECK( calls == 0 );
}

TEST_CASE( "lua_platform_nested_response_action_cleanup_preserves_other_sessions",
           "[lua][platform][dialogue][callbacks][gc]" )
{
    platform_dialogue::clear_response_callbacks();
    const on_out_of_scope cleanup( []() {
        platform_dialogue::clear_response_callbacks();
    } );
    dialogue outer;
    dialogue inner;
    const cata::lua_platform::game_handle_runtime_owner_ptr owner =
        cata::lua_platform::make_game_handle_runtime_owner();
    const cata::lua_platform::game_handle_runtime runtime( owner, 1 );
    platform_dialogue::begin_session( outer, runtime, 1 );
    platform_dialogue::begin_session( inner, runtime, 1 );
    const platform_dialogue::dialogue_session_ptr outer_session = platform_dialogue::session_for(
                outer, "TALK_OUTER_ACTION", runtime, 1 );
    const platform_dialogue::dialogue_session_ptr inner_session = platform_dialogue::session_for(
                inner, "TALK_INNER_ACTION", runtime, 1 );
    REQUIRE( outer_session );
    REQUIRE( inner_session );
    std::weak_ptr<int> outer_capture;
    std::weak_ptr<int> inner_capture;
    int outer_calls = 0;
    int inner_calls = 0;
    std::uint64_t outer_id = 0;
    std::uint64_t inner_id = 0;
    {
        const std::shared_ptr<int> outer_lifetime = std::make_shared<int>( 1 );
        const std::shared_ptr<int> inner_lifetime = std::make_shared<int>( 1 );
        outer_capture = outer_lifetime;
        inner_capture = inner_lifetime;
        outer_id = platform_dialogue::register_response_action_callback(
                       platform_dialogue::response_callback_origin::platform,
        [outer_lifetime, &outer_calls]( dialogue &, bool success ) {
            CHECK_FALSE( success );
            outer_calls += *outer_lifetime;
        }, outer_session, "TALK_OUTER_ACTION" );
        inner_id = platform_dialogue::register_response_action_callback(
                       platform_dialogue::response_callback_origin::platform,
        [inner_lifetime, &inner_calls]( dialogue &, bool ) {
            inner_calls += *inner_lifetime;
        }, inner_session, "TALK_INNER_ACTION" );
    }
    platform_dialogue::end_session( inner );
    CHECK( inner_capture.expired() );
    CHECK_FALSE( outer_capture.expired() );
    CHECK( outer_session->active() );
    platform_dialogue::apply_response_action_callback( inner, inner_id, true );
    platform_dialogue::apply_response_action_callback( outer, outer_id, false );
    platform_dialogue::apply_response_action_callback( outer, outer_id, false );
    CHECK( inner_calls == 0 );
    CHECK( outer_calls == 1 );
    CHECK( outer_capture.expired() );
}

TEST_CASE( "lua_platform_sessionless_response_actions_require_explicit_retirement",
           "[lua][platform][dialogue][callbacks][gc]" )
{
    platform_dialogue::clear_response_callbacks();
    const on_out_of_scope cleanup( []() {
        platform_dialogue::clear_response_callbacks();
    } );
    dialogue conversation;
    std::weak_ptr<int> capture;
    int calls = 0;
    std::uint64_t callback_id = 0;
    {
        const std::shared_ptr<int> lifetime = std::make_shared<int>( 1 );
        capture = lifetime;
        callback_id = platform_dialogue::register_response_action_callback(
                          platform_dialogue::response_callback_origin::platform,
        [lifetime, &calls]( dialogue &, bool ) {
            calls += *lifetime;
        } );
    }
    // Matching a selection callback ID must not associate an independent
    // action ID with this dialogue.
    conversation.responses.emplace_back();
    conversation.responses.back().lua_response_id = callback_id;
    platform_dialogue::clear_response_callbacks( conversation );
    CHECK_FALSE( capture.expired() );
    SECTION( "explicit action invocation remains one-shot" ) {
        platform_dialogue::apply_response_action_callback( conversation, callback_id, true );
        platform_dialogue::apply_response_action_callback( conversation, callback_id, true );
        CHECK( calls == 1 );
    }
    SECTION( "origin cleanup releases unowned actions" ) {
        platform_dialogue::clear_response_callbacks(
            platform_dialogue::response_callback_origin::platform );
        platform_dialogue::apply_response_action_callback( conversation, callback_id, true );
        CHECK( calls == 0 );
    }
    SECTION( "global cleanup releases unowned actions" ) {
        platform_dialogue::clear_response_callbacks();
        platform_dialogue::apply_response_action_callback( conversation, callback_id, true );
        CHECK( calls == 0 );
    }
    CHECK( capture.expired() );
}

#endif
