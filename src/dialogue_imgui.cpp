#include "dialogue_imgui.h"

#include <algorithm>
#include <array>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <imgui/imgui.h>
#include <imgui/imgui_internal.h>

#include "cata_imgui.h"
#include "cata_scope_helpers.h"
#include "debug.h"
#include "dialogue.h"
#include "npc.h"
#include "output.h"
#include "panels.h"
#include "string_formatter.h"
#include "talker.h"
#include "text.h"
#include "translations.h"
#include "ui_profile.h"

namespace
{
void dialogue_paragraph( const nc_color color, const std::string_view text )
{
    float wrap_position = 0.0F;
#ifdef TUI
    // ImTui places each glyph in the following cell; leave that cell inside
    // the actual command clip rectangle rather than losing each row's end.
    wrap_position = ImGui::GetCursorPosX() +
                    std::max( 1.0F, ImGui::GetContentRegionAvail().x - 1.0F );
#endif
    cataimgui::TextColoredParagraphNewline( color, text, std::nullopt, wrap_position );
}
} // namespace

std::string dialogue_sidebar_text( const const_dialogue &conversation, std::string text )
{
    if( conversation.has_actor( false ) && conversation.has_actor( true ) ) {
        parse_tags( text, *conversation.const_actor( false ), *conversation.const_actor( true ),
                    conversation, conversation.cur_item );
    }
    if( !text.empty() && ( text.front() == '&' || text.front() == '*' ) ) {
        text.erase( 0, 1 );
    }
    return text;
}

// Adapted in order from the first-parent net changes of CDDA #88235,
// #88369 and #88498.  Topic progression and Lua ownership stay in npctalk.cpp.
dialogue_imgui_impl::dialogue_imgui_impl( dialogue *conversation, const bool is_computer,
        const bool is_not_conversation, const std::string &remote_name ) :
    cataimgui::window( _( "Dialogue" ), ImGuiWindowFlags_NoMove | ImGuiWindowFlags_NoResize |
                       ImGuiWindowFlags_NoNav |
                       ImGuiWindowFlags_NoScrollbar | ImGuiWindowFlags_NoTitleBar |
                       ImGuiWindowFlags_NoScrollWithMouse | ImGuiWindowFlags_NoFocusOnAppearing ),
    is_computer( is_computer ), is_not_conversation( is_not_conversation ),
    is_remote( !remote_name.empty() ), remote_name( remote_name ), conversation( conversation )
{
}

void dialogue_imgui_impl::draw()
{
    const ImVec2 viewport = ImGui::GetMainViewport()->WorkSize;
    if( viewport.x != viewport_width || viewport.y != viewport_height ) {
        viewport_width = viewport.x;
        viewport_height = viewport.y;
        mark_resized();
#ifndef TUI
        cataimgui::request_clear();
#endif
    }
    cataimgui::window::draw();
}

cataimgui::bounds dialogue_imgui_impl::get_bounds()
{
    const ImGuiViewport *viewport = ImGui::GetMainViewport();
    const float panel_width = str_width_to_pixels(
                                  panel_manager::get_manager().get_width_right() +
                                  panel_manager::get_manager().get_width_left() );
    // Keep the map panels on roomy displays.  A small terminal needs the
    // whole viewport: its coordinates are cells rather than SDL pixels.
    const float width = viewport->WorkSize.x - panel_width >= str_width_to_pixels( 48 ) ?
                        viewport->WorkSize.x - panel_width : viewport->WorkSize.x;
    return { viewport->WorkPos.x, viewport->WorkPos.y,
             std::max( 1.0F, width ), std::max( 1.0F, viewport->WorkSize.y ) };
}

void dialogue_imgui_impl::set_hidden( const bool hidden )
{
    if( hide_ui != hidden ) {
        hide_ui = hidden;
        mark_resized();
#ifndef TUI
        cataimgui::request_clear();
#endif
    }
}

std::string dialogue_imgui_impl::take_special_action()
{
    std::string result;
    result.swap( special_action );
    return result;
}

