#include <map>

#include "avatar.h"
#include "bodypart.h"
#include "cata_catch.h"
#include "damage.h"
#include "game.h"
#include "item.h"
#include "map.h"
#include "map_helpers.h"
#include "map_helpers_tests.h"
#include "player_helpers.h"
#include "rng.h"
#include "trap.h"
#include "type_id.h"
#include "units.h"

namespace
{

using pit_trigger = bool ( * )( const tripoint_bub_ms &, Creature *, item * );

std::map<bodypart_id, int> hit_points( const avatar &player )
{
    std::map<bodypart_id, int> result;
    for( const bodypart_id &bp : player.get_all_body_parts( get_body_part_flags::only_main ) ) {
        result[bp] = player.get_part_hp_cur( bp );
    }
    return result;
}

void prepare_pit( const ter_id &terrain )
{
    clear_creatures();
    clear_avatar();
    clear_map_without_vision();
    avatar &player = get_avatar();
    player.set_dodges_left( 1 );
    get_map().ter_set( player.pos_bub(), terrain );
}

} // namespace

TEST_CASE( "ordinary_pit_damages_main_limbs_with_armor_aware_bash", "[trap][pit][damage]" )
{
    prepare_pit( ter_id( "t_pit" ) );
    avatar &player = get_avatar();
    player.set_dex_base( 0 );
    REQUIRE( player.get_dodge() == 0.0f );
    const std::map<bodypart_id, int> before = hit_points( player );

    REQUIRE( trapfunc::pit( player.pos_bub(), &player, nullptr ) );
    const int torso_damage = before.at( bodypart_id( "torso" ) ) - player.get_part_hp_cur(
                                 bodypart_id( "torso" ) );
    REQUIRE( torso_damage >= 6 );
    REQUIRE( torso_damage <= 12 );
    for( const auto &[bp, hp] : before ) {
        const int damage = hp - player.get_part_hp_cur( bp );
        CHECK( damage == ( bp->primary_limb_type() == bp_type::leg ? 2 * torso_damage :
                           torso_damage ) );
    }
}

TEST_CASE( "ordinary_pit_bash_is_blocked_by_armor", "[trap][pit][damage]" )
{
    prepare_pit( ter_id( "t_pit" ) );
    avatar &player = get_avatar();
    player.set_dex_base( 0 );
    REQUIRE( player.wear_item( item( itype_id( "test_power_armor" ) ), false ) );
    REQUIRE( player.get_dodge() == 0.0f );
    REQUIRE( player.get_armor_type( damage_type_id( "bash" ), bodypart_id( "torso" ) ) > 12 );
    const std::map<bodypart_id, int> before = hit_points( player );

    REQUIRE( trapfunc::pit( player.pos_bub(), &player, nullptr ) );
    CHECK( player.get_part_hp_cur( bodypart_id( "torso" ) ) == before.at( bodypart_id( "torso" ) ) );
    CHECK( player.get_part_hp_cur( bodypart_id( "head" ) ) < before.at( bodypart_id( "head" ) ) );
}

TEST_CASE( "spiked_and_glass_pits_can_damage_each_main_limb", "[trap][pit][damage]" )
{
    const bool spiked = GENERATE( true, false );
    CAPTURE( spiked );
    prepare_pit( ter_id( spiked ? "t_pit_spiked" : "t_pit_glass" ) );
    avatar &player = get_avatar();
    player.set_dex_base( 0 );
    REQUIRE( player.get_dodge() == 0.0f );
    const std::map<bodypart_id, int> before = hit_points( player );

    const pit_trigger trigger = spiked ? trapfunc::pit_spikes : trapfunc::pit_glass;
    REQUIRE( trigger( player.pos_bub(), &player, nullptr ) );
    REQUIRE( before.size() >= 6 );
    for( const auto &[bp, hp] : before ) {
        CHECK( player.get_part_hp_cur( bp ) < hp );
    }
}

