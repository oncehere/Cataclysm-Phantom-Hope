#include <memory>
#include <set>
#include <sstream>
#include <string>
#include <tuple>
#include <utility>

#include "activity_actor_definitions.h"
#include "avatar.h"
#include "calendar.h"
#include "cata_catch.h"
#include "character.h"
#include "coordinates.h"
#include "enums.h"
#include "flexbuffer_json.h"
#include "game.h"
#include "item.h"
#include "item_location.h"
#include "json.h"
#include "json_loader.h"
#include "map.h"
#include "map_helpers.h"
#include "messages.h"
#include "npc.h"
#include "player_activity.h"
#include "player_helpers.h"
#include "point.h"
#include "type_id.h"
#include "units.h"
#include "veh_type.h"
#include "vehicle.h"
#include "vpart_position.h"

static const furn_str_id furn_f_chair( "f_chair" );
static const itype_id itype_test_rock( "test_rock" );
static const ter_str_id ter_t_wall( "t_wall" );
static const vpart_id vpart_frame( "frame" );
static const vpart_id vpart_trunk( "trunk" );
static const vproto_id vehicle_prototype_bicycle( "bicycle" );
static const vproto_id vehicle_prototype_none( "none" );

static npc &adapter_proxy()
{
    clear_avatar();
    clear_map_without_vision();
    clear_npcs();
    map &here = get_map();
    get_avatar().setpos( here, tripoint_bub_ms( 60, 60, 0 ) );
    npc &proxy = spawn_npc( point_bub_ms( 30, 30 ), "test_talker" );
    clear_character( proxy );
    proxy.set_str_base( 50 );
    proxy.set_str_bonus( 0 );
    proxy.set_moves( 10000 );
    return proxy;
}

TEST_CASE( "mp_adapter_grab_state_and_avatar_save_contract", "[mp][mp_adapter][save]" )
{
    npc &proxy = adapter_proxy();
    avatar &host = get_avatar();
    CHECK( proxy.get_grab_type() == object_type::NONE );
    Character &remote = proxy;
    remote.grab( object_type::FURNITURE, tripoint_rel_ms::east );
    CHECK( remote.get_grab_type() == object_type::FURNITURE );
    CHECK( remote.grab_point == tripoint_rel_ms::east );
    CHECK( host.get_grab_type() == object_type::NONE );

    Character &player = host;
    player.grab( object_type::FURNITURE, tripoint_rel_ms::north );
    std::ostringstream output;
    JsonOut json( output );
    host.serialize( json );
    JsonObject saved = json_loader::from_string( output.str() ).get_object();
    saved.allow_omitted_members();
    CHECK( saved.get_string( "grab_type" ) == "OBJECT_FURNITURE" );
    tripoint_rel_ms saved_point;
    saved.read( "grab_point", saved_point );
    CHECK( saved_point == tripoint_rel_ms::north );

    avatar restored;
    restored.deserialize( saved );
    CHECK( restored.get_grab_type() == object_type::FURNITURE );
    CHECK( restored.grab_point == tripoint_rel_ms::north );
    remote.grab( object_type::NONE );
    CHECK( remote.grab_point == tripoint_rel_ms::zero );
    CHECK( host.get_grab_type() == object_type::FURNITURE );
}

