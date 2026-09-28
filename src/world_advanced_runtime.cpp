#include "world_advanced_runtime.h"

#include <algorithm>
#include <string>
#include <vector>

#include "options.h"
#include "regional_settings.h"
#include "string_formatter.h"
#include "translations.h"
#include "type_id.h"
#include "weather_type.h"
#include "world_advanced_options.h"

bool validate_active_world_advanced_options( std::string &error )
{
    const world_advanced_options *rules = active_world_advanced_options();
    if( !rules ) {
        return true;
    }
    if( !rules->validate( error ) ) {
        return false;
    }
    if( rules->find( "HIGHWAY_GRID_ROW_SEPARATION" ) ||
        rules->find( "HIGHWAY_GRID_COLUMN_SEPARATION" ) || rules->find( "HIGHWAY_GRID_VARIANCE" ) ) {
        const int row = get_option<int>( "HIGHWAY_GRID_ROW_SEPARATION" );
        const int column = get_option<int>( "HIGHWAY_GRID_COLUMN_SEPARATION" );
        const int variance = get_option<int>( "HIGHWAY_GRID_VARIANCE" );
        if( variance < 1 || 2LL * variance >= std::min( row, column ) ) {
            error = _( "Highway deviation must be positive and less than half of both effective highway spacings, including inherited mod values." );
            return false;
        }
    }
    if( rules->find( "MIN_CATCHUP_EXP_PER_POST_CATA_DAY" ) ||
        rules->find( "MAX_CATCHUP_EXP_PER_POST_CATA_DAY" ) ) {
        if( get_option<int>( "MIN_CATCHUP_EXP_PER_POST_CATA_DAY" ) >
            get_option<int>( "MAX_CATCHUP_EXP_PER_POST_CATA_DAY" ) ) {
            error = _( "Minimum NPC catch-up experience exceeds the effective maximum, including inherited mod values." );
            return false;
        }
    }
    if( const std::optional<std::string> weather = rules->find( "ETERNAL_WEATHER" ) ) {
        if( *weather != "normal" && !weather_type_id( *weather ).is_valid() ) {
            error = string_format( _( "Weather '%s' is not defined by the selected core and mods." ),
                                   *weather );
            return false;
        }
    }
    const std::vector<std::string> region_errors = validate_world_advanced_regions();
    if( !region_errors.empty() ) {
        error.clear();
        for( const std::string &region_error : region_errors ) {
            error += region_error + "\n";
        }
        return false;
    }
    return true;
}
