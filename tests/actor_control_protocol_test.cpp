#include <cmath>
#include <cstdint>
#include <limits>
#include <locale>
#include <string>
#include <vector>

#include "actor_control_protocol.h"
#include "actor_control_protocol_generated.h"
#include "actor_control_types.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "debug.h"
#include "flexbuffer_json.h"
#include "json_loader.h"

namespace
{
class grouped_protocol_punctuation : public std::numpunct<char>
{
    protected:
        char do_thousands_sep() const override {
            return ',';
        }
        std::string do_grouping() const override {
            return "\3";
        }
};
} // namespace

TEST_CASE( "actor_control_nested_json_ignores_numeric_locale",
           "[actor_control][protocol][locale]" )
{
    const std::locale original = std::locale();
    const on_out_of_scope cleanup( [&]() {
        std::locale::global( original );
    } );
    std::locale::global( std::locale( std::locale::classic(), new grouped_protocol_punctuation ) );
    const JsonValue input = json_loader::from_string(
                                R"({"limits":{"tokens":32768,"negative":-1234567,"ratio":0.7},"values":[32768,true,null,"a\"b"],"scalars":[1.0,-0.0,9223372036854775807,1e-30]})" );
    const std::string encoded = cata::actor_control::stringify( input );
    CHECK( encoded.find( "32,768" ) == std::string::npos );
    const JsonObject output = json_loader::from_string( encoded ).get_object();
    const JsonObject limits = output.get_object( "limits" );
    CHECK( limits.get_int( "tokens" ) == 32768 );
    CHECK( limits.get_int( "negative" ) == -1234567 );
    CHECK( limits.get_float( "ratio" ) == 0.7 );
    const JsonArray values = output.get_array( "values" );
    REQUIRE( values.size() == 4 );
    CHECK( values.get_int( 0 ) == 32768 );
    CHECK( values[1].get_bool() );
    CHECK( values[2].test_null() );
    CHECK( values.get_string( 3 ) == "a\"b" );
    const JsonArray scalars = output.get_array( "scalars" );
    REQUIRE( scalars.size() == 4 );
    CHECK_FALSE( scalars[0].test_int() );
    CHECK( scalars[0].get_float() == 1.0 );
    CHECK_FALSE( scalars[1].test_int() );
    CHECK( std::signbit( scalars[1].get_float() ) );
    CHECK( scalars[2].get_int64() == std::numeric_limits<int64_t>::max() );
    CHECK( scalars[2].get_float() > 0 );
    CHECK( scalars[3].get_float() == 1e-30 );
}

TEST_CASE( "actor_control_shared_protocol_fixtures_match_native_validity",
           "[actor_control][protocol]" )
{
    const JsonArray fixtures = json_loader::from_string(
                                   cata::actor_control::protocol_fixtures_json ).get_array();
    REQUIRE_FALSE( fixtures.empty() );
    int valid_count = 0;
    int invalid_count = 0;
    for( const JsonObject &fixture : fixtures ) {
        fixture.allow_omitted_members();
        INFO( fixture.get_string( "name" ) );
        const bool expected = fixture.get_bool( "valid" );
        const JsonValue plan = fixture.get_member( "plan" );
        std::vector<cata::actor_control::action_step> steps;
        std::string error;
        bool accepted = false;
        const std::string diagnostic = capture_debugmsg_during( [&accepted, &plan, &steps, &error]() {
            accepted = cata::actor_control::parse_plan(
                           cata::actor_control::stringify( plan ), steps, error );
            CHECK_FALSE( cata::actor_control::capability_catalog().empty() );
        } );
        CHECK( diagnostic.empty() );
        REQUIRE( accepted == expected );
        if( expected ) {
            ++valid_count;
            CHECK( error.empty() );
            const JsonObject plan_object = plan.get_object();
            plan_object.allow_omitted_members();
            const JsonArray offered = plan_object.get_array( "steps" );
            REQUIRE( steps.size() == offered.size() );
            for( std::size_t i = 0; i < steps.size(); ++i ) {
                const JsonObject source = offered.get_object( i );
                source.allow_omitted_members();
                CHECK( steps[i].id == source.get_string( "id" ) );
                CHECK( steps[i].action == source.get_string( "action" ) );
            }
        } else {
            ++invalid_count;
            CHECK_FALSE( error.empty() );
            CHECK( steps.empty() );
        }
    }
    CHECK( valid_count > 0 );
    CHECK( invalid_count > 0 );
}

TEST_CASE( "actor_control_status_report_schema_preserves_ordinary_queries_and_rejects_raw_errors",
           "[actor_control][protocol][planning]" )
{
    std::string error;
    CHECK( cata::actor_control::parse_status_parameters( "{}", error ) );
    CHECK( cata::actor_control::parse_status_parameters(
               R"({"include_debug":true,"operation_id":"operation"})", error ) );
    const std::string report =
        R"({"decision_id":"load.1","request_id":"request","state":"failed","reason":"provider_failed"})";
    CHECK( cata::actor_control::parse_status_parameters( "{\"planning_report\":" + report + "}",
            error ) );
    CHECK_FALSE( cata::actor_control::parse_status_parameters( R"({"unknown":"SECRET"})", error ) );
    CHECK( error == "unknown_field" );
    CHECK_FALSE( cata::actor_control::parse_status_parameters(
                     R"({"planning_report":{"decision_id":"load.1","request_id":"request","state":"failed","reason":"SECRET"}})",
                     error ) );
    CHECK( error == "invalid_enum" );
}

TEST_CASE( "actor_control_shared_task_fixtures_match_native_validity",
           "[actor_control][protocol][tasks]" )
{
    const JsonArray fixtures = json_loader::from_string(
                                   cata::actor_control::protocol_task_fixtures_json ).get_array();
    REQUIRE( fixtures.size() > 0 );
    int valid_count = 0;
    int invalid_count = 0;
    for( const JsonObject &fixture : fixtures ) {
        fixture.allow_omitted_members();
        INFO( fixture.get_string( "name" ) );
        const bool expected = fixture.get_bool( "valid" );
        const JsonValue offer = fixture.get_member( "offer" );
        std::string error;
        bool accepted = false;
        const std::string diagnostic = capture_debugmsg_during( [&accepted, &offer, &error]() {
            accepted = cata::actor_control::parse_tasks(
                           cata::actor_control::stringify( offer ), error );
            CHECK_FALSE( cata::actor_control::task_capability_catalog().empty() );
        } );
        CHECK( diagnostic.empty() );
        REQUIRE( accepted == expected );
        if( expected ) {
            ++valid_count;
            CHECK( error.empty() );
        } else {
            ++invalid_count;
            CHECK( error == fixture.get_string( "error" ) );
        }
    }
    CHECK( valid_count > 0 );
    CHECK( invalid_count > 0 );
}
