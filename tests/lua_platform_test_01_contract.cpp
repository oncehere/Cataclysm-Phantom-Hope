#include <build_reqs.h>
#include <character_id.h>
#include <debug.h>
#include <dialogue.h>
#include <dialogue_chatbin.h>
#include <enums.h>
#include <item_location.h>
#include <item_uid.h>
#if defined(CATA_ENABLE_LUA_PLATFORM) && CATA_ENABLE_LUA_PLATFORM
extern "C" {
#include <lua.h>
}
#endif
#include <map_iterator.h>
#include <memory_fast.h>
#include <monster_uid.h>
#include <npc_opinion.h>
#include <overmap.h>
#include <overmap_ui.h>
#include <pimpl.h>
#include <player_activity.h>
#include <plf/list.h>
#include <pocket_type.h>
#include <point.h>
#include <recipe.h>
#include <ret_val.h>
#include <stomach.h>
#include <type_id.h>
#include <units.h>
#include <vehicle_uid.h>
#include <visitable.h>
#include <vpart_position.h>
#include <weather.h>
#include <weather_gen.h>
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <functional>
#include <initializer_list>
#include <limits>
#include <list>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <system_error>
#include <type_traits>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include "activity_actor_definitions.h"
#include "ascii_art.h"
#include "avatar.h"
#include "basecamp.h"
#include "bodypart.h"
#include "calendar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "character.h"
#include "clzones.h"
#include "coordinates.h"
#include "creature_tracker.h"
#include "faction.h"
#include "field_type.h"
// IWYU pragma: no_include <flexbuffer_json.h>
#include "flexbuffer_json.h"
#include "game.h"
#include "inventory.h"
#include "item.h"
#include "item_category.h"
#include "iteminfo_query.h"
#include "itype.h"
#include "json.h"
#include "json_loader.h"
#include "lua_platform_bindings_coords.h"
#include "lua_platform_bindings_enums.h"
#include "lua_platform_bindings_values.h"
#include "lua_platform_camps.h"
#include "lua_platform_content.h"
#include "lua_platform_dialogue.h"
#include "lua_platform_factions.h"
#include "lua_platform_handle.h"
#include "lua_platform_hooks.h"
#include "lua_platform_hordes.h"
#include "lua_platform_identity.h"
#include "lua_platform_items.h"
#include "lua_platform_loader.h"
#include "lua_platform_mapgen.h"
#include "lua_platform_missions.h"
#include "lua_platform_npcs.h"
#include "lua_platform_overmap.h"
#include "lua_platform_runtime.h"
#include "lua_platform_sol.h"
#include "lua_platform_trade.h"
#include "lua_platform_vehicles.h"
#include "lua_platform_weather.h"
#include "lua_platform_world.h"
#include "lua_platform_world_content.h"
#include "lua_platform_world_services.h"
#include "lua_platform_zones.h"
#include "map.h"
#include "map_helpers.h"
#include "map_scale_constants.h"
#include "mapbuffer.h"
#include "mapgen_functions.h"
#include "mapgendata.h"
#include "mission.h"
#include "monster.h"
#include "npc.h"
#include "npctalk.h"
#include "npctrade.h"
#include "overmapbuffer.h"
#include "player_helpers.h"
#include "submap.h"
#include "talker.h"
#include "talker_monster.h"
#include "talker_npc.h"
#include "talker_topic.h"
#include "thread_pool.h"
#if defined(LOCALIZE)
    #include "translation_manager.h"
#endif
#include "translations.h"
#include "veh_type.h"
#include "vehicle.h"

namespace cata::lua_platform
{
class runtime;
}  // namespace cata::lua_platform

namespace
{

static const vproto_id vehicle_prototype_test_shopping_cart( "test_shopping_cart" );

struct registrar_graph_entry {
    std::string id;
    std::string copy_from;
};

template<typename Type, typename = void>
struct has_legacy_dialogue_quote_trade_item : std::false_type {
};

template<typename Type>
struct has_legacy_dialogue_quote_trade_item<Type, std::void_t<
decltype( &Type::quote_trade_item )>> : std::true_type {
};

template<typename Type, typename = void>
struct has_legacy_dialogue_buy_quoted_item : std::false_type {
};

template<typename Type>
struct has_legacy_dialogue_buy_quoted_item<Type, std::void_t<
decltype( &Type::buy_quoted_item )>> : std::true_type {
};

} // namespace

