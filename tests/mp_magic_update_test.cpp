#include <string>

#include "avatar.h"
#include "bodypart.h"
#include "calendar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "creature_tracker.h"
#include "effect.h"
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
#include "mtype.h"
#include "npc.h"
#include "npc_execution_adapter.h"
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

spell_id mp_test_spell( const std::string &suffix, const std::string &properties )
{
    const spell_id id( "test_mp_" + suffix );
    if( !id.is_valid() ) {
        const std::string definition = "{\"id\":\"" + id.str() +
                                       "\",\"name\":\"Test co-op spell\","
                                       "\"description\":\"Deterministic co-op regression.\","
                                       "\"valid_targets\":[\"self\",\"ally\",\"hostile\",\"ground\"],"
                                       "\"flags\":[\"SILENT\",\"NO_EXPLOSION_SFX\"],"
                                       "\"shape\":\"blast\",\"max_level\":4,"
                                       "\"min_range\":6,\"max_range\":6," + properties + "}";
        spell_type::load_spell( json_loader::from_string( definition ), "" );
    }
    return id;
}
} // namespace

TEST_CASE( "mp_magic_hooks_keep_npc_effects_local_and_checked_ai_permissions_bounded",
           "[multiplayer][magic][actor_control][native]" )
{
    const bool client = GENERATE( false, true );
    const std::string operation = GENERATE( "charm_monster", "targeted_polymorph", "banishment",
                                            "attack" );
    clear_map_without_vision();
    clear_avatar();
    const client_mode_scope mode( client );
    map &here = get_map();
    get_avatar().setpos( here, tripoint_bub_ms( 60, 60, 0 ) );
    npc &caster = spawn_npc( point_bub_ms( 59, 60 ), "test_talker" );
    caster.set_value( "cph_ai.real_stamina", "true" );
    const tripoint_bub_ms target( 61, 60, 0 );
    monster &victim = spawn_test_monster( "test_mon_mummy", target );
    // A synced identity must not turn an NPC spell into the client's avatar cast.
    victim.mp_net_id = 731;
    std::string properties = "\"effect\":\"" + operation + "\",\"min_damage\":10000,"
                             "\"max_damage\":10000,\"min_duration\":2000,\"max_duration\":2000";
    if( operation == "targeted_polymorph" ) {
        properties += ",\"effect_str\":\"mon_zombie\"";
    } else if( operation == "attack" ) {
        properties = "\"effect\":\"attack\",\"effect_str\":\"stunned\","
                     "\"min_duration\":2000,\"max_duration\":2000";
    }
    const spell_id id = mp_test_spell( "npc_" + operation, properties );
    caster.magic->learn_spell( id, caster, true );
    const int moves = caster.get_moves();
    const int mana = caster.magic->available_mana();
    const auto rejected = cata::actor_control::NpcExecutionAdapter::validate_spell_cast(
                              caster, id, target );
    CHECK( rejected.state == cata::actor_control::execution_state::failed );
    CHECK( rejected.code == ( operation == "attack" ? "npc_unsupported_status_effect" :
                              "npc_unsupported_effect" ) );
    CHECK( caster.get_moves() == moves );
    CHECK( caster.magic->available_mana() == mana );
    CHECK_FALSE( caster.activity );

    // Native effects remain usable independently of the deliberately narrower AI interface.
    spell native( id );
    native.cast_spell_effect( caster, target );
    INFO( client );
    INFO( operation );
    if( operation == "charm_monster" ) {
        CHECK( victim.friendly == 20 );
    } else if( operation == "targeted_polymorph" ) {
        CHECK( victim.type->id == mtype_id( "mon_zombie" ) );
        CHECK( victim.mp_net_id == 731 );
    } else if( operation == "banishment" ) {
        CHECK( victim.is_dead() );
        CHECK_FALSE( victim.death_drops );
        CHECK( here.i_at( target ).empty() );
    } else {
        CHECK( victim.has_effect( efftype_id( "stunned" ) ) );
    }
}

