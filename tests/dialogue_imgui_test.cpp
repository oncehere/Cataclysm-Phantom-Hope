#include <algorithm>
#include <cstddef>
#include <cstdio>
#include <limits>
#include <memory>
#include <string>
#include <vector>

#include "avatar.h"
#include "cata_catch.h"
#include "cata_imgui.h"
#include "cata_scope_helpers.h"
#include "color.h"
#include "debug.h"
#include "dialogue.h"
#include "dialogue_helpers.h"
#include "dialogue_imgui.h"
#include "imgui/imgui.h"
#include "imgui/imgui_internal.h"
#include "input.h"
#include "input_enums.h"
#include "input_replay.h"
#include "npc.h"
#include "player_helpers.h"
#include "talker_topic.h"
#include "uistate.h"

#if defined(CATA_ENABLE_LUA_PLATFORM) && CATA_ENABLE_LUA_PLATFORM
    #include "lua_platform_dialogue.h"
    #include "lua_platform_handle.h"
    #include "lua_platform_hooks.h"
    #include "lua_platform_runtime.h"
    #include "lua_platform_runtime_internal.h"
    #include "lua_platform_sol.h"
#endif

namespace
{
dialogue topic_conversation()
{
    return dialogue( std::make_unique<talker_topic>(), std::make_unique<talker_topic>() );
}

class dialogue_imgui_frame_fixture
{
    public:
        dialogue_imgui_frame_fixture() : previous_( ImGui::GetCurrentContext() ),
            context_( ImGui::CreateContext() ) {
            ImGui::SetCurrentContext( context_ );
            ImGuiIO &io = ImGui::GetIO();
            io.IniFilename = nullptr;
            io.LogFilename = nullptr;
            io.DisplaySize = ImVec2( 800, 600 );
            io.DeltaTime = 1.0F / 60.0F;
            io.ConfigInputTrickleEventQueue = false;
            io.Fonts->AddFontDefault();
            io.Fonts->AddFontDefault();
            unsigned char *pixels = nullptr;
            int width = 0;
            int height = 0;
            io.Fonts->GetTexDataAsRGBA32( &pixels, &width, &height );
            ImGuiStyle &style = ImGui::GetStyle();
            style.FrameRounding = 0;
            style.DisabledAlpha = 1.0F;
            const ImVec4 button_color( 17.0F / 255, 33.0F / 255, 65.0F / 255, 1 );
            style.Colors[ImGuiCol_Button] = button_color;
            style.Colors[ImGuiCol_ButtonHovered] = button_color;
            style.Colors[ImGuiCol_ButtonActive] = button_color;
        }

        ~dialogue_imgui_frame_fixture() {
            ImGui::DestroyContext( context_ );
            ImGui::SetCurrentContext( previous_ );
        }

        void frame( dialogue_imgui_impl &window ) const {
            ImGui::NewFrame();
            window.draw();
            ImGui::Render();
        }

        void settle( dialogue_imgui_impl &window ) const {
            frame( window );
            frame( window );
            frame( window );
        }

        ImGuiWindow *child( const std::string &name ) const {
            for( ImGuiWindow *window : context_->Windows ) {
                if( std::string( window->Name ).find( name ) != std::string::npos ) {
                    return window;
                }
            }
            return nullptr;
        }

        std::vector<ImRect> buttons( const ImGuiWindow *window ) const {
            if( !window ) {
                return {};
            }
            // Each unrounded button background is one real draw-list quad.
            // A unique test theme identifies these without exposing UI test hooks.
            constexpr ImU32 button_color = IM_COL32( 17, 33, 65, 255 );
            std::vector<ImRect> result;
            const ImVector<ImDrawVert> &vertices = window->DrawList->VtxBuffer;
            for( int i = 0; i + 3 < vertices.Size; ++i ) {
                if( vertices[i].col != button_color || vertices[i + 1].col != button_color ||
                    vertices[i + 2].col != button_color || vertices[i + 3].col != button_color ) {
                    continue;
                }
                ImRect rect( vertices[i].pos, vertices[i].pos );
                for( int corner = 1; corner < 4; ++corner ) {
                    rect.Add( vertices[i + corner].pos );
                }
                result.push_back( rect );
                i += 3;
            }
            return result;
        }

