#include <algorithm>
#include <cstdlib>
#include <map>
#include <memory>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

#include "avatar.h"
#include "cata_catch.h"
#include "flag.h"
#include "inventory.h"
#include "item.h"
#include "item_factory.h"
#include "item_location.h"
#include "itype.h"
#include "melee.h"
#include "monster.h"
#include "player_helpers.h"
#include "recipe.h"
#include "recipe_dictionary.h"
#include "requirements.h"
#include "ret_val.h"
#include "sounds.h"
#include "string_formatter.h"
#include "test_data.h"
#include "type_id.h"

static const itype_id itype_test_balanced_sword( "test_balanced_sword" );
static const itype_id itype_test_clumsy_sword( "test_clumsy_sword" );
static const itype_id itype_test_normal_sword( "test_normal_sword" );

static const mtype_id mon_zombie_smoker_no_weakpoints( "mon_zombie_smoker_no_weakpoints" );
static const mtype_id mon_zombie_soldier_no_weakpoints( "mon_zombie_soldier_no_weakpoints" );
static const mtype_id mon_zombie_survivor_no_weakpoints( "mon_zombie_survivor_no_weakpoints" );
static const mtype_id pseudo_debug_mon( "pseudo_debug_mon" );

static const skill_id skill_bashing( "bashing" );
static const skill_id skill_cutting( "cutting" );
static const skill_id skill_melee( "melee" );
static const skill_id skill_stabbing( "stabbing" );
static const skill_id skill_unarmed( "unarmed" );

// Run a large number of trials of a player attacking a monster with a given weapon,
// and return the average damage done per second.
static double weapon_dps_trials( avatar &attacker, monster &defender, item &weapon )
{
    constexpr int trials = 1000;

    int total_damage = 0;
    int total_moves = 0;

    clear_character( attacker );
    REQUIRE( attacker.can_wield( weapon ).success() );

    melee::clear_stats();
    melee_statistic_data melee_stats = melee::get_stats();
    // rerun the trials in groups of 1000 until 100 crits occur
    for( int i = 0; i < 10 && melee_stats.actual_crit_count < 100;
         i++, melee_stats = melee::get_stats() ) {
        for( int j = 0; j < trials; j++ ) {
            // Reset and re-wield weapon before each attack to prevent skill-up during trials
            clear_character( attacker );
            attacker.wield( weapon );
            // Verify that wielding worked (and not e.g. using martial arts instead)
            REQUIRE( !!attacker.used_weapon() );
            REQUIRE( attacker.used_weapon()->type == weapon.type );

            int before_moves = attacker.get_moves();

            // Keep the defender at maximum health
            const int starting_hp = defender.get_hp_max();
            defender.set_hp( starting_hp );

            // Attack once
            attacker.melee_attack_abstract( defender, false, matec_id( "" ) );

            // Tally total damage and moves
            total_damage += std::max( 0, starting_hp - defender.get_hp() );
            total_moves += std::abs( attacker.get_moves() - before_moves );

            // Every hit or miss enqueues a new sound
            // Ideally, we'd have sound vector get cleared after every test, but it's not easy
            sounds::reset_sounds();
        }
    }

    // Scale damage-per-move to damage-per-second
    // 1 second == 100 moves
    return 100.0f * total_damage / total_moves;
}

// Compare actual DPS with estimated effective DPS for an attacker/defender/weapon combo.
static void check_actual_dps( avatar &attacker, monster &defender, item &weapon )
{
    clear_character( attacker );
    double expect_dps = weapon.effective_dps( attacker, defender );
    double actual_dps = weapon_dps_trials( attacker, defender, weapon );
    CHECK( actual_dps == Approx( expect_dps ).epsilon( 0.2f ) );
}

