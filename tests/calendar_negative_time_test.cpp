#include <array>
#include <cstdint>
#include <limits>
#include <utility>

#include "calendar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "options_helpers.h"

TEST_CASE( "calendar_extreme_dates_format_with_valid_months", "[calendar]" )
{
    override_option show_months( "SHOW_MONTHS", "true" );
    const int previous_length = to_days<int>( calendar::season_length() );
    const bool previous_eternal = calendar::eternal_season();
    on_out_of_scope restore_calendar( [previous_length, previous_eternal]() {
        calendar::set_season_length( previous_length );
        calendar::set_eternal_season( previous_eternal );
    } );
    calendar::set_season_length( 91 );
    calendar::set_eternal_season( false );

    struct date_case {
        int turn;
        int year;
        month expected_month;
        int day;
        season_type season;
    };
    // March 21 is turn zero; January 1 is 81 days earlier.  These dates include
    // the exact negative timestamp whose native CHECK formatting crashed.
    const std::array<date_case, 7> cases = {{
            { -2126008811, -68, month::AUGUST, 14, SUMMER },
            { std::numeric_limits<int>::min(), -69, month::DECEMBER, 8, AUTUMN },
            { -6998401, -1, month::DECEMBER, 30, WINTER },
            { -6998400, 0, month::JANUARY, 1, WINTER },
            { -1, 0, month::MARCH, 20, WINTER },
            { 0, 0, month::MARCH, 21, SPRING },
            { std::numeric_limits<int>::max(), 68, month::JULY, 3, SUMMER },
        }
    };
    for( const date_case &sample : cases ) {
        CAPTURE( sample.turn );
        const time_point date = time_point::from_turn( sample.turn );
        // Exercise production formatting itself, rather than hiding the crash
        // by comparing only integer turns in the Lua parity regression.
        CHECK_FALSE( to_string( date ).empty() );
        const std::pair<month, int> actual = month_and_day( date );
        CHECK( actual.first == sample.expected_month );
        CHECK( actual.second == sample.day );
        CHECK( calendar::years_since_cataclysm( date ) == sample.year );
        CHECK( season_of_year( date ) == sample.season );
        const time_duration within_year = time_past_new_year( date );
        CHECK( within_year >= 0_seconds );
        CHECK( within_year < calendar::year_length() );
    }

    // Existing positive dates and opening-season locks keep their meaning,
    // including worlds with a nonstandard season length and a custom start.
    restore_on_out_of_scope restore_initial( calendar::initial_season );
    restore_on_out_of_scope restore_start( calendar::start_of_game );
    calendar::set_season_length( 73 );
    calendar::start_of_game = calendar::turn_zero + 5_days;
    const time_point opening = calendar::turn_zero + 73_days + 10_days;
    CHECK( season_of_year( opening ) == SUMMER );
    CHECK( day_of_week( calendar::start_of_game ) == weekdays::THURSDAY );
    CHECK( day_of_week( calendar::start_of_game - 1_days ) == weekdays::WEDNESDAY );
    CHECK( month_and_day( opening ).first == month::UNKNOWN );
    CHECK_FALSE( to_string( opening ).empty() );
    calendar::initial_season = AUTUMN;
    calendar::set_eternal_season( true );
    CHECK( season_of_year( opening ) == AUTUMN );
    CHECK( season_of_year( opening, true ) == SUMMER );
    CHECK_FALSE( to_string( opening ).empty() );
}
