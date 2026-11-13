#include <memory>
#include <sstream>
#include <string>
#include <unordered_set>

#include "activity_actor_definitions.h"
#include "activity_item_handling.h"
#include "avatar.h"
#include "cata_catch.h"
#include "construction.h"
#include "coordinates.h"
#include "json.h"
#include "json_loader.h"
#include "map.h"
#include "map_helpers.h"
#include "npc.h"
#include "player_activity.h"
#include "player_helpers.h"
#include "point.h"
#include "type_id.h"

static const activity_id ACT_BUILD( "ACT_BUILD" );
static const construction_str_id construction_test_door( "test_constr_door" );

TEST_CASE( "construction_activity_preserves_completed_site_across_save",
           "[activities][construction][save]" )
{
    clear_map();
    clear_avatar();
    map &here = get_map();
    avatar &u = get_avatar();
    const tripoint_bub_ms site = u.pos_bub() + tripoint::east;
    partial_con pc;
    pc.id = construction_test_door.id();
    here.partial_con_set( site, pc );
    build_construction_activity_actor original( here.get_abs( site ) );
    player_activity activity;
    original.start( activity, u );

    std::ostringstream out;
    JsonOut jsout( out );
    original.serialize( jsout );
    JsonValue value = json_loader::from_string( out.str() );
    std::unique_ptr<activity_actor> restored = build_construction_activity_actor::deserialize( value );
    here.partial_con_remove( site );
    here.ter_set( site, ter_str_id( construction_test_door->post_terrain ) );
    activity = player_activity( ACT_BUILD );
    restored->do_turn( activity, u );
    CHECK( activity.is_null() );
}

TEST_CASE( "construction_occupied_sites_include_avatar",
           "[activities][construction][zones]" )
{
    clear_map();
    clear_avatar();
    map &here = get_map();
    avatar &u = get_avatar();
    npc &worker = spawn_npc( u.pos_bub().xy() + point::west, "test_talker" );
    const tripoint_abs_ms site = here.get_abs( u.pos_bub() + tripoint::east );
    u.assign_activity( build_construction_activity_actor( site ) );
    const std::unordered_set<tripoint_abs_ms> occupied =
        multi_activity_actor::occupied_construction_sites( worker );
    CHECK( occupied.count( site ) == 1 );
}