TEST_CASE( "lua_platform_exposes_one_runtime_contract", "[lua][platform]" )
{
    CHECK( cata::lua_platform::platform_version == 1 );
    CHECK( cata::lua_platform::loaded_mod_ids().empty() );
}
TEST_CASE( "lua_platform_shutdown_is_idempotent", "[lua][platform]" )
{
    cata::lua_platform::shutdown();
    cata::lua_platform::shutdown();
    CHECK( cata::lua_platform::loaded_mod_ids().empty() );
}

TEST_CASE( "lua_platform_registrar_orders_forward_inheritance_deterministically",
           "[lua][platform][content]" )
{
    const std::vector<registrar_graph_entry> entries = {
        { "child", "parent" },
        { "sibling", "" },
        { "parent", "native_parent" },
    };
    std::vector<std::size_t> order;
    std::string error;
    const bool resolved = cata::lua_platform::detail::resolve_platform_inheritance_order(
                              entries,
    []( const registrar_graph_entry & entry ) {
        return entry.id;
    },
    []( const registrar_graph_entry & entry ) {
        return entry.copy_from;
    },
    []( const std::string & id ) {
        return id == "native_parent";
    },
    order, error, "test definition" );

    REQUIRE( resolved );
    CHECK( error.empty() );
    REQUIRE( order.size() == entries.size() );
    CHECK( order[0] == 2 );
    CHECK( order[1] == 0 );
    CHECK( order[2] == 1 );
}

TEST_CASE( "lua_platform_registrar_rejects_inheritance_cycles",
           "[lua][platform][content]" )
{
    const std::vector<registrar_graph_entry> entries = {
        { "first", "second" },
        { "second", "first" },
    };
    std::vector<std::size_t> order;
    std::string error;

    CHECK_FALSE( cata::lua_platform::detail::resolve_platform_inheritance_order(
                     entries,
    []( const registrar_graph_entry & entry ) {
        return entry.id;
    },
    []( const registrar_graph_entry & entry ) {
        return entry.copy_from;
    },
    []( const std::string & ) {
        return false;
    },
    order, error, "test definition" ) );
    CHECK( order.empty() );
    CHECK( error.find( "cycle" ) != std::string::npos );
}

TEST_CASE( "lua_platform_registrar_applies_typed_extend_delete_atomically",
           "[lua][platform][content]" )
{
    std::set<std::string> target = { "base" };
    const std::set<std::string> extend = { "added" };
    const std::set<std::string> remove = { "base" };
    std::string error;

    REQUIRE( cata::lua_platform::detail::apply_platform_collection_patch(
                 target, &extend, &remove,
    []( const std::string & value ) {
        return value;
    },
    "test flags", error ) );
    CHECK( target == std::set<std::string> { "added" } );

    const std::set<std::string> conflicting = { "added" };
    CHECK_FALSE( cata::lua_platform::detail::apply_platform_collection_patch(
                     target, &conflicting,
                     static_cast<const std::set<std::string> *>( nullptr ),
    []( const std::string & value ) {
        return value;
    },
    "test flags", error ) );
    CHECK( error.find( "conflicts" ) != std::string::npos );
}

