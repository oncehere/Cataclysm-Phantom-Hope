#include <string>

#include "avatar.h"
#include "bodypart.h"
#include "calendar.h"
#include "cata_catch.h"
#include "creature_tracker.h"
#include "event.h"
#include "event_bus.h"
#include "game.h"
#include "flexbuffer_json.h"
#include "json_loader.h"
#include "magic.h"
#include "map.h"
#include "map_helpers.h"
#include "map_helpers_tests.h"
#include "mod_manager.h"
#include "monster.h"
#include "mp_client_conn.h"
#include "mp_gamestate.h"
#include "mp_magic.h"
#include "mp_mod_compat.h"
#include "npc.h"
#include "player_helpers.h"
#include "type_id.h"
#include "worldfactory.h"

static const spell_id spell_test_spell_tp_mummy( "test_spell_tp_mummy" );
static const bodypart_str_id bodypart_torso( "torso" );

namespace
{
// The production mode setter exercises client-only behavior without a socket.
// These fixtures prove local hooks and role guards, not a network round trip.
class client_mode_scope
{
    public:
        explicit client_mode_scope( bool enabled ) : previous( cata_mp::is_client_mode() ) {
            cata_mp::set_client_mode( enabled );
        }
        ~client_mode_scope() {
            cata_mp::set_client_mode( previous );
        }
        client_mode_scope( const client_mode_scope & ) = delete;
        client_mode_scope &operator=( const client_mode_scope & ) = delete;
    private:
        bool previous;
};
} // namespace

TEST_CASE( "mp_magic_summon_uses_host_authority_only_for_client_avatar",
           "[multiplayer][magic][summon]" )
{
    clear_map_without_vision();
    clear_avatar();
    map &here = get_map();
    avatar &caster = get_avatar();
    caster.setpos( here, tripoint_bub_ms( 60, 60, 0 ) );
    const tripoint_bub_ms target( 61, 60, 0 );
    creature_tracker &creatures = get_creature_tracker();
    spell summon( spell_test_spell_tp_mummy );
    REQUIRE( !creatures.creature_at( target ) );

    SECTION( "single_player_retains_the_local_summon" ) {
        const client_mode_scope mode( false );
        summon.cast_spell_effect( caster, target );
        monster *created = creatures.creature_at<monster>( target );
        REQUIRE( created != nullptr );
        CHECK( cata_mp::mp_is_summoned( *created ) );
        CHECK( created->get_summoner() == &caster );
    }

    SECTION( "client_avatar_removes_local_copy_without_a_corpse" ) {
        const client_mode_scope mode( true );
        summon.cast_spell_effect( caster, target );
        CHECK( creatures.creature_at( target ) == nullptr );
        CHECK( here.i_at( target ).empty() );
    }

    SECTION( "client_npc_casts_do_not_use_the_avatar_channel" ) {
        const client_mode_scope mode( true );
        npc &npc_caster = spawn_npc( point_bub_ms( 59, 60 ), "test_talker" );
        summon.cast_spell_effect( npc_caster, target );
        monster *created = creatures.creature_at<monster>( target );
        REQUIRE( created != nullptr );
        CHECK( created->get_summoner() == &npc_caster );
        CHECK( cata_mp::mp_is_summoned( *created ) );
    }
}

TEST_CASE( "mp_magic_incoming_packets_are_inert_in_single_player",
           "[multiplayer][magic]" )
{
    const client_mode_scope mode( false );
    REQUIRE_FALSE( cata_mp::is_hosting() );
    clear_map_without_vision();
    clear_avatar();
    avatar &caster = get_avatar();
    const int hp_before = caster.get_part_hp_cur( bodypart_torso.id() );
    const size_t creatures_before = g->num_creatures();

    cata_mp::mp_handle_client_hp( R"({"type":"client_hp","parts":[{"bp":"torso","d":-7}]})" );
    cata_mp::mp_handle_partner_spell(
        R"({"type":"partner_spell","spell":"test_spell_tp_mummy","level":3})" );
    cata_mp::mp_handle_client_summon(
        R"({"type":"client_summon","mtype":"test_mon_mummy","x":0,"y":0,"z":0})" );

    CHECK( caster.get_part_hp_cur( bodypart_torso.id() ) == hp_before );
    CHECK( g->num_creatures() == creatures_before );
    spell summon( spell_test_spell_tp_mummy );
    CHECK( cata_mp::mp_confirm_long_cast( summon, caster ) );
}

