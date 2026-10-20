#include "actor_control_ui.h"

#include <algorithm>
#include <filesystem>
#include <optional>
#include <sstream>
#include <string>
#include <vector>

#include "actor_control.h"
#include "actor_control_runtime.h"
#include "avatar.h"
#include "debug.h"
#include "cata_imgui.h"
#include "catacharset.h"
#include "flexbuffer_json.h"
#include "game.h"
#include "imgui/imgui_stdlib.h"
#include "input_popup.h"
#include "json_loader.h"
#include "map.h"
#include "npc.h"
#include "output.h"
#include "string_input_popup.h"
#include "translations.h"
#include "uilist.h"
#include "ui_manager.h"

namespace cata::actor_control
{
namespace
{
std::string session_api_key;

class profile_text_popup : public input_popup
{
    public:
        profile_text_popup( const std::string &title, const std::string &initial,
                            bool secret = false, bool multiline = false ) :
            input_popup( 80, title ), text( initial ), secret( secret ), multiline( multiline ) {}
        ~profile_text_popup() override {
            if( secret ) {
                std::fill( text.begin(), text.end(), '\0' );
            }
        }
        std::optional<std::string> query() {
            while( get_is_open() ) {
                ui_manager::redraw_invalidated();
                const std::string action = ctxt.handle_input();
                if( action == "TEXT.CONFIRM" ) {
                    return text;
                }
                if( action == "TEXT.QUIT" ) {
                    break;
                }
                if( action == "TEXT.CLEAR" ) {
                    text.clear();
                }
            }
            return std::nullopt;
        }
    protected:
        void draw_input_control() override {
            if( multiline ) {
                ImGui::InputTextMultiline( "##companion_profile_text", &text, ImVec2( -1, 240 ) );
            } else {
                ImGui::InputText( "##companion_profile_text", &text,
                                  secret ? ImGuiInputTextFlags_Password : ImGuiInputTextFlags_None );
            }
        }
    private:
        std::string text;
        bool secret;
        bool multiline;
};

std::string joined( const std::vector<std::string> &values )
{
    std::string text;
    for( const std::string &value : values ) {
        text += ( text.empty() ? "" : "," ) + value;
    }
    return text;
}

std::vector<std::string> separated( const std::string &text )
{
    std::vector<std::string> result;
    std::istringstream input( text );
    std::string value;
    while( std::getline( input, value, ',' ) ) {
        const auto first = value.find_first_not_of( " \t\r\n" );
        if( first == std::string::npos ) {
            continue;
        }
        value = value.substr( first, value.find_last_not_of( " \t\r\n" ) - first + 1 );
        if( std::find( result.begin(), result.end(), value ) == result.end() ) {
            result.push_back( value );
        }
    }
    return result;
}

void configure_runtime()
{
    const JsonObject current = json_loader::from_string( status() ).get_object();
    current.allow_omitted_members();
    runtime_preferences preferences;
    std::string error;
    if( !read_runtime_preferences( current.get_string( "profile_id" ),
                                   current.get_int( "actor_id" ), preferences, error ) ) {
        popup( "%s", _( "The bundled companion runtime or profile is unavailable." ) );
        return;
    }
    while( true ) {
        uilist menu;
        menu.title = _( "AI companion configuration" );
        menu.text = _( "Set the API base URL and model, enter a session key, then save. "
                       "Nothing contacts the model until you choose Start AI companion." );
        menu.desc_enabled = true;
        menu.addentry( 0, true, 'e', _( "Model endpoint: %s" ), preferences.endpoint );
        menu.addentry( 1, true, 'm', _( "Model: %s" ), preferences.model );
        menu.addentry( 2, true, 'k', session_api_key.empty() ? _( "Set API key for this game session" ) :
                       _( "Replace API key for this game session" ) );
        menu.addentry( 3, true, 'b', _( "Edit character background" ) );
        menu.addentry_desc( 4, true, 'd', _( "Allowed daily duties" ),
                            _( "Extra work the companion may choose without a player request. "
                               "Basic following and guarding remain available. Start with no extra duties." ) );
        menu.addentry_desc( 5, true, 'i', string_format( _( "Allowed item IDs: %s" ),
                            preferences.item_types.empty() ? _( "None" ) : joined( preferences.item_types ) ),
                            _( "Advanced: comma-separated item IDs for autonomous gathering. "
                               "This grants permission; it does not create items." ) );
        menu.addentry_desc( 6, true, 'r', string_format( _( "Allowed recipe IDs: %s" ),
                            preferences.recipes.empty() ? _( "None" ) : joined( preferences.recipes ) ),
                            _( "Advanced: comma-separated recipe IDs for autonomous crafting. "
                               "The companion still needs the recipe, tools and materials." ) );
        menu.addentry( 7, true, 'a', _( "Daily duty distance: %d" ), preferences.max_distance );
        menu.addentry( 8, true, 's', _( "Save configuration" ) );
        menu.query();
        if( menu.ret < 0 ) {
            return;
        }
        if( menu.ret == 8 ) {
            popup( "%s", save_runtime_preferences( preferences, error ) ?
                   _( "Companion configuration saved. Restart AI to apply provider changes." ) :
                   _( "The companion configuration could not be saved." ) );
            return;
        }
        if( menu.ret == 4 ) {
            const std::vector<std::pair<std::string, std::string>> choices = {
                { "follow", _( "Follow" ) }, { "guard", pgettext( "AI companion task", "Guard" ) },
                { "move", pgettext( "AI companion task", "Travel" ) },
                { "gather", _( "Gather permitted items" ) }, { "craft", _( "Craft permitted recipes" ) }
            };
            while( true ) {
                uilist duties;
                duties.title = _( "Daily duties (item and recipe lists also apply)" );
                for( std::size_t i = 0; i < choices.size(); ++i ) {
                    const bool selected = std::find( preferences.duties.begin(), preferences.duties.end(),
                                                     choices[i].first ) != preferences.duties.end();
                    duties.addentry( static_cast<int>( i ), true, -1, "%s %s", selected ? "[x]" : "[ ]",
                                     choices[i].second );
                }
                duties.query();
                if( duties.ret < 0 ) {
                    break;
                }
                const std::string selected = choices[duties.ret].first;
                const auto found = std::find( preferences.duties.begin(), preferences.duties.end(), selected );
                if( found == preferences.duties.end() ) {
                    preferences.duties.push_back( selected );
                } else {
                    preferences.duties.erase( found );
                }
            }
            continue;
        }
        std::string initial;
        if( menu.ret == 0 ) {
            initial = preferences.endpoint;
        }
        if( menu.ret == 1 ) {
            initial = preferences.model;
        }
        if( menu.ret == 3 ) {
            initial = preferences.background;
        }
        if( menu.ret == 5 ) {
            initial = joined( preferences.item_types );
        }
        if( menu.ret == 6 ) {
            initial = joined( preferences.recipes );
        }
        if( menu.ret == 7 ) {
            initial = std::to_string( preferences.max_distance );
        }
        const std::vector<std::string> titles = {
            _( "API base URL (OpenAI-compatible)" ), _( "Model ID from your provider" ),
            _( "API key (memory only; never saved)" ), _( "Character background" ), "",
            _( "Allowed item IDs, separated by commas" ), _( "Allowed recipe IDs, separated by commas" ),
            _( "Maximum daily duty distance (1-60 tiles)" )
        };
        profile_text_popup editor( titles.at( menu.ret ), initial, menu.ret == 2, menu.ret == 3 );
        const std::optional<std::string> edited = editor.query();
        if( !edited ) {
            continue;
        }
        if( menu.ret == 0 ) {
            preferences.endpoint = *edited;
        }
        if( menu.ret == 1 ) {
            preferences.model = *edited;
        }
        if( menu.ret == 2 ) {
            std::fill( session_api_key.begin(), session_api_key.end(), '\0' );
            session_api_key = *edited;
        }
        if( menu.ret == 3 ) {
            preferences.background = *edited;
        }
        if( menu.ret == 5 ) {
            preferences.item_types = separated( *edited );
        }
        if( menu.ret == 6 ) {
            preferences.recipes = separated( *edited );
        }
        if( menu.ret == 7 ) {
            std::istringstream number( *edited );
            int distance = 0;
            if( number >> distance && number.eof() && distance >= 1 && distance <= 60 ) {
                preferences.max_distance = distance;
            } else {
                popup( "%s", _( "Distance must be an integer from 1 to 60." ) );
            }
        }
    }
}

void withdraw_player_request()
{
    const std::vector<player_requirement> requests = player_requirements();
    uilist menu;
    menu.title = _( "Withdraw one of your requests" );
    for( std::size_t index = 0; index < requests.size(); ++index ) {
        const player_requirement &request = requests[index];
        std::string preview = utf8_truncate( request.text, 60 );
        std::replace( preview.begin(), preview.end(), '\n', ' ' );
        std::replace( preview.begin(), preview.end(), '\t', ' ' );
        menu.addentry( static_cast<int>( index ), !request.withdrawn, -1,
                       request.withdrawn ? _( "Request #%lld (withdrawn by you): %s" ) : _( "Request #%lld: %s" ),
                       static_cast<long long>( request.sequence ), preview );
    }
    if( requests.empty() ) {
        popup( "%s", _( "No recorded player requests are available." ) );
        return;
    }
    menu.query();
    if( menu.ret >= 0 ) {
        std::string error;
        popup( "%s", withdraw_requirement( requests[menu.ret].id, error ) ?
               _( "Your request has been withdrawn. Any current activity will end safely." ) :
               _( "The request could not be withdrawn." ) );
    }
}

std::string progress_kind( const std::string &kind )
{
    if( kind == "follow" ) {
        return pgettext( "AI companion task", "Following" );
    }
    if( kind == "guard" ) {
        return pgettext( "AI companion task", "Guarding" );
    }
    if( kind == "move" ) {
        return _( "Travelling" );
    }
    if( kind == "gather" ) {
        return _( "Gathering" );
    }
    if( kind == "craft" ) {
        return _( "Crafting" );
    }
    return _( "Observed activity" );
}

std::string progress_state( const std::string &phase )
{
    if( phase == "running" ) {
        return _( "In progress" );
    }
    if( phase == "completed" ) {
        return _( "Completed" );
    }
    if( phase == "blocked" ) {
        return _( "Blocked" );
    }
    if( phase == "failed" ) {
        return _( "Failed" );
    }
    if( phase == "cancelled" ) {
        return _( "Cancelled" );
    }
    if( phase == "suspended" || phase == "paused" ) {
        return _( "Paused" );
    }
    if( phase == "queued" ) {
        return _( "Queued" );
    }
    return _( "Observed progress" );
}

std::string conversation_text()
{
    const bool running = managed_runtime_running();
    const JsonObject value = json_loader::from_string( status() ).get_object();
    return player_status_text( value, running );
}

std::string quick_start_text()
{
    return _( "1. Bind a living, recruited companion you can see. The player keeps control of their own character.\n\n"
              "2. Configure AI companion: set your provider's API base URL and model ID, enter the session-only key, then Save configuration. Leave extra daily duties off for a first try.\n\n"
              "3. Choose Start AI companion explicitly. A local connection is not proof that the model service is available.\n\n"
              "4. Speak normally, or use Task examples to draft a message. Try following or guarding first. Watch Status and conversation for replies and progress you have observed.\n\n"
              "The model can be slow. Existing tasks and basic NPC behavior can continue while it waits or is offline; close this menu and advance the game to see actions. Do not repeatedly resend the same request.\n\n"
              "Pause preserves work. Withdraw retracts one of your requests. Cancel all AI work clears tasks. Stop cancels work and safely returns control.\n\n"
              "The key must be entered again after restarting the game. Model spending limits survive reloads and restarts; restarting does not grant a new budget." );
}

std::string player_error_text( const std::string &error )
{
    if( error == "actor_cannot_hear" ) {
        return _( "The companion cannot hear you. Move closer and try again." );
    }
    if( error == "fixed_binding_conflict" ) {
        return _( "This profile is already bound to another companion. Reconnect the original companion." );
    }
    if( error == "multiplayer_proxy_not_supported" ) {
        return _( "A multiplayer partner cannot be bound as an AI companion. Choose a recruited NPC." );
    }
    if( error == "event_backpressure" || error == "invalid_dialogue_text" ) {
        return _( "The message was not recorded. Try a shorter message after pending work has been processed." );
    }
    return _( "The companion is unavailable. Reconnect the bound companion while they are alive, recruited and nearby." );
}

void speak_to_companion( const std::string &initial = "" )
{
    string_input_popup editor;
    editor.title( _( "Speak to the companion" ) )
    .description(
        _( "A request is not a promise. Existing work continues unless you clearly ask to prioritize or change it." ) )
    .text( initial ).width( 80 ).max_length( 4096 );
    const std::string text = editor.query_string();
    if( !editor.canceled() && !text.empty() ) {
        std::string error;
        if( !chat( text, error ) ) {
            popup( "%s", player_error_text( error ) );
        }
    }
}

void task_examples()
{
    const std::vector<std::string> examples = {
        _( "Please stay close and follow me." ),
        _( "Please wait here and keep watch." ),
        _( "Please collect 3 more rocks from the nearby ground into your own inventory." ),
        _( "What are you doing, and do you need anything?" )
    };
    uilist menu;
    menu.title = _( "Task examples" );
    menu.text = _( "Choose a draft, then edit and confirm it. Selecting an example does not send it. "
                   "Gathering means loose ground items; crafting needs a known recipe and real resources." );
    for( std::size_t i = 0; i < examples.size(); ++i ) {
        menu.addentry( static_cast<int>( i ), true, -1, examples[i] );
    }
    menu.query();
    if( menu.ret >= 0 ) {
        speak_to_companion( examples.at( menu.ret ) );
    }
}

} // namespace

bool diagnostics_available( const JsonObject &value )
{
    value.allow_omitted_members();
    return value.has_object( "debug" );
}

std::string player_status_text( const JsonObject &value, bool runtime_running )
{
    value.allow_omitted_members();
    if( !value.get_bool( "enabled", false ) ) {
        return _( "AI companion is not enabled in this world.\nEnable the companion Mod for this world to use this menu." );
    }
    if( !value.has_int( "actor_id" ) ) {
        return _( "No companion is bound.\nNext: Bind a recruited companion you can see, then configure and start AI." );
    }
    const bool connected = value.get_bool( "connected", false );
    std::string text = connected ? _( "AI runtime connected." ) :
                       runtime_running ? _( "Starting the AI runtime; waiting for the local connection." ) :
                       _( "AI runtime disconnected; existing local actions can continue." );
    const std::string state = value.get_string( "state", "unbound" );
    if( state == "off_bubble" ) {
        text += "\n" + std::string( _( "The companion is outside the simulated area." ) );
    } else if( value.get_string( "detach_state", "" ) == "detach_pending" ) {
        text += "\n" + std::string( _( "Waiting for the current activity to finish safely." ) );
    } else if( value.get_string( "detach_state", "" ) == "detached" ) {
        text += "\n" + std::string( _( "AI control has been handed back." ) );
    } else if( state == "paused" ) {
        text += "\n" + std::string( _( "AI work is paused. Resume execution to continue." ) );
    } else if( state == "unsupported_schema" ) {
        text += "\n" + std::string(
                    _( "Saved AI data uses an unsupported format. Use a matching game and companion bundle; the data is preserved." ) );
    } else if( state == "dead" ) {
        text += "\n" + std::string( _( "The bound companion has died. AI cannot resume control." ) );
    } else if( !connected && !runtime_running ) {
        text += "\n" + std::string(
                    _( "Next: Configure and save your provider settings, enter the session key, then choose Start AI companion." ) );
    }
    const std::string planning = value.get_string( "planning_state", "offline" );
    if( planning == "thinking" ) {
        text += "\n" + std::string(
                    _( "Waiting for an AI decision. Existing local actions can continue; advance the game to see them." ) );
    } else if( planning == "pending" ) {
        text += "\n" + std::string( _( "The decision is pending; no model request is running." ) );
    } else if( planning == "suspended" ) {
        text += "\n" + std::string(
                    _( "Model planning has reached its spending limit. Existing local actions can continue." ) );
    } else if( planning == "failed" ) {
        const std::string reason = value.get_string( "planning_reason", "" );
        if( reason == "provider_failed" ) {
            text += "\n" + std::string(
                        _( "The model service request failed. Stop AI and check the saved provider settings and session key." ) );
        } else if( reason == "decision_timeout" ) {
            text += "\n" + std::string(
                        _( "AI planning timed out for this decision. Existing local actions can continue." ) );
        } else if( reason == "invalid_model_response" ) {
            text += "\n" + std::string(
                        _( "The model returned an unusable response. No new work was accepted." ) );
        } else {
            text += "\n" + std::string(
                        _( "AI could not resolve this decision. Review the conversation and provide new information if needed." ) );
        }
    } else if( planning == "candidate_pending" ) {
        text += "\n" + std::string( _( "Waiting for a safe handoff." ) );
    } else if( planning == "idle" ) {
        text += "\n" + std::string( _( "Local actions can continue." ) );
    }
    bool observed_progress = false;
    if( value.has_array( "player_progress" ) ) {
        for( const JsonObject &entry : value.get_array( "player_progress" ) ) {
            entry.allow_omitted_members();
            observed_progress = true;
            const std::string kind = progress_kind( entry.get_string( "task_kind", "" ) );
            const std::string phase = progress_state( entry.get_string( "state", "" ) );
            text += "\n" + ( entry.get_int( "target", 0 ) > 0 ?
                             string_format( _( "Known progress: %s, %d/%d (%s)" ), kind,
                                            entry.get_int( "progress", 0 ), entry.get_int( "target", 0 ), phase ) :
                             string_format( _( "Known progress: %s (%s)" ), kind, phase ) );
        }
    }
    if( !observed_progress ) {
        text += "\n" + std::string( _( "No observed progress yet." ) );
    }
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

void open_menu()
{
    while( true ) {
        pump_incoming();
        uilist menu;
        menu.title = _( "AI companion" );
        menu.text = _( "First use: Bind -> Configure -> Start. Use Quick start (h) for help." );
        // The header participates in uilist sizing. Full conversation and progress
        // remain in the status page instead of an unmeasured drawing callback.
        std::istringstream summary( conversation_text() );
        std::string line;
        for( int i = 0; i < 2 && std::getline( summary, line ); ++i ) {
            menu.text += "\n" + line;
        }
        menu.desc_enabled = true;
        const bool running = managed_runtime_running();
        const JsonObject current_state = json_loader::from_string( status() ).get_object();
        current_state.allow_omitted_members();
        const bool connected = current_state.get_bool( "connected", false );
        const bool attached = has_binding() &&
                              current_state.get_string( "detach_state", "" ) == "attached";
        menu.addentry_desc( 0, enabled(), 'b', _( "Bind or reconnect the fixed companion" ),
                            _( "Choose a visible, recruited NPC. A profile stays bound to the same companion." ) );
        menu.addentry_desc( 8, has_binding() && !running && !connected, 'o', _( "Configure AI companion" ),
                            _( "Save the provider address and model. Enter a key for this game session. Stop AI before editing." ) );
        menu.addentry_desc( 9, has_binding() && !running && !connected, 'a', _( "Start AI companion" ),
                            _( "Explicitly starts the model runtime. Requires saved settings and a session key." ) );
        menu.addentry_desc( 1, attached, 'c', _( "Speak to the companion" ),
                            _( "Talk or request work. While disconnected, messages are recorded for a later response." ) );
        menu.addentry_desc( 12, attached, 'e', _( "Task examples" ),
                            _( "Draft a simple request, edit it, then confirm to send." ) );
        menu.addentry_desc( 2, true, 's', _( "Status and conversation" ),
                            _( "Connection, dialogue and progress you have observed. A local connection does not verify the provider." ) );
        menu.addentry_desc( 10, has_binding(), 'w', _( "Withdraw one of your requests" ),
                            _( "Retract a specific message you sent, without cancelling unrelated work." ) );
        const bool paused = current_state.get_string( "state", "" ) == "paused";
        menu.addentry_desc( paused ? 4 : 3, attached, paused ? 'r' : 'p',
                            paused ? _( "Resume execution" ) : _( "Pause execution" ),
                            _( "Keep existing work and pause or resume its execution. Native emergency reactions remain available." ) );
        menu.addentry_desc( 5, attached, 'x', _( "Cancel all AI work" ),
                            _( "Cancel queued and persistent AI tasks at a safe point. Your earlier messages remain recorded." ) );
        menu.addentry_desc( 6, attached, 'u', _( "Stop AI and safely return control" ),
                            _( "Cancel AI work and return control to ordinary NPC behavior after a safe handoff." ) );
        menu.addentry( 11, true, 'h', _( "Quick start" ) );
        const JsonObject diagnostic = json_loader::from_string( status( true ) ).get_object();
        if( diagnostics_available( diagnostic ) && has_binding() ) {
            menu.addentry( 7, true, 'd', _( "Diagnostic state (debug enabled)" ) );
        }
        menu.selected = !has_binding() ? 0 : running || connected ? 3 : 1;
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
            const JsonObject current = json_loader::from_string( status() ).get_object();
            current.allow_omitted_members();
            const std::string profile = has_binding() ? current.get_string( "profile_id" ) :
                                        "companion-" + std::to_string( candidates.at( selection.ret )->getID().get_value() );
            std::string error;
            if( !bind( *candidates.at( selection.ret ), profile, error ) ) {
                popup( "%s", player_error_text( error ) );
            } else {
                popup( "%s", conversation_text() );
            }
        } else if( menu.ret == 1 ) {
            speak_to_companion();
        } else if( menu.ret == 2 ) {
            popup( "%s", conversation_text() );
        } else if( menu.ret == 7 ) {
            const std::string wire = status( true );
            const JsonObject diagnostic = json_loader::from_string( wire ).get_object();
            if( diagnostics_available( diagnostic ) ) {
                popup( "%s", wire );
            }
        } else if( menu.ret == 3 || menu.ret == 4 ) {
            pause( menu.ret == 3 );
        } else if( menu.ret == 5 ) {
            cancel();
        } else if( menu.ret == 6 ) {
            stop();
            popup( "%s", conversation_text() );
        } else if( menu.ret == 8 ) {
            configure_runtime();
        } else if( menu.ret == 10 ) {
            withdraw_player_request();
        } else if( menu.ret == 11 ) {
            popup( "%s", quick_start_text() );
        } else if( menu.ret == 12 ) {
            task_examples();
        } else if( menu.ret == 9 ) {
            const JsonObject current = json_loader::from_string( status() ).get_object();
            current.allow_omitted_members();
            if( current.get_bool( "connected", false ) ) {
                popup( "%s", conversation_text() );
                continue;
            }
            const int actor_id = current.get_int( "actor_id" );
            const std::string profile = current.get_string( "profile_id" );
            std::string error;
            if( !bundled_runtime_available() ) {
                popup( "%s",
                       _( "The matching companion runtime is missing. Use the complete game bundle; copying only the Mod is not enough." ) );
                continue;
            }
            runtime_preferences preferences;
            std::error_code filesystem_error;
            if( !read_runtime_preferences( profile, actor_id, preferences, error ) ||
                preferences.endpoint.empty() || preferences.model.empty() ||
                !std::filesystem::is_regular_file( runtime_profile_directory( profile ) / "config.json",
                                                   filesystem_error ) ) {
                popup( "%s",
                       _( "Configure AI companion first: enter the API base URL and model ID, then choose Save configuration." ) );
                continue;
            }
            if( session_api_key.empty() ) {
                popup( "%s",
                       _( "No API key has been entered for this game session. Open Configure AI companion and set the session key." ) );
                continue;
            }
            bool rebound = false;
            for( npc &person : g->all_npcs() ) {
                if( person.getID().get_value() == actor_id ) {
                    rebound = bind( person, profile, error );
                    break;
                }
            }
            if( !rebound || !start_managed_runtime( profile, session_api_key, error ) ) {
                popup( "%s", !rebound ? player_error_text( error ) :
                       _( "The AI runtime could not start. Check the complete game bundle and saved provider settings; local NPC behavior remains available." ) );
            }
        }
    }
}
} // namespace cata::actor_control