static void check_accuracy_dps( avatar &attacker, monster &defender, item &wpn1, item &wpn2,
                                item &wpn3 )
{
    clear_character( attacker );
    melee::clear_stats();
    double dps_wpn1 = weapon_dps_trials( attacker, defender, wpn1 );
    const melee_statistic_data wpn1_stats = melee::get_stats();
    melee::clear_stats();
    double dps_wpn2 = weapon_dps_trials( attacker, defender, wpn2 );
    const melee_statistic_data wpn2_stats = melee::get_stats();
    melee::clear_stats();
    double dps_wpn3 = weapon_dps_trials( attacker, defender, wpn3 );
    const melee_statistic_data wpn3_stats = melee::get_stats();
    REQUIRE( wpn1_stats.hit_count > 0 );
    REQUIRE( wpn2_stats.hit_count > 0 );
    REQUIRE( wpn3_stats.hit_count > 0 );
    CAPTURE( wpn1_stats.attack_count );
    CAPTURE( wpn2_stats.attack_count );
    CAPTURE( wpn3_stats.attack_count );
    double wpn1_hit_rate = static_cast<double>( wpn1_stats.hit_count ) / wpn1_stats.attack_count;
    double wpn2_hit_rate = static_cast<double>( wpn2_stats.hit_count ) / wpn2_stats.attack_count;
    double wpn3_hit_rate = static_cast<double>( wpn3_stats.hit_count ) / wpn3_stats.attack_count;
    CHECK( wpn2_hit_rate > wpn1_hit_rate );
    CHECK( wpn3_hit_rate > wpn2_hit_rate );
    CHECK( dps_wpn2 > dps_wpn1 );
    CHECK( dps_wpn3 > dps_wpn2 );
}
TEST_CASE( "effective_damage_per_second", "[effective][dps]" )
{
    avatar &dummy = get_avatar();
    clear_character( dummy );

    item clumsy_sword( itype_test_clumsy_sword );
    item normal_sword( itype_test_normal_sword );
    item good_sword( itype_test_balanced_sword );

    SECTION( "against a debug monster with no armor or dodge" ) {
        monster mummy( pseudo_debug_mon );

        CHECK( clumsy_sword.effective_dps( dummy, mummy ) == Approx( 25.0f ).epsilon( 0.15f ) );
        CHECK( good_sword.effective_dps( dummy, mummy ) == Approx( 38.0f ).epsilon( 0.15f ) );
    }

    SECTION( "against an agile target" ) {
        monster smoker( mon_zombie_smoker_no_weakpoints );
        REQUIRE( smoker.get_dodge() >= 4 );

        CHECK( clumsy_sword.effective_dps( dummy, smoker ) == Approx( 11.0f ).epsilon( 0.15f ) );
        CHECK( good_sword.effective_dps( dummy, smoker ) == Approx( 25.0f ).epsilon( 0.15f ) );
    }

    SECTION( "against an armored target" ) {
        monster soldier( mon_zombie_soldier_no_weakpoints );

        CHECK( clumsy_sword.effective_dps( dummy, soldier ) == Approx( 8.0f ).epsilon( 0.15f ) );
        CHECK( good_sword.effective_dps( dummy, soldier ) == Approx( 15.0f ).epsilon( 0.15f ) );
    }

    SECTION( "effect of STR and DEX on damage per second" ) {
        monster mummy( pseudo_debug_mon );

        SECTION( "STR 6, DEX 6" ) {
            dummy.set_str_base( 6 );
            dummy.set_dex_base( 6 );

            CHECK( clumsy_sword.effective_dps( dummy, mummy ) == Approx( 20.0f ).epsilon( 0.15f ) );
            CHECK( normal_sword.effective_dps( dummy, mummy ) == Approx( 26.0f ).epsilon( 0.15f ) );
            CHECK( good_sword.effective_dps( dummy, mummy ) == Approx( 33.0f ).epsilon( 0.15f ) );
        }

        SECTION( "STR 8, DEX 10" ) {
            dummy.set_str_base( 8 );
            dummy.set_dex_base( 10 );

            CHECK( clumsy_sword.effective_dps( dummy, mummy ) == Approx( 25.0f ).epsilon( 0.15f ) );
            CHECK( normal_sword.effective_dps( dummy, mummy ) == Approx( 32.0f ).epsilon( 0.15f ) );
            CHECK( good_sword.effective_dps( dummy, mummy ) == Approx( 38.0f ).epsilon( 0.15f ) );
        }

        SECTION( "STR 10, DEX 10" ) {
            dummy.set_str_base( 10 );
            dummy.set_dex_base( 10 );

            CHECK( clumsy_sword.effective_dps( dummy, mummy ) == Approx( 27.0f ).epsilon( 0.15f ) );
            CHECK( normal_sword.effective_dps( dummy, mummy ) == Approx( 34.0f ).epsilon( 0.15f ) );
            CHECK( good_sword.effective_dps( dummy, mummy ) == Approx( 41.0f ).epsilon( 0.15f ) );
        }
    }
}

