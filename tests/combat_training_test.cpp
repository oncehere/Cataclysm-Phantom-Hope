#include "avatar.h"
#include "cata_catch.h"
#include "combat_training.h"
#include "game_constants.h"
#include "player_helpers.h"
#include "skill.h"
#include "type_id.h"

static const skill_id skill_bashing( "bashing" );
static const skill_id skill_dodge( "dodge" );
static const skill_id skill_melee( "melee" );
static const skill_id skill_unarmed( "unarmed" );

TEST_CASE( "combat_training_uses_soft_difficulty_limits", "[skill][combat]" )
{
    CHECK( combat_training_multiplier( 2, 8 ) == 1.0 );
    CHECK( combat_training_multiplier( 8, 8 ) == 1.0 );
    CHECK( combat_training_multiplier( 8, 6 ) == Approx( 1.0 / 3.0 ) );
    CHECK( combat_training_multiplier( 8, 2 ) == Approx( 1.0 / 7.0 ) );
    CHECK( combat_training_multiplier( 20, 0 ) > 0.0 );
    CHECK( combat_training_multiplier( 10, 4 ) < combat_training_multiplier( 8, 4 ) );
}

TEST_CASE( "combat_practice_continues_above_opponent_training_level", "[skill][combat]" )
{
    clear_avatar();
    avatar &you = get_avatar();
    const skill_id id = GENERATE( skill_melee, skill_bashing, skill_unarmed, skill_dodge );
    // The opponent limit is soft; the global skill limit is still hard.
    const int practical_level = MAX_SKILL - 2;
    REQUIRE( practical_level > 2 );
    you.set_skill_level( id, practical_level );
    you.set_focus( 100 );
    REQUIRE( you.get_knowledge_level( id ) == practical_level );
    const int before = you.get_skill_level_object( id ).exercise( true );

    you.practice_combat( id, 90, 2 );

    CHECK( you.get_skill_level_object( id ).exercise( true ) > before );
}

TEST_CASE( "strong_opponents_train_faster_without_changing_other_practice_caps", "[skill][combat]" )
{
    const skill_id id = GENERATE( skill_melee, skill_bashing, skill_unarmed, skill_dodge );
    const int practical_level = MAX_SKILL - 2;
    const int weak_training_level = 2;
    REQUIRE( practical_level > weak_training_level );
    const int reduction_divisor = 1 + practical_level - weak_training_level;
    // Make the scaled amount integral so the exact rate does not depend on RNG rounding.
    const int amount = 10 * reduction_divisor;
    clear_avatar();
    avatar &you = get_avatar();
    you.set_skill_level( id, practical_level );
    you.set_focus( 100 );
    you.practice_combat( id, amount, weak_training_level );
    const int weak_experience = you.get_skill_level_object( id ).exercise( true );
    REQUIRE( weak_experience > 0 );

    clear_avatar();
    you.set_skill_level( id, practical_level );
    you.set_focus( 100 );
    you.practice_combat( id, amount, practical_level );
    CHECK( you.get_skill_level_object( id ).exercise( true ) ==
           weak_experience * reduction_divisor );

    clear_avatar();
    you.set_skill_level( id, practical_level );
    you.set_focus( 100 );
    you.practice( id, amount, weak_training_level, true );
    CHECK( you.get_skill_level_object( id ).exercise( true ) == 0 );

    clear_avatar();
    you.set_skill_level( id, MAX_SKILL );
    you.set_focus( 100 );
    you.practice_combat( id, amount, MAX_SKILL );
    CHECK( you.get_skill_level_object( id ).exercise( true ) == 0 );
}