bool dialogue_imgui_impl::has_physical_information() const
{
    return !is_computer && !is_not_conversation && !is_remote && conversation &&
           conversation->actor( false ) && conversation->actor( true );
}

std::string dialogue_imgui_impl::display_name() const
{
    if( is_not_conversation ) {
        return {};
    }
    if( !remote_name.empty() ) {
        return remote_name;
    }
    return conversation && conversation->actor( true ) ?
           conversation->actor( true )->disp_name() : std::string();
}

const std::string &dialogue_imgui_impl::sidebar_text( const std::string &text )
{
    const auto found = sidebar_text_cache.find( text );
    if( found != sidebar_text_cache.end() ) {
        return found->second;
    }
    // Resolve snippets once per topic rather than consuming RNG on every frame.
    return sidebar_text_cache.emplace( text, conversation ?
                                       dialogue_sidebar_text( *conversation, text ) : text ).first->second;
}

void dialogue_imgui_impl::draw_controls()
{
    if( hide_ui ) {
        hide_if_hidden();
        return;
    }

    // Help and other UI layers keep drawing this view underneath them.
    // The live adaptor stack also covers direct model frames and NoNav windows.
    ImGui::BeginDisabled( !is_on_top() );
    on_out_of_scope restore_interaction( []() {
        ImGui::EndDisabled();
    } );

    const bool physical_information = has_physical_information();
    if( !physical_information ) {
        if( is_computer ) {
            dialogue_paragraph( default_color(),
                                string_format( _( "Interaction: %s" ), display_name() ) );
        } else if( !is_not_conversation ) {
            dialogue_paragraph( default_color(),
                                string_format( _( "Dialogue: %s" ), display_name() ) );
        }
    }
    if( debug_mode ) {
        const std::array<bool, 5> flags = { show_dynamic_line_conditionals, show_response_conditionals,
                                            show_dynamic_line_effects, show_response_effects, show_all_responses
                                          };
        const std::array<std::string, 5> names = { "DL_COND", "RESP_COND", "DL_EFF", "RESP_EFF", "ALL_RESP" };
        std::string status;
        for( int i = 0; i < static_cast<int>( flags.size() ); ++i ) {
            status += colorize( names[i], flags[i] ? c_yellow : c_brown ) + " ";
        }
        dialogue_paragraph( c_white, status );
    }

    const float gap = std::max( ImGui::GetStyle().ItemSpacing.x,
                                static_cast<float>( str_width_to_pixels( 1 ) ) );
    float available_width = std::max( 1.0F, ImGui::GetContentRegionAvail().x );
    const float minimum_sidebar = str_width_to_pixels( 16 );
    const float minimum_dialogue = str_width_to_pixels( 28 );
    const bool side_by_side = physical_information &&
                              available_width >= minimum_sidebar + minimum_dialogue + gap;
    if( physical_information && !side_by_side ) {
        if( ImGui::Button( compact_sidebar ? _( "Back" ) : _( "Info" ) ) ) {
            compact_sidebar = !compact_sidebar;
        }
    } else {
        compact_sidebar = false;
    }

    available_width = std::max( 1.0F, ImGui::GetContentRegionAvail().x );
    const float available_height = std::max( 2.0F, ImGui::GetContentRegionAvail().y );
    const ImVec2 origin = ImGui::GetCursorPos();
    if( compact_sidebar ) {
        draw_dialogue_sidebar( available_width, available_height );
        return;
    }

    const float sidebar_width = side_by_side ?
                                std::clamp( available_width * 0.3F, minimum_sidebar,
                                            available_width - minimum_dialogue - gap ) : 0.0F;
    if( side_by_side ) {
        draw_dialogue_sidebar( sidebar_width, available_height );
    }
    const float dialogue_width = std::max( 1.0F, available_width - sidebar_width -
                                           ( side_by_side ? gap : 0.0F ) );
    const float vertical_gap = std::max( ImGui::GetStyle().ItemSpacing.y,
                                         static_cast<float>( str_height_to_pixels( 1 ) ) );
    const float history_height = std::max( 1.0F, ( available_height - vertical_gap ) * 0.6F );
    const float response_height = std::max( 1.0F, available_height - history_height - vertical_gap );
    const float dialogue_x = origin.x + sidebar_width + ( side_by_side ? gap : 0.0F );
    ImGui::SetCursorPos( ImVec2( dialogue_x, origin.y ) );
    draw_dialogue_history( dialogue_width, history_height );
    ImGui::SetCursorPos( ImVec2( dialogue_x, origin.y + history_height + vertical_gap ) );
    draw_dialogue_responses( dialogue_width, response_height );
}