#if defined(CATA_ENABLE_LUA_PLATFORM) && CATA_ENABLE_LUA_PLATFORM
TEST_CASE( "lua_platform_item_description_append_hook_contract", "[lua][platform][hooks]" )
{
    cata::lua_platform::clear_active_runtimes();
    sol::state lua;
    sol::table ccb = lua.create_table();
    const std::shared_ptr<cata::lua_platform::runtime> runtime =
        cata::lua_platform::make_runtime( "test_footnotes_mod", 1, lua );
    on_out_of_scope cleanup( []() {
        cata::lua_platform::clear_active_runtimes();
        debug_reset_error_observed();
    } );
    cata::lua_platform::install_runtime_api( runtime, lua, ccb );
    lua["ccb"] = ccb;
    cata::lua_platform::set_active_runtimes( { runtime } );
    cata::lua_platform::runtime_world_ready( true );

    CHECK_FALSE( cata::lua_platform::dispatch_item_description_append(
                     "rock", std::nullopt, "en" ).has_value() );

    // 2. Register valid handler returning text
    lua.script( R"(
        ccb.runtime.handler("footnote_h1", function(payload)
            if payload.item_id == "rock" then
                return { text = "First footnote." }
            end
            return nil
        end)
        ccb.runtime.hook("on_item_description_append", "footnote_h1")
    )" );

    std::optional<std::string> res1 = cata::lua_platform::dispatch_item_description_append(
                                          "rock", std::nullopt, "en" );
    REQUIRE( res1.has_value() );
    CHECK( *res1 == "First footnote." );

    // 3. Register second handler -> aggregate text with \n
    lua.script( R"(
        ccb.runtime.handler("footnote_h2", function(payload)
            return { text = "Second footnote." }
        end)
        ccb.runtime.hook("on_item_description_append", "footnote_h2")
    )" );

    std::optional<std::string> res2 = cata::lua_platform::dispatch_item_description_append(
                                          "rock", std::nullopt, "en" );
    REQUIRE( res2.has_value() );
    CHECK( *res2 == "First footnote.\nSecond footnote." );

    // 4. Register invalid handler (extra fields like results) -> rejected, others preserved
    lua.script( R"(
        ccb.runtime.handler("footnote_bad", function(payload)
            return { text = "Bad footnote", results = {} }
        end)
        ccb.runtime.hook("on_item_description_append", "footnote_bad")
    )" );

    std::optional<std::string> res3 = cata::lua_platform::dispatch_item_description_append(
                                          "rock", std::nullopt, "en" );
    REQUIRE( res3.has_value() );
    CHECK( *res3 == "First footnote.\nSecond footnote." );
    CHECK( debug_has_error_been_observed() );
    debug_reset_error_observed();

    // Reject forbidden ASCII controls while preserving other handlers' text.
    lua.script( R"(
        ccb.runtime.handler("footnote_ctrl_chars", function(payload)
            return { text = "Corrupt\x1b[31mtext\x07." }
        end)
        ccb.runtime.hook("on_item_description_append", "footnote_ctrl_chars")
    )" );

    std::optional<std::string> res4 = cata::lua_platform::dispatch_item_description_append(
                                          "rock", std::nullopt, "en" );
    REQUIRE( res4.has_value() );
    CHECK( *res4 == "First footnote.\nSecond footnote." );
    CHECK( debug_has_error_been_observed() );
    debug_reset_error_observed();

    // 5b. Each C1 value is tested without DEL, which would mask a C1 regression.
    lua.script( R"(
        ccb.runtime.handler("footnote_c1_ctrl_chars", function(payload)
            return { text = footnote_control_text }
        end)
        ccb.runtime.hook("on_item_description_append", "footnote_c1_ctrl_chars")
    )" );

    for( const std::string &control : {
             std::string( "\xC2\x80" ),
             std::string( "\xC2\x9B" ),
             std::string( "\xC2\x9F" ),
             std::string( "\x7F" )
         } ) {
        lua["footnote_control_text"] = "Corrupt" + control + "text.";
        std::optional<std::string> res4b = cata::lua_platform::dispatch_item_description_append(
                                               "rock", std::nullopt, "en" );
        REQUIRE( res4b.has_value() );
        CHECK( *res4b == "First footnote.\nSecond footnote." );
        CHECK( debug_has_error_been_observed() );
        debug_reset_error_observed();
    }

    // Isolate the valid reentrancy case from the deliberately invalid handlers.
    sol::table reentrant_ccb = lua.create_table();
    const std::shared_ptr<cata::lua_platform::runtime> reentrant_runtime =
        cata::lua_platform::make_runtime( "test_reentrant_footnotes", 1, lua );
    cata::lua_platform::install_runtime_api( reentrant_runtime, lua, reentrant_ccb );
    lua["ccb"] = reentrant_ccb;
    cata::lua_platform::set_active_runtimes( { reentrant_runtime } );
    cata::lua_platform::runtime_world_ready( true );
    REQUIRE_FALSE( debug_has_error_been_observed() );

    // A handler may subscribe another handler without invalidating this dispatch.
    lua.script( R"(
        local dynamic_registered = false
        ccb.runtime.handler("footnote_reentrant", function(payload)
            if not dynamic_registered then
                ccb.runtime.handler("footnote_dynamic", function(p)
                    return { text = "Dynamic footnote." }
                end)
                ccb.runtime.hook("on_item_description_append", "footnote_dynamic")
                dynamic_registered = true
            end
            return { text = "Reentrant footnote." }
        end)
        ccb.runtime.hook("on_item_description_append", "footnote_reentrant")
    )" );

    std::optional<std::string> res5 = cata::lua_platform::dispatch_item_description_append(
                                          "rock", std::nullopt, "en" );
    REQUIRE( res5.has_value() );
    CHECK( *res5 == "Reentrant footnote." );
    CHECK_FALSE( debug_has_error_been_observed() );

    // Subsequent dispatch executes snapshot containing the newly added dynamic handler
    std::optional<std::string> res6 = cata::lua_platform::dispatch_item_description_append(
                                          "rock", std::nullopt, "en" );
    REQUIRE( res6.has_value() );
    CHECK( *res6 == "Reentrant footnote.\nDynamic footnote." );
    CHECK_FALSE( debug_has_error_been_observed() );
}