TEST_CASE( "effective_vs_actual_damage_per_second", "[actual][dps][!mayfail]" )
{
    avatar &dummy = get_avatar();
    clear_character( dummy );

    monster soldier( mon_zombie_soldier_no_weakpoints );
    monster smoker( mon_zombie_smoker_no_weakpoints );
    monster survivor( mon_zombie_survivor_no_weakpoints );

    item clumsy_sword( itype_test_clumsy_sword );
    item normal_sword( itype_test_normal_sword );
    item good_sword( itype_test_balanced_sword );

    SECTION( "soldier zombie" ) {
        check_actual_dps( dummy, soldier, clumsy_sword );
        check_actual_dps( dummy, soldier, normal_sword );
        check_actual_dps( dummy, soldier, good_sword );
    }

    SECTION( "smoker zombie" ) {
        check_actual_dps( dummy, smoker, clumsy_sword );
        check_actual_dps( dummy, smoker, normal_sword );
        check_actual_dps( dummy, smoker, good_sword );
    }

    SECTION( "survivor zombie" ) {
        check_actual_dps( dummy, survivor, clumsy_sword );
        check_actual_dps( dummy, survivor, normal_sword );
        check_actual_dps( dummy, survivor, good_sword );
    }
}

TEST_CASE( "accuracy_increases_success", "[accuracy][dps]" )
{
    avatar &dummy = get_avatar();
    clear_character( dummy );

    monster soldier( mon_zombie_soldier_no_weakpoints );
    monster smoker( mon_zombie_smoker_no_weakpoints );
    monster survivor( mon_zombie_survivor_no_weakpoints );

    item clumsy_sword( itype_test_clumsy_sword );
    item normal_sword( itype_test_normal_sword );
    item good_sword( itype_test_balanced_sword );

    SECTION( "soldier zombie" ) {
        check_accuracy_dps( dummy, soldier, clumsy_sword, normal_sword, good_sword );
    }

    SECTION( "smoker zombie" ) {
        check_accuracy_dps( dummy, smoker, clumsy_sword, normal_sword, good_sword );
    }

    SECTION( "survivor zombie" ) {
        check_accuracy_dps( dummy, survivor, clumsy_sword, normal_sword, good_sword );
    }
}