void dialogue_imgui_impl::special_action_button( const std::string &action,
        const std::string &label )
{
    ImGui::PushID( action.c_str() );
    if( ImGui::Button( label.c_str() ) && !cataimgui::interaction_suppressed() ) {
        special_action = action;
    }
    ImGui::PopID();
}

void dialogue_imgui_impl::draw_sidebar_information()
{
    if( !has_physical_information() ) {
        return;
    }
    if( conversation->actor( true )->get_npc() &&
        ImGui::GetContentRegionAvail().x >= str_width_to_pixels( 28 ) ) {
        // Original #88235 placeholder portrait, by RenechCDDA.
        const std::string portrait =
            "|--------------------------|\n"
            "|           _____   -Renech|\n"
            "|          /     \\         |\n"
            "|         | 0  0 |         |\n"
            "|          \\ -  /          |\n"
            "|          |\\__/|          |\n"
            "|      ___/------\\___      |\n"
            "|     / _/        \\_ \\     |\n"
            "|    / / |  NPC   | \\ \\    |\n"
            "|   / /  |        |  \\ \\   |\n"
            "|                          |\n"
            "|--------------------------|";
        cataimgui::PushMonoFont();
        dialogue_paragraph( c_white, portrait );
        ImGui::PopFont();
    }
#ifndef TUI
    cataimgui::PushGuiFont1_5x();
#endif
    dialogue_paragraph( default_color(), display_name() );
#ifndef TUI
    cataimgui::PopGuiFont1_5x();
#endif
    ImGui::Separator();
    if( conversation->actor( false )->can_see() ) {
        dialogue_paragraph( c_blue,
                            sidebar_text( conversation->actor( true )->short_description() ) );
    } else {
        std::string blind_description = string_format(
                                            _( "&You're blind and can't look at %s." ), display_name() );
        if( !blind_description.empty() && blind_description.front() == '&' ) {
            blind_description.erase( 0, 1 );
        }
        dialogue_paragraph( c_blue, sidebar_text( blind_description ) );
    }
    ImGui::Separator();
    dialogue_paragraph( c_red,
                        sidebar_text( conversation->actor( true )->evaluation_by( *conversation->actor( false ) ) ) );
    ImGui::Separator();
    dialogue_paragraph( c_pink,
                        sidebar_text( conversation->actor( true )->view_personality_traits() ) );
    ImGui::Separator();
    dialogue_paragraph( c_yellow,
                        sidebar_text( conversation->actor( true )->opinion_text() ) );
    ImGui::Separator();
    // These remain actions as well as sidebar information.  In particular,
    // YELL has a real effect and must not disappear with the old window.
    special_action_button( "LOOK_AT", _( "Look at" ) );
    special_action_button( "SIZE_UP_STATS", _( "Size up stats" ) );
    special_action_button( "ASSESS_PERSONALITY", _( "Assess personality" ) );
    special_action_button( "CHECK_OPINION", _( "Check opinion" ) );
    special_action_button( "YELL", _( "Yell" ) );
}

void dialogue_imgui_impl::draw_dialogue_sidebar( const float width, const float height )
{
    if( !sidebar_scroll_initialized ) {
        ImGui::SetNextWindowScroll( ImVec2( 0, 0 ) );
        sidebar_scroll_initialized = true;
    }
    // Children do not inherit NoNav; input_context owns keyboard and gamepad selection.
    if( ImGui::BeginChild( "##DIALOGUE_SIDEBAR", ImVec2( width, height ), ImGuiChildFlags_Borders,
                           ImGuiWindowFlags_NoNav ) ) {
        draw_sidebar_information();
    }
    ImGui::EndChild();
}

