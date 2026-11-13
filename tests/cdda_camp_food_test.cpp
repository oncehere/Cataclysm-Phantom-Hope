#include <functional>
#include <map>
#include <vector>

#include "avatar.h"
#include "basecamp.h"
#include "calendar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "clzones.h"
#include "faction.h"
#include "npc.h"
#include "options_helpers.h"
#include "player_helpers.h"
#include "type_id.h"

static const efftype_id effect_camp_test_nausea( "nausea" );
static const vitamin_id vitamin_camp_test( "mutagen" );

static nutrients camp_test_food( int calories, int vitamins = 0 )
{
    nutrients food;
    food.calories = calories;
    if( vitamins != 0 ) {
        food.set_vitamin( vitamin_camp_test, vitamins );
    }
    return food;
}

TEST_CASE( "cdda_camp_food_withdrawal", "[camp][cdda_camp_food]" )
{
    faction owner;
    const time_point early = calendar::turn + 2_days;
    const time_point late = calendar::turn + 5_days;
    owner.add_to_food_supply( { { calendar::turn_zero, camp_test_food( 100000, 10 ) },
        { early, camp_test_food( 200000, 20 ) }, { late, camp_test_food( 300000, 30 ) }
    } );

    SECTION( "earliest perishables are taken before later and permanent food" ) {
        const camp_food_portion taken = owner.take_food_supply( camp_test_food( 250000, 25 ) );
        REQUIRE( taken.by_expiry.size() == 2 );
        CHECK( taken.by_expiry.at( early ).calories == 200000 );
        CHECK( taken.by_expiry.at( late ).calories == 50000 );
        CHECK( taken.total().get_vitamin( vitamin_camp_test ) == 25 );
        CHECK( owner.food_supply().calories == 350000 );
        CHECK( owner.food_supply().get_vitamin( vitamin_camp_test ) == 35 );
    }
    SECTION( "shortfall reports only what was actually taken" ) {
        const camp_food_portion taken = owner.take_food_supply( camp_test_food( 900000, 90 ) );
        CHECK( taken.total().calories == 600000 );
        CHECK( taken.total().get_vitamin( vitamin_camp_test ) == 60 );
        CHECK( owner.food_supply().calories == 0 );
        CHECK( owner.take_food_supply( camp_test_food( 1000 ) ).total().calories == 0 );
    }
    SECTION( "permanent stock supplies vitamins after perishable calories suffice" ) {
        owner.empty_food_supply();
        owner.add_to_food_supply( { { calendar::turn_zero, camp_test_food( 100000, 10 ) },
            { early, camp_test_food( 100000, 2 ) }
        } );
        const camp_food_portion taken = owner.take_food_supply( camp_test_food( 100000, 8 ) );
        REQUIRE( taken.by_expiry.count( early ) == 1 );
        REQUIRE( taken.by_expiry.count( calendar::turn_zero ) == 1 );
        CHECK( taken.total().calories == 100000 );
        CHECK( taken.total().get_vitamin( vitamin_camp_test ) == 8 );
        CHECK( taken.by_expiry.at( calendar::turn_zero ).calories == 0 );
        CHECK( taken.by_expiry.at( calendar::turn_zero ).get_vitamin( vitamin_camp_test ) == 6 );
        CHECK( owner.food_supply().calories == 100000 );
        CHECK( owner.food_supply().get_vitamin( vitamin_camp_test ) == 4 );
    }
    SECTION( "legacy consume returns unmet nutrients" ) {
        const nutrients missing = owner.consume_food_supply( camp_test_food( 900000, 90 ) );
        CHECK( missing.calories == 300000 );
        CHECK( missing.get_vitamin( vitamin_camp_test ) == 30 );
        CHECK( owner.consume_food_supply( camp_test_food( 1000 ) ).calories == 1000 );
    }
}

TEST_CASE( "cdda_camp_food_integer_shares", "[camp][cdda_camp_food]" )
{
    const time_point early = calendar::turn + 2_days;
    const time_point late = calendar::turn + 5_days;
    camp_food_portion remaining{ { { early, camp_test_food( 5000, 7 ) },
            { late, camp_test_food( 2000, 5 ) }
        } };
    const camp_food_portion first = remaining.take_share( 3 );
    const camp_food_portion second = remaining.take_share( 2 );
    const camp_food_portion third = remaining.take_share( 1 );
    const auto at_expiry = []( const camp_food_portion & portion, time_point expiry ) {
        const auto it = portion.by_expiry.find( expiry );
        return it == portion.by_expiry.end() ? nutrients() : it->second;
    };
    for( const time_point expiry : {
             early, late
         } ) {
        const int original_calories = expiry == early ? 5000 : 2000;
        const int original_vitamins = expiry == early ? 7 : 5;
        CHECK( at_expiry( first, expiry ).calories + at_expiry( second, expiry ).calories +
               at_expiry( third, expiry ).calories == original_calories );
        CHECK( at_expiry( first, expiry ).get_vitamin( vitamin_camp_test ) +
               at_expiry( second, expiry ).get_vitamin( vitamin_camp_test ) +
               at_expiry( third, expiry ).get_vitamin( vitamin_camp_test ) == original_vitamins );
    }
    CHECK( remaining.total().calories == 0 );
    CHECK( remaining.total().get_vitamin( vitamin_camp_test ) == 0 );
}