TEST_CASE( "lua_platform_item_ascii_art_fallback_hook_contract", "[lua][platform][hooks]" )
{
    cata::lua_platform::clear_active_runtimes();
    sol::state lua;
    sol::table ccb = lua.create_table();
    const std::shared_ptr<cata::lua_platform::runtime> runtime =
        cata::lua_platform::make_runtime( "test_art_mod", 1, lua );
    on_out_of_scope cleanup( []() {
        cata::lua_platform::clear_active_runtimes();
        debug_reset_error_observed();
    } );
    cata::lua_platform::install_runtime_api( runtime, lua, ccb );
    lua["ccb"] = ccb;
    cata::lua_platform::set_active_runtimes( { runtime } );
    cata::lua_platform::runtime_world_ready( true );

    // Load mock ascii art
    JsonObject jo = json_loader::from_string(
                        R"({"id": "test_mock_art_id", "picture": ["-*-"]})" ).get_object();
    ascii_art::load_ascii_art( jo, "test" );
    REQUIRE( ascii_art_id( "test_mock_art_id" ).is_valid() );

    CHECK_FALSE( cata::lua_platform::dispatch_item_ascii_art_fallback(
                     "rock", std::nullopt, "en" ).has_value() );

    // 2. Invalid candidate first, valid candidate second -> first valid wins
    lua.script( R"(
        ccb.runtime.handler("art_h1", function(payload)
            return { art_id = "nonexistent_art_id_xyz" }
        end)
        ccb.runtime.handler("art_h2", function(payload)
            return { art_id = "test_mock_art_id" }
        end)
        ccb.runtime.handler("art_h3", function(payload)
            return { art_id = "test_mock_art_id_unreached" }
        end)
        ccb.runtime.hook("on_item_ascii_art_fallback", "art_h1")
        ccb.runtime.hook("on_item_ascii_art_fallback", "art_h2")
        ccb.runtime.hook("on_item_ascii_art_fallback", "art_h3")
    )" );

    std::optional<std::string> art_res = cata::lua_platform::dispatch_item_ascii_art_fallback(
            "rock", std::nullopt, "en" );
    REQUIRE( art_res.has_value() );
    CHECK( *art_res == "test_mock_art_id" );
    CHECK( debug_has_error_been_observed() );
    debug_reset_error_observed();
}

