#include "world_advanced_options.h"

#include <charconv>
#include <cmath>
#include <locale>
#include <sstream>
#include <utility>

#include "cata_path.h"
#include "cata_utility.h"
#include "filesystem.h"
#include "json.h"
#include "string_formatter.h"
#include "translations.h"

namespace
{
const world_advanced_options *active_options = nullptr;
std::size_t active_revision = 0;
std::size_t context_revision = 0;

bool parse_number( const std::string &value, double &number )
{
    std::istringstream input( value );
    input.imbue( std::locale::classic() );
    input >> std::noskipws >> number;
    return input && input.peek() == std::char_traits<char>::eof() && std::isfinite( number );
}

std::string number_text( double number )
{
    // Shortest round-trip representation, independent of the interface locale.
    // A finite double needs fewer than 32 characters in the default format.
    char buffer[64];
    const std::to_chars_result result = std::to_chars( buffer, buffer + sizeof( buffer ),
                                        number == 0 ? 0.0 : number );
    return std::string( buffer, result.ptr );
}

const char *target_name( world_advanced_target target )
{
    switch( target ) {
        case world_advanced_target::external:
            return "external";
        case world_advanced_target::region:
            return "region";
        case world_advanced_target::climate:
            return "climate";
    }
    return "";
}
} // namespace

world_advanced_options &world_advanced_options::operator=( const world_advanced_options &other )
{
    if( values_ != other.values_ ) {
        values_ = other.values_;
        ++revision_;
    }
    return *this;
}

world_advanced_options &world_advanced_options::operator=( world_advanced_options &&other )
{
    if( values_ != other.values_ ) {
        values_ = std::move( other.values_ );
        ++revision_;
    }
    return *this;
}

const world_advanced_definition *find_world_advanced_definition( const std::string &id )
{
    for( const world_advanced_definition &definition : world_advanced_definitions() ) {
        if( definition.id == id ) {
            return &definition;
        }
    }
    return nullptr;
}

bool validate_world_advanced_scalar( const std::string &id, const std::string &value,
                                     std::string &error )
{
    error.clear();
    const world_advanced_definition *definition = find_world_advanced_definition( id );
    if( !definition ) {
        error = string_format( _( "Unknown advanced world option: %s" ), id );
        return false;
    }
    if( definition->type == world_advanced_type::boolean ) {
        if( value == "true" || value == "false" ) {
            return true;
        }
        error = string_format( _( "%s requires true or false." ), definition->name.translated() );
        return false;
    }
    if( definition->type == world_advanced_type::text ) {
        if( !value.empty() && value.size() <= 128 &&
            value.find_first_of( " \t\r\n" ) == std::string::npos ) {
            return true;
        }
        error = string_format( _( "%s requires a nonempty identifier of at most 128 bytes." ),
                               definition->name.translated() );
        return false;
    }
    double number = 0;
    if( !parse_number( value, number ) || number < definition->minimum ||
        number > definition->maximum ||
        ( definition->type == world_advanced_type::integer && std::floor( number ) != number ) ) {
        error = string_format( _( "%s requires a finite %s between %g and %g." ),
                               definition->name.translated(),
                               definition->type == world_advanced_type::integer ? _( "integer" ) : _( "number" ),
                               definition->minimum, definition->maximum );
        return false;
    }
    return true;
}

bool world_advanced_options::set( const std::string &id, const std::string &value,
                                  std::string &error )
{
    if( !validate_world_advanced_scalar( id, value, error ) ) {
        return false;
    }
    const world_advanced_definition &definition = *find_world_advanced_definition( id );
    std::string canonical = value;
    if( definition.type == world_advanced_type::integer ||
        definition.type == world_advanced_type::number ) {
        double number = 0;
        parse_number( value, number );
        canonical = definition.type == world_advanced_type::integer ?
                    std::to_string( static_cast<int>( number ) ) : number_text( number );
    }
    const auto existing = values_.find( id );
    if( existing == values_.end() || existing->second != canonical ) {
        values_[id] = std::move( canonical );
        ++revision_;
    }
    return true;
}

void world_advanced_options::erase( const std::string &id )
{
    if( values_.erase( id ) ) {
        ++revision_;
    }
}

void world_advanced_options::clear()
{
    if( !values_.empty() ) {
        values_.clear();
        ++revision_;
    }
}

std::optional<std::string> world_advanced_options::find( const std::string &id ) const
{
    const auto entry = values_.find( id );
    return entry == values_.end() ? std::nullopt : std::optional<std::string>( entry->second );
}

bool world_advanced_options::empty() const
{
    return values_.empty();
}

const std::map<std::string, std::string> &world_advanced_options::values() const
{
    return values_;
}

std::size_t world_advanced_options::revision() const
{
    return revision_;
}

