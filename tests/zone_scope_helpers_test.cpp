#include <vector>

#include "activity_item_handling.h"
#include "avatar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "clzones.h"
#include "coordinates.h"
#include "flexbuffer_json.h"
#include "item.h"
#include "item_location.h"
#include "json_loader.h"
#include "map.h"
#include "map_helpers.h"
#include "player_helpers.h"
#include "pocket_type.h"
#include "point.h"
#include "type_id.h"

static const faction_id faction_your_followers( "your_followers" );
static const itype_id itype_test_apple( "test_apple" );
static const zone_type_id zone_type_LOOT_CUSTOM( "LOOT_CUSTOM" );
static const zone_type_id zone_type_LOOT_IGNORE( "LOOT_IGNORE" );
static const zone_type_id zone_type_AUTO_EAT( "AUTO_EAT" );
static const zone_type_id zone_type_UNLOAD_ALL( "UNLOAD_ALL" );
static const zone_type_id zone_type_LOOT_IGNORE_FAVORITES( "LOOT_IGNORE_FAVORITES" );

TEST_CASE( "zone_scope_helpers_filter_custom_destinations_and_capacity",
           "[zones][personal_scope][sorting]" )
{
    clear_avatar();
    clear_map_without_vision();
    avatar &you = get_avatar();
    map &here = get_map();
    you.setpos( here, tripoint_bub_ms( 60, 60, 0 ) );
    zone_manager &zones = zone_manager::get_manager();
    zones.clear();
    const on_out_of_scope cleanup( [&]() {
        zones.clear();
    } );
    const tripoint_abs_ms origin = you.pos_abs();
    const tripoint_rel_ms offset( 1, 0, 0 );
    const tripoint_abs_ms dest = origin + offset;
    auto fixed = make_shared_fast<loot_options>();
    fixed->set_mark( "nonexistent_zzz" );
    auto personal = make_shared_fast<loot_options>();
    personal->set_mark( "apple" );
    REQUIRE( zones.add( "fixed", zone_type_LOOT_CUSTOM, faction_your_followers, false, true,
                        dest, dest, fixed, true, nullptr, false ) );
    REQUIRE( zones.add( "personal", zone_type_LOOT_CUSTOM, faction_your_followers, false, true,
                        offset, offset, personal, you.getID() ) );
    const tripoint_rel_ms personal_offset( 2, 0, 0 );
    const tripoint_abs_ms personal_dest = origin + personal_offset;
    REQUIRE( zones.add( "personal only", zone_type_LOOT_CUSTOM, faction_your_followers, false,
                        true, personal_offset, personal_offset, personal, you.getID() ) );
    item apple( itype_test_apple );
    const std::vector<item_location> other;
    for( const zone_scope scope : {
             zone_scope::all, zone_scope::static_only, zone_scope::personal_only
         } ) {
        CAPTURE( static_cast<int>( scope ) );
        const zone_query_context q = zone_query_context::for_character( you, origin, scope );
        const bool expect_personal = scope != zone_scope::static_only;
        CHECK( zone_sorting::sort_skip_item( you, &apple, other, false, dest, 1.0f, nullptr,
                                             &q ) == expect_personal );
        CHECK( zone_sorting::dest_has_capacity( dest, zone_type_LOOT_CUSTOM, apple,
                                                faction_your_followers, &q ) );
        CHECK( zone_sorting::dest_has_capacity( personal_dest, zone_type_LOOT_CUSTOM, apple,
                                                faction_your_followers, &q ) == expect_personal );
    }
}

TEST_CASE( "zone_scope_helpers_filter_ignore_and_unload_options",
           "[zones][personal_scope][sorting]" )
{
    clear_avatar();
    clear_map_without_vision();
    avatar &you = get_avatar();
    map &here = get_map();
    you.setpos( here, tripoint_bub_ms( 60, 60, 0 ) );
    zone_manager &zones = zone_manager::get_manager();
    zones.clear();
    const on_out_of_scope cleanup( [&]() {
        zones.clear();
    } );
    const tripoint_abs_ms origin = you.pos_abs();
    const tripoint_rel_ms offset( 1, 0, 0 );
    const tripoint_abs_ms dest = origin + offset;
    auto ignore = make_shared_fast<ignorable_options>();
    ignore->deserialize( json_loader::from_string( R"({"ignore_contents":true})" ).get_object() );
    auto unload = make_shared_fast<unload_options>();
    unload->deserialize( json_loader::from_string(
                             R"({"mark":"","mods":true,"molle":true,"sparse_only":false,"sparse_threshold":20,"always_unload":true})" ).get_object() );
    REQUIRE( zones.add( "personal ignore", zone_type_LOOT_IGNORE, faction_your_followers, false,
                        true, offset, offset, nullptr, you.getID() ) );
    REQUIRE( zones.add( "personal eat", zone_type_AUTO_EAT, faction_your_followers, false,
                        true, offset, offset, ignore, you.getID() ) );
    REQUIRE( zones.add( "personal unload", zone_type_UNLOAD_ALL, faction_your_followers, false,
                        true, offset, offset, unload, you.getID() ) );
    REQUIRE( zones.add( "disabled favorite", zone_type_LOOT_IGNORE_FAVORITES, faction_your_followers,
                        false, false, offset, offset, nullptr, you.getID() ) );
    for( const zone_scope scope : {
             zone_scope::all, zone_scope::static_only, zone_scope::personal_only
         } ) {
        CAPTURE( static_cast<int>( scope ) );
        const zone_query_context q = zone_query_context::for_character( you, origin, scope );
        const bool personal = scope != zone_scope::static_only;
        CHECK( zone_sorting::ignore_contents( you, dest, &q ) == personal );
        CHECK( zone_sorting::ignore_zone_position( you, dest, false, &q ) == personal );
        const auto options = zone_sorting::set_unload_options( you, dest, true, &q );
        CHECK( options.unload_mods == personal );
        CHECK( options.unload_molle == personal );
        CHECK( options.unload_always == personal );
        CHECK_FALSE( options.ignore_favorite );
    }
}

