#include <optional>
#include <string>
#include <vector>

#include "cata_catch.h"
#include "mp_intent.h"
#include "point.h"

TEST_CASE( "mp_intent_accepts_only_the_eight_adjacent_move_hints", "[multiplayer][intent]" )
{
    const std::vector<point> directions = {
        point::north, point::north_east, point::east, point::south_east,
        point::south, point::south_west, point::west, point::north_west
    };
    for( const point &direction : directions ) {
        const std::string message = R"({"type":"intent","kind":"move","dx":)" +
                                    std::to_string( direction.x ) + R"(,"dy":)" +
                                    std::to_string( direction.y ) + "}";
        CAPTURE( message );
        const std::optional<point> decoded = cata_mp::mp_decode_intent_direction( message );
        REQUIRE( decoded );
        CHECK( *decoded == direction );
    }
}

TEST_CASE( "mp_intent_rejects_remote_offsets_before_map_or_render_math", "[multiplayer][intent]" )
{
    const std::vector<std::string> invalid = {
        R"({"type":"intent","kind":"move","dx":2147483647,"dy":1})",
        R"({"type":"intent","kind":"move","dx":-2147483648,"dy":-1})",
        R"({"type":"intent","kind":"move","dx":0,"dy":2})",
        R"({"type":"intent","kind":"move","dx":0,"dy":0})",
        R"({"type":"intent","kind":"move","dx":1})",
        R"({"type":"intent","kind":"move","dx":"east","dy":0})",
        R"({"type":"intent","kind":"unknown","dx":1,"dy":0})",
        R"({"type":"action","kind":"move","dx":1,"dy":0})",
        R"({"type":"intent","kind":"wait","dx":1,"dy":0})",
        R"({"type":"intent","kind":"move","dx":)"
    };
    for( const std::string &message : invalid ) {
        CAPTURE( message );
        CHECK_FALSE( cata_mp::mp_decode_intent_direction( message ) );
    }
}

TEST_CASE( "mp_intent_none_packet_clears_with_normal_json_whitespace", "[multiplayer][intent]" )
{
    const std::optional<point> decoded = cata_mp::mp_decode_intent_direction(
            R"({ "type" : "intent", "kind" : "none" })" );
    REQUIRE( decoded );
    CHECK( *decoded == point::zero );
}