bool world_advanced_options::validate( std::string &error ) const
{
    error.clear();
    for( const auto &entry : values_ ) {
        if( !validate_world_advanced_scalar( entry.first, entry.second, error ) ) {
            return false;
        }
    }
    const auto number = [this]( const std::string & id ) {
        const std::optional<std::string> value = find( id );
        const world_advanced_definition &definition = *find_world_advanced_definition( id );
        double result = 0;
        parse_number( value.value_or( definition.default_value ), result );
        return result;
    };
    if( find( "REGION_FOREST_THRESHOLD" ) && find( "REGION_THICK_FOREST_THRESHOLD" ) &&
        number( "REGION_THICK_FOREST_THRESHOLD" ) < number( "REGION_FOREST_THRESHOLD" ) ) {
        error = _( "The thick forest threshold must be at least the forest threshold." );
        return false;
    }
    if( find( "MIN_CATCHUP_EXP_PER_POST_CATA_DAY" ) &&
        find( "MAX_CATCHUP_EXP_PER_POST_CATA_DAY" ) &&
        number( "MIN_CATCHUP_EXP_PER_POST_CATA_DAY" ) >
        number( "MAX_CATCHUP_EXP_PER_POST_CATA_DAY" ) ) {
        error = _( "Minimum NPC catch-up experience must not exceed the maximum." );
        return false;
    }
    if( find( "HIGHWAY_GRID_VARIANCE" ) ) {
        for( const std::string id : {
                 "HIGHWAY_GRID_ROW_SEPARATION", "HIGHWAY_GRID_COLUMN_SEPARATION"
             } ) {
            if( find( id ) && 2 * number( "HIGHWAY_GRID_VARIANCE" ) >= number( id ) ) {
                error = _( "Highway variance must be less than half of both highway separations." );
                return false;
            }
        }
    }
    return true;
}

void world_advanced_options::serialize( JsonOut &out ) const
{
    out.start_object();
    out.member( "version", 1 );
    for( world_advanced_target target : {
             world_advanced_target::external,
             world_advanced_target::region, world_advanced_target::climate
         } ) {
        out.member( target_name( target ) );
        out.start_object();
        for( const auto &entry : values_ ) {
            const world_advanced_definition &definition = *find_world_advanced_definition( entry.first );
            if( definition.target != target ) {
                continue;
            }
            if( definition.type == world_advanced_type::boolean ) {
                out.member( entry.first, entry.second == "true" );
            } else if( definition.type == world_advanced_type::integer ) {
                out.member( entry.first, std::stoi( entry.second ) );
            } else if( definition.type == world_advanced_type::number ) {
                double number = 0;
                parse_number( entry.second, number );
                out.member( entry.first, number );
            } else {
                out.member( entry.first, entry.second );
            }
        }
        out.end_object();
    }
    out.end_object();
}

void world_advanced_options::deserialize( const JsonObject &obj )
{
    if( !obj.get_member( "version" ).test_int() || obj.get_int( "version" ) != 1 ) {
        obj.throw_error_at( "version", "Unsupported advanced world options version" );
    }
    world_advanced_options parsed;
    for( world_advanced_target target : {
             world_advanced_target::external,
             world_advanced_target::region, world_advanced_target::climate
         } ) {
        const JsonObject group = obj.get_object( target_name( target ) );
        for( const JsonMember member : group ) {
            const std::string id = member.name();
            const world_advanced_definition *definition = find_world_advanced_definition( id );
            if( !definition || definition->target != target ) {
                group.throw_error_at( id, "Unknown advanced world option or incorrect target group" );
            }
            const bool valid_type =
                ( definition->type == world_advanced_type::boolean && member.test_bool() ) ||
                ( definition->type == world_advanced_type::integer && member.test_int() ) ||
                ( definition->type == world_advanced_type::number && member.test_number() ) ||
                ( definition->type == world_advanced_type::text && member.test_string() );
            if( !valid_type ) {
                group.throw_error_at( id, "Incorrect JSON scalar type for advanced world option" );
            }
            std::string value;
            if( definition->type == world_advanced_type::boolean ) {
                value = group.get_bool( id ) ? "true" : "false";
            } else if( definition->type == world_advanced_type::integer ) {
                value = std::to_string( group.get_int( id ) );
            } else if( definition->type == world_advanced_type::number ) {
                value = number_text( group.get_float( id ) );
            } else {
                value = group.get_string( id );
            }
            std::string error;
            if( !parsed.set( id, value, error ) ) {
                group.throw_error_at( id, error );
            }
        }
    }
    std::string error;
    if( !parsed.validate( error ) ) {
        obj.throw_error( error );
    }
    values_ = std::move( parsed.values_ );
    ++revision_;
}

bool world_advanced_options::save( const cata_path &file_path ) const
{
    std::string error;
    if( !validate( error ) ) {
        return false;
    }
    return write_to_file( file_path, [this]( std::ostream & output ) {
        JsonOut json( output );
        serialize( json );
    }, _( "advanced world options" ) );
}

bool world_advanced_options::load( const cata_path &file_path )
{
    clear();
    if( !file_exist( file_path ) ) {
        return true;
    }
    return read_from_file_json( file_path, [this]( const JsonValue & value ) {
        deserialize( value.get_object() );
    } );
}

void set_active_world_advanced_options( const world_advanced_options *options )
{
    active_options = options;
    active_revision = options ? options->revision() : 0;
    ++context_revision;
}

const world_advanced_options *active_world_advanced_options()
{
    return active_options;
}

std::size_t world_advanced_options_revision()
{
    if( active_options && active_options->revision() != active_revision ) {
        active_revision = active_options->revision();
        ++context_revision;
    }
    return context_revision;
}

std::optional<std::string> get_world_advanced_value( const std::string &id )
{
    return active_options ? active_options->find( id ) : std::nullopt;
}

double world_advanced_number( const std::string &id, double fallback )
{
    const std::optional<std::string> value = get_world_advanced_value( id );
    double number = 0;
    return value && parse_number( *value, number ) ? number : fallback;
}

bool world_advanced_bool( const std::string &id, bool fallback )
{
    const std::optional<std::string> value = get_world_advanced_value( id );
    return value ? *value == "true" : fallback;
}
