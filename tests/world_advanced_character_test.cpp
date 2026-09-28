#include <string>

#include "avatar.h"
#include "calendar.h"
#include "cata_catch.h"
#include "character.h"
#include "npc.h"
#include "options.h"
#include "player_helpers.h"
#include "rng.h"
#include "type_id.h"
#include "world_advanced_options.h"

namespace
{
class character_world_rules_scope
{
    public:
        world_advanced_options rules;
        character_world_rules_scope() : previous( active_world_advanced_options() ),
            random_state( rng_get_engine() ) {
            set_active_world_advanced_options( &rules );
            options_manager::update_options_cache();
        }
        ~character_world_rules_scope() {
            set_active_world_advanced_options( previous );
            options_manager::update_options_cache();
            rng_get_engine() = random_state;
        }
        void set( const std::string &id, const std::string &value ) {
            std::string error;
            INFO( id << "=" << value );
            REQUIRE( rules.set( id, value, error ) );
            options_manager::update_options_cache();
        }
    private:
        const world_advanced_options *previous;
        cata_default_random_engine random_state;
};
} // namespace

TEST_CASE( "world_advanced_character_limits_needs_and_healing_use_effective_rules",
           "[world_advanced][character][stamina][heal]" )
{
    character_world_rules_scope scope;
    avatar player;
    npc companion;
    clear_character( player );
    clear_character( companion );
    player.set_lifestyle( 0 );
    companion.set_lifestyle( 0 );
    const float inherited_player_healing = player.healing_rate( 1.0f );
    const float inherited_npc_healing = companion.healing_rate( 1.0f );
    player.set_str_base( 40 );
    player.set_dex_base( 40 );
    player.set_per_base( 40 );
    player.set_int_base( 40 );
    companion.set_str_base( 40 );
    scope.set( "PLAYER_MAX_STR_VALUE", "12" );
    scope.set( "PLAYER_MAX_DEX_VALUE", "13" );
    scope.set( "PLAYER_MAX_PER_VALUE", "14" );
    scope.set( "PLAYER_MAX_INT_VALUE", "15" );
    CHECK( player.get_str() == 12 );
    CHECK( player.get_dex() == 13 );
    CHECK( player.get_per() == 14 );
    CHECK( player.get_int() == 15 );
    CHECK( companion.get_str() == 12 );

    scope.set( "PLAYER_CARDIOFIT_STAMINA_SCALING", "0" );
    scope.set( "PLAYER_MAX_STAMINA_BASE", "2000" );
    CHECK( player.get_stamina_max() == 2000 );
    scope.set( "PLAYER_MAX_STAMINA_BASE", "4000" );
    CHECK( player.get_stamina_max() == 4000 );
    player.set_stamina( 0 );
    player.mod_stamina( 8000 );
    CHECK( player.get_stamina() == 4000 );

    scope.set( "PLAYER_HUNGER_RATE", "0" );
    scope.set( "PLAYER_THIRST_RATE", "0" );
    scope.set( "PLAYER_SLEEPINESS_RATE", "0" );
    scope.set( "PLAYER_HEALING_RATE", "0" );
    scope.set( "NPC_HEALING_RATE", "0" );
    const needs_rates suppressed = player.calc_needs_rates();
    CHECK( suppressed.hunger == 0 );
    CHECK( suppressed.thirst == 0 );
    CHECK( suppressed.sleepiness == 0 );
    CHECK( player.healing_rate( 1.0f ) == 0 );
    CHECK( companion.healing_rate( 1.0f ) == 0 );

    scope.set( "PLAYER_HUNGER_RATE", "2" );
    scope.set( "PLAYER_THIRST_RATE", "3" );
    scope.set( "PLAYER_SLEEPINESS_RATE", "4" );
    scope.set( "PLAYER_HEALING_RATE", "0.0004" );
    scope.set( "NPC_HEALING_RATE", "0.0008" );
    const needs_rates active = player.calc_needs_rates();
    CHECK( active.hunger > 0 );
    CHECK( active.thirst == Approx( 3 ) );
    CHECK( active.sleepiness == Approx( 4 ) );
    CHECK( player.healing_rate( 1.0f ) == Approx( 0.0004 ) );
    CHECK( companion.healing_rate( 1.0f ) == Approx( 0.0008 ) );
    CHECK( player.healing_rate( 0.0f ) == 0 );
    scope.rules.clear();
    options_manager::update_options_cache();
    CHECK( player.healing_rate( 1.0f ) == Approx( inherited_player_healing ) );
    CHECK( companion.healing_rate( 1.0f ) == Approx( inherited_npc_healing ) );
}

TEST_CASE( "world_advanced_learning_rules_change_npc_proficiency_progress",
           "[world_advanced][npc][proficiency]" )
{
    character_world_rules_scope scope;
    npc learner;
    clear_character( learner );
    const proficiency_id proficiency( "prof_test" );
    REQUIRE( proficiency.is_valid() );
    learner.set_int_base( 12 );
    scope.set( "INT_BASED_LEARNING_BASE_VALUE", "8" );
    scope.set( "INT_BASED_LEARNING_FOCUS_ADJUSTMENT", "0" );
    scope.set( "PROFICIENCY_TRAINING_SPEED", "1" );
    learner.set_focus( 100 );
    REQUIRE_FALSE( learner.practice_proficiency( proficiency, 1_hours ) );
    const time_duration neutral_progress = learner.get_proficiency_practiced_time( proficiency );
    REQUIRE( neutral_progress == 1_hours );

    learner.set_proficiency_practice( proficiency, 0_seconds );
    learner.set_focus( 100 );
    scope.set( "INT_BASED_LEARNING_FOCUS_ADJUSTMENT", "10" );
    REQUIRE_FALSE( learner.practice_proficiency( proficiency, 1_hours ) );
    CHECK( learner.get_proficiency_practiced_time( proficiency ) > neutral_progress );

    scope.set( "INT_BASED_LEARNING_FOCUS_ADJUSTMENT", "0" );
    learner.set_proficiency_practice( proficiency, 0_seconds );
    learner.set_focus( 100 );
    REQUIRE_FALSE( learner.practice_proficiency( proficiency, 12_hours ) );
    CHECK_FALSE( learner.has_proficiency( proficiency ) );
    learner.set_proficiency_practice( proficiency, 0_seconds );
    learner.set_focus( 100 );
    scope.set( "PROFICIENCY_TRAINING_SPEED", "2" );
    CHECK( learner.practice_proficiency( proficiency, 12_hours ) );
    CHECK( learner.has_proficiency( proficiency ) );

    learner.lose_proficiency( proficiency, true );
    learner.set_focus( 100 );
    scope.set( "PROFICIENCY_TRAINING_SPEED", "0" );
    CHECK_FALSE( learner.practice_proficiency( proficiency, 48_hours ) );
    CHECK_FALSE( learner.has_proficiency( proficiency ) );
    CHECK( learner.get_proficiency_practiced_time( proficiency ) == 0_seconds );
}