static void make_experienced_tester( avatar &test_guy )
{
    clear_character( test_guy );
    test_guy.set_str_base( 10 );
    test_guy.set_dex_base( 10 );
    test_guy.set_int_base( 10 );
    test_guy.set_per_base( 10 );
    test_guy.set_str_bonus( 0 );
    test_guy.set_dex_bonus( 0 );
    test_guy.set_int_bonus( 0 );
    test_guy.set_per_bonus( 0 );
    test_guy.reset_bonuses();
    test_guy.set_speed_base( 100 );
    test_guy.set_speed_bonus( 0 );
    test_guy.set_body();
    test_guy.set_all_parts_hp_to_max();

    test_guy.set_skill_level( skill_bashing, 4 );
    test_guy.set_skill_level( skill_cutting, 4 );
    test_guy.set_skill_level( skill_stabbing, 4 );
    test_guy.set_skill_level( skill_unarmed, 4 );
    test_guy.set_skill_level( skill_melee, 4 );

    REQUIRE( test_guy.get_str() == 10 );
    REQUIRE( test_guy.get_dex() == 10 );
    REQUIRE( test_guy.get_per() == 10 );
    REQUIRE( static_cast<int>( test_guy.get_skill_level( skill_bashing ) ) == 4 );
    REQUIRE( static_cast<int>( test_guy.get_skill_level( skill_cutting ) ) == 4 );
    REQUIRE( static_cast<int>( test_guy.get_skill_level( skill_stabbing ) ) == 4 );
    REQUIRE( static_cast<int>( test_guy.get_skill_level( skill_unarmed ) ) == 4 );
    REQUIRE( static_cast<int>( test_guy.get_skill_level( skill_melee ) ) == 4 );
}

/*
 * A super tedious set of test cases to make sure that weapon values do not drift too far out
 * of range without anyone noticing them and adjusting them.
 * The weapons that *must* be enumerated include anything with a DPS over 25,
 * essentially candidates for pushing into the top tier of weapons.
 * Additionally we want to test a bunch of misc makeshift items to get coverage of
 * shifts in the lwer tiers of weapons.
 * Used expected_dps(), which should make actual dps because of the calculations above.
 */
TEST_CASE( "expected_weapon_dps", "[expected][dps]" )
{
    avatar &test_guy = get_avatar();
    make_experienced_tester( test_guy );

    REQUIRE_FALSE( test_data::expected_dps.empty() );

    const auto calc_expected_dps = [&test_guy]( const itype_id & weapon_id ) {
        item weapon( weapon_id );
        return Approx( test_guy.melee_value( weapon ) ).margin( 0.5 );
    };

    std::unordered_set<itype_id> tested;
    for( std::pair<const itype_id, double> &weap : test_data::expected_dps ) {
        if( weap.first->src.empty() || weap.first->src.back().second.str() != "ccb" ) {
            continue;
        }
        tested.emplace( weap.first );
        INFO( string_format( "%s's dps changed, if it's intended replace the value in the respective file in data/mods/TEST_DATA/expected_dps_data.",
                             weap.first.str() ) );
        CHECK( calc_expected_dps( weap.first ) == weap.second );
    }

    for( const itype *it : item_controller->all() ) {
        if( it->src.empty() || it->src.back().second.str() != "ccb" ) {
            continue;
        }
        if( it->has_flag( flag_PSEUDO ) ) {
            continue;
        }
        if( !item( it ).is_melee() ) {
            continue;
        }
        if( tested.find( it->get_id() ) != tested.end() ) {
            continue;
        }
        INFO( string_format( "'%s' is a weapon, but is not included in DPS tests.  Please place it in the appropriate file in data/mods/TEST_DATA/expected_dps_data.",
                             it->get_id().str() ) );
        CHECK( calc_expected_dps( it->get_id() ) <= 25.0 );
    }
}

TEST_CASE( "cph_selected_spear_damage_and_actual_dps", "[spear][dps]" )
{
    // I-0622 deliberately keeps the tempered spear's extra bash damage.
    const std::vector<std::pair<std::string, std::pair<int, int>>> damage = {
        { "spear_spike", { 4, 19 } },
        { "spear_knife_superior", { 4, 22 } },
        { "spear_knife_proper", { 4, 22 } },
        { "spear_homemade_halfpike", { 4, 20 } },
        { "spear_steel_crude", { 4, 20 } },
        { "spear_pipe", { 7, 20 } },
        { "spear_knife", { 4, 22 } },
        { "crude_goedendag", { 22, 6 } },
        { "qt_spear_steel", { 8, 35 } }
    };
    avatar &attacker = get_avatar();
    for( const auto &entry : damage ) {
        const item weapon( itype_id( entry.first ) );
        CAPTURE( entry.first );
        CHECK( weapon.damage_melee( damage_type_id( "bash" ) ) == entry.second.first );
        CHECK( weapon.damage_melee( damage_type_id( "stab" ) ) == entry.second.second );
        make_experienced_tester( attacker );
        const double rated_dps = attacker.melee_value( weapon );
        for( const mtype_id &target : {
                 mon_zombie_smoker_no_weakpoints, mon_zombie_soldier_no_weakpoints
             } ) {
            monster defender( target );
            item trial_weapon = weapon;
            clear_character( attacker );
            const double estimated = weapon.effective_dps( attacker, defender );
            const double actual = weapon_dps_trials( attacker, defender, trial_weapon );
            WARN( entry.first << " target=" << target.str() << " rated=" << rated_dps
                  << " estimated=" << estimated << " actual=" << actual );
            CHECK( actual == Approx( estimated ).epsilon( 0.2 ) );
        }
    }
}

