#include <algorithm>
#include <cstddef>
#include <cstdio>
#include <limits>
#include <memory>
#include <optional>
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

#ifdef TUI
    #include <imtui/imtui-impl-text.h>
    #include <imtui/imtui.h>
#endif

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

class dialogue_help_overlay : public cataimgui::window
{
    public:
        dialogue_help_overlay() : cataimgui::window( "Keybindings overlay",
                    ImGuiWindowFlags_NoMove | ImGuiWindowFlags_NoTitleBar ) {}

    protected:
        cataimgui::bounds get_bounds() override {
            const ImVec2 viewport = ImGui::GetIO().DisplaySize;
            return { viewport.x * 0.85F, 0, viewport.x * 0.15F, viewport.y * 0.08F };
        }

        void draw_controls() override {
            ImGui::TextUnformatted( "Help" );
        }
};

class dialogue_imgui_frame_fixture
{
    public:
        static ImVec2 roomy_viewport() {
#ifdef TUI
            return ImVec2( 120, 40 );
#else
            return ImVec2( 800, 600 );
#endif
        }

        static ImVec2 narrow_viewport() {
#ifdef TUI
            return ImVec2( 32, 48 );
#else
            return ImVec2( 200, 700 );
#endif
        }

        static float layout_tolerance() {
            return ImGui::GetTextLineHeight() * 0.1F;
        }

        static float scroll_tolerance() {
            return ImGui::GetTextLineHeight() * 0.5F;
        }

        dialogue_imgui_frame_fixture() : previous_( ImGui::GetCurrentContext() ),
            context_( ImGui::CreateContext() ) {
            ImGui::SetCurrentContext( context_ );
            ImGuiIO &io = ImGui::GetIO();
            io.IniFilename = nullptr;
            io.LogFilename = nullptr;
            io.DisplaySize = roomy_viewport();
            io.DeltaTime = 1.0F / 60.0F;
            // Match production clients: keyboard input is also delivered to
            // ImGui, while dialogue navigation belongs to input_context.
            io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard;
#ifndef TUI
            io.ConfigFlags |= ImGuiConfigFlags_NavEnableGamepad;
#endif
            io.ConfigInputTrickleEventQueue = false;
            io.ConfigErrorRecoveryEnableAssert = false;
            context_->ErrorCallbackUserData = this;
            context_->ErrorCallback = []( ImGuiContext *, void *data, const char *message ) {
                static_cast<dialogue_imgui_frame_fixture *>( data )->errors_.emplace_back( message );
            };
#ifdef TUI
            // Reuse the production text renderer's cell font and style without
            // initializing a terminal or platform input backend.
            ImTui_ImplText_Init();
#else
            // GUI and mono placeholders match the two font slots used by Tiles.
            io.Fonts->AddFontDefault();
            io.Fonts->AddFontDefault();
            unsigned char *pixels = nullptr;
            int width = 0;
            int height = 0;
            io.Fonts->GetTexDataAsRGBA32( &pixels, &width, &height );
#endif
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

        void assert_no_errors() const {
            std::string diagnostics;
            for( const std::string &error : errors_ ) {
                diagnostics += error + "\n";
            }
            INFO( diagnostics );
            REQUIRE( errors_.empty() );
            CHECK( context_->ErrorCountCurrentFrame == 0 );
        }

        void frame( dialogue_imgui_impl &window, cataimgui::window *overlay = nullptr ) const {
            ImGui::NewFrame();
            window.draw();
            if( overlay ) {
                overlay->draw();
            }
            ImGui::Render();
            assert_no_errors();
        }

        void settle( dialogue_imgui_impl &window, cataimgui::window *overlay = nullptr ) const {
            frame( window, overlay );
            frame( window, overlay );
            frame( window, overlay );
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
#ifdef TUI
                // The inherited ImTui ButtonEx and RenderFrame patches shift
                // the painted quad while ButtonBehavior keeps the original
                // hit rectangle. Undo those paint offsets for layout and
                // click assertions; the renderer itself remains unchanged.
                rect.Min.x -= 1.0F;
                rect.Max.x -= 0.4F;
                rect.Max.y += 0.1F;
#endif
                result.push_back( rect );
                i += 3;
            }
            return result;
        }

        std::vector<ImRect> buttons() const {
            return buttons( child( "##DIALOGUE_RESPONSES" ) );
        }