TEST_CASE( "mp_adapter_npc_furniture_drag_uses_proxy", "[mp][mp_adapter][furniture]" )
{
    npc &proxy = adapter_proxy();
    map &here = get_map();
    const tripoint_bub_ms pos = proxy.pos_bub();
    const tripoint_abs_ms host_pos = get_avatar().pos_abs();
    const int host_moves = get_avatar().get_moves();
    here.furn_set( pos + tripoint_rel_ms::east, furn_f_chair );
    proxy.grab( object_type::FURNITURE, tripoint_rel_ms::east );

    SECTION( "push" ) {
        CHECK_FALSE( g->grabbed_furn_move( proxy, tripoint_rel_ms::east ) );
        CHECK( here.furn( pos + tripoint_rel_ms( 2, 0, 0 ) ) == furn_f_chair );
        CHECK_FALSE( here.has_furn( pos + tripoint_rel_ms::east ) );
    }
    SECTION( "pull onto the proxy's tile" ) {
        CHECK_FALSE( g->grabbed_furn_move( proxy, tripoint_rel_ms::west ) );
        CHECK( here.furn( pos ) == furn_f_chair );
        CHECK_FALSE( here.has_furn( pos + tripoint_rel_ms::east ) );
    }
    SECTION( "sideways shift" ) {
        CHECK( g->grabbed_furn_move( proxy, tripoint_rel_ms::north ) );
        CHECK( here.furn( pos + tripoint_rel_ms( 1, -1, 0 ) ) == furn_f_chair );
        CHECK( proxy.grab_point == tripoint_rel_ms( 1, -1, 0 ) );
    }
    SECTION( "blocked push" ) {
        here.ter_set( pos + tripoint_rel_ms( 2, 0, 0 ), ter_t_wall );
        CHECK( g->grabbed_furn_move( proxy, tripoint_rel_ms::east ) );
        CHECK( here.furn( pos + tripoint_rel_ms::east ) == furn_f_chair );
    }
    CHECK( proxy.pos_bub() == pos );
    CHECK( get_avatar().pos_abs() == host_pos );
    CHECK( get_avatar().get_moves() == host_moves );
    CHECK( get_avatar().get_grab_type() == object_type::NONE );
}

TEST_CASE( "mp_adapter_npc_unloads_grabbed_vehicle_furniture", "[mp][mp_adapter][furniture]" )
{
    npc &proxy = adapter_proxy();
    map &here = get_map();
    const tripoint_bub_ms pos = proxy.pos_bub();
    vehicle *cart = here.add_vehicle( vehicle_prototype_none, pos + tripoint_rel_ms::east,
                                      0_degrees, 0, veh_spawn_status::UNDAMAGED );
    REQUIRE( cart != nullptr );
    REQUIRE( cart->install_part( here, point_rel_ms::zero, vpart_frame ) >= 0 );
    const int cargo = cart->install_part( here, point_rel_ms::zero, vpart_trunk );
    REQUIRE( cargo >= 0 );
    item base( cart->part( cargo ).get_base() );
    base.set_var( "tied_down_furniture", furn_f_chair.str() );
    cart->part( cargo ).set_base( std::move( base ) );
    cart->refresh();
    here.rebuild_vehicle_level_caches();
    proxy.grab( object_type::FURNITURE_ON_VEHICLE, tripoint_rel_ms::east );

    CHECK( g->grabbed_furn_move_time( proxy, tripoint_rel_ms::west ) == 50 );
    CHECK_FALSE( g->grabbed_furn_move( proxy, tripoint_rel_ms::west ) );
    CHECK( here.furn( pos ) == furn_f_chair );
    CHECK_FALSE( cart->part( cargo ).get_base().has_var( "tied_down_furniture" ) );
    CHECK( proxy.get_grab_type() == object_type::FURNITURE );
    CHECK( get_avatar().get_grab_type() == object_type::NONE );
}

TEST_CASE( "mp_adapter_npc_hauling_moves_items_without_host_activity", "[mp][mp_adapter][hauling]" )
{
    npc &proxy = adapter_proxy();
    map &here = get_map();
    const tripoint_bub_ms source = proxy.pos_bub();
    const tripoint_bub_ms dest = source + tripoint_rel_ms::east;
    item &rock = here.add_item_or_charges( source, item( itype_test_rock, calendar::turn ) );
    const item_location location( map_cursor( source ), &rock );
    proxy.start_hauling( { location } );
    REQUIRE( proxy.is_hauling() );
    proxy.setpos( here, dest );
    g->start_hauling( proxy, source );
    REQUIRE( proxy.activity );
    CHECK( proxy.activity.id() == activity_id( "ACT_MOVE_ITEMS" ) );
    CHECK_FALSE( get_avatar().activity );
    proxy.set_moves( 100000 );
    proxy.activity.do_turn( proxy );
    CHECK( here.get_haulable_items( source ).empty() );
    CHECK( here.get_haulable_items( dest ).size() == 1 );
}

