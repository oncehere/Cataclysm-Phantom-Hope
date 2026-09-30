#pragma once
#ifndef CATA_SRC_DIALOGUE_IMGUI_H
#define CATA_SRC_DIALOGUE_IMGUI_H

#include <string>
#include <vector>

#include "cata_imgui.h"
#include "color.h"
#include "dialogue.h"

/** The dialogue view.  The caller owns the topic stack and Lua session. */
class dialogue_imgui_impl : public cataimgui::window
{
    public:
        explicit dialogue_imgui_impl( dialogue *conversation, bool is_computer = false,
                                      bool is_not_conversation = false, const std::string &remote_name = {} );
        void draw() override;
        void add_to_history( const std::string &text );
        void add_to_history( const std::string &text, const std::string &speaker_name,
                             nc_color speaker_color );
        void add_to_history( const std::string &text, nc_color color );
        void set_responses( const std::vector<talk_data> &responses,
                            const std::vector<bool> &selectable = {} );
        void set_responses_debug( const std::vector<std::string> &responses );
        void set_hidden( bool hidden );
        std::string take_special_action();

        std::string debug_topic_name;
        bool is_computer = false;
        bool is_not_conversation = false;
        bool is_remote = false;
        std::string remote_name;
        bool show_dynamic_line_conditionals = true;
        bool show_dynamic_line_effects = true;
        bool show_response_conditionals = true;
        bool show_response_effects = true;
        bool show_all_responses = false;
        int sel_response = 0;
        cataimgui::scroll scroll_to = cataimgui::scroll::none;
        bool user_clicked_response_button = false;

    private:
        struct history_message {
            history_message( nc_color c, const std::string &t ) : color( c ), text( t ) {}
            nc_color color;
            std::string text;
        };

        dialogue *conversation;
        std::vector<history_message> history;
        std::vector<talk_data> response_list;
        std::vector<bool> response_selectable;
        std::vector<std::string> responses_debug;
        std::string special_action;
        int previous_response = -1;
        bool compact_sidebar = false;
        float viewport_width = -1.0F;
        float viewport_height = -1.0F;

        nc_color default_color() const;
        bool has_physical_information() const;
        std::string display_name() const;
        void draw_history() const;
        void draw_responses();
        void draw_sidebar_information();
        void draw_dialogue_sidebar( float width, float height );
        void draw_dialogue_history( float width, float height );
        void draw_dialogue_responses( float width, float height );
        void special_action_button( const std::string &action, const std::string &label );

    protected:
        cataimgui::bounds get_bounds() override;
        void draw_controls() override;
};

#endif // CATA_SRC_DIALOGUE_IMGUI_H