        void click( dialogue_imgui_impl &window, const ImVec2 &position,
                    cataimgui::window *overlay = nullptr ) const {
            ImGuiIO &io = ImGui::GetIO();
            io.AddMousePosEvent( position.x, position.y );
            frame( window, overlay );
            io.AddMouseButtonEvent( 0, true );
            frame( window, overlay );
            io.AddMouseButtonEvent( 0, false );
            frame( window, overlay );
        }

    private:
        ImGuiContext *previous_;
        ImGuiContext *context_;
        std::vector<std::string> errors_;
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

TEST_CASE( "dialogue_imgui_keyboard_navigation_does_not_activate_mouse_controls",
           "[dialogue][imgui][input][mouse][npc]" )
{
    clear_avatar();
    npc interlocutor;
    interlocutor.normalize();
    interlocutor.name = "Keyboard NPC";
    dialogue_imgui_frame_fixture frames;
    dialogue conversation( get_talker_for( get_avatar() ), get_talker_for( interlocutor ) );
    dialogue_imgui_impl window( &conversation );
    window.set_responses( { { c_white, "a", "First response" },
        { c_white, "b", "Second response" } } );
    frames.settle( window );

    SECTION( "response child after a real mouse selection" ) {
        const std::vector<ImRect> buttons = frames.buttons();
        REQUIRE( buttons.size() == 2 );
        frames.click( window, buttons[1].GetCenter() );
        REQUIRE( window.user_clicked_response_button );
        REQUIRE( window.sel_response == 1 );
        window.user_clicked_response_button = false;
    }
    SECTION( "sidebar child after a real mouse action" ) {
        ImGuiWindow *sidebar = frames.child( "##DIALOGUE_SIDEBAR" );
        REQUIRE( sidebar );
        ImGui::SetScrollY( sidebar, sidebar->ScrollMax.y );
        frames.settle( window );
        const std::vector<ImRect> buttons = frames.buttons( sidebar );
        REQUIRE_FALSE( buttons.empty() );
        frames.click( window, buttons.back().GetCenter() );
        REQUIRE( window.take_special_action() == "YELL" );
    }
    const int selected = window.sel_response;
    ImGuiIO &io = ImGui::GetIO();
    // Apply an actual move request on one frame and Enter on the next.  Hiding
    // the nav cursor during drawing is too late to prevent NewFrame activation.
    io.AddKeyEvent( ImGuiKey_UpArrow, true );
    frames.frame( window );
    io.AddKeyEvent( ImGuiKey_UpArrow, false );
    io.AddKeyEvent( ImGuiKey_Enter, true );
    frames.frame( window );
    io.AddKeyEvent( ImGuiKey_Enter, false );
    frames.frame( window );
    CHECK_FALSE( window.user_clicked_response_button );
    CHECK( window.sel_response == selected );
    CHECK( window.take_special_action().empty() );
}

TEST_CASE( "dialogue_imgui_response_rows_finish_without_layout_errors",
           "[dialogue][imgui][layout]" )
{
    dialogue_imgui_frame_fixture frames;
    dialogue conversation = topic_conversation();
    dialogue_imgui_impl window( &conversation, false, true );
    SECTION( "a single short final response" ) {
        window.set_responses( { { c_white, "a", "Short response" } } );
    }
    SECTION( "explicit newlines and Chinese text" ) {
        window.set_responses( { { c_white, "a", "First line\n第二行中文回应\nLast line" } } );
    }
    SECTION( "a prefix above a very narrow response" ) {
        const ImVec2 narrow = frames.narrow_viewport();
        ImGui::GetIO().DisplaySize = ImVec2( narrow.x * 0.3F, narrow.y );
        window.set_responses( { { c_white, "a", "Narrow response" } } );
    }
    frames.settle( window );
    REQUIRE_FALSE( frames.buttons().empty() );
}

TEST_CASE( "dialogue_imgui_overlay_blocks_lower_responses_sidebar_and_compact_switches",
           "[dialogue][imgui][input][mouse][npc][layout]" )
{
    clear_avatar();
    npc interlocutor;
    interlocutor.normalize();
    interlocutor.name = "Overlay NPC";
    dialogue_imgui_frame_fixture frames;
    dialogue conversation( get_talker_for( get_avatar() ), get_talker_for( interlocutor ) );
    dialogue_imgui_impl window( &conversation );
    window.set_responses( { { c_white, "a", "First response" },
        { c_white, "b", "Second response" } } );
    frames.settle( window );
    ImGuiWindow *sidebar = frames.child( "##DIALOGUE_SIDEBAR" );
    REQUIRE( sidebar );
    ImGui::SetScrollY( sidebar, sidebar->ScrollMax.y );
    frames.settle( window );
    std::vector<ImRect> response_buttons = frames.buttons();
    std::vector<ImRect> action_buttons = frames.buttons( sidebar );
    REQUIRE( response_buttons.size() == 2 );
    REQUIRE_FALSE( action_buttons.empty() );
    const ImVec2 response_click = response_buttons.back().GetCenter();
    const ImVec2 yell_click = action_buttons.back().GetCenter();
    {
        dialogue_help_overlay overlay;
        frames.settle( window, &overlay );
        frames.click( window, response_click, &overlay );
        CHECK_FALSE( window.user_clicked_response_button );
        CHECK( window.sel_response == 0 );
        frames.click( window, yell_click, &overlay );
        CHECK( window.take_special_action().empty() );
    }
    frames.settle( window );
    frames.click( window, response_click );
    CHECK( window.user_clicked_response_button );
    CHECK( window.sel_response == 1 );
    frames.click( window, yell_click );
    CHECK( window.take_special_action() == "YELL" );

    ImGui::GetIO().DisplaySize = frames.narrow_viewport();
    frames.settle( window );
    ImGuiWindow *responses = frames.child( "##DIALOGUE_RESPONSES" );
    REQUIRE( responses );
    const ImGuiWindow *parent = responses->ParentWindow;
    std::vector<ImRect> switches = frames.buttons( parent );
    REQUIRE( switches.size() == 1 );
    const ImVec2 info_click = switches.front().GetCenter();
    {
        dialogue_help_overlay overlay;
        frames.settle( window, &overlay );
        frames.click( window, info_click, &overlay );
        CHECK( responses->Active );
        CHECK_FALSE( sidebar->Active );
    }
    frames.settle( window );
    frames.click( window, info_click );
    frames.settle( window );
    CHECK( sidebar->Active );
    CHECK_FALSE( responses->Active );
    switches = frames.buttons( parent );
    REQUIRE( switches.size() == 1 );
    const ImVec2 back_click = switches.front().GetCenter();
    {
        dialogue_help_overlay overlay;
        frames.settle( window, &overlay );
        frames.click( window, back_click, &overlay );
        CHECK( sidebar->Active );
        CHECK_FALSE( responses->Active );
    }
    frames.settle( window );
    frames.click( window, back_click );
    frames.settle( window );
    CHECK( responses->Active );
    CHECK_FALSE( sidebar->Active );
}

TEST_CASE( "dialogue_imgui_sidebar_expands_names_and_strips_narration_markers",
           "[dialogue][imgui][npc][text]" )
{
    clear_avatar();
    npc interlocutor;
    interlocutor.normalize();
    interlocutor.name = "Sidebar NPC";
    dialogue conversation( get_talker_for( get_avatar() ), get_talker_for( interlocutor ) );
    CHECK( dialogue_sidebar_text( conversation, "&<npc_name> is here." ) == "Sidebar NPC is here." );
    CHECK( dialogue_sidebar_text( conversation, "*<color_red><npc_name></color>" ) ==
           "<color_red>Sidebar NPC</color>" );
    for( const std::string &raw : {
             conversation.actor( true )->evaluation_by( *conversation.actor( false ) ),
             conversation.actor( true )->view_personality_traits()
         } ) {
        const std::string rendered = dialogue_sidebar_text( conversation, raw );
        CHECK( rendered.find( "<npc_name>" ) == std::string::npos );
        CHECK( ( rendered.empty() || ( rendered.front() != '&' && rendered.front() != '*' ) ) );
    }
    dialogue generic = topic_conversation();
    CHECK( dialogue_sidebar_text( generic, "*Detached participant" ) == "Detached participant" );
    CHECK( dialogue_sidebar_text( generic, "&<npc_name>" ).find( "<npc_name>" ) == std::string::npos );
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
    // GetContentRegionAvail sizes widgets against ContentRegionRect.  The
    // renderer's InnerClipRect is floored to integer pixels/cells, so a normal
    // full-width button can have a fractional right edge beyond that clip.
    CHECK( buttons[0].Max.x <= responses->ContentRegionRect.Max.x + frames.layout_tolerance() );
    ImRect visible_button = buttons[0];
    visible_button.ClipWith( responses->InnerClipRect );
    const float line_height = ImGui::GetTextLineHeightWithSpacing();
    REQUIRE( visible_button.GetHeight() > line_height );
    const float lower_visible_line = visible_button.Max.y - line_height * 0.25F;
    REQUIRE( lower_visible_line > buttons[0].Min.y + line_height );
    frames.click( window, ImVec2( visible_button.GetCenter().x, lower_visible_line ) );
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
    CHECK( history->Scroll.y >= history->ScrollMax.y - frames.scroll_tolerance() );
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
    ImGui::GetIO().DisplaySize = frames.narrow_viewport();
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
    CHECK( narrow_responses->Pos.x + narrow_responses->Size.x <=
           ImGui::GetIO().DisplaySize.x + frames.layout_tolerance() );
    CHECK( narrow_responses->Pos.y + narrow_responses->Size.y <=
           ImGui::GetIO().DisplaySize.y + frames.layout_tolerance() );

    window.set_hidden( true );
    frames.settle( window );
    CHECK_FALSE( narrow_responses->Active );
    CHECK( narrow_responses->ParentWindow->Hidden );
    window.set_hidden( false );
    ImGui::GetIO().DisplaySize = frames.roomy_viewport();
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

    ImGui::GetIO().DisplaySize = frames.narrow_viewport();
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
    CHECK( sidebar->Pos.x + sidebar->Size.x <=
           ImGui::GetIO().DisplaySize.x + frames.layout_tolerance() );
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
    restore_on_out_of_scope<bool> restore_debug( debug_mode );
    debug_mode = false;
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
                    text = "Disabled exit response",
                    condition = false,
                    show_always = true,
                    topic = "TALK_DONE",
                    on_select = function()
                        error("A disabled exit response was selected")
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
    const auto keyboard_binding = []( const std::string & action,
    const std::string &context = "DIALOGUE_CHOOSE_RESPONSE" ) {
        const std::vector<input_event> bindings = inp_mngr.get_input_for_action(
                    action, context );
        const auto found = std::find_if( bindings.begin(), bindings.end(),
        []( const input_event & event ) {
            return event.type == input_event_t::keyboard_char ||
                   event.type == input_event_t::keyboard_code;
        } );
        REQUIRE( found != bindings.end() );
        return *found;
    };
    const input_event confirm = keyboard_binding( "CONFIRM" );
    std::vector<input_event> events;
    SECTION( "keyboard movement and confirmation reset the next topic selection" ) {
        events = { keyboard_binding( "DOWN" ), confirm, confirm };
    }
    SECTION( "quit skips the disabled first exit and retains the Lua callbacks" ) {
        events = { keyboard_binding( "QUIT" ), confirm };
    }
    SECTION( "help closes and returns to the current dialogue" ) {
        events = { keyboard_binding( "HELP_KEYBINDINGS" ),
                   keyboard_binding( "QUIT", "HELP_KEYBINDINGS" ),
                   keyboard_binding( "QUIT" ), confirm
                 };
    }
    // Headless input exhaustion exits the test process.  Leave a recovery
    // sequence queued so a rejected selection produces assertions instead.
    const std::vector<input_event> recovery = { keyboard_binding( "DOWN" ), confirm, confirm };
    REQUIRE( input_replay::begin_record( replay_path ) );
    for( const input_event &event : events ) {
        input_replay::on_record( event );
    }
    for( const input_event &event : recovery ) {
        input_replay::on_record( event );
    }
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
    CHECK( input_replay::replay_remaining() == static_cast<int>( recovery.size() ) );
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
    frames.assert_no_errors();
}
#endif

TEST_CASE( "dialogue_imgui_reopened_instance_shows_new_content_on_first_frame",
           "[dialogue][imgui][scroll]" )
{
    dialogue_imgui_frame_fixture frames;
    dialogue conversation = topic_conversation();
    std::optional<dialogue_imgui_impl> window;
    window.emplace( &conversation, false, true );
    const void *const original_address = &*window;
    std::vector<talk_data> responses;
    for( int i = 0; i < 80; ++i ) {
        responses.push_back( { c_white, "a", "Old response " + std::to_string( i ) } );
    }
    window->set_responses( responses );
    window->sel_response = 79;
    for( int i = 0; i < 100; ++i ) {
        window->add_to_history( "Old history line " + std::to_string( i ) );
    }
    frames.settle( *window );
    const ImGuiWindow *const old_history = frames.child( "##DIALOGUE_HISTORY" );
    const ImGuiWindow *const old_responses = frames.child( "##DIALOGUE_RESPONSES" );
    REQUIRE( old_history );
    REQUIRE( old_responses );
    REQUIRE( old_history->Scroll.y > 0 );
    REQUIRE( old_responses->Scroll.y > 0 );

    const auto visible_history_glyphs = []( const ImGuiWindow * child ) {
        int count = 0;
#ifdef TUI
        // ImTui intentionally encodes glyphs in zero-height quads.  Decode the
        // real history draw list with the production text renderer and inspect
        // its clipped cells instead of imposing pixel-font geometry.
        ImTui::ImplImtui_Data terminal;
        ImGuiIO &io = ImGui::GetIO();
        restore_on_out_of_scope<void *> restore_backend( io.BackendPlatformUserData );
        io.BackendPlatformUserData = &terminal;
        ImDrawData draw_data = *ImGui::GetDrawData();
        draw_data.CmdLists.resize( 1 );
        draw_data.CmdLists[0] = child->DrawList;
        draw_data.CmdListsCount = 1;
        draw_data.TotalIdxCount = child->DrawList->IdxBuffer.Size;
        draw_data.TotalVtxCount = child->DrawList->VtxBuffer.Size;
        ImTui_ImplText_RenderDrawData( &draw_data );
        std::string visible_text;
        for( int y = 0; y < terminal.Screen.ny; ++y ) {
            for( int x = 0; x < terminal.Screen.nx; ++x ) {
                if( !child->InnerClipRect.Contains( ImVec2( x, y ) ) ) {
                    continue;
                }
                const ImTui::TCell &cell = terminal.Screen.data[y * terminal.Screen.nx + x];
                if( cell.ch > ' ' && cell.chwidth > 0 ) {
                    ++count;
                }
                // Spaces have no glyph quad, so an unpainted cell is a blank.
                visible_text.push_back( cell.ch >= ' ' && cell.ch < 128 ?
                                        static_cast<char>( cell.ch ) : ' ' );
            }
            visible_text.push_back( '\n' );
        }
        INFO( visible_text );
        CHECK( visible_text.find( "Fresh greeting must be visible" ) != std::string::npos );
#else
        const ImVec2 white = ImGui::GetIO().Fonts->TexUvWhitePixel;
        const ImVector<ImDrawVert> &v = child->DrawList->VtxBuffer;
        for( int i = 0; i + 3 < v.Size; i += 4 ) {
            bool textured = false;
            ImRect bounds( v[i].pos, v[i].pos );
            for( int j = 0; j < 4; ++j ) {
                textured = textured || v[i + j].uv.x != white.x || v[i + j].uv.y != white.y;
                bounds.Add( v[i + j].pos );
            }
            if( textured && bounds.GetWidth() > 0 && bounds.GetHeight() > 0 &&
                bounds.Overlaps( child->InnerClipRect ) ) {
                ++count;
            }
        }
#endif
        return count;
    };
    const auto assert_visible_content = [&]() {
        const ImGuiWindow *const history = frames.child( "##DIALOGUE_HISTORY" );
        const ImGuiWindow *const response = frames.child( "##DIALOGUE_RESPONSES" );
        REQUIRE( history );
        REQUIRE( response );
        const int glyphs = visible_history_glyphs( history );
        const std::vector<ImRect> buttons = frames.buttons( response );
        int visible_buttons = 0;
        for( const ImRect &button : buttons ) {
            if( button.Overlaps( response->InnerClipRect ) ) {
                ++visible_buttons;
            }
        }
        CHECK( history->Scroll.y <= frames.scroll_tolerance() );
        CHECK( response->Scroll.y <= frames.scroll_tolerance() );
        CHECK( glyphs > 0 );
        CHECK( visible_buttons == 1 );
    };

    window.reset();
    window.emplace( &conversation, false, true );
    REQUIRE( static_cast<const void *>( &*window ) == original_address );
    window->add_to_history( "Fresh greeting must be visible" );
    window->set_responses( { { c_white, "a", "First fresh response" } } );
    frames.frame( *window );
    assert_visible_content();
    frames.frame( *window );
    assert_visible_content();
    frames.frame( *window );
    assert_visible_content();
}
