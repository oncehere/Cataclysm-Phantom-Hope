#include "actor_control_protocol.h"

#include <algorithm>
#include <cstddef>
#include <exception>
#include <set>
#include <sstream>
#include <utility>

#include "actor_control_protocol_generated.h"
#include "flexbuffer_json.h"
#include "json.h"
#include "json_loader.h"

namespace cata::actor_control
{
namespace
{
const JsonObject &contract()
{
    static const JsonObject value = json_loader::from_string( protocol_json ).get_object();
    value.allow_omitted_members();
    return value;
}

bool fail( std::string &error, const std::string &code )
{
    error = code;
    return false;
}
} // namespace

std::string quote( const std::string &text )
{
    std::ostringstream output;
    JsonOut json( output );
    json.write( text );
    return output.str();
}

std::string stringify( const JsonValue &value )
{
    if( value.test_object() ) {
        const JsonObject object = value.get_object();
        // Serialization retains every member; it is not a partial schema read.
        object.allow_omitted_members();
        return object.str();
    }
    if( value.test_array() ) {
        std::string result = "[";
        bool first = true;
        for( const JsonValue &entry : value.get_array() ) {
            result += ( first ? "" : "," ) + stringify( entry );
            first = false;
        }
        return result + "]";
    }
    if( value.test_string() ) {
        return quote( value.get_string() );
    }
    if( value.test_null() ) {
        return "null";
    }
    if( value.test_bool() ) {
        return value.get_bool() ? "true" : "false";
    }
    if( value.test_int() ) {
        return std::to_string( value.get_int64() );
    }
    return std::to_string( value.get_float() );
}

std::string capability_catalog()
{
    return stringify( contract().get_member( "actions" ) );
}

bool is_behavior( const std::string &name )
{
    for( const std::string &entry : contract().get_array( "behaviors" ) ) {
        if( entry == name ) {
            return true;
        }
    }
    return false;
}

bool validate_schema( const JsonValue &value, const JsonValue &schema_value,
                      std::string &error )
{
    const JsonObject schema = schema_value.get_object();
    schema.allow_omitted_members();
    const std::string type = schema.get_string( "type", "" );
    if( type == "object" ) {
        if( !value.test_object() ) {
            return fail( error, "object_required" );
        }
        const JsonObject object = value.get_object();
        object.allow_omitted_members();
        const JsonObject properties = schema.has_object( "properties" ) ?
                                      schema.get_object( "properties" ) : JsonObject();
        properties.allow_omitted_members();
        if( schema.has_array( "required" ) ) {
            for( const std::string &key : schema.get_array( "required" ) ) {
                if( !object.has_member( key ) ) {
                    return fail( error, "missing_field" );
                }
            }
        }
        for( const JsonMember &member : object ) {
            if( properties.has_member( member.name() ) ) {
                if( !validate_schema( member, properties.get_member( member.name() ), error ) ) {
                    return false;
                }
            } else if( !schema.get_bool( "additionalProperties", true ) ) {
                return fail( error, "unknown_field" );
            }
        }
    } else if( type == "array" ) {
        if( !value.test_array() ) {
            return fail( error, "array_required" );
        }
        const JsonArray values = value.get_array();
        if( values.size() < static_cast<std::size_t>( schema.get_int( "minItems", 0 ) ) ||
            values.size() > static_cast<std::size_t>( schema.get_int( "maxItems", 1048576 ) ) ) {
            return fail( error, "array_size" );
        }
        for( const JsonValue &element : values ) {
            if( !validate_schema( element, schema.get_member( "items" ), error ) ) {
                return false;
            }
        }
    } else if( type == "string" ) {
        if( !value.test_string() ) {
            return fail( error, "string_required" );
        }
        const std::string text = value.get_string();
        const std::size_t count = std::count_if( text.begin(), text.end(), []( const unsigned char ch ) {
            return ( ch & 0xc0 ) != 0x80;
        } );
        if( text.find( '\0' ) != std::string::npos ||
            count < static_cast<std::size_t>( schema.get_int( "minLength", 0 ) ) ||
            count > static_cast<std::size_t>( schema.get_int( "maxLength", 1048576 ) ) ) {
            return fail( error, "string_size" );
        }
    } else if( type == "integer" ) {
        if( !value.test_int() || value.test_bool() ) {
            return fail( error, "integer_required" );
        }
        const double number = value.get_float();
        if( number < schema.get_float( "minimum", -9007199254740991.0 ) ||
            number > schema.get_float( "maximum", 9007199254740991.0 ) ) {
            return fail( error, "integer_range" );
        }
    } else if( type == "boolean" && !value.test_bool() ) {
        return fail( error, "boolean_required" );
    }
    if( schema.has_array( "enum" ) ) {
        bool found = false;
        for( const JsonValue &option : schema.get_array( "enum" ) ) {
            if( stringify( option ) == stringify( value ) ) {
                found = true;
                break;
            }
        }
        if( !found ) {
            return fail( error, "invalid_enum" );
        }
    }
    return true;
}

bool parse_plan( const std::string &text, std::vector<action_step> &steps,
                 std::string &error )
{
    steps.clear();
    if( text.size() > 1048576 ) {
        return fail( error, "message_too_large" );
    }
    try {
        const JsonValue parsed = json_loader::from_string( text );
        const JsonObject schemas = contract().get_object( "schemas" );
        schemas.allow_omitted_members();
        if( !validate_schema( parsed, schemas.get_member( "plan" ),
                              error ) ) {
            return false;
        }
        const JsonObject plan = parsed.get_object();
        plan.allow_omitted_members();
        std::set<std::string> seen;
        std::set<std::string> refused;
        std::set<std::string> worked;
        if( plan.get_string( "intent", "" ) == "refuse" ) {
            return fail( error, "refusal_requires_requirement" );
        }
        std::vector<action_step> candidate;
        for( const JsonObject &entry : plan.get_array( "steps" ) ) {
            entry.allow_omitted_members();
            const std::string id = entry.get_string( "id" );
            if( seen.count( id ) ) {
                return fail( error, "duplicate_step" );
            }
            if( entry.has_string( "from_step" ) && !seen.count( entry.get_string( "from_step" ) ) ) {
                return fail( error, "invalid_dependency" );
            }
            seen.insert( id );
            const std::string action = entry.get_string( "action" );
            bool found = false;
            for( const JsonObject &definition : contract().get_array( "actions" ) ) {
                definition.allow_omitted_members();
                if( definition.get_string( "name" ) == action ) {
                    found = true;
                    if( !validate_schema( entry.get_member( "args" ), definition.get_member( "args" ),
                                          error ) ) {
                        return false;
                    }
                    break;
                }
            }
            if( !found ) {
                return fail( error, "unknown_action" );
            }
            const JsonObject arguments = entry.get_object( "args" );
            arguments.allow_omitted_members();
            if( action == "attack" ) {
                const bool character = arguments.has_int( "target" );
                const bool monster = arguments.has_int( "x" ) && arguments.has_int( "y" ) &&
                                     arguments.has_int( "z" ) && arguments.has_string( "monster_type" );
                if( character == monster || ( character && ( arguments.has_member( "x" ) ||
                                              arguments.has_member( "y" ) || arguments.has_member( "z" ) ||
                                              arguments.has_member( "monster_type" ) ) ) ) {
                    return fail( error, "invalid_attack_target" );
                }
            }
            if( action == "talk" && arguments.has_member( "topic" ) != arguments.has_member( "option" ) ) {
                return fail( error, "incomplete_dialogue_option" );
            }
            const std::string requirement = entry.get_string( "requirement_id", "" );
            if( action == "refuse" ) {
                if( requirement.empty() ) {
                    return fail( error, "refusal_requires_requirement" );
                }
                refused.insert( requirement );
            } else {
                if( entry.get_string( "intent", "" ) == "refuse" ) {
                    return fail( error, "refusal_requires_requirement" );
                }
                if( !requirement.empty() ) {
                    worked.insert( requirement );
                }
            }
            candidate.push_back( action_step { id, action, arguments.str(),
                                               entry.get_string( "intent", "" ), {}, requirement } );
        }
        for( const std::string &requirement : refused ) {
            if( worked.count( requirement ) != 0 ) {
                return fail( error, "contradictory_requirement_decision" );
            }
        }
        steps = std::move( candidate );
        return true;
    } catch( const std::exception & ) {
        return fail( error, "invalid_json" );
    }
}
} // namespace cata::actor_control
