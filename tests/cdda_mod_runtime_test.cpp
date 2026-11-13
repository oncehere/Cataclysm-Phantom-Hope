#include <algorithm>
#include <memory>
#include <vector>

#include "avatar.h"
#include "calendar.h"
#include "cata_catch.h"
#include "effect_on_condition.h"
#include "magic_ter_furn_transform.h"
#include "map.h"
#include "map_helpers.h"
#include "mod_id_compat.h"
#include "player_helpers.h"
#include "point.h"
#include "recipe.h"
#include "requirements.h"
#include "type_id.h"
#include "worldfactory.h"

static void require_runtime_mod( const mod_id &id )
{
    REQUIRE( world_generator != nullptr );
    REQUIRE( world_generator->active_world != nullptr );
    INFO( "Required active mod: " << id.str() );
    REQUIRE( mod_id_is_in_active_order( id, world_generator->active_world->active_mod_order ) );
}

static bool recipe_has_component( const recipe &making, const itype_id &id, int count )
{
    for( const auto &alternatives : making.simple_requirements().get_components() ) {
        for( const item_comp &component : alternatives ) {
            if( component.type == id && component.count == count ) {
                return true;
            }
        }
    }
    return false;
}

TEST_CASE( "cdda_innawood_loaded_recipe_autolearn", "[.cdda_mod_runtime][mods]" )
{
    require_runtime_mod( mod_id( "innawood" ) );
    for( const auto &test : {
    std::pair<recipe_id, itype_id> { recipe_id( "mask_filter" ), itype_id( "charcoal" ) },
    { recipe_id( "churn" ), itype_id( "2x4" ) }
         } ) {
        CAPTURE( test.first.str() );
        REQUIRE( test.first.is_valid() );
        const recipe &making = test.first.obj();
        REQUIRE_FALSE( making.autolearn_requirements.empty() );
        CHECK( recipe_has_component( making, test.second, test.first == recipe_id( "churn" ) ? 18 : 10 ) );
        avatar learner;
        CHECK_FALSE( learner.knows_recipe( &making ) );
        for( const auto &required : making.autolearn_requirements ) {
            learner.set_skill_level( required.first, required.second );
            learner.set_knowledge_level( required.first, required.second );
        }
        CHECK( learner.knows_recipe( &making ) );
    }
}

TEST_CASE( "cdda_skyisland_loaded_balthazar_overrides", "[.cdda_mod_runtime][mods]" )
{
    require_runtime_mod( mod_id( "skyisland" ) );
    for( const effect_on_condition_id &id : {
             effect_on_condition_id( "EOC_START_BALTHAZAR_COUNTERS" ),
             effect_on_condition_id( "EOC_DAILY_BALTHAZAR_POWER" )
         } ) {
        CAPTURE( id.str() );
        REQUIRE( id.is_valid() );
        CHECK( id->type == eoc_type::ACTIVATION );
        CHECK( id->true_effect.effects.empty() );
    }
}

TEST_CASE( "cdda_skyisland_mindovermatter_loaded_tear_transform", "[.cdda_mod_runtime][mods]" )
{
    require_runtime_mod( mod_id( "skyisland" ) );
    require_runtime_mod( mod_id( "mindovermatter" ) );
    const field_type_id temporary_tear( "fd_tear_in_reality_temporary" );
    const field_type_id fatigue( "fd_fatigue" );
    const ter_furn_transform_id close_breach( "ter_close_tears_and_portals" );
    REQUIRE( temporary_tear.is_valid() );
    REQUIRE( fatigue.is_valid() );
    REQUIRE( close_breach.is_valid() );
    clear_avatar();
    clear_map_without_vision();
    map &here = get_map();
    const tripoint_bub_ms first = get_avatar().pos_bub() + tripoint::east;
    const tripoint_bub_ms second = get_avatar().pos_bub() + tripoint::west;
    REQUIRE( here.add_field( first, temporary_tear, 1, 0_turns, false ) );
    REQUIRE( here.add_field( second, fatigue, 1, 0_turns, false ) );
    close_breach->transform( here, first );
    close_breach->transform( here, second );
    CHECK( here.get_field( first, temporary_tear ) == nullptr );
    CHECK( here.get_field( second, fatigue ) == nullptr );
}
