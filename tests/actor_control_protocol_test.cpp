#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

#include "actor_control_protocol.h"
#include "actor_control_types.h"
#include "cata_catch.h"
#include "flexbuffer_json.h"
#include "json_loader.h"
#include "path_info.h"

TEST_CASE( "actor_control_shared_protocol_fixtures_match_native_validity",
           "[actor_control][protocol]" )
{
    const std::filesystem::path path = std::filesystem::path( PATH_INFO::datadir() ) /
                                       "reference" / "actor_control" / "fixtures.json";
    std::ifstream input( path );
    REQUIRE( input.is_open() );
    const std::string text( ( std::istreambuf_iterator<char>( input ) ),
                            std::istreambuf_iterator<char>() );
    const JsonArray fixtures = json_loader::from_string( text ).get_array();
    REQUIRE( fixtures.size() == 12 );
    int valid_count = 0;
    int invalid_count = 0;
    for( const JsonObject &fixture : fixtures ) {
        INFO( fixture.get_string( "name" ) );
        const bool expected = fixture.get_bool( "valid" );
        const JsonValue plan = fixture.get_member( "plan" );
        std::vector<cata::actor_control::action_step> steps;
        std::string error;
        const bool accepted = cata::actor_control::parse_plan(
                                  cata::actor_control::stringify( plan ), steps, error );
        REQUIRE( accepted == expected );
        if( expected ) {
            ++valid_count;
            CHECK( error.empty() );
            const JsonArray offered = plan.get_object().get_array( "steps" );
            REQUIRE( steps.size() == offered.size() );
            for( std::size_t i = 0; i < steps.size(); ++i ) {
                const JsonObject source = offered.get_object( i );
                CHECK( steps[i].id == source.get_string( "id" ) );
                CHECK( steps[i].action == source.get_string( "action" ) );
            }
        } else {
            ++invalid_count;
            CHECK_FALSE( error.empty() );
            CHECK( steps.empty() );
        }
    }
    CHECK( valid_count == 4 );
    CHECK( invalid_count == 8 );
}