void dialogue_imgui_impl::draw_dialogue_history( const float width, const float height )
{
    // ImGui retains child state when a later dialogue reuses the same address.
    // Reset before the first layout so its new greeting is immediately visible.
    if( !history_scroll_initialized ) {
        ImGui::SetNextWindowScroll( ImVec2( 0, 0 ) );
        history_scroll_initialized = true;
    }
    if( ImGui::BeginChild( "##DIALOGUE_HISTORY", ImVec2( width, height ), ImGuiChildFlags_Borders,
                           ImGuiWindowFlags_NoNav ) ) {
        draw_history();
        cataimgui::set_scroll( scroll_to );
    }
    ImGui::EndChild();
}

void dialogue_imgui_impl::draw_dialogue_responses( const float width, const float height )
{
    if( !response_scroll_initialized ) {
        ImGui::SetNextWindowScroll( ImVec2( 0, 0 ) );
        response_scroll_initialized = true;
    }
    if( ImGui::BeginChild( "##DIALOGUE_RESPONSES", ImVec2( width, height ),
                           ImGuiChildFlags_Borders,
                           ImGuiWindowFlags_NoNav ) ) {
        dialogue_paragraph( default_color(), is_computer ? _( "Your input:" ) :
                            is_not_conversation ? _( "What do you do?" ) : _( "Your response:" ) );
        draw_responses();
    }
    ImGui::EndChild();
}

void dialogue_imgui_impl::add_to_history( const std::string &text, const std::string &speaker_name,
        const nc_color speaker_color )
{
    add_to_history( speaker_name, speaker_color );
    add_to_history( text );
}

void dialogue_imgui_impl::add_to_history( const std::string &text )
{
    add_to_history( text, default_color() );
}

void dialogue_imgui_impl::add_to_history( const std::string &text, const nc_color color )
{
    history.emplace_back( color, text );
    scroll_to = cataimgui::scroll::end;
}

void dialogue_imgui_impl::draw_history() const
{
    for( const history_message &msg : history ) {
        dialogue_paragraph( msg.color, msg.text );
    }
}

nc_color dialogue_imgui_impl::default_color() const
{
    return is_computer ? c_green : c_white;
}

void dialogue_imgui_impl::set_responses( const std::vector<talk_data> &responses,
        const std::vector<bool> &selectable )
{
    response_list = responses;
    sidebar_text_cache.clear();
    response_selectable = selectable;
    previous_response = -1;
    user_clicked_response_button = false;
    sel_response = response_list.empty() ? 0 :
                   std::clamp( sel_response, 0, static_cast<int>( response_list.size() ) - 1 );
}