        std::vector<ImRect> buttons() const {
            return buttons( child( "##DIALOGUE_RESPONSES" ) );
        }

        void click( dialogue_imgui_impl &window, const ImVec2 &position ) const {
            ImGuiIO &io = ImGui::GetIO();
            io.AddMousePosEvent( position.x, position.y );
            frame( window );
            io.AddMouseButtonEvent( 0, true );
            frame( window );
            io.AddMouseButtonEvent( 0, false );
            frame( window );
        }

    private:
        ImGuiContext *previous_;
        ImGuiContext *context_;
};
} // namespace

TEST_CASE( "dialogue_imgui_hotkeys_ignore_unassigned_and_nonkeyboard_input",
           "[dialogue][imgui][input]" )
{
    const input_event first( 'a', input_event_t::keyboard_char );
    const input_event second( 'b', input_event_t::keyboard_char );
    const std::vector<input_event> hotkeys = { first, second };
    CHECK( dialogue_response_hotkey_index( hotkeys, first ) == 0 );
    CHECK( dialogue_response_hotkey_index( hotkeys, second ) == 1 );
    CHECK_FALSE( dialogue_response_hotkey_index( hotkeys,
                 input_event( 'z', input_event_t::keyboard_char ) ) );
    CHECK_FALSE( dialogue_response_hotkey_index( hotkeys,
                 input_event( MouseInput::LeftButtonReleased, input_event_t::mouse ) ) );
    CHECK_FALSE( dialogue_response_hotkey_index( hotkeys, input_event() ) );
    CHECK_FALSE( dialogue_response_hotkey_index( {}, first ) );
}

TEST_CASE( "dialogue_imgui_selection_rejects_disabled_and_invalid_responses",
           "[dialogue][imgui][input]" )
{
    restore_on_out_of_scope<bool> restore_debug( debug_mode );
    debug_mode = false;
    dialogue conversation = topic_conversation();
    conversation.add_topic( "TALK_CURRENT" );
    int applied = 0;
    talk_response response;
    response.text = "Unavailable";
    response.success.next_topic = talk_topic( "TALK_SELECTED" );
    response.success.set_effect( talk_effect_fun_t( [&applied]( dialogue & ) {
        ++applied;
    } ) );
    conversation.add_gen_response( response, false, true, false );
    CHECK_FALSE( conversation.response_is_selectable( 0 ) );
    CHECK_FALSE( conversation.response_is_selectable( 1 ) );
    CHECK_FALSE( conversation.response_is_selectable( std::numeric_limits<std::size_t>::max() ) );
    CHECK( conversation.apply_response( 0 ).id == "TALK_CURRENT" );
    CHECK( conversation.apply_response( 1 ).id == "TALK_CURRENT" );
    CHECK( applied == 0 );

    conversation.response_condition_eval[0] = true;
    CHECK( conversation.response_is_selectable( 0 ) );
    CHECK( conversation.apply_response( 0 ).id == "TALK_SELECTED" );
    CHECK( applied == 1 );

    conversation.response_condition_eval[0] = false;
    debug_mode = true;
    CHECK( conversation.response_is_selectable( 0 ) );
    CHECK( conversation.apply_response( 0 ).id == "TALK_SELECTED" );
    CHECK( applied == 2 );
}