TEST_CASE( "mp_adapter_vehicle_snapshot_keeps_pivot_and_registers_cache",
           "[mp][mp_adapter][vehicle]" )
{
    clear_avatar();
    clear_map_without_vision();
    map &here = get_map();
    vehicle *original = here.add_vehicle( vehicle_prototype_bicycle, tripoint_bub_ms( 30, 30, 0 ),
                                          45_degrees, 0, veh_spawn_status::UNDAMAGED );
    REQUIRE( original != nullptr );
    original->name = "snapshot vehicle";
    original->precalc_mounts( 0, original->face.dir(), point_rel_ms( 1, 1 ) );
    const tripoint_abs_ms original_pos = original->pos_abs();
    const point_rel_ms original_pivot = original->pivot_anchor[0];
    const int parts = original->part_count();
    std::ostringstream output;
    JsonOut json( output );
    original->serialize( json );
    auto snapshot = std::make_unique<vehicle>( vehicle_prototype_none );
    snapshot->deserialize( json_loader::from_string( output.str() ).get_object() );
    // Vehicle saves contain submap-relative coordinates.  The network packet
    // supplies the absolute anchor separately, as apply_vehicle_sync does.
    std::tie( snapshot->sm_pos, snapshot->pos ) =
        coords::project_remain<coords::sm>( original_pos );
    snapshot->precalc_mounts( 0, snapshot->pivot_rotation[0], snapshot->pivot_anchor[0] );
    REQUIRE( snapshot->pos_abs() == original_pos );
    here.destroy_vehicle( original );
    REQUIRE( here.get_vehicles().empty() );

    vehicle *placed = here.add_vehicle_from_snapshot( std::move( snapshot ) );
    REQUIRE( placed != nullptr );
    CHECK( snapshot == nullptr );
    CHECK( placed->name == "snapshot vehicle" );
    CHECK( placed->pos_abs() == original_pos );
    CHECK( placed->pivot_anchor[0] == original_pivot );
    CHECK( placed->part_count() == parts );
    REQUIRE( here.get_vehicles().size() == 1 );
    for( const tripoint_abs_ms &part_pos : placed->get_points() ) {
        const optional_vpart_position vp = here.veh_at( part_pos );
        REQUIRE( vp );
        CHECK( &vp->vehicle() == placed );
    }
    CHECK( here.add_vehicle_from_snapshot( std::unique_ptr<vehicle>() ) == nullptr );
}

TEST_CASE( "mp_adapter_construction_location_is_source_bound", "[mp][mp_adapter][construction]" )
{
    const tripoint_abs_ms tile( 123, 456, 0 );
    const build_construction_activity_actor actor( tile );
    CHECK( actor.get_construction_location() == tile );
}

TEST_CASE( "mp_adapter_message_watermark_survives_clear", "[mp][mp_adapter][messages]" )
{
    // This verifies the test double's link contract. Real MESSAGE_LIMIT and
    // coalescing behaviour require the separate production-messages probe.
    Messages::clear_messages();
    const unsigned long long before = Messages::appended_total();
    Messages::add_msg( "mp watermark first" );
    CHECK( Messages::appended_total() == before + 1 );
    Messages::clear_messages();
    CHECK( Messages::size() == 0 );
    CHECK( Messages::appended_total() == before + 1 );
    Messages::add_msg( "" );
    CHECK( Messages::appended_total() == before + 1 );
    Messages::add_msg( "mp watermark second" );
    CHECK( Messages::appended_total() == before + 2 );
    Messages::clear_messages();
}