TEST_CASE( "cdda_camp_food_shares_across_expiries", "[camp][cdda_camp_food]" )
{
    camp_food_portion remaining;
    for( int day = 1; day <= 5; ++day ) {
        remaining.by_expiry[calendar::turn + day * 1_days] = camp_test_food( 1000 );
    }
    const camp_food_portion first = remaining.take_share( 2 );
    const camp_food_portion second = remaining.take_share( 1 );
    CHECK( first.total().calories == 3000 );
    CHECK( second.total().calories == 2000 );
    CHECK( remaining.total().calories == 0 );
    for( int day = 1; day <= 5; ++day ) {
        const time_point expiry = calendar::turn + day * 1_days;
        const auto a = first.by_expiry.find( expiry );
        const auto b = second.by_expiry.find( expiry );
        const int first_calories = a == first.by_expiry.end() ? 0 : a->second.calories;
        const int second_calories = b == second.by_expiry.end() ? 0 : b->second.calories;
        CHECK( first_calories + second_calories == 1000 );
        CHECK( first_calories == ( day <= 3 ? 1000 : 0 ) );
    }
}

TEST_CASE( "cdda_camp_food_refunds", "[camp][cdda_camp_food]" )
{
    clear_avatar();
    faction *owner = get_player_character().get_faction();
    owner->empty_food_supply();
    on_out_of_scope cleanup( [owner]() {
        owner->empty_food_supply();
    } );
    basecamp camp;
    camp.set_owner( your_fac );
    standard_npc worker;
    worker.set_fac( your_fac );
    const time_point expiry = calendar::turn + 2_days;
    owner->add_to_food_supply( { { expiry, camp_test_food( 100000, 20 ) } } );

    SECTION( "eaten share uses perishable stock and rejected share keeps permanent expiry" ) {
        override_option food_on( "NO_NPC_FOOD", "false" );
        owner->empty_food_supply();
        owner->add_to_food_supply( { { calendar::turn_zero, camp_test_food( 100000, 20 ) },
            { expiry, camp_test_food( 100000, 20 ) }
        } );
        worker.stomach.empty();
        worker.set_hunger( 300 );
        worker.set_stored_kcal( 1000 );
        standard_npc refusing;
        refusing.set_fac( your_fac );
        refusing.add_effect( effect_camp_test_nausea, 10_minutes );
        const camp_food_portion meal = camp.camp_food_supply( -200 );
        const std::vector<std::reference_wrapper<Character>> workers{ worker, refusing };
        CHECK( camp.feed_workers( workers, meal, true ) > 0 );
        const camp_food_portion returned = owner->take_food_supply( camp_test_food( 200000, 40 ) );
        REQUIRE( returned.by_expiry.size() == 1 );
        REQUIRE( returned.by_expiry.count( calendar::turn_zero ) == 1 );
        CHECK( returned.total().calories == 100000 );
        CHECK( returned.total().get_vitamin( vitamin_camp_test ) == 20 );
    }
    SECTION( "zero calorie portions are not consumed and personal vitamins are returned" ) {
        override_option food_on( "NO_NPC_FOOD", "false" );
        owner->empty_food_supply();
        worker.stomach.empty();
        camp_food_portion small{ { { expiry, camp_test_food( 500, 3 ) } } };
        const auto before = worker.stomach.contains();
        CHECK( camp.feed_workers( worker, small, true ) == 0 );
        CHECK( worker.stomach.contains() == before );
        const camp_food_portion returned = owner->take_food_supply( camp_test_food( 500, 3 ) );
        REQUIRE( returned.by_expiry.count( expiry ) == 1 );
        CHECK( returned.total().calories == 500 );
        CHECK( returned.total().get_vitamin( vitamin_camp_test ) == 3 );
        CHECK( camp.feed_workers( worker, {}, false ) == 0 );
        CHECK( worker.stomach.contains() == before );
        CHECK( camp.feed_workers( worker, small, false ) == 0 );
        CHECK( worker.stomach.contains() == before );
        CHECK( owner->food_supply().calories == 0 );
    }
    SECTION( "nauseous worker returns personal meal with its expiry" ) {
        override_option food_on( "NO_NPC_FOOD", "false" );
        worker.add_effect( effect_camp_test_nausea, 10_minutes );
        camp_food_portion meal = camp.camp_food_supply( -100 );
        REQUIRE( owner->food_supply().calories == 0 );
        CHECK( camp.feed_workers( worker, meal, true ) == 0 );
        const camp_food_portion returned = owner->take_food_supply( camp_test_food( 100000, 20 ) );
        REQUIRE( returned.by_expiry.count( expiry ) == 1 );
        CHECK( returned.by_expiry.at( expiry ).calories == 100000 );
        CHECK( returned.by_expiry.at( expiry ).get_vitamin( vitamin_camp_test ) == 20 );
    }
    SECTION( "nauseous worker does not return mission provisions" ) {
        override_option food_on( "NO_NPC_FOOD", "false" );
        worker.add_effect( effect_camp_test_nausea, 10_minutes );
        camp_food_portion meal = camp.camp_food_supply( -100 );
        CHECK( camp.feed_workers( worker, meal ) == 0 );
        CHECK( owner->food_supply().calories == 0 );
    }
    SECTION( "NO_NPC_FOOD refunds personal meals but mission provisions stay spent" ) {
        override_option no_food( "NO_NPC_FOOD", "true" );
        camp_food_portion meal = camp.camp_food_supply( -100 );
        CHECK( camp.feed_workers( worker, meal, true ) == 0 );
        CHECK( owner->food_supply().calories == 100000 );
        meal = camp.camp_food_supply( -100 );
        CHECK( camp.feed_workers( worker, meal ) == 0 );
        CHECK( owner->food_supply().calories == 0 );
    }
}