TEST_CASE( "lua_platform_item_info_footnotes_integration", "[lua][platform][hooks]" )
{
    cata::lua_platform::clear_active_runtimes();
    sol::state lua;
    sol::table ccb = lua.create_table();
    const std::shared_ptr<cata::lua_platform::runtime> runtime =
        cata::lua_platform::make_runtime( "test_item_footnotes", 1, lua );
    on_out_of_scope cleanup( []() {
        cata::lua_platform::clear_active_runtimes();
        debug_reset_error_observed();
    } );
    cata::lua_platform::install_runtime_api( runtime, lua, ccb );
    lua["ccb"] = ccb;
    cata::lua_platform::set_active_runtimes( { runtime } );
    cata::lua_platform::runtime_world_ready( true );

    lua.script( R"(
        ccb.runtime.handler("footnote", function(payload)
            if payload.item_id ~= "rock" then return nil end
            if payload.language == "zh_CN" then
                return { text = "文明倒退后，它又成了高科技。" }
            end
            return { text = "Civilization collapsed and this became cutting-edge technology." }
        end)
        ccb.runtime.handler("art", function(payload)
            return { art_id = "test_item_footnotes_fallback_art" }
        end)
        ccb.runtime.hook("on_item_description_append", "footnote")
        ccb.runtime.hook("on_item_ascii_art_fallback", "art")
    )" );

    JsonObject fallback_art = json_loader::from_string(
                                  R"({"id":"test_item_footnotes_fallback_art","picture":["|fallback|"]})" ).get_object();
    ascii_art::load_ascii_art( fallback_art, "test" );
    JsonObject native_art = json_loader::from_string(
                                R"({"id":"test_item_footnotes_native_art","picture":["|native|"]})" ).get_object();
    ascii_art::load_ascii_art( native_art, "test" );

    item rock( itype_id( "rock" ) );
    itype &rock_type = const_cast<itype &>( *rock.type );
    const ascii_art_id original_art = rock_type.picture_id;
    on_out_of_scope restore_art( [&rock_type, original_art]() {
        rock_type.picture_id = original_art;
    } );
    const auto info_contains = []( const std::vector<iteminfo> &info, const std::string & text ) {
        return std::any_of( info.begin(), info.end(), [&text]( const iteminfo & entry ) {
            return entry.sName.find( text ) != std::string::npos ||
                   entry.sFmt.find( text ) != std::string::npos;
        } );
    };

#if defined(LOCALIZE)
    const std::string original_language = TranslationManager::GetInstance().GetCurrentLanguage();
    on_out_of_scope restore_language( [original_language]() {
        set_language( original_language );
    } );
    set_language( "zh_CN" );
    std::vector<iteminfo> chinese_info;
    rock.basic_info( chinese_info, &iteminfo_query::all, 1, false );
    CHECK( info_contains( chinese_info, "文明倒退后" ) );
    set_language( "en" );
#endif
    std::vector<iteminfo> english_info;
    rock.basic_info( english_info, &iteminfo_query::all, 1, false );
    CHECK( info_contains( english_info, "Civilization collapsed" ) );
    CHECK_FALSE( info_contains( english_info, "文明倒退后" ) );

    rock_type.picture_id = ascii_art_id();
    std::vector<iteminfo> fallback_info;
    rock.ascii_art_info( fallback_info, &iteminfo_query::all, 1, false );
    CHECK( info_contains( fallback_info, "|fallback|" ) );

    rock_type.picture_id = ascii_art_id( "test_item_footnotes_native_art" );
    std::vector<iteminfo> native_info;
    rock.ascii_art_info( native_info, &iteminfo_query::all, 1, false );
    CHECK( info_contains( native_info, "|native|" ) );
    CHECK_FALSE( info_contains( native_info, "|fallback|" ) );

    cata::lua_platform::clear_active_runtimes();
    CHECK_FALSE( cata::lua_platform::dispatch_item_description_append(
                     "rock", std::nullopt, "en" ).has_value() );
    CHECK_FALSE( cata::lua_platform::dispatch_item_ascii_art_fallback(
                     "rock", std::nullopt, "en" ).has_value() );
}

TEST_CASE( "lua_platform_item_display_hooks_skip_pool_workers",
           "[lua][platform][hooks][thread_pool]" )
{
    cata::lua_platform::clear_active_runtimes();
    sol::state lua;
    sol::table ccb = lua.create_table();
    const std::shared_ptr<cata::lua_platform::runtime> runtime =
        cata::lua_platform::make_runtime( "test_item_display_workers", 1, lua );
    on_out_of_scope cleanup( []() {
        cata::lua_platform::clear_active_runtimes();
        debug_reset_error_observed();
    } );
    cata::lua_platform::install_runtime_api( runtime, lua, ccb );
    lua["ccb"] = ccb;
    cata::lua_platform::set_active_runtimes( { runtime } );
    cata::lua_platform::runtime_world_ready( true );
    lua.script( R"(
        display_calls = 0
        ccb.runtime.handler("description", function(payload)
            display_calls = display_calls + 1
            return { text = "Additional display text." }
        end)
        ccb.runtime.handler("art", function(payload)
            display_calls = display_calls + 1
            return { art_id = "test_item_display_worker_art" }
        end)
        ccb.runtime.hook("on_item_description_append", "description")
        ccb.runtime.hook("on_item_ascii_art_fallback", "art")
    )" );
    JsonObject art = json_loader::from_string(
                         R"({"id":"test_item_display_worker_art","picture":["|art|"]})" ).get_object();
    ascii_art::load_ascii_art( art, "test" );
    REQUIRE( cata::lua_platform::dispatch_item_description_append( "rock" ).has_value() );
    REQUIRE( cata::lua_platform::dispatch_item_ascii_art_fallback( "rock" ).has_value() );
    REQUIRE( lua["display_calls"].get<int>() == 2 );

    cata_thread_pool pool( 1 );
    auto result = pool.submit_returning( []() {
        const bool worker = is_pool_worker_thread();
        const auto description = cata::lua_platform::dispatch_item_description_append( "rock" );
        const auto fallback = cata::lua_platform::dispatch_item_ascii_art_fallback( "rock" );
        return worker && !description.has_value() && !fallback.has_value();
    } );
    CHECK( result.get() );
    CHECK( lua["display_calls"].get<int>() == 2 );
    CHECK_FALSE( debug_has_error_been_observed() );
}

#endif