TEST_CASE( "dialogue_imgui_topic_returns_are_safe_at_root_and_preserve_categories",
           "[dialogue][imgui][topic]" )
{
    dialogue conversation = topic_conversation();
    SECTION( "empty root" ) {
        CHECK_FALSE( conversation.advance_topic( talk_topic( "TALK_NONE" ) ) );
        CHECK( conversation.done );
        CHECK( conversation.topic_stack.empty() );
    }
    SECTION( "single categorized topic" ) {
        conversation.add_topic( "TALK_MISSION_OFFER" );
        CHECK_FALSE( conversation.advance_topic( talk_topic( "TALK_NONE" ) ) );
        CHECK( conversation.done );
        CHECK( conversation.topic_stack.empty() );
    }
    SECTION( "category is popped together" ) {
        conversation.add_topic( "TALK_BASE" );
        conversation.add_topic( "TALK_MISSION_DESCRIBE" );
        conversation.add_topic( "TALK_MISSION_OFFER" );
        REQUIRE( conversation.advance_topic( talk_topic( "TALK_NONE" ) ) );
        REQUIRE( conversation.topic_stack.size() == 1 );
        CHECK( conversation.topic_stack.back().id == "TALK_BASE" );
        CHECK_FALSE( conversation.done );
    }
    SECTION( "special information topics are not grouped" ) {
        conversation.add_topic( "TALK_BASE" );
        conversation.add_topic( "TALK_LOOK_AT" );
        conversation.add_topic( "TALK_OPINION" );
        REQUIRE( conversation.advance_topic( talk_topic( "TALK_NONE" ) ) );
        REQUIRE( conversation.topic_stack.size() == 2 );
        CHECK( conversation.topic_stack.back().id == "TALK_LOOK_AT" );
    }
    SECTION( "next topic retains item and reason" ) {
        conversation.add_topic( "TALK_BASE" );
        const talk_topic next( "TALK_NEXT", itype_id( "water" ), "chosen reason" );
        REQUIRE( conversation.advance_topic( next ) );
        CHECK( conversation.topic_stack.back().id == next.id );
        CHECK( conversation.topic_stack.back().item_type == next.item_type );
        CHECK( conversation.topic_stack.back().reason == next.reason );
        CHECK_FALSE( conversation.advance_topic( talk_topic( "TALK_DONE" ) ) );
        CHECK( conversation.done );
    }
}

TEST_CASE( "dialogue_imgui_quit_skips_disabled_exit_responses",
           "[dialogue][imgui][input]" )
{
    restore_on_out_of_scope<bool> restore_debug( debug_mode );
    debug_mode = false;
    dialogue conversation = topic_conversation();
    talk_response exit;
    exit.success.next_topic = talk_topic( "TALK_DONE" );
    conversation.add_gen_response( exit, false, true, false );
    CHECK( conversation.get_best_quit_response() == 1 );
    conversation.add_gen_response( exit, false, true, true );
    CHECK( conversation.get_best_quit_response() == 1 );
    conversation.response_condition_eval[1] = false;
    CHECK( conversation.get_best_quit_response() == 2 );
    debug_mode = true;
    CHECK( conversation.get_best_quit_response() == 0 );
}

TEST_CASE( "dialogue_imgui_mouse_selects_duplicate_labels_and_rejects_disabled_buttons",
           "[dialogue][imgui][input][mouse]" )
{
    dialogue_imgui_frame_fixture frames;
    dialogue conversation = topic_conversation();
    dialogue_imgui_impl window( &conversation, false, true );
    const std::vector<talk_data> responses = {
        { c_white, "a", "Identical label" },
        { c_white, "b", "Identical label" }
    };
    window.set_responses( responses, { true, true } );
    frames.settle( window );
    std::vector<ImRect> buttons = frames.buttons();
    REQUIRE( buttons.size() == 2 );
    frames.click( window, buttons[0].GetCenter() );
    CHECK( window.user_clicked_response_button );
    CHECK( window.sel_response == 0 );
    window.user_clicked_response_button = false;
    buttons = frames.buttons();
    REQUIRE( buttons.size() == 2 );
    frames.click( window, buttons[1].GetCenter() );
    CHECK( window.user_clicked_response_button );
    CHECK( window.sel_response == 1 );

    window.set_responses( responses, { true, false } );
    window.sel_response = 0;
    window.user_clicked_response_button = false;
    frames.settle( window );
    buttons = frames.buttons();
    REQUIRE( buttons.size() == 2 );
    frames.click( window, buttons[1].GetCenter() );
    CHECK_FALSE( window.user_clicked_response_button );
    CHECK( window.sel_response == 0 );
}

