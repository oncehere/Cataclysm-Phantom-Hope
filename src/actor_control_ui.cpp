#include "actor_control_ui.h"

#include <string>
#include <chrono>
#include <vector>

#include "actor_control.h"
#include "avatar.h"
#include "debug.h"
#include "cata_imgui.h"
#include "flexbuffer_json.h"
#include "game.h"
#include "json_loader.h"
#include "map.h"
#include "npc.h"
#include "output.h"
#include "string_input_popup.h"
#include "translations.h"
#include "uilist.h"

namespace cata::actor_control
{
namespace
{
std::string conversation_text()
{
    const JsonObject value = json_loader::from_string( status() ).get_object();
    value.allow_omitted_members();
    std::string text = value.get_bool( "connected", false ) ?
                       _( "AI connected" ) : _( "AI disconnected; local behavior remains available" );
    text += "\n" + string_format( _( "Profile: %s" ), value.get_string( "profile_id", "" ) );
    const std::string state = value.get_string( "state", "unbound" );
    if( state == "off_bubble" ) {
        text += "\n" + std::string( _( "The companion is outside the simulated area." ) );
    } else if( value.get_string( "detach_state", "" ) == "detach_pending" ) {
        text += "\n" + std::string( _( "Waiting for the current activity to finish safely." ) );
    } else if( value.get_string( "detach_state", "" ) == "detached" ) {
        text += "\n" + std::string( _( "AI control has been handed back." ) );
    } else if( state == "paused" ) {
        text += "\n" + std::string( _( "The execution queue is paused." ) );
    }
    text += "\n" + string_format( _( "Queued actions: %d" ), value.get_int( "queue_length", 0 ) );
    if( value.has_array( "transcript" ) ) {
        const JsonArray transcript = value.get_array( "transcript" );
        const std::size_t first = transcript.size() > 8 ? transcript.size() - 8 : 0;
        for( std::size_t index = first; index < transcript.size(); ++index ) {
            const JsonObject line = transcript.get_object( index );
            line.allow_omitted_members();
            text += "\n\n" + string_format( "%s: %s", line.get_string( "speaker", "" ),
                                            line.get_string( "text", "" ) );
        }
    }
    return text;
}

class companion_menu_callback : public uilist_callback
{
    public:
        void refresh( uilist * ) override {
            const auto now = std::chrono::steady_clock::now();
            if( now >= next_refresh ) {
                current_text = conversation_text();
                next_refresh = now + std::chrono::milliseconds( 200 );
            }
            // Input polling owns communication. Drawing never executes a turn.
            cataimgui::draw_colored_text( current_text );
        }

    private:
        std::string current_text;
        std::chrono::steady_clock::time_point next_refresh {};
};
} // namespace

void open_menu()
{
    while( true ) {
        pump_incoming();
        uilist menu;
        companion_menu_callback live_conversation;
        menu.callback = &live_conversation;
        menu.title = _( "AI companion" );
        menu.addentry( 0, enabled(), 'b', _( "Bind or reconnect the fixed companion" ) );
        menu.addentry( 1, has_binding(), 'c', _( "Speak to the companion" ) );
        menu.addentry( 2, true, 's', _( "Status and conversation" ) );
        menu.addentry( 3, has_binding(), 'p', _( "Pause execution" ) );
        menu.addentry( 4, has_binding(), 'r', _( "Resume execution" ) );
        menu.addentry( 5, has_binding(), 'x', _( "Cancel the plan" ) );
        menu.addentry( 6, has_binding(), 'u', _( "Stop AI and safely return control" ) );
        menu.addentry( 7, has_binding(), 'd', _( "Diagnostic state (if enabled in configuration)" ) );
        menu.query();
        if( menu.ret < 0 ) {
            return;
        }
        if( menu.ret == 0 ) {
            std::vector<npc *> candidates;
            uilist selection;
            selection.title = _( "Bind which recruited companion?" );
            for( npc &person : g->all_npcs() ) {
                if( person.is_player_ally() && !person.is_dead() &&
                    get_avatar().sees( get_map(), person ) ) {
                    selection.addentry( static_cast<int>( candidates.size() ), true, -1,
                                        person.get_name() );
                    candidates.push_back( &person );
                }
            }
            if( candidates.empty() ) {
                popup( _( "No recruited companion is visible." ) );
                continue;
            }
            selection.query();
            if( selection.ret < 0 ) {
                continue;
            }
            const std::string profile = string_input_popup().title( _( "Profile ID" ) )
                                        .text( "ai_adventurer" ).width( 60 ).max_length( 128 ).query_string();
            if( profile.empty() ) {
                continue;
            }
            std::string error;
            if( !bind( *candidates.at( selection.ret ), profile, error ) ) {
                popup( "%s", error );
            } else {
                popup( "%s", status() );
            }
        } else if( menu.ret == 1 ) {
            const std::string text = string_input_popup().title( _( "Speak to the companion" ) )
                                     .width( 80 ).max_length( 4096 ).query_string();
            if( !text.empty() ) {
                std::string error;
                if( !chat( text, error ) ) {
                    popup( "%s", error );
                }
            }
        } else if( menu.ret == 2 || menu.ret == 7 ) {
            popup( "%s", menu.ret == 7 ? status( true ) : conversation_text() );
        } else if( menu.ret == 3 || menu.ret == 4 ) {
            pause( menu.ret == 3 );
        } else if( menu.ret == 5 ) {
            cancel();
        } else if( menu.ret == 6 ) {
            stop();
            popup( "%s", status() );
        }
    }
}
} // namespace cata::actor_control
