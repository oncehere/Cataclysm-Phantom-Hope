#if defined(CATA_ENABLE_LUA_PLATFORM) && CATA_ENABLE_LUA_PLATFORM

#include <array>
#include <cstddef>
#include <functional>
#include <optional>

#include "avatar.h"
#include "bodypart.h"
#include "calendar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "character.h"
#include "character_id.h"
#include "event.h"
#include "event_bus.h"
#include "game.h"
#include "item.h"
#include "itype.h"
#include "lua_platform_runtime.h"
#include "map.h"
#include "map_helpers.h"
#include "npc.h"
#include "options_helpers.h"
#include "player_helpers.h"
#include "point.h"
#include "type_id.h"
#include "vitamin.h"

static const bodypart_str_id body_part_torso( "torso" );
static const efftype_id effect_fcl_cureall( "fcl_cureall" );
static const efftype_id effect_stunned( "stunned" );
static const itype_id itype_panacea( "panacea" );
static const vitamin_id vitamin_blood( "blood" );
static const vitamin_id vitamin_calcium( "calcium" );
static const vitamin_id vitamin_iron( "iron" );
static const vitamin_id vitamin_redcells( "redcells" );
static const vitamin_id vitamin_vitC( "vitC" );

namespace
{
using vitamin_state = std::array<int, 5>;

const std::array<vitamin_id, 5> vitamins = {
    vitamin_calcium, vitamin_iron, vitamin_vitC, vitamin_redcells, vitamin_blood
};

vitamin_state read_vitamins( const Character &patient )
{
    vitamin_state result;
    for( std::size_t index = 0; index < vitamins.size(); ++index ) {
        result[index] = patient.vitamin_get( vitamins[index] );
    }
    return result;
}

void set_vitamins( Character &patient, const vitamin_state &values )
{
    for( std::size_t index = 0; index < vitamins.size(); ++index ) {
        REQUIRE( vitamins[index].is_valid() );
        patient.vitamin_set( vitamins[index], values[index] );
    }
    REQUIRE( read_vitamins( patient ) == values );
}
} // namespace

// Run explicitly with --mods catalegacy_future. The item is panacea;
// fcl_cureall is the effect its real consume_drug action adds.
TEST_CASE( "fcl_lua_panacea_applies_vitamin_rules_to_the_actual_user",
           "[.][lua][mods][catalegacy_future]" )
{
    INFO( "This gameplay regression requires --mods catalegacy_future" );
    REQUIRE( g != nullptr );
    REQUIRE( effect_fcl_cureall.is_valid() );
    REQUIRE( itype_panacea.is_valid() );
    const override_option vitamins_enabled( "NO_VITAMINS", "false" );
    clear_map_without_vision();
    clear_avatar();
    const on_out_of_scope cleanup( []() {
        clear_npcs();
        clear_avatar();
    } );
    avatar &player = get_avatar();
    npc &other = spawn_npc( player.pos_bub().xy() + point::east, "thug" );
    clear_character( other, true );
    REQUIRE( g->find_npc( other.getID() ) == &other );
    cata::lua_platform::runtime_world_ready( true );

    const bool npc_user = GENERATE( false, true );
    Character &patient = npc_user ? static_cast<Character &>( other ) : player;
    Character &bystander = npc_user ? static_cast<Character &>( player ) : other;
    struct blood_case {
        int redcells_before;
        int blood_before;
        int redcells_after;
        int blood_after;
        int iron_before;
        int iron_after;
    };
    // Literal expectations from Lua: add 1000 before applying the lower
    // bounds -5000/-2500. Native vitamins.set also clamps at each maximum.
    const std::array<blood_case, 5> cases = {{
            { -8000, -5000, -5000, -2500, -100, 0 },
            { -6000, -3500, -5000, -2500, 0, 0 },
            { -5000, -2500, -4000, -1500, 250, 250 },
            { -1500, -1500, -500, -500, -20, 0 },
            { -500, 0, 0, 0, -50, 0 },
        }
    };
    const int case_index = GENERATE( 0, 1, 2, 3, 4 );
    const blood_case &sample = cases[case_index];
    CAPTURE( npc_user, case_index );
    REQUIRE( vitamin_redcells->max() == 0 );
    REQUIRE( vitamin_blood->max() == 0 );
    set_vitamins( patient, { -120, sample.iron_before, -180,
                             sample.redcells_before, sample.blood_before
                           } );
    const vitamin_state spectator_values = { -321, -222, -123, -4321, -3210 };
    set_vitamins( bystander, spectator_values );
    REQUIRE_FALSE( patient.has_effect( effect_fcl_cureall ) );

    item dose( itype_panacea, calendar::turn );
    REQUIRE( dose.type->can_use( "consume_drug" ) );
    map &here = get_map();
    const std::optional<int> result = dose.type->invoke(
                                          &patient, dose, &here, patient.pos_bub( here ), "consume_drug" );
    REQUIRE( result.has_value() );
    CHECK( *result == 1 );
    REQUIRE( patient.has_effect( effect_fcl_cureall ) );
    const vitamin_state expected = { 0, sample.iron_after, 0,
                                     sample.redcells_after, sample.blood_after
                                   };
    CHECK( read_vitamins( patient ) == expected );
    CHECK( read_vitamins( bystander ) == spectator_values );
}

TEST_CASE( "fcl_lua_cureall_ignores_unrelated_and_unresolved_effect_events",
           "[.][lua][mods][catalegacy_future]" )
{
    INFO( "This gameplay regression requires --mods catalegacy_future" );
    REQUIRE( g != nullptr );
    REQUIRE( effect_fcl_cureall.is_valid() );
    REQUIRE( effect_stunned.is_valid() );
    const override_option vitamins_enabled( "NO_VITAMINS", "false" );
    clear_map_without_vision();
    clear_avatar();
    const on_out_of_scope cleanup( []() {
        clear_avatar();
    } );
    avatar &patient = get_avatar();
    cata::lua_platform::runtime_world_ready( true );
    const vitamin_state before = { -120, -100, -180, -8000, -5000 };
    set_vitamins( patient, before );

    SECTION( "another_effect_does_not_apply_the_cureall_rules" ) {
        patient.add_effect( effect_stunned, 1_minutes );
        REQUIRE( patient.has_effect( effect_stunned ) );
    }
    SECTION( "an_event_without_a_resolvable_character_does_not_target_the_avatar" ) {
        const character_id absent( 19581015 );
        REQUIRE( patient.getID() != absent );
        REQUIRE( g->find_npc( absent ) == nullptr );
        // The public event bridge omits actors.character for an unknown ID.
        // consume_drug itself does not promise to accept a null Character.
        get_event_bus().send<event_type::character_gains_effect>(
            absent, body_part_torso.id(), effect_fcl_cureall, 1 );
    }
    CHECK_FALSE( patient.has_effect( effect_fcl_cureall ) );
    CHECK( read_vitamins( patient ) == before );
}

#endif