TEST_CASE( "zone_scope_helpers_sortable_items_follow_personal_scope",
           "[zones][personal_scope][sorting]" )
{
    clear_avatar();
    clear_map_without_vision();
    avatar &you = get_avatar();
    map &here = get_map();
    you.setpos( here, tripoint_bub_ms( 60, 60, 0 ) );
    zone_manager &zones = zone_manager::get_manager();
    zones.clear();
    const on_out_of_scope cleanup( [&]() {
        zones.clear();
    } );
    const tripoint_abs_ms origin = you.pos_abs();
    const tripoint_rel_ms src_offset( 1, 0, 0 );
    const tripoint_rel_ms dest_offset( 2, 0, 0 );
    const tripoint_abs_ms src = origin + src_offset;
    const zone_type_id unsorted( "LOOT_UNSORTED" );
    auto personal = make_shared_fast<loot_options>();
    personal->set_mark( "apple" );
    REQUIRE( zones.add( "personal source", unsorted, faction_your_followers, false, true,
                        src_offset, src_offset, nullptr, you.getID() ) );
    REQUIRE( zones.add( "personal destination", zone_type_LOOT_CUSTOM, faction_your_followers,
                        false, true, dest_offset, dest_offset, personal, you.getID() ) );
    here.add_item_or_charges( here.get_bub( src ), item( itype_test_apple ) );
    const auto items = zone_sorting::populate_items( here.get_bub( src ) );
    REQUIRE_FALSE( items.empty() );
    const std::vector<item_location> other;
    for( const zone_scope scope : {
             zone_scope::all, zone_scope::static_only, zone_scope::personal_only
         } ) {
        CAPTURE( static_cast<int>( scope ) );
        const zone_query_context q = zone_query_context::for_character( you, origin, scope );
        bool pickup_failure = false;
        const auto options = zone_sorting::set_unload_options( you, src, true, &q );
        CHECK( zone_sorting::has_items_to_sort( you, src, options, other, items, &pickup_failure,
                                                nullptr, &q ) == ( scope != zone_scope::static_only ) );
    }
}

TEST_CASE( "zone_scope_helpers_unload_real_contents_only_in_selected_scope",
           "[zones][personal_scope][sorting][unload]" )
{
    clear_avatar();
    clear_map_without_vision();
    avatar &you = get_avatar();
    map &here = get_map();
    you.setpos( here, tripoint_bub_ms( 60, 60, 0 ) );
    zone_manager &zones = zone_manager::get_manager();
    zones.clear();
    const on_out_of_scope cleanup( [&]() {
        zones.clear();
    } );
    const tripoint_abs_ms origin = you.pos_abs();
    const tripoint_rel_ms offset( 1, 0, 0 );
    const tripoint_abs_ms src = origin + offset;
    const tripoint_bub_ms src_bub = here.get_bub( src );
    auto options = make_shared_fast<unload_options>();
    options->deserialize( json_loader::from_string(
                              R"({"mark":"","mods":false,"molle":false,"sparse_only":false,"sparse_threshold":20,"always_unload":true})" ).get_object() );
    REQUIRE( zones.add( "personal unload", zone_type_UNLOAD_ALL, faction_your_followers, false,
                        true, offset, offset, options, you.getID() ) );
    const itype_id container_type( "test_watertight_open_sealed_container_250ml" );
    for( const zone_scope scope : {
             zone_scope::all, zone_scope::static_only, zone_scope::personal_only
         } ) {
        CAPTURE( static_cast<int>( scope ) );
        here.i_clear( src_bub );
        item container( container_type );
        item apple( itype_test_apple );
        apple.set_owner( faction_your_followers );
        apple.set_var( "scope_test", "preserved" );
        REQUIRE( container.put_in( apple, pocket_type::CONTAINER ).success() );
        item_location placed = here.add_item_or_charges_ret_loc( src_bub, container );
        REQUIRE( placed );
        you.set_moves( 10000 );
        int processed = 0;
        const zone_query_context q = zone_query_context::for_character( you, origin, scope );
        const auto opts = zone_sorting::set_unload_options( you, src, true, &q );
        const std::unordered_set<tripoint_abs_ms> destinations;
        const auto result = zone_sorting::unload_item( you, src, opts, std::nullopt,
                            placed.get_item(), destinations, processed, &q );
        REQUIRE( result.has_value() );
        const bool should_unload = scope != zone_scope::static_only;
        CHECK( *result == should_unload );
        CHECK( placed->all_items_top( pocket_type::CONTAINER ).size() == ( should_unload ? 0 : 1 ) );
        int apples = 0;
        for( const item &ground : here.i_at( src_bub ) ) {
            if( ground.typeId() == itype_test_apple ) {
                ++apples;
                CHECK( ground.get_owner() == faction_your_followers );
                CHECK( ground.get_var( "scope_test" ) == "preserved" );
            }
        }
        CHECK( apples == ( should_unload ? 1 : 0 ) );
        if( !should_unload ) {
            const item *stored = placed->all_items_top( pocket_type::CONTAINER ).front();
            CHECK( stored->get_owner() == faction_your_followers );
            CHECK( stored->get_var( "scope_test" ) == "preserved" );
        }
    }
}