TEST_CASE( "mp_magic_single_target_share_does_not_recast_an_area_or_extra_spells",
           "[multiplayer][magic][native]" )
{
    clear_map_without_vision();
    clear_avatar();
    avatar &receiver = get_avatar();
    receiver.setpos( get_map(), tripoint_bub_ms( 60, 60, 0 ) );
    npc &caster = spawn_npc( point_bub_ms( 57, 60 ), "test_talker" );
    npc &neighbor = spawn_npc( point_bub_ms( 61, 60 ), "test_talker" );
    receiver.set_part_hp_cur( bodypart_torso.id(), 10 );
    caster.set_part_hp_cur( bodypart_torso.id(), 10 );
    neighbor.set_part_hp_cur( bodypart_torso.id(), 10 );
    const spell_id extra = mp_test_spell( "extra_self_heal",
                                          "\"effect\":\"attack\",\"min_damage\":-50,\"max_damage\":-50" );
    const spell_id healing = mp_test_spell( "single_area_heal",
                                            "\"effect\":\"attack\",\"min_damage\":-7,\"max_damage\":-7,"
                                            "\"min_aoe\":3,\"max_aoe\":3,\"extra_effects\":[{\"id\":\"" +
                                            extra.str() + "\",\"hit_self\":true}]" );
    const bool client = GENERATE( false, true );
    const client_mode_scope mode( client );
    cata_mp::mp_spell_hit_single_target( spell( healing ), caster, receiver.pos_bub() );
    CHECK( receiver.get_part_hp_cur( bodypart_torso.id() ) == 17 );
    CHECK( neighbor.get_part_hp_cur( bodypart_torso.id() ) == 10 );
    CHECK( caster.get_part_hp_cur( bodypart_torso.id() ) == 10 );
}

TEST_CASE( "mp_magic_monster_effect_snapshot_is_authoritative_and_idempotent",
           "[multiplayer][magic][effects][native]" )
{
    const time_point old_turn = calendar::turn;
    const on_out_of_scope restore_clock( [old_turn]() {
        calendar::turn = old_turn;
    } );
    calendar::turn += 100_turns;
    monster source( mtype_id( "test_mon_mummy" ) );
    monster receiver( mtype_id( "test_mon_mummy" ) );
    const efftype_id stunned( "stunned" );
    const efftype_id blind( "blind" );
    const efftype_id downed( "downed" );
    source.add_effect( stunned, 20_turns, false, 1, true, true );
    source.add_effect( blind, 1_turns, true, 1, true, true );
    receiver.add_effect( downed, 10_turns, false, 1, true, true );
    const std::string wire = cata_mp::mp_monster_effects_wire( source );
    REQUIRE_FALSE( wire.empty() );
    JsonObject snapshot = json_loader::from_string( "{\"nid\":731" + wire + "}" ).get_object();
    snapshot.allow_omitted_members();
    const int hp = receiver.get_hp();
    cata_mp::mp_apply_monster_effects( receiver, snapshot );
    CHECK_FALSE( receiver.has_effect( downed ) );
    REQUIRE( receiver.has_effect( stunned ) );
    CHECK( receiver.get_effect_dur( stunned ) == 20_turns );
    REQUIRE( receiver.has_effect( blind ) );
    CHECK( receiver.get_effect( blind ).is_permanent() );
    cata_mp::mp_apply_monster_effects( receiver, snapshot );
    CHECK( receiver.get_effect_dur( stunned ) == 20_turns );
    CHECK( receiver.get_hp() == hp );

    // Absolute expiry leaves the delta stable while the authoritative timer ticks.
    calendar::turn += 5_turns;
    source.get_effect( stunned ).set_duration( 15_turns );
    CHECK( cata_mp::mp_monster_effects_wire( source ) == wire );
    cata_mp::mp_apply_monster_effects( receiver, snapshot );
    CHECK( receiver.get_effect_dur( stunned ) == 15_turns );

    JsonObject empty = json_loader::from_string( "{}" ).get_object();
    cata_mp::mp_apply_monster_effects( receiver, empty );
    CHECK_FALSE( receiver.has_effect( stunned ) );
    CHECK_FALSE( receiver.has_effect( blind ) );
    CHECK( receiver.get_hp() == hp );
}

