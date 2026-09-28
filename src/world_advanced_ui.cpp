#include "world_advanced_ui.h"

#include <algorithm>
#include <map>
#include <optional>
#include <string>
#include <vector>

#include "input.h"
#include "options.h"
#include "output.h"
#include "string_formatter.h"
#include "string_input_popup.h"
#include "translations.h"
#include "uilist.h"
#include "world_advanced_options.h"

static std::string wrap_rule_description( const std::string &text )
{
    std::string result;
    for( const std::string &line : foldstring( text, std::max( 40, std::min( 80, TERMX - 12 ) ) ) ) {
        if( !result.empty() ) {
            result += '\n';
        }
        result += line;
    }
    return result;
}

std::string world_advanced_value_label( const world_advanced_options *rules,
                                        const std::string &id )
{
    const std::optional<std::string> value = rules ? rules->find( id ) : std::nullopt;
    const world_advanced_definition *definition = find_world_advanced_definition( id );
    if( !value ) {
        if( definition ) {
            std::string reference = definition->default_value;
            if( definition->type == world_advanced_type::boolean ) {
                reference = reference == "true" ? _( "Yes" ) : _( "No" );
            }
            return string_format( _( "Follow core / mods (reference: %s %s)" ), reference,
                                  definition->unit.translated() );
        }
        return _( "Follow core / mods" );
    }
    std::string display = *value;
    if( definition && definition->type == world_advanced_type::boolean ) {
        display = *value == "true" ? _( "Yes" ) : _( "No" );
    }
    return string_format( _( "Custom: %s %s" ), display,
                          definition ? definition->unit.translated() : "" );
}

void edit_world_advanced_rule( world_advanced_options &rules, const std::string &id )
{
    const world_advanced_definition *definition = find_world_advanced_definition( id );
    if( !definition ) {
        return;
    }
    uilist mode;
    mode.title = definition->name.translated();
    mode.text = wrap_rule_description( world_advanced_value_label( &rules, id ) + "\n" +
                                       definition->help.translated() );
    mode.addentry( 0, true, 'f', _( "Follow core / mods" ) );
    if( definition->type == world_advanced_type::boolean ) {
        mode.addentry( 1, true, 'y', _( "Yes (override)" ) );
        mode.addentry( 2, true, 'n', _( "No (override)" ) );
    } else {
        mode.addentry( 1, true, 'c', _( "Set custom value" ) );
    }
    mode.query();
    if( mode.ret < 0 ) {
        return;
    }
    if( mode.ret == 0 ) {
        rules.erase( id );
        return;
    }
    std::string value;
    if( definition->type == world_advanced_type::boolean ) {
        value = mode.ret == 1 ? "true" : "false";
    } else {
        string_input_popup input;
        input.title( definition->name.translated() );
        input.description( definition->type == world_advanced_type::text ?
                           definition->help.translated() :
                           string_format( _( "Range: %g to %g %s. Step: %g.\n%s" ),
                                          definition->minimum, definition->maximum,
                                          definition->unit.translated(), definition->step,
                                          definition->help.translated() ) );
        input.text( rules.find( id ).value_or( definition->default_value ) );
        value = input.query_string();
        if( input.canceled() ) {
            return;
        }
    }
    std::string error;
    if( !rules.set( id, value, error ) ) {
        popup( "%s", error );
    }
}

void show_world_advanced_options( world_advanced_options &rules, const bool editable )
{
    // Stage edits, so Cancel also restores "follow" versus explicit-default state.
    world_advanced_options working = rules;
    std::vector<world_advanced_definition> definitions = world_advanced_definitions();
    std::map<std::string, std::size_t> group_order;
    for( const world_advanced_definition &definition : definitions ) {
        group_order.emplace( definition.group.translated(), group_order.size() );
    }
    std::stable_sort( definitions.begin(),
                      definitions.end(), [&]( const world_advanced_definition & lhs,
    const world_advanced_definition & rhs ) {
        return group_order.at( lhs.group.translated() ) < group_order.at( rhs.group.translated() );
    } );
    int selected = 0;
    std::string filter;
    while( true ) {
        uilist menu;
        menu.title = editable ? _( "Advanced world rules" ) : _( "Advanced world rules (read only)" );
        menu.text = wrap_rule_description(
                        _( "Unchanged rules follow core and mods. Custom values take precedence. "
                           "Terrain controls apply to all dimensions with the corresponding generators; "
                           "missing components and pregenerated maps are not replaced. "
                           "Reference defaults are shown; inherited values may vary by mod and region. "
                           "Overrides may prevent missions or starting locations from generating. "
                           "Use the list filter to search names or groups." ) );
        menu.desc_enabled = true;
        menu.filtering = true;
        menu.filtering_nocase = true;
        menu.filter = filter;
        menu.selected = selected;
        if( editable ) {
            menu.addentry( static_cast<int>( definitions.size() ), true, 's', _( "Apply changes" ) );
            menu.addentry( static_cast<int>( definitions.size() ) + 1, true, 'r',
                           _( "Restore all rules to follow core / mods" ) );
        }
        for( size_t index = 0; index < definitions.size(); ++index ) {
            const world_advanced_definition &definition = definitions[index];
            const std::string label = string_format( "[%s] %s", definition.group.translated(),
                                      definition.name.translated() );
            const std::string value = world_advanced_value_label( &working, definition.id );
            // uilist measures unwrapped text when sizing its window.  Keep the list
            // compact and put the complete value and compatibility notes in its footer.
            menu.addentry_desc( static_cast<int>( index ), true, MENU_AUTOASSIGN,
                                label + ": " + ( working.find( definition.id ) ? trim_by_length( value, 24 ) :
                                                 _( "Follow core / mods" ) ),
                                wrap_rule_description( label + "\n" + value + "\n" +
                                        definition.help.translated() ) );
        }
        menu.query( true, 50, true );
        filter = menu.filter;
        if( menu.ret < 0 ) {
            return;
        }
        selected = menu.selected;
        if( menu.ret == static_cast<int>( definitions.size() ) && editable ) {
            std::string error;
            if( !working.validate( error ) ) {
                popup( "%s", error );
                continue;
            }
            rules = working;
            return;
        }
        if( menu.ret == static_cast<int>( definitions.size() ) + 1 && editable ) {
            if( working.empty() || query_yn( _( "Restore all advanced rules to follow core and mods?" ) ) ) {
                working.clear();
            }
            continue;
        }
        if( menu.ret < static_cast<int>( definitions.size() ) ) {
            const world_advanced_definition &definition = definitions[menu.ret];
            if( editable ) {
                edit_world_advanced_rule( working, definition.id );
            } else {
                popup( "%s\n\n%s", definition.help.translated(),
                       world_advanced_value_label( &working, definition.id ) );
            }
        }
    }
}