void dialogue_imgui_impl::draw_responses()
{
    if( debug_mode ) {
        dialogue_paragraph( c_white, "talk_topic: " + debug_topic_name );
    }
    if( !response_list.empty() ) {
        sel_response = std::clamp( sel_response, 0, static_cast<int>( response_list.size() ) - 1 );
    }
    const cata::ui::profile profile = cata::ui::current_profile();
    const bool suppress_click = cataimgui::handle_vertical_swipe(
                                    profile.allow_swipe, ImGui::GetStyle().FramePadding.x );
    const cataimgui::scoped_interaction_suppression suppress_interactions( suppress_click );
    ImGui::SetNavCursorVisible( false );
    for( int i = 0; i < static_cast<int>( response_list.size() ); ++i ) {
        const talk_data &talk = response_list[i];
        const bool enabled = response_selectable.empty() ||
                             ( i < static_cast<int>( response_selectable.size() ) && response_selectable[i] );
        ImGui::PushID( i );
        if( !enabled ) {
            ImGui::BeginDisabled();
        }
        const ImVec2 row_origin = ImGui::GetCursorPos();
        const float row_width = std::max( 1.0F, ImGui::GetContentRegionAvail().x );
        const float prefix_width = ImGui::CalcTextSize( ">>>>>" ).x +
                                   ImGui::CalcTextSize( talk.hotkey_desc.c_str() ).x +
                                   ImGui::GetStyle().ItemSpacing.x * 2;
        if( row_width > prefix_width + str_width_to_pixels( 6 ) ) {
            cataimgui::draw_colored_text( sel_response == i ? ">>>>>" : "     ", c_yellow );
            ImGui::SameLine();
            cataimgui::draw_colored_text( formatted_hotkey( talk.hotkey_desc, talk.color ) );
            ImGui::SameLine();
        } else {
            // A narrow response still needs its keyboard hint and selection
            // marker.  Put the prefix above the full-width text button.
            cataimgui::draw_colored_text( colorize( sel_response == i ? ">>>>>" : "     ",
                                                    c_yellow ) + " " + formatted_hotkey( talk.hotkey_desc, talk.color ),
                                          row_width );
        }
        const ImVec2 button_origin = ImGui::GetCursorPos();
        const float button_width = std::max( 1.0F, ImGui::GetContentRegionAvail().x );
        const ImVec2 padding( std::min( ImGui::GetStyle().FramePadding.x, button_width * 0.25F ),
                              ImGui::GetStyle().FramePadding.y );
        ImGui::PushStyleVar( ImGuiStyleVar_FramePadding, padding );
        const float text_width = std::max( 1.0F, button_width - padding.x * 2 );
        // Measure the same colored paragraph that we draw.  A raw text-width
        // division misses CJK wrapping, explicit newlines and color segments.
        // Split drawing channels so the button background stays behind its label.
        ImDrawListSplitter splitter;
        splitter.Split( ImGui::GetWindowDrawList(), 2 );
        splitter.SetCurrentChannel( ImGui::GetWindowDrawList(), 1 );
        ImGui::SetCursorPos( ImVec2( button_origin.x + padding.x, button_origin.y + padding.y ) );
        ImGui::BeginGroup();
        cataimgui::TextColoredParagraph( c_white, talk.text, std::nullopt,
                                         ImGui::GetCursorPosX() + text_width );
        ImGui::EndGroup();
        const float measurement_width = std::max( text_width, ImGui::CalcTextSize( " " ).x );
        const float text_height = std::max( ImGui::GetItemRectSize().y,
                                            static_cast<float>( cataimgui::get_string_height( talk.text, measurement_width ) ) );
        const float button_height = std::max( text_height + padding.y * 2,
                                              profile.is_touch() ? profile.minimum_target : ImGui::GetFrameHeight() );
        splitter.SetCurrentChannel( ImGui::GetWindowDrawList(), 0 );
        ImGui::SetCursorPos( button_origin );
        const bool colored_button = talk.color != c_white;
        if( colored_button ) {
            ImGui::PushStyleColor( ImGuiCol_Button, talk.color );
        }
        if( ImGui::Button( "##response", ImVec2( button_width, button_height ) ) &&
            !cataimgui::interaction_suppressed() ) {
            sel_response = i;
            user_clicked_response_button = true;
        }
        if( sel_response == i && previous_response != sel_response ) {
            ImGui::SetScrollHereY( 0.5F );
        }
        if( colored_button ) {
            ImGui::PopStyleColor();
        }
        splitter.Merge( ImGui::GetWindowDrawList() );
        ImGui::PopStyleVar();
        ImGui::SetCursorPos( ImVec2( row_origin.x, button_origin.y + button_height ) );
        // Submit the row end to layout instead of extending bounds with a cursor
        // move alone. ItemSize supplies the following row spacing.
        ImGui::Dummy( ImVec2( 0.0F, 0.0F ) );
        if( !enabled ) {
            ImGui::EndDisabled();
        }
        ImGui::PopID();
    }
    previous_response = sel_response;
    if( debug_mode ) {
        for( const std::string &info : responses_debug ) {
            dialogue_paragraph( c_yellow, info );
        }
    }
}

void dialogue_imgui_impl::set_responses_debug( const std::vector<std::string> &responses )
{
    responses_debug = responses;
}