TEST_CASE( "mp_magic_rejects_invalid_effect_snapshots_without_partial_mutation",
           "[multiplayer][magic][effects][native]" )
{
    monster receiver( mtype_id( "test_mon_mummy" ) );
    const efftype_id stunned( "stunned" );
    receiver.add_effect( stunned, 20_turns, false, 1, true, true );
    const std::string invalid = GENERATE(
                                    "[\"invalid_test_mp_effect\",1,-1]",
                                    "[\"blind\",0,-1]",
                                    "[\"blind\",1,-2]",
                                    "[\"blind\",1,-1,\"invalid_test_mp_bodypart\"]",
                                    "[\"ridden\",1,-1]" );
    const JsonObject snapshot = json_loader::from_string(
                                    "{\"eff\":[[\"blind\",1,-1]," + invalid + "]}" ).get_object();
    cata_mp::mp_apply_monster_effects( receiver, snapshot );
    CHECK( receiver.get_effect_dur( stunned ) == 20_turns );
    CHECK_FALSE( receiver.has_effect( efftype_id( "blind" ) ) );
}

TEST_CASE( "mp_magic_partner_packets_without_a_real_partner_do_not_use_the_avatar_as_caster",
           "[multiplayer][magic][native]" )
{
    cata_mp::mp_on_world_exit();
    clear_map_without_vision();
    clear_avatar();
    const client_mode_scope mode( true );
    REQUIRE( cata_mp::get_partner_npc() == nullptr );
    avatar &receiver = get_avatar();
    receiver.set_part_hp_cur( bodypart_torso.id(), 10 );
    const spell_id id = mp_test_spell( "no_proxy",
                                       "\"effect\":\"attack\",\"min_damage\":-7,\"max_damage\":-7" );
    cata_mp::mp_set_magic_generation( "no-proxy-test" );
    const on_out_of_scope clear_generation( []() {
        cata_mp::mp_set_magic_generation( "" );
    } );
    cata_mp::mp_handle_partner_spell( "{\"type\":\"partner_spell\",\"spell\":\"" + id.str() +
                                      "\",\"level\":0,\"magic_epoch\":\"no-proxy-test\",\"magic_seq\":1}" );
    CHECK( receiver.get_part_hp_cur( bodypart_torso.id() ) == 10 );
    CHECK_FALSE( receiver.magic->knows_spell( id ) );
}

TEST_CASE( "mp_magic_client_load_rejects_the_discarded_state_generation",
           "[multiplayer][magic][save][native]" )
{
    cata_mp::mp_on_world_exit();
    const client_mode_scope mode( true );
    const on_out_of_scope clear_generation( []() {
        cata_mp::mp_set_magic_generation( "" );
    } );
    cata_mp::mp_set_magic_generation( "before-load" );
    const time_point load_turn = calendar::turn;
    cata_mp::mp_cleanup_stale_npcs_after_load();
    CHECK( calendar::turn == load_turn );
    CHECK( cata_mp::mp_magic_generation().empty() );
    // A second callback during the same load must retain the discarded epoch.
    cata_mp::mp_cleanup_stale_npcs_after_load();
    cata_mp::mp_set_magic_generation( "before-load" );
    CHECK( cata_mp::mp_magic_generation().empty() );
    cata_mp::mp_set_magic_generation( "after-load" );
    CHECK( cata_mp::mp_magic_generation() == "after-load" );
    // A genuinely new connection may reuse another server's epoch value.
    cata_mp::mp_set_magic_generation( "" );
    cata_mp::mp_set_magic_generation( "before-load" );
    CHECK( cata_mp::mp_magic_generation() == "before-load" );
}

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
    // Catch runs this setup again for each section in the same loaded registry.
    if( !heal_id.is_valid() ) {
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