TEST_CASE( "dialogue_imgui_long_chinese_response_wraps_and_lower_lines_are_clickable",
           "[dialogue][imgui][layout][mouse]" )
{
    dialogue_imgui_frame_fixture frames;
    dialogue conversation = topic_conversation();
    dialogue_imgui_impl window( &conversation, false, true );
    std::string long_text;
    for( int i = 0; i < 100; ++i ) {
        long_text += "这是一段包含中文和 English 的长回应。";
    }
    window.set_responses( { { c_white, "a", long_text } } );
    frames.settle( window );
    const std::vector<ImRect> buttons = frames.buttons();
    REQUIRE( buttons.size() == 1 );
    const ImGuiWindow *responses = frames.child( "##DIALOGUE_RESPONSES" );
    REQUIRE( responses );
    CHECK( buttons[0].GetHeight() > ImGui::GetTextLineHeightWithSpacing() * 3 );
    CHECK( buttons[0].Max.x <= responses->InnerClipRect.Max.x + 1 );
    const float lower_visible_line = std::min( buttons[0].Max.y,
                                     responses->InnerClipRect.Max.y ) - 3;
    REQUIRE( lower_visible_line > buttons[0].Min.y + ImGui::GetTextLineHeightWithSpacing() );
    frames.click( window, ImVec2( buttons[0].GetCenter().x, lower_visible_line ) );
    CHECK( window.user_clicked_response_button );
    CHECK( window.sel_response == 0 );
}

TEST_CASE( "dialogue_imgui_history_and_keyboard_selection_scroll_with_updated_content",
           "[dialogue][imgui][scroll]" )
{
    dialogue_imgui_frame_fixture frames;
    dialogue conversation = topic_conversation();
    dialogue_imgui_impl window( &conversation, false, true );
    std::vector<talk_data> responses;
    for( int i = 0; i < 80; ++i ) {
        responses.push_back( { c_white, "a", "Response " + std::to_string( i ) } );
    }
    window.set_responses( responses );
    window.add_to_history( "Initial greeting" );
    frames.settle( window );
    window.sel_response = 79;
    frames.settle( window );
    const ImGuiWindow *response_window = frames.child( "##DIALOGUE_RESPONSES" );
    REQUIRE( response_window );
    CHECK( response_window->Scroll.y > 0 );

    for( int i = 0; i < 100; ++i ) {
        window.add_to_history( "History line " + std::to_string( i ) );
    }
    window.scroll_to = cataimgui::scroll::end;
    frames.settle( window );
    const ImGuiWindow *history = frames.child( "##DIALOGUE_HISTORY" );
    REQUIRE( history );
    REQUIRE( history->ScrollMax.y > 0 );
    CHECK( history->Scroll.y >= history->ScrollMax.y - 1 );
    CHECK( window.scroll_to == cataimgui::scroll::none );
}

TEST_CASE( "dialogue_imgui_resize_and_modal_hide_preserve_accessible_children",
           "[dialogue][imgui][layout]" )
{
    dialogue_imgui_frame_fixture frames;
    dialogue conversation = topic_conversation();
    dialogue_imgui_impl window( &conversation, false, true );
    window.set_responses( { { c_white, "a", "Available response" } } );
    window.add_to_history( "Preserved history" );
    frames.settle( window );
    const ImGuiWindow *wide_responses = frames.child( "##DIALOGUE_RESPONSES" );
    REQUIRE( wide_responses );
    const float wide_width = wide_responses->Size.x;
    ImGui::GetIO().DisplaySize = ImVec2( 200, 700 );
    frames.settle( window );
    const ImGuiWindow *narrow_responses = frames.child( "##DIALOGUE_RESPONSES" );
    const ImGuiWindow *history = frames.child( "##DIALOGUE_HISTORY" );
    REQUIRE( narrow_responses );
    REQUIRE( history );
    CHECK( narrow_responses->Size.x < wide_width );
    CHECK( narrow_responses->Size.x > 0 );
    CHECK( narrow_responses->Size.y > 0 );
    CHECK( history->Size.x > 0 );
    CHECK( history->Size.y > 0 );
    CHECK( narrow_responses->Pos.x + narrow_responses->Size.x <= 201 );
    CHECK( narrow_responses->Pos.y + narrow_responses->Size.y <= 701 );

    window.set_hidden( true );
    frames.settle( window );
    CHECK_FALSE( narrow_responses->Active );
    CHECK( narrow_responses->ParentWindow->Hidden );
    window.set_hidden( false );
    ImGui::GetIO().DisplaySize = ImVec2( 800, 600 );
    frames.settle( window );
    REQUIRE( frames.child( "##DIALOGUE_RESPONSES" ) );
    CHECK_FALSE( frames.child( "##DIALOGUE_RESPONSES" )->Hidden );
    CHECK( frames.child( "##DIALOGUE_RESPONSES" )->Size.x == Approx( wide_width ) );
    CHECK_FALSE( frames.buttons().empty() );
}