TEST_CASE( "cph_selected_spear_crafting_requirements", "[spear][crafting]" )
{
    struct spear_recipe {
        std::string id;
        int difficulty;
        int minutes;
        int hammer;
    };
    const std::vector<spear_recipe> recipes = {
        { "spear_steel_crude", 3, 90, 3 },
        { "spear_knife_superior", 2, 90, 3 },
        { "spear_knife_superior_from simple version", 2, 30, 1 },
        { "spear_knife_proper", 3, 150, 3 }
    };
    avatar &crafter = get_avatar();
    for( const spear_recipe &entry : recipes ) {
        CAPTURE( entry.id );
        const recipe_id rid( entry.id );
        REQUIRE( rid.is_valid() );
        const recipe &rec = rid.obj();
        CHECK( rec.difficulty == entry.difficulty );
        clear_character( crafter );
        crafter.add_proficiency( proficiency_id( "prof_carving" ), true );
        CHECK( rec.batch_time( crafter, 1, 1.0, 0, {} ) == entry.minutes * 60 * 100 );

        inventory components;
        for( const std::vector<item_comp> &alternatives : rec.simple_requirements().get_components() ) {
            REQUIRE_FALSE( alternatives.empty() );
            const item_comp &component = alternatives.front();
            for( int i = 0; i < component.count; ++i ) {
                components.add_item( item( component.type ), false, false );
            }
        }
        components.add_item( item( itype_id( "knife_combat" ) ), false, false );

        // Exercise the same available recipe and nested recipe sources used by the crafting menu.
        crafter.set_skill_level( skill_id( "fabrication" ), entry.difficulty - 1 );
        crafter.set_knowledge_level( skill_id( "fabrication" ), entry.difficulty - 1 );
        CHECK_FALSE( crafter.get_group_available_recipes( &components ).contains( &rec ) );
        crafter.set_skill_level( skill_id( "fabrication" ), entry.difficulty );
        crafter.set_knowledge_level( skill_id( "fabrication" ), entry.difficulty );
        const recipe_subset &available = crafter.get_group_available_recipes( &components );
        CHECK( available.contains( &rec ) );
        bool nested_visible = false;
        for( const recipe *parent : crafter.get_available_nested( available ) ) {
            nested_visible |= parent->nested_category_data.count( rid ) != 0;
        }
        CHECK( nested_visible );

        for( const bool proper_hammer : {
                 false, true
             } ) {
            for( const bool proper_drill : {
                     false, true
                 } ) {
                inventory tools = components;
                tools.add_item( item( itype_id( proper_hammer ? "hammer" : "rock" ) ), false, false );
                tools.add_item( item( itype_id( proper_drill ? "hand_drill" : "makeshift_hand_drill" ) ),
                                false, false );
                const bool expected = proper_drill && ( proper_hammer || entry.hammer == 1 );
                CAPTURE( proper_hammer, proper_drill );
                CHECK( rec.deduped_requirements().can_make_with_inventory( &crafter, tools,
                        rec.get_component_filter() ) == expected );
            }
        }
    }
}
