#include <optional>

#include "avatar.h"
#include "basecamp.h"
#include "calendar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "clzones.h"
#include "coordinates.h"
#include "faction.h"
#include "map.h"
#include "map_helpers.h"
#include "npc.h"
#include "options_helpers.h"
#include "overmapbuffer.h"
#include "player_helpers.h"
#include "point.h"
#include "stomach.h"
#include "type_id.h"

TEST_CASE( "cdda_npc_camp_meal_reports_actual_consumption", "[camp][npc][cdda_npc_camp_meal]" )
{
    clear_avatar();
    clear_map_without_vision();
    override_option food_on( "NO_NPC_FOOD", "false" );
    map &here = get_map();
    npc &worker = spawn_npc( { 50, 50 }, "test_talker" );
    clear_character( worker, true );
    worker.set_fac( your_fac );
    worker.set_hunger( 300 );
    worker.set_thirst( 0 );
    worker.set_stored_kcal( 1000 );
    worker.stomach.empty();
    worker.guts.empty();
    const tripoint_abs_omt camp_omt = project_to<coords::omt>( worker.pos_abs() );
    here.add_camp( camp_omt, "faction_camp" );
    on_out_of_scope remove_camp( [&]() {
        overmap_buffer.clear_camps( camp_omt.xy() );
    } );
    const std::optional<basecamp *> camp = overmap_buffer.find_camp( camp_omt.xy() );
    REQUIRE( camp );
    ( *camp )->set_owner( your_fac );
    avatar &you = get_avatar();
    you.camps.clear();
    you.camps.insert( camp_omt );
    on_out_of_scope remove_camp_reference( [&]() {
        you.camps.clear();
    } );
    faction *owner = you.get_faction();
    owner->empty_food_supply();
    on_out_of_scope clear_food( [owner]() {
        owner->empty_food_supply();
    } );
    nutrients food;
    food.calories = 5000000;
    const time_point expiry = calendar::turn + 2_days;
    owner->add_to_food_supply( { { expiry, food } } );

    SECTION( "refusing a meal returns false and restores the same expiry" ) {
        worker.add_effect( efftype_id( "nausea" ), 10_minutes );
        CHECK_FALSE( worker.consume_food_from_camp( npc::consume_filter::food_only ) );
        CHECK( owner->food_supply().calories == food.calories );
        const camp_food_portion returned = owner->take_food_supply( food );
        REQUIRE( returned.by_expiry.count( expiry ) == 1 );
        CHECK( returned.by_expiry.at( expiry ).calories == food.calories );
    }
    SECTION( "an accepted meal returns true and spends food" ) {
        CHECK( worker.consume_food_from_camp( npc::consume_filter::food_only ) );
        CHECK( owner->food_supply().calories < food.calories );
        CHECK( worker.stomach.get_calories() > 0 );
    }
}