TEST_CASE( "dialogue_imgui_npc_sidebar_and_actions_remain_accessible_on_narrow_windows",
           "[dialogue][imgui][layout][npc][mouse]" )
{
    clear_avatar();
    npc interlocutor;
    interlocutor.normalize();
    interlocutor.name = "Sidebar NPC";
    dialogue_imgui_frame_fixture frames;
    dialogue conversation( get_talker_for( get_avatar() ), get_talker_for( interlocutor ) );
    dialogue_imgui_impl window( &conversation );
    window.set_responses( { { c_white, "a", "Available response" } } );
    window.add_to_history( "Preserved conversation" );
    frames.settle( window );
    ImGuiWindow *sidebar = frames.child( "##DIALOGUE_SIDEBAR" );
    ImGuiWindow *responses = frames.child( "##DIALOGUE_RESPONSES" );
    REQUIRE( sidebar );
    REQUIRE( responses );
    CHECK( sidebar->Active );
    CHECK( sidebar->Pos.x + sidebar->Size.x <= responses->Pos.x );

    ImGui::SetScrollY( sidebar, sidebar->ScrollMax.y );
    frames.settle( window );
    const std::vector<ImRect> action_buttons = frames.buttons( sidebar );
    REQUIRE_FALSE( action_buttons.empty() );
    frames.click( window, action_buttons.back().GetCenter() );
    CHECK( window.take_special_action() == "YELL" );
    CHECK( window.take_special_action().empty() );

    ImGui::GetIO().DisplaySize = ImVec2( 200, 700 );
    frames.settle( window );
    REQUIRE( responses->Active );
    const ImGuiWindow *parent = responses->ParentWindow;
    std::vector<ImRect> toggles = frames.buttons( parent );
    REQUIRE( toggles.size() == 1 );
    frames.click( window, toggles.front().GetCenter() );
    frames.settle( window );
    CHECK( sidebar->Active );
    CHECK_FALSE( responses->Active );
    CHECK( sidebar->Size.x > 0 );
    CHECK( sidebar->Pos.x + sidebar->Size.x <= 201 );
    toggles = frames.buttons( parent );
    REQUIRE( toggles.size() == 1 );
    frames.click( window, toggles.front().GetCenter() );
    frames.settle( window );
    CHECK( responses->Active );
    CHECK_FALSE( frames.buttons().empty() );
}

#if defined(CATA_ENABLE_LUA_PLATFORM) && CATA_ENABLE_LUA_PLATFORM
TEST_CASE( "dialogue_imgui_apply_response_preserves_lua_order_and_once_only_callback",
           "[dialogue][imgui][lua][platform]" )
{
    namespace platform = cata::lua_platform;
    platform::dialogue::clear_response_callbacks();
    on_out_of_scope cleanup( []() {
        platform::dialogue::clear_response_callbacks();
    } );
    dialogue conversation = topic_conversation();
    conversation.add_topic( "TALK_CALLBACK" );
    const auto runtime_owner = platform::make_game_handle_runtime_owner();
    const platform::game_handle_runtime runtime( runtime_owner, 1 );
    const auto session = platform::dialogue::begin_session( conversation, runtime, 1 );
    REQUIRE( platform::dialogue::session_for( conversation, "TALK_CALLBACK", runtime, 1 ) ==
             session );
    std::vector<std::string> order;
    talk_response response;
    response.text = "Callback response";
    response.success.next_topic = talk_topic( "TALK_NATIVE" );
    response.success.set_effect( talk_effect_fun_t( [&order]( dialogue & ) {
        order.emplace_back( "native_effect" );
    } ) );
    response.lua_response_id = platform::dialogue::register_response_callback(
                                   platform::dialogue::response_callback_origin::platform,
    [&order]( dialogue &, const talk_topic & fallback, bool success ) {
        CHECK( fallback.id == "TALK_NATIVE" );
        CHECK( success );
        order.emplace_back( "lua_callback" );
        dialogue nested = topic_conversation();
        nested.gen_responses( talk_topic( "TALK_DONE" ) );
        return talk_topic( "TALK_LUA" );
    }, session, "TALK_CALLBACK" );
    conversation.add_gen_response( response, false, false, true );
    {
        dialogue child = topic_conversation();
        platform::begin_dialogue_session( child );
        child.gen_responses( talk_topic( "TALK_DONE" ) );
        platform::end_dialogue_session( child );
    }
    CHECK( session->active() );
    CHECK( conversation.apply_response( 0 ).id == "TALK_LUA" );
    CHECK( order == std::vector<std::string> { "native_effect", "lua_callback" } );
    CHECK( conversation.apply_response( 0 ).id == "TALK_NATIVE" );
    CHECK( order == std::vector<std::string> { "native_effect", "lua_callback", "native_effect" } );

    bool stale_called = false;
    conversation.responses[0].lua_response_id = platform::dialogue::register_response_callback(
                platform::dialogue::response_callback_origin::platform,
    [&stale_called]( dialogue &, const talk_topic &, bool ) {
        stale_called = true;
        return talk_topic( "TALK_STALE" );
    }, session, "TALK_CALLBACK" );
    platform::end_dialogue_session( conversation );
    CHECK_FALSE( session->active() );
    CHECK( conversation.apply_response( 0 ).id == "TALK_NATIVE" );
    CHECK_FALSE( stale_called );
}

