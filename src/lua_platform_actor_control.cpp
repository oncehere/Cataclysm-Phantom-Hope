#if CATA_ENABLE_LUA_PLATFORM

#include "lua_platform_actor_control.h"

#include <optional>
#include <string>
#include <utility>

#include "actor_control.h"
#include "flexbuffer_json.h"
#include "json_loader.h"
#include "lua_platform_handle.h"
#include "npc.h"

namespace cata::lua_platform
{
namespace
{
// Only engine-produced, already bounded status data enters this conversion.
// No Lua decoder, raw object pointer, or execution hook is exposed.
sol::object detached_json( sol::state_view lua, const JsonValue &json )
{
    if( json.test_object() ) {
        sol::table value = lua.create_table();
        const JsonObject object = json.get_object();
        object.allow_omitted_members();
        for( const JsonMember &entry : object ) {
            value[entry.name()] = detached_json( lua, entry );
        }
        return sol::make_object( lua, std::move( value ) );
    }
    if( json.test_array() ) {
        sol::table value = lua.create_table();
        int index = 1;
        for( const JsonValue &entry : json.get_array() ) {
            value[index++] = detached_json( lua, entry );
        }
        return sol::make_object( lua, std::move( value ) );
    }
    if( json.test_string() ) {
        return sol::make_object( lua, json.get_string() );
    }
    if( json.test_bool() ) {
        return sol::make_object( lua, json.get_bool() );
    }
    if( json.test_int() ) {
        return sol::make_object( lua, json.get_int64() );
    }
    if( json.test_number() ) {
        return sol::make_object( lua, json.get_float() );
    }
    return sol::make_object( lua, sol::nil );
}

sol::table control_result( sol::state_view lua, bool success, const std::string &error )
{
    if( !success ) {
        return make_game_error_result( lua, {error, "Actor control operation rejected"} );
    }
    return make_game_value_result( lua, detached_json( lua,
                                   json_loader::from_string( cata::actor_control::status() ) ) );
}
} // namespace

void install_actor_control_api(
    sol::table &services,
    std::function<game_handle_runtime()> current_runtime_generation,
    std::function<std::size_t()> current_world_generation,
    std::function<void()> require_read,
    std::function<void()> require_write )
{
    sol::state_view lua( services.lua_state() );
    sol::table api = lua.create_table();
    api.set_function( "enable", [require_write]( sol::this_state state, bool value ) {
        require_write();
        cata::actor_control::enable( value );
        return control_result( sol::state_view( state ), true, "" );
    } );
    api.set_function( "bind", [require_write, current_runtime_generation, current_world_generation](
    sol::this_state state, const game_handle & handle, const std::string & profile_id ) {
        require_write();
        sol::state_view lua_state( state );
        std::optional<game_handle_error> resolution_error;
        npc *actor = resolve_exact_npc( handle, current_runtime_generation(),
                                        current_world_generation(), resolution_error );
        if( actor == nullptr ) {
            return make_game_error_result( lua_state, *resolution_error );
        }
        std::string error;
        const bool success = cata::actor_control::bind( *actor, profile_id, error );
        return control_result( lua_state, success, error );
    } );
    api.set_function( "chat", [require_write]( sol::this_state state, const std::string & text ) {
        require_write();
        std::string error;
        const bool success = cata::actor_control::chat( text, error );
        return control_result( sol::state_view( state ), success, error );
    } );
    api.set_function( "status", [require_read]( sol::this_state state,
    sol::optional<bool> include_debug ) {
        require_read();
        sol::state_view lua_state( state );
        return make_game_value_result( lua_state, detached_json( lua_state,
                                       json_loader::from_string( cata::actor_control::status(
                                               include_debug.value_or( false ) ) ) ) );
    } );
    api.set_function( "pause", [require_write]( sol::this_state state, bool value ) {
        require_write();
        cata::actor_control::pause( value );
        return control_result( sol::state_view( state ), true, "" );
    } );
    api.set_function( "cancel", [require_write]( sol::this_state state ) {
        require_write();
        cata::actor_control::cancel();
        return control_result( sol::state_view( state ), true, "" );
    } );
    api.set_function( "stop", [require_write]( sol::this_state state ) {
        require_write();
        cata::actor_control::stop();
        return control_result( sol::state_view( state ), true, "" );
    } );
    services["actor_control"] = std::move( api );
}
} // namespace cata::lua_platform

#endif // CATA_ENABLE_LUA_PLATFORM
