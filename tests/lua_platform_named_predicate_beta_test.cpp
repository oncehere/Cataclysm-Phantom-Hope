// Generated Lua captured from tools/migrate_lua_first.py SHA256
// 3e48e5dd40b5358ca648e155f689815be8f0f09527c6fdf846995286a28b51d0
// Native services and handles remain real.

#if defined(CATA_ENABLE_LUA_PLATFORM) && CATA_ENABLE_LUA_PLATFORM

#include <functional>
#include <memory>
#include <optional>
#include <string>

#include "avatar.h"
#include "calendar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "character_id.h"
#include "condition.h"
#include "dialogue.h"
#include "item.h"
#include "json_loader.h"
#include "lua_platform_bindings_values.h"
#include "lua_platform_handle.h"
#include "lua_platform_mutations.h"
#include "lua_platform_npcs.h"
#include "lua_platform_sol.h"
#include "lua_platform_variables.h"
#include "npc.h"
#include "talker.h"
#include "type_id.h"

TEST_CASE( "lua_platform_named_predicate_uses_later_beta_with_real_handles",
           "[lua][platform][named_predicates][semantic]" )
{
    namespace platform = cata::lua_platform;
    const trait_id quick( "QUICK" );
    avatar alpha;
    avatar avatar_beta;
    npc setter_beta;
    npc later_beta;
    npc later_alpha;
    alpha.normalize();
    avatar_beta.normalize();
    setter_beta.normalize();
    later_beta.normalize();
    later_alpha.normalize();
    alpha.setID( character_id( 7471 ), true );
    avatar_beta.setID( character_id( 7472 ), true );
    setter_beta.setID( character_id( 7473 ), true );
    later_beta.setID( character_id( 7474 ), true );
    later_alpha.setID( character_id( 7475 ), true );
    const trait_id tough( "TOUGH" );
    alpha.unset_mutation( quick );
    setter_beta.unset_mutation( quick );
    later_beta.set_mutation( quick );
    avatar_beta.set_mutation( quick );
    later_beta.set_mutation( tough );
    avatar_beta.set_mutation( tough );
    later_alpha.set_mutation( quick );
    later_alpha.unset_mutation( tough );
    alpha.set_value( "beta_trait", "QUICK" );
    setter_beta.set_value( "alpha_trait", "TOUGH" );
    later_alpha.set_value( "beta_trait", "TOUGH" );
    later_beta.set_value( "alpha_trait", "QUICK" );
    avatar_beta.set_value( "alpha_trait", "QUICK" );
    later_beta.myclass = npc_class_id( "NC_NONE" );
    later_beta.rules.aim = aim_rule::WHEN_CONVENIENT;
    platform::register_npc_handle_identity( setter_beta );
    platform::register_npc_handle_identity( later_beta );
    platform::register_npc_handle_identity( later_alpha );
    const on_out_of_scope retire( [&]() {
        platform::retire_npc_handle_identity( setter_beta );
        platform::retire_npc_handle_identity( later_beta );
        platform::retire_npc_handle_identity( later_alpha );
    } );

    dialogue original( get_talker_for( alpha ), get_talker_for( setter_beta ) );
    talk_effect_t set_native;
    set_native.parse_sub_effect( json_loader::from_string(
                                     R"({"set_condition":"later_beta","condition":{"npc_has_trait":"QUICK"}})"
                                 ).get_object(), "named_predicate_real_beta" );
    for( const talk_effect_fun_t &effect : set_native.effects ) {
        effect( original );
    }
    talk_effect_t set_pair_native;
    set_pair_native.parse_sub_effect( json_loader::from_string(
                                          R"({"set_condition":"pair","condition":{"and":[{"u_has_trait":{"npc_val":"alpha_trait"}},{"npc_has_trait":{"u_val":"beta_trait"}}]}})"
                                      ).get_object(), "named_predicate_real_pair" );
    for( const talk_effect_fun_t &effect : set_pair_native.effects ) {
        effect( original );
    }
    talk_effect_t set_or_native;
    set_or_native.parse_sub_effect( json_loader::from_string(
                                        R"({"set_condition":"alpha_or_beta","condition":{"or":[{"u_has_trait":"QUICK"},{"npc_has_trait":"QUICK"}]}})"
                                    ).get_object(), "named_predicate_real_or" );
    for( const talk_effect_fun_t &effect : set_or_native.effects ) {
        effect( original );
    }
    const conditional_t get_or_native( json_loader::from_string(
                                           R"({"get_condition":"alpha_or_beta"})" ).get_object() );
    const conditional_t get_pair_native( json_loader::from_string(
            R"({"get_condition":"pair"})" ).get_object() );
    const conditional_t get_native( json_loader::from_string(
                                        R"({"get_condition":"later_beta"})" ).get_object() );
    dialogue child( get_talker_for( alpha ), get_talker_for( later_beta ),
                    original.get_conditionals(), original.get_context() );
    dialogue avatar_child( get_talker_for( alpha ), get_talker_for( avatar_beta ),
                           original.get_conditionals(), original.get_context() );
    dialogue pair_child( get_talker_for( later_alpha ), get_talker_for( later_beta ),
                         original.get_conditionals(), original.get_context() );
    dialogue avatar_pair_child( get_talker_for( later_alpha ), get_talker_for( avatar_beta ),
                                original.get_conditionals(), original.get_context() );
    dialogue null_beta_child( get_talker_for( later_alpha ), nullptr,
                              original.get_conditionals(), original.get_context() );
    const conditional_t native_class( json_loader::from_string(
                                          R"({"npc_has_class":"NC_NONE"})" ).get_object() );
    const conditional_t native_rule( json_loader::from_string(
                                         R"({"npc_aim_rule":"AIM_WHEN_CONVENIENT"})" ).get_object() );

    sol::state lua;
    lua.open_libraries( sol::lib::base );
    sol::table services = lua.create_table();
    const platform::game_handle_runtime_owner_ptr owner =
        platform::make_game_handle_runtime_owner();
    const platform::game_handle_runtime runtime{ owner, 1 };
    std::size_t current_world = 1;
    platform::install_value_type_api( lua, services, []() {} );
    platform::install_game_handle_api( lua, services, [runtime]() {
        return runtime;
    }, [&]() {
        return current_world;
    }, []() {} );
    platform::install_mutation_api( services, [runtime]() {
        return runtime;
    }, [&]() {
        return current_world;
    }, []() {}, []() {} );
    platform::install_npc_api( services, [runtime]() {
        return runtime;
    }, [&]() {
        return current_world;
    }, []() {}, []() {}, []() {} );
    platform::install_variable_api( services, [runtime]() {
        return runtime;
    }, [&]() {
        return current_world;
    }, []() {}, []() {}, []() {
        return false;
    } );
    const auto handle_for = [&]( Creature & target, const std::string & scope ) {
        return platform::game_handle::from_creature(
                   target, { scope, 0, 0, 0, 0, {} }, runtime, 1 );
    };
    const platform::game_handle alpha_handle = handle_for( alpha, "avatar" );
    const platform::game_handle later_alpha_handle = handle_for( later_alpha, "npc" );
    const platform::game_handle setter_beta_handle = handle_for( setter_beta, "npc" );
    const platform::game_handle later_beta_handle = handle_for( later_beta, "npc" );
    const platform::game_handle avatar_beta_handle = handle_for( avatar_beta, "avatar" );
    // Character services resolve the underlying live Character even when the
    // locator says "character".  NPC-only services additionally require "npc".
    const platform::game_handle character_beta_handle = handle_for( avatar_beta, "character" );
    const platform::game_handle character_npc_beta_handle = handle_for( later_beta, "character" );
    std::optional<platform::game_handle_error> subtype_error;
    REQUIRE( platform::resolve_exact_character( character_npc_beta_handle, runtime,
             current_world, subtype_error ) == &later_beta );
    CHECK_FALSE( subtype_error.has_value() );
    CHECK( character_npc_beta_handle.locator().stable_id == later_beta.getID().get_value() );
    CHECK( platform::resolve_exact_npc( character_npc_beta_handle, runtime,
                                        current_world, subtype_error ) == nullptr );
    REQUIRE( subtype_error.has_value() );
    CHECK( subtype_error->code == "wrong_subtype" );
    item wrong_kind( itype_id( "rock" ), calendar::turn );
    const platform::game_handle item_beta_handle = platform::game_handle::from_item(
                wrong_kind, { "test_item", 0, 0, 0, 0, {} },
                runtime, 1 );
    lua["services"] = services;
    const sol::protected_function_result helpers = lua.safe_script( R"(
        local function service_value(result)
            assert(result.ok)
            return result.value
        end
        local native_query = services.mutations.has_id_text
        queries = 0
        services.mutations.has_id_text = function(character, text)
            queries = queries + 1
            return native_query(character, text)
        end
        local native_resolve = services.variables.resolve
        variable_queries = 0
        services.variables.resolve = function(...)
            variable_queries = variable_queries + 1
            return native_resolve(...)
        end
        local native_npc_get, native_ai_rules = services.npcs.get, services.npcs.ai_rules
        npc_queries = 0
        services.npcs.get = function(npc)
            npc_queries = npc_queries + 1
            return native_npc_get(npc)
        end
        services.npcs.ai_rules = function(npc)
            npc_queries = npc_queries + 1
            return native_ai_rules(npc)
        end
        store_named = function(context, actor, setter_beta)
    context.conditions = context.conditions or {}
    local stored_condition_name = tostring(("later_beta") or "")
    context.conditions[stored_condition_name] = function(context, actor, stored_condition_beta)
        local matched, valid = (function() if stored_condition_beta == nil or stored_condition_beta.kind ~= "creature" or (stored_condition_beta.subtype ~= "avatar" and stored_condition_beta.subtype ~= "character" and stored_condition_beta.subtype ~= "npc") or not stored_condition_beta:is_valid() then return false, false end; return ((function(character) if character == nil or character.kind ~= "creature" then return false end; if character.subtype ~= "avatar" and character.subtype ~= "character" and character.subtype ~= "npc" then return false end; local raw = "QUICK"; if type(raw) ~= "string" then return false end; return service_value(services.mutations.has_id_text(character, raw)) end)(stored_condition_beta)), true end)()
        return valid and matched
    end
        end
        read_named = function(context, actor, beta)
            context.actors = {alpha = actor, beta = beta}
            return (function() local stored_condition = context.conditions and context.conditions["later_beta"]; return stored_condition ~= nil and stored_condition(context, actor, context.actors.beta) or false end)()
        end
        store_pair = function(context, actor, setter_beta)
    context.conditions = context.conditions or {}
    local stored_condition_name = tostring(("pair") or "")
    context.conditions[stored_condition_name] = function(context, actor, stored_condition_beta)
        local matched, valid = (function() local matched, valid = (function() if stored_condition_beta == nil or stored_condition_beta.kind ~= "creature" or (stored_condition_beta.subtype ~= "avatar" and stored_condition_beta.subtype ~= "character" and stored_condition_beta.subtype ~= "npc") or not stored_condition_beta:is_valid() then return false, false end; return ((function(character) if character == nil or character.kind ~= "creature" then return false end; if character.subtype ~= "avatar" and character.subtype ~= "character" and character.subtype ~= "npc" then return false end; local raw = (function(result) if result.exists == false then return "" end; return type(result.value) == "string" and result.value or "" end)(service_value(services.variables.resolve(context.data, stored_condition_beta, "npc", "alpha_trait"))); if type(raw) ~= "string" then return false end; return service_value(services.mutations.has_id_text(character, raw)) end)(actor)), true end)(); if not valid then return false, false end; if not matched then return false, true end; local matched, valid = (function() if stored_condition_beta == nil or stored_condition_beta.kind ~= "creature" or (stored_condition_beta.subtype ~= "avatar" and stored_condition_beta.subtype ~= "character" and stored_condition_beta.subtype ~= "npc") or not stored_condition_beta:is_valid() then return false, false end; return ((function(character) if character == nil or character.kind ~= "creature" then return false end; if character.subtype ~= "avatar" and character.subtype ~= "character" and character.subtype ~= "npc" then return false end; local raw = (function(result) if result.exists == false then return "" end; return type(result.value) == "string" and result.value or "" end)(service_value(services.variables.resolve(context.data, actor, "u", "beta_trait"))); if type(raw) ~= "string" then return false end; return service_value(services.mutations.has_id_text(character, raw)) end)(stored_condition_beta)), true end)(); if not valid then return false, false end; if not matched then return false, true end; return true, true; end)()
        return valid and matched
    end
        end
        read_pair = function(context, actor, beta)
            context.actors = {alpha = actor, beta = beta}
            return (function() local stored_condition = context.conditions and context.conditions["pair"]; return stored_condition ~= nil and stored_condition(context, actor, context.actors.beta) or false end)()
        end
        store_npc_only = function(context, actor, setter_beta)
    context.conditions = context.conditions or {}
    local stored_condition_name = tostring(("npc_only") or "")
    context.conditions[stored_condition_name] = function(context, actor, stored_condition_beta)
        local matched, valid = (function() local matched, valid = (function() if stored_condition_beta == nil or stored_condition_beta.kind ~= "creature" or (stored_condition_beta.subtype ~= "avatar" and stored_condition_beta.subtype ~= "character" and stored_condition_beta.subtype ~= "npc") or not stored_condition_beta:is_valid() then return false, false end; return ((function() local npc = stored_condition_beta; if npc == nil or npc.kind ~= "creature" or npc.subtype ~= "npc" or not npc:is_valid() then return false end; return service_value(services.npcs.get(npc)).class.value == "NC_NONE" end)()), true end)(); if not valid then return false, false end; if not matched then return false, true end; local matched, valid = (function() if stored_condition_beta == nil or stored_condition_beta.kind ~= "creature" or (stored_condition_beta.subtype ~= "avatar" and stored_condition_beta.subtype ~= "character" and stored_condition_beta.subtype ~= "npc") or not stored_condition_beta:is_valid() then return false, false end; return ((function() local npc = stored_condition_beta; if npc == nil or npc.kind ~= "creature" or npc.subtype ~= "npc" or not npc:is_valid() then return false end; return service_value(services.npcs.ai_rules(npc)).aim == "AIM_WHEN_CONVENIENT" end)()), true end)(); if not valid then return false, false end; if not matched then return false, true end; return true, true; end)()
        return valid and matched
    end
        end
        read_npc_only = function(context, actor, beta)
            context.actors = {alpha = actor, beta = beta}
            return (function() local stored_condition = context.conditions and context.conditions["npc_only"]; return stored_condition ~= nil and stored_condition(context, actor, context.actors.beta) or false end)()
        end
        store_or = function(context, actor, setter_beta)
    context.conditions = context.conditions or {}
    local stored_condition_name = tostring(("alpha_or_beta") or "")
    context.conditions[stored_condition_name] = function(context, actor, stored_condition_beta)
        local matched, valid = (function() local matched, valid = (function() return ((function(character) if character == nil or character.kind ~= "creature" then return false end; if character.subtype ~= "avatar" and character.subtype ~= "character" and character.subtype ~= "npc" then return false end; local raw = "QUICK"; if type(raw) ~= "string" then return false end; return service_value(services.mutations.has_id_text(character, raw)) end)(actor)), true end)(); if not valid then return false, false end; if matched then return true, true end; local matched, valid = (function() if stored_condition_beta == nil or stored_condition_beta.kind ~= "creature" or (stored_condition_beta.subtype ~= "avatar" and stored_condition_beta.subtype ~= "character" and stored_condition_beta.subtype ~= "npc") or not stored_condition_beta:is_valid() then return false, false end; return ((function(character) if character == nil or character.kind ~= "creature" then return false end; if character.subtype ~= "avatar" and character.subtype ~= "character" and character.subtype ~= "npc" then return false end; local raw = "QUICK"; if type(raw) ~= "string" then return false end; return service_value(services.mutations.has_id_text(character, raw)) end)(stored_condition_beta)), true end)(); if not valid then return false, false end; if matched then return true, true end; return false, true; end)()
        return valid and matched
    end
        end
        read_or = function(context, actor, beta)
            context.actors = {alpha = actor, beta = beta}
            return (function() local stored_condition = context.conditions and context.conditions["alpha_or_beta"]; return stored_condition ~= nil and stored_condition(context, actor, context.actors.beta) or false end)()
        end
    )", sol::script_pass_on_error );
    REQUIRE( helpers.valid() );
    sol::table context = lua.create_table();
    context["data"] = lua.create_table();
    sol::protected_function store = lua["store_named"];
    REQUIRE( store( context, alpha_handle, setter_beta_handle ).valid() );
    sol::protected_function store_pair = lua["store_pair"];
    sol::protected_function store_npc_only = lua["store_npc_only"];
    sol::protected_function store_or = lua["store_or"];
    REQUIRE( store_pair( context, alpha_handle, setter_beta_handle ).valid() );
    REQUIRE( store_npc_only( context, alpha_handle, setter_beta_handle ).valid() );
    REQUIRE( store_or( context, alpha_handle, setter_beta_handle ).valid() );
    const sol::protected_function read = lua["read_named"];
    const auto query = [&]( const platform::game_handle & beta ) {
        const sol::protected_function_result result = read( context, alpha_handle, beta );
        if( !result.valid() ) {
            const sol::error error = result;
            INFO( error.what() );
        }
        REQUIRE( result.valid() );
        return result.get<bool>();
    };
    CHECK_FALSE( get_native( original ) );
    CHECK( query( setter_beta_handle ) == get_native( original ) );
    CHECK( get_native( child ) );
    CHECK( query( later_beta_handle ) == get_native( child ) );
    CHECK( query( setter_beta_handle ) == get_native( original ) );
    CHECK( query( avatar_beta_handle ) == get_native( avatar_child ) );
    CHECK( query( character_beta_handle ) == get_native( avatar_child ) );
    CHECK( query( character_npc_beta_handle ) == get_native( child ) );
    const sol::protected_function read_pair = lua["read_pair"];
    const auto query_pair = [&]( const platform::game_handle & actor,
    const platform::game_handle & beta ) {
        const sol::protected_function_result result = read_pair( context, actor, beta );
        if( !result.valid() ) {
            const sol::error error = result;
            INFO( error.what() );
        }
        REQUIRE( result.valid() );
        return result.get<bool>();
    };
    CHECK_FALSE( get_pair_native( original ) );
    CHECK( query_pair( alpha_handle, setter_beta_handle ) == get_pair_native( original ) );
    CHECK( get_pair_native( pair_child ) );
    CHECK( query_pair( later_alpha_handle, later_beta_handle ) == get_pair_native( pair_child ) );
    CHECK( query_pair( later_alpha_handle,
                       avatar_beta_handle ) == get_pair_native( avatar_pair_child ) );
    CHECK( query_pair( later_alpha_handle,
                       character_beta_handle ) == get_pair_native( avatar_pair_child ) );
    CHECK( query_pair( later_alpha_handle,
                       character_npc_beta_handle ) == get_pair_native( pair_child ) );
    CHECK_FALSE( query_pair( alpha_handle, later_beta_handle ) );
    CHECK_FALSE( query_pair( later_alpha_handle, setter_beta_handle ) );
    // Native OR does not read an absent beta after a true alpha branch.  A
    // whole-predicate beta guard would incorrectly reject this valid child.
    REQUIRE_FALSE( null_beta_child.has_actor( true ) );
    REQUIRE( get_or_native( null_beta_child ) );
    const int queries_before_short_circuit = lua["queries"].get<int>();
    const int variables_before_short_circuit = lua["variable_queries"].get<int>();
    const int npcs_before_short_circuit = lua["npc_queries"].get<int>();
    const sol::protected_function read_or = lua["read_or"];
    const sol::protected_function_result short_circuit = read_or( context, later_alpha_handle,
            sol::lua_nil );
    REQUIRE( short_circuit.valid() );
    CHECK( short_circuit.get<bool>() == get_or_native( null_beta_child ) );
    CHECK( lua["queries"].get<int>() == queries_before_short_circuit + 1 );
    CHECK( lua["variable_queries"].get<int>() == variables_before_short_circuit );
    CHECK( lua["npc_queries"].get<int>() == npcs_before_short_circuit );
    const sol::protected_function npc_only = lua["read_npc_only"];
    const auto query_npc_only = [&]( const platform::game_handle & beta ) {
        const sol::protected_function_result result = npc_only( context, alpha_handle, beta );
        REQUIRE( result.valid() );
        return result.get<bool>();
    };
    CHECK( query_npc_only( later_beta_handle ) ==
           ( native_class( child ) && native_rule( child ) ) );
    const int npc_queries_before_non_npc = lua["npc_queries"].get<int>();
    CHECK_FALSE( native_class( avatar_child ) );
    CHECK_FALSE( native_rule( avatar_child ) );
    CHECK_FALSE( query_npc_only( avatar_beta_handle ) );
    CHECK_FALSE( query_npc_only( character_beta_handle ) );
    // Native talker conditions know this is an NPC, but the public NPC service
    // rejects its non-NPC locator.  The renderer must fail closed at that API
    // boundary rather than call a service guaranteed to return wrong_subtype.
    CHECK( native_class( child ) );
    CHECK( native_rule( child ) );
    CHECK_FALSE( query_npc_only( character_npc_beta_handle ) );
    CHECK( lua["npc_queries"].get<int>() == npc_queries_before_non_npc );
    const int queries_before_invalid = lua["queries"].get<int>();
    const int variables_before_invalid = lua["variable_queries"].get<int>();
    const int npcs_before_invalid = lua["npc_queries"].get<int>();
    const sol::protected_function_result absent = read( context, alpha_handle, sol::lua_nil );
    REQUIRE( absent.valid() );
    CHECK_FALSE( absent.get<bool>() );
    const sol::protected_function_result absent_pair = read_pair( context, later_alpha_handle,
            sol::lua_nil );
    REQUIRE( absent_pair.valid() );
    CHECK_FALSE( absent_pair.get<bool>() );
    const sol::protected_function_result absent_npc = npc_only( context, alpha_handle,
            sol::lua_nil );
    REQUIRE( absent_npc.valid() );
    CHECK_FALSE( absent_npc.get<bool>() );
    CHECK_FALSE( query( platform::game_handle() ) );
    CHECK_FALSE( query_pair( later_alpha_handle, platform::game_handle() ) );
    CHECK_FALSE( query_npc_only( platform::game_handle() ) );
    CHECK_FALSE( query( item_beta_handle ) );
    CHECK_FALSE( query_pair( later_alpha_handle, item_beta_handle ) );
    CHECK_FALSE( query_npc_only( item_beta_handle ) );
    platform::retire_npc_handle_identity( later_beta );
    CHECK_FALSE( query( later_beta_handle ) );
    CHECK_FALSE( query_pair( later_alpha_handle, later_beta_handle ) );
    CHECK_FALSE( query_npc_only( later_beta_handle ) );
    CHECK_FALSE( query( character_npc_beta_handle ) );
    CHECK_FALSE( query_pair( later_alpha_handle, character_npc_beta_handle ) );
    CHECK_FALSE( query_npc_only( character_npc_beta_handle ) );
    current_world = 2;
    CHECK_FALSE( query( avatar_beta_handle ) );
    CHECK_FALSE( query_pair( later_alpha_handle, avatar_beta_handle ) );
    CHECK_FALSE( query_npc_only( avatar_beta_handle ) );
    CHECK_FALSE( query_npc_only( setter_beta_handle ) );
    CHECK( lua["queries"].get<int>() == queries_before_invalid );
    CHECK( lua["variable_queries"].get<int>() == variables_before_invalid );
    CHECK( lua["npc_queries"].get<int>() == npcs_before_invalid );
}
#endif