TEST_CASE( "dialogue_imgui_avatar_driver_preserves_lua_hooks_and_context_lifetimes",
           "[dialogue][imgui][lua][platform][input][integration]" )
{
    namespace platform = cata::lua_platform;
    clear_avatar();
    platform::clear_active_runtimes();
    sol::state lua;
    lua.open_libraries( sol::lib::base, sol::lib::table );
    sol::table ccb = lua.create_table();
    const auto owner = platform::make_runtime( "dialogue_imgui_driver", 5902, lua );
    const std::string replay_path = "dialogue_imgui_driver_replay.txt";
    const on_out_of_scope cleanup( [&replay_path]() {
        input_replay::finish();
        std::remove( replay_path.c_str() );
        platform::clear_active_runtimes();
    } );
    platform::install_runtime_api( owner, lua, ccb );
    lua["ccb"] = ccb;
    lua.set_function( "generate_nested_responses", []() {
        dialogue nested = topic_conversation();
        platform::begin_dialogue_session( nested );
        nested.gen_responses( talk_topic( "TALK_DONE" ) );
        platform::end_dialogue_session( nested );
    } );
    const sol::protected_function_result registration = lua.safe_script( R"(
        trace = {}
        contexts = {}
        local function remember(context, phase, topic)
            assert(context:valid())
            assert(context:topic() == (topic or "TALK_IMGUI_DRIVER"))
            assert(context:by_radio())
            contexts[phase] = context
            table.insert(trace, phase)
        end
        ccb.dialogue.register_topic {
            id = "TALK_IMGUI_DRIVER",
            dynamic_line = function(context)
                remember(context, "line")
                return "A scripted conversation."
            end,
            responses = function(context)
                remember(context, "responses")
                return {{
                    text = "Unselected response",
                    topic = "TALK_DONE",
                    on_select = function()
                        error("The keyboard selection did not move down")
                    end
                }, {
                    text = "Finish conversation",
                    topic = "TALK_DONE",
                    on_success = function(context, success, fallback)
                        remember(context, "success")
                        assert(success and fallback == "TALK_DONE")
                        generate_nested_responses()
                    end,
                    on_select = function(context, success, fallback)
                        remember(context, "select")
                        assert(success and fallback == "TALK_DONE")
                        return "TALK_IMGUI_NEXT"
                    end
                }}
            end,
            speaker_effects = function(context)
                remember(context, "speaker_effect")
                generate_nested_responses()
            end
        }
        ccb.dialogue.register_topic {
            id = "TALK_IMGUI_NEXT",
            dynamic_line = function(context)
                remember(context, "next_line", "TALK_IMGUI_NEXT")
                return "The next topic starts at its first response."
            end,
            responses = function(context)
                remember(context, "next_responses", "TALK_IMGUI_NEXT")
                return {{
                    text = "Finish conversation",
                    topic = "TALK_DONE",
                    on_select = function(context)
                        remember(context, "next_select", "TALK_IMGUI_NEXT")
                    end
                }, {
                    text = "Unselected second response",
                    topic = "TALK_DONE",
                    on_select = function()
                        error("The previous topic selection was retained")
                    end
                }}
            end
        }
        ccb.runtime.handler("dialogue_start", function(payload)
            assert(payload.initial_topic == "TALK_IMGUI_BEFORE")
            assert(payload.by_radio and payload.speaker and payload.interlocutor)
            table.insert(trace, "start")
            return {result = "TALK_IMGUI_DRIVER"}
        end)
        ccb.runtime.handler("dialogue_option", function(payload)
            if payload.current_topic == "TALK_IMGUI_DRIVER" then
                assert(payload.selected_topic == "TALK_IMGUI_NEXT")
            else
                assert(payload.current_topic == "TALK_IMGUI_NEXT")
                assert(payload.selected_topic == "TALK_DONE")
            end
            assert(payload.by_radio)
            table.insert(trace, "option")
            return {result = payload.selected_topic}
        end)
        ccb.runtime.handler("dialogue_end", function(payload)
            assert(payload.last_topic == "TALK_IMGUI_NEXT" and payload.by_radio)
            table.insert(trace, "end")
        end)
        ccb.runtime.hook("on_dialogue_start", "dialogue_start")
        ccb.runtime.hook("on_dialogue_option", "dialogue_option")
        ccb.runtime.hook("on_dialogue_end", "dialogue_end")
    )", sol::script_pass_on_error );
    if( !registration.valid() ) {
        const sol::error error = registration;
        INFO( error.what() );
    }
    REQUIRE( registration.valid() );
    platform::set_active_runtimes( { owner } );
    owner->world_is_ready = true;
    const std::vector<input_event> confirm = inp_mngr.get_input_for_action(
                "CONFIRM", "DIALOGUE_CHOOSE_RESPONSE" );
    const auto keyboard_confirm = std::find_if( confirm.begin(), confirm.end(),
    []( const input_event & event ) {
        return event.type == input_event_t::keyboard_char ||
               event.type == input_event_t::keyboard_code;
    } );
    REQUIRE( keyboard_confirm != confirm.end() );
    const std::vector<input_event> down = inp_mngr.get_input_for_action(
            "DOWN", "DIALOGUE_CHOOSE_RESPONSE" );
    const auto keyboard_down = std::find_if( down.begin(), down.end(),
    []( const input_event & event ) {
        return event.type == input_event_t::keyboard_char ||
               event.type == input_event_t::keyboard_code;
    } );
    REQUIRE( keyboard_down != down.end() );
    REQUIRE( input_replay::begin_record( replay_path ) );
    input_replay::on_record( *keyboard_down );
    input_replay::on_record( *keyboard_confirm );
    input_replay::on_record( *keyboard_confirm );
    input_replay::finish();
    REQUIRE( input_replay::begin_replay( replay_path ) );
    restore_on_out_of_scope<bool> restore_distraction( uistate.distraction_conversation );
    uistate.distraction_conversation = false;
    npc interlocutor;
    interlocutor.normalize();
    interlocutor.name = "Driver NPC";
    interlocutor.set_attitude( NPCATT_FOLLOW );
    dialogue_imgui_frame_fixture frames;
    CHECK( get_avatar().talk_to( get_talker_for( interlocutor ), true, false, false,
                                 "TALK_IMGUI_BEFORE", "Test intercom" ) ==
           avatar_talk_to_result::completed );
    CHECK( input_replay::replay_remaining() == 0 );
    const sol::protected_function_result lifecycle = lua.safe_script( R"(
        assert(table.concat(trace, ",") ==
            "start,line,responses,speaker_effect,success,select,option," ..
            "next_line,next_responses,next_select,option,end")
        for _, context in pairs(contexts) do
            assert(not context:valid())
        end
    )", sol::script_pass_on_error );
    if( !lifecycle.valid() ) {
        const sol::error error = lifecycle;
        INFO( error.what() );
    }
    CHECK( lifecycle.valid() );
}
#endif