TEST_CASE( "mp_magic_cast_events_observe_only_multiplayer_avatars",
           "[multiplayer][magic][event]" )
{
    clear_map_without_vision();
    clear_avatar();
    avatar &caster = get_avatar();
    caster.magic->learn_spell( spell_test_spell_tp_mummy, caster, true );
    const spell &summon = caster.magic->get_spell( spell_test_spell_tp_mummy );
    const int original_turns = cata_mp::mp_turns_since_last_cast();
    const std::string original_spell = cata_mp::mp_last_cast_spell();

    {
        const client_mode_scope mode( false );
        get_event_bus().send<event_type::spellcasting_finish>( caster.getID(), true,
                spell_test_spell_tp_mummy, summon.spell_class(), 2, 100, 100, 1 );
        CHECK( cata_mp::mp_turns_since_last_cast() == original_turns );
        CHECK( cata_mp::mp_last_cast_spell() == original_spell );
    }
    {
        const client_mode_scope mode( true );
        get_event_bus().send<event_type::spellcasting_finish>( caster.getID(), true,
                spell_test_spell_tp_mummy, summon.spell_class(), 2, 100, 100, 1 );
        CHECK( cata_mp::mp_turns_since_last_cast() == 0 );
        CHECK( cata_mp::mp_last_cast_spell() == spell_test_spell_tp_mummy.str() );
    }
}

TEST_CASE( "mp_magic_explicit_spell_healing_keeps_single_player_effects",
           "[multiplayer][magic][heal]" )
{
    clear_map_without_vision();
    clear_avatar();
    avatar &caster = get_avatar();
    caster.setpos( get_map(), tripoint_bub_ms( 60, 60, 0 ) );
    const spell_id heal_id( "test_mp_direct_heal" );
    JsonObject definition = json_loader::from_string( R"({
        "id": "test_mp_direct_heal",
        "name": "Test co-op healing",
        "description": "Deterministic healing for multiplayer role guards.",
        "valid_targets": [ "self", "ally" ],
        "effect": "attack",
        "shape": "blast",
        "min_damage": -7,
        "max_damage": -7,
        "max_level": 1
    })" );
    // Catch runs this setup again for each section in the same loaded registry.
    if( !heal_id.is_valid() ) {
        spell_type::load_spell( definition, "" );
    }
    spell healing( heal_id );
    caster.set_part_hp_cur( bodypart_torso.id(), 10 );

    SECTION( "single_player" ) {
        const client_mode_scope mode( false );
        CHECK( healing.heal( caster.pos_bub(), caster ) == 7 );
        CHECK( caster.get_part_hp_cur( bodypart_torso.id() ) == 17 );
    }
    SECTION( "client_avatar" ) {
        const client_mode_scope mode( true );
        CHECK( healing.heal( caster.pos_bub(), caster ) == 7 );
        CHECK( caster.get_part_hp_cur( bodypart_torso.id() ) == 17 );
    }
}

TEST_CASE( "mp_magic_experimental_note_reaches_the_mod_description_panel",
           "[multiplayer][magic][mod_manager][ui]" )
{
    const mod_id magiclysm( "magiclysm" );
    REQUIRE( magiclysm.is_valid() );
    mod_ui ui( world_generator->get_mod_manager() );
    CHECK( cata_mp::mod_coop_status( magiclysm.str() ) == cata_mp::mod_coop::ok );
    const std::string note = cata_mp::mod_coop_note( magiclysm.str() );
    REQUIRE_FALSE( note.empty() );
    SECTION( "single_player" ) {
        const client_mode_scope mode( false );
        CHECK( cata_mp::mod_coop_info_suffix( magiclysm.str() ).empty() );
        CHECK( ui.get_information( &magiclysm.obj() ).find( note ) == std::string::npos );
    }
    SECTION( "multiplayer" ) {
        const client_mode_scope mode( true );
        CHECK( ui.get_information( &magiclysm.obj() ).find( note ) != std::string::npos );
    }
}