TEST_CASE( "spiked_pit_uses_stab_and_bash_when_spikes_miss", "[trap][pit][damage]" )
{
    prepare_pit( ter_id( "t_pit_spiked" ) );
    avatar &player = get_avatar();
    player.set_dex_base( 0 );
    REQUIRE( player.wear_item( item( itype_id( "test_zentai_resist_stab_cut" ) ), false ) );
    REQUIRE( player.get_armor_type( damage_type_id( "stab" ), bodypart_id( "torso" ) ) > 20 );
    REQUIRE( player.get_armor_type( damage_type_id( "bash" ), bodypart_id( "torso" ) ) < 5 );
    const std::map<bodypart_id, int> before = hit_points( player );

    rng_set_engine_seed( 88166 );
    REQUIRE( trapfunc::pit_spikes( player.pos_bub(), &player, nullptr ) );
    int protected_limbs = 0;
    int bruised_limbs = 0;
    for( const auto &[bp, hp] : before ) {
        protected_limbs += player.get_part_hp_cur( bp ) == hp;
        bruised_limbs += player.get_part_hp_cur( bp ) < hp;
    }
    CHECK( protected_limbs > 0 );
    CHECK( bruised_limbs > 0 );
}

TEST_CASE( "partially_filled_pits_use_bash_when_sharp_parts_miss", "[trap][pit][damage]" )
{
    const bool spiked = GENERATE( true, false );
    CAPTURE( spiked );
    prepare_pit( ter_id( spiked ? "t_pit_spiked" : "t_pit_glass" ) );
    avatar &player = get_avatar();
    player.set_dex_base( 0 );
    map &here = get_map();
    const tripoint_bub_ms p = player.pos_bub() + tripoint::east;
    here.ter_set( p, ter_id( spiked ? "t_pit_spiked" : "t_pit_glass" ) );
    const item corpse = item::make_corpse( mtype_id( "mon_zombie" ) );
    REQUIRE( corpse.volume() == 62500_ml );
    for( int count = 0; count < ( spiked ? 4 : 3 ); ++count ) {
        here.add_item_or_charges( p, corpse );
    }
    int corpses_in_pit = 0;
    units::volume corpse_volume = 0_ml;
    for( item &pit_item : here.i_at( p ) ) {
        corpses_in_pit += pit_item.is_corpse();
        if( pit_item.is_corpse() ) {
            corpse_volume += pit_item.volume();
        }
    }
    REQUIRE( corpses_in_pit == ( spiked ? 4 : 3 ) );
    REQUIRE( corpse_volume == ( spiked ? 250_liter : 187500_ml ) );
    const std::map<bodypart_id, int> before = hit_points( player );

    const pit_trigger trigger = spiked ? trapfunc::pit_spikes : trapfunc::pit_glass;
    rng_set_engine_seed( 88166 );
    REQUIRE( trigger( p, &player, nullptr ) );
    for( const auto &[bp, hp] : before ) {
        const int damage = hp - player.get_part_hp_cur( bp );
        CHECK( damage >= ( spiked ? 5 : 2 ) );
        CHECK( damage <= ( spiked ? 10 : 4 ) );
    }
}

TEST_CASE( "post_trigger_dodge_can_prevent_pit_damage", "[trap][pit][damage]" )
{
    const int variant = GENERATE( 0, 1, 2 );
    CAPTURE( variant );
    const ter_id terrain( variant == 0 ? "t_pit" : variant == 1 ? "t_pit_spiked" :
                          "t_pit_glass" );
    const pit_trigger trigger = variant == 0 ? trapfunc::pit : variant == 1 ?
                                trapfunc::pit_spikes : trapfunc::pit_glass;
    prepare_pit( terrain );
    avatar &player = get_avatar();
    player.set_dex_base( 20 );
    player.set_skill_level( skill_id( "dodge" ), 10 );
    player.set_dodge_bonus( 40.0f );
    REQUIRE( player.get_dodge() > 30.0f );
    const std::map<bodypart_id, int> before = hit_points( player );

    REQUIRE( trigger( player.pos_bub(), &player, nullptr ) );
    CHECK( hit_points( player ) == before );
}
