#include <cstdlib>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <set>
#include <sstream>
#include <string>
#include <utility>

#ifndef _WIN32
    #include <sys/stat.h>
#endif

#include "actor_control.h"
#include "actor_control_bridge.h"
#include "actor_control_protocol.h"
#include "actor_control_runtime.h"
#include "avatar.h"
#include "calendar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "character_attire.h"
#include "character_id.h"
#include "coordinates.h"
#include "effect.h"
#include "enums.h"
#include "flag.h"
#include "flexbuffer_json.h"
#include "game.h"
#include "item.h"
#include "item_factory.h"
#include "item_location.h"
#include "itype.h"
#include "json.h"
#include "json_loader.h"
#include "map.h"
#include "map_helpers.h"
#include "map_helpers_tests.h"
#include "map_iterator.h"
#include "npc.h"
#include "npc_execution_adapter.h"
#include "path_info.h"
#include "player_helpers.h"
#include "recipe.h"
#include "recipe_dictionary.h"
#include "type_id.h"

namespace
{
namespace control = cata::actor_control;

const char task_policy[] =
    R"({"schema_version":1,"applies_to":"bound_companion_only","expression_policy":"natural_with_intent_checks","social_behavior":{"refuse":true,"argue":true,"propose_own_goals":true,"deception":{"enabled":true,"lie_in_dialogue":true,"conceal_information":true,"false_promise":true,"transaction_fraud":false},"betrayal":{"enabled":true,"break_commitment":true,"aid_conflicting_party":true,"disclose_known_information":true,"leave_group":false,"misappropriate_items":false,"sabotage":false,"attack_player":false,"attack_allies":false}}})";

JsonObject task_object( const std::string &text )
{
    JsonObject result = json_loader::from_string( text ).get_object();
    result.allow_omitted_members();
    return result;
}

JsonObject task_child( const JsonObject &object, const std::string &name )
{
    JsonObject result = object.get_object( name );
    result.allow_omitted_members();
    return result;
}

JsonObject task_rpc( const std::string &method, const std::string &params = "{}" )
{
    std::string error;
    const std::string result = control::dispatch( method, params, error );
    INFO( method << ": " << error );
    REQUIRE( error.empty() );
    return task_object( result );
}

std::string task_saved()
{
    std::ostringstream output;
    JsonOut out( output );
    control::serialize( out );
    return output.str();
}

JsonObject task_entry( const std::string &id )
{
    const JsonObject debug = task_child( task_object( control::status( true ) ), "debug" );
    for( JsonObject row : debug.get_array( "tasks" ) ) {
        row.allow_omitted_members();
        if( row.get_string( "id" ) == id ) {
            return row;
        }
    }
    FAIL( "Missing persistent task " << id );
    return task_object( "{}" );
}

std::string task_state( const std::string &id )
{
    return task_entry( id ).get_string( "state" );
}

int task_amount( const Character &actor, const char *name )
{
    const itype_id type( name );
    return item::count_by_charges( type ) ? actor.charges_of( type ) : actor.amount_of( type );
}

int task_ground_amount( const tripoint_bub_ms &position, const char *name )
{
    const itype_id type( name );
    int count = 0;
    for( const item &stock : get_map().i_at( position ) ) {
        if( stock.typeId() == type ) {
            count += stock.count_by_charges() ? stock.charges : 1;
        }
    }
    return count;
}

class task_fixture
{
    public:
        task_fixture() : old_turn( calendar::turn ) {
            const char *runtime = std::getenv( "XDG_RUNTIME_DIR" );
            had_runtime = runtime != nullptr;
            old_runtime = runtime ? runtime : "";
            directory = std::filesystem::temp_directory_path() /
                        ( "cph-actor-tasks-" + control::new_identity() );
            std::filesystem::create_directory( directory );
#ifndef _WIN32
            REQUIRE( chmod( directory.c_str(), 0700 ) == 0 );
            REQUIRE( setenv( "XDG_RUNTIME_DIR", directory.c_str(), 1 ) == 0 );
#endif
            control::enable( false );
            control::reset();
            clear_avatar();
            clear_map_without_vision();
            clear_npcs();
            set_time( calendar::turn_zero + 12_hours );
            get_avatar().setpos( get_map(), tripoint_bub_ms( 59, 60, 0 ) );
            actor = &spawn_npc( { 60, 60 }, "test_talker" );
            clear_character( *actor, true );
            actor->setpos( get_map(), tripoint_bub_ms( 60, 60, 0 ) );
            actor->set_attitude( NPCATT_FOLLOW );
            actor->set_fac( faction_id( "your_followers" ) );
            actor->worn.wear_item( *actor, item( itype_id( "debug_backpack" ) ), false, false );
            actor->set_moves( 1000 );
            actor->recalc_sight_limits();
            clear_items( 0 );
            control::enable( true );
            std::string error;
            REQUIRE( control::bind( *actor, "task-tests", error ) );
            REQUIRE( error.empty() );
            task_rpc( "configure",
                      "{\"profile_id\":\"task-tests\",\"personality\":" + std::string( task_policy ) +
                      R"(,"limits":{"max_steps":5,"cooldown":0},"debug":{"enabled":true}})" );
            sync();
        }

        ~task_fixture() {
            control::enable( false );
            control::reset();
            clear_npcs();
            set_time( old_turn );
#ifndef _WIN32
            if( had_runtime ) {
                setenv( "XDG_RUNTIME_DIR", old_runtime.c_str(), 1 );
            } else {
                unsetenv( "XDG_RUNTIME_DIR" );
            }
#endif
            std::error_code error;
            std::filesystem::remove_all( directory, error );
        }

        void sync() {
            task_rpc( "sync_memory",
                      R"({"version":"task-memory","snapshot":{"revision":"task-memory","records":[]}})" );
        }

        JsonObject request() {
            std::string error;
            REQUIRE( control::chat( "Please consider this task request.", error ) );
            REQUIRE( error.empty() );
            return task_rpc( "take_request" );
        }

        JsonObject offer( const std::string &tasks, const std::string &mode = "append" ) {
            const JsonObject next = request();
            const JsonArray requirements = next.get_array( "requirement_decisions" );
            REQUIRE_FALSE( requirements.empty() );
            std::string requirement;
            std::int64_t latest = -1;
            for( JsonObject incoming : requirements ) {
                incoming.allow_omitted_members();
                const std::int64_t sequence = incoming.get_int64( "source_sequence" );
                if( sequence > latest ) {
                    latest = sequence;
                    requirement = incoming.get_string( "requirement_id" );
                }
            }
            std::string linked = "[";
            for( JsonObject definition : json_loader::from_string( tasks ).get_array() ) {
                definition.allow_omitted_members();
                if( linked.size() > 1 ) {
                    linked += ',';
                }
                linked += '{';
                for( const JsonMember &member : definition ) {
                    linked += control::quote( member.name() ) + ':' + control::stringify( member ) + ',';
                }
                linked += "\"requirement_id\":" + control::quote( requirement ) + '}';
            }
            linked += ']';
            return task_rpc( "offer_tasks", "{\"context\":" + task_child( next, "context" ).str() +
                             ",\"mode\":" + control::quote( mode ) + ",\"tasks\":" + linked + "}" );
        }

        void tick( int count = 1 ) {
            for( int index = 0; index < count; ++index ) {
                actor->set_moves( 1000 );
                control::act( *actor, false );
            }
        }

        void stock( const char *type, int count, const tripoint_bub_ms &position ) {
            for( int index = 0; index < count; ++index ) {
                item added( itype_id( type ), calendar::turn );
                added.set_owner( *actor );
                get_map().add_item_or_charges( position, added );
            }
        }

        std::string position( const tripoint_bub_ms &target ) const {
            const tripoint_abs_ms absolute = get_map().get_abs( target );
            return "{\"x\":" + std::to_string( absolute.x() ) + ",\"y\":" +
                   std::to_string( absolute.y() ) + ",\"z\":" + std::to_string( absolute.z() ) + "}";
        }

        npc *actor = nullptr;
        std::filesystem::path directory;

    private:
        time_point old_turn;
        bool had_runtime = false;
        std::string old_runtime;
};
} // namespace

TEST_CASE( "actor_control_tasks_gather_real_stock_across_sources_without_overcollection",
           "[actor_control][tasks][inventory]" )
{
    task_fixture f;
    f.stock( "rock", 2, tripoint_bub_ms( 60, 61, 0 ) );
    f.stock( "rock", 2, tripoint_bub_ms( 61, 60, 0 ) );
    const int player_moves = get_avatar().get_moves();
    const time_point before = calendar::turn;
    f.offer( R"([{"id":"stones","kind":"gather","args":{"item_type":"rock","count":3},"quantity_mode":"acquired"}])" );
    f.tick( 12 );
    CHECK( task_state( "stones" ) == "completed" );
    CHECK( task_amount( *f.actor, "rock" ) == 3 );
    CHECK( task_entry( "stones" ).get_int( "progress" ) == 3 );
    CHECK( task_ground_amount( tripoint_bub_ms( 60, 61, 0 ), "rock" ) +
           task_ground_amount( tripoint_bub_ms( 61, 60, 0 ), "rock" ) == 1 );
    CHECK( get_avatar().get_moves() == player_moves );
    CHECK( calendar::turn == before );
    f.tick( 5 );
    CHECK( task_amount( *f.actor, "rock" ) == 3 );
}

TEST_CASE( "actor_control_tasks_quantity_modes_preserve_existing_stock_meaning",
           "[actor_control][tasks][inventory]" )
{
    task_fixture f;
    item existing( itype_id( "rock" ), calendar::turn );
    existing.set_owner( *f.actor );
    f.actor->i_add( existing );
    f.stock( "rock", 4, tripoint_bub_ms( 60, 61, 0 ) );
    SECTION( "inventory target includes the existing item" ) {
        f.offer( R"([{"id":"stones","kind":"gather","args":{"item_type":"rock","count":3},"quantity_mode":"inventory"}])" );
        f.tick( 12 );
        CHECK( task_amount( *f.actor, "rock" ) == 3 );
    }
    SECTION( "acquired target counts only this task's collection" ) {
        f.offer( R"([{"id":"stones","kind":"gather","args":{"item_type":"rock","count":3},"quantity_mode":"acquired"}])" );
        f.tick( 12 );
        CHECK( task_amount( *f.actor, "rock" ) == 4 );
    }
    CHECK( task_state( "stones" ) == "completed" );
}

TEST_CASE( "actor_control_tasks_inventory_target_uses_stock_outside_observation_limit",
           "[actor_control][tasks][inventory]" )
{
    task_fixture f;
    std::set<std::string> held_types;
    for( const itype *type : item_controller->all() ) {
        if( type->phase != phase_id::SOLID || type->count_by_charges() ) {
            continue;
        }
        item added( type, calendar::turn, item::solitary_tag {} );
        if( added.is_null() || added.has_flag( flag_PSEUDO ) || added.is_craft() ||
            added.weight() > 1_kilogram || added.volume() > 1_liter ) {
            continue;
        }
        added.set_owner( *f.actor );
        REQUIRE( f.actor->i_add( std::move( added ) ) );
        held_types.insert( type->get_id().str() );
        if( held_types.size() == 130 ) {
            break;
        }
    }
    REQUIRE( held_types.size() == 130 );
    const JsonObject observation = task_object( control::NpcExecutionAdapter::observe( *f.actor ) );
    const JsonArray inventory = task_child( observation, "actor" ).get_array( "inventory" );
    REQUIRE( inventory.size() == 128 );
    for( JsonObject entry : inventory ) {
        entry.allow_omitted_members();
        held_types.erase( entry.get_string( "item_type" ) );
    }
    REQUIRE_FALSE( held_types.empty() );
    const std::string omitted = *held_types.begin();
    CAPTURE( omitted );
    const int initial = task_amount( *f.actor, omitted.c_str() );
    REQUIRE( initial > 0 );
    int target = initial;
    SECTION( "already held stock satisfies the target without another pickup" ) {}
    SECTION( "only the real shortfall is collected" ) {
        target += 2;
    }
    const tripoint_bub_ms source( 60, 61, 0 );
    f.stock( omitted.c_str(), 3, source );
    const int source_before = task_ground_amount( source, omitted.c_str() );
    f.offer( "[{\"id\":\"stock\",\"kind\":\"gather\",\"args\":{\"item_type\":" +
             control::quote( omitted ) + ",\"count\":" + std::to_string( target ) +
             "},\"quantity_mode\":\"inventory\"}]" );
    f.tick( 12 );
    CHECK( task_state( "stock" ) == "completed" );
    CHECK( task_entry( "stock" ).get_int( "progress" ) == target );
    CHECK( task_amount( *f.actor, omitted.c_str() ) == target );
    CHECK( task_ground_amount( source, omitted.c_str() ) == source_before - ( target - initial ) );
}

TEST_CASE( "actor_control_tasks_block_without_stock_and_resume_only_real_available_work",
           "[actor_control][tasks][recovery]" )
{
    task_fixture f;
    f.offer( R"([{"id":"stones","kind":"gather","args":{"item_type":"rock","count":1}}])" );
    const int player_moves = get_avatar().get_moves();
    f.tick( 10 );
    CHECK( task_state( "stones" ) == "blocked" );
    CHECK( task_amount( *f.actor, "rock" ) == 0 );
    const std::string blocked = task_entry( "stones" ).str();
    f.tick( 10 );
    CHECK( task_entry( "stones" ).str() == blocked );
    f.stock( "rock", 1, tripoint_bub_ms( 60, 61, 0 ) );
    f.tick( 12 );
    CHECK( task_state( "stones" ) == "completed" );
    CHECK( task_amount( *f.actor, "rock" ) == 1 );
    CHECK( get_avatar().get_moves() == player_moves );
}

TEST_CASE( "actor_control_tasks_urgent_native_reaction_does_not_spend_or_discard_task",
           "[actor_control][tasks][recovery]" )
{
    task_fixture f;
    f.stock( "rock", 1, tripoint_bub_ms( 60, 61, 0 ) );
    f.offer( R"([{"id":"stones","kind":"gather","args":{"item_type":"rock","count":1}}])" );
    const int moves = f.actor->get_moves();
    CHECK_FALSE( control::act( *f.actor, true ) );
    CHECK( f.actor->get_moves() == moves );
    CHECK( task_amount( *f.actor, "rock" ) == 0 );
    f.tick( 12 );
    CHECK( task_state( "stones" ) == "completed" );
    CHECK( task_amount( *f.actor, "rock" ) == 1 );
}

TEST_CASE( "actor_control_tasks_route_recovery_observes_real_passability_changes",
           "[actor_control][tasks][recovery]" )
{
    task_fixture f;
    const tripoint_bub_ms start = f.actor->pos_bub();
    const tripoint_bub_ms target = start + tripoint_rel_ms( 2, 0, 0 );
    f.offer( "[{\"id\":\"journey\",\"kind\":\"move\",\"args\":" + f.position( target ) + "}]" );
    get_avatar().setpos( get_map(), tripoint_bub_ms( 59, 58, 0 ) );
    for( const tripoint_bub_ms &neighbor : get_map().points_in_radius( start, 1 ) ) {
        if( neighbor != start ) {
            get_map().ter_set( neighbor, ter_str_id( "t_reinforced_glass" ) );
        }
    }
    get_map().invalidate_map_cache( 0 );
    REQUIRE( f.actor->sees( get_map(), target ) );
    f.tick( 10 );
    REQUIRE( task_state( "journey" ) == "blocked" );
    CHECK( f.actor->pos_bub() == start );
    const std::size_t failed_operations = task_object(
            control::status() ).get_array( "receipts" ).size();
    SECTION( "unrelated ground stock does not renew route attempts" ) {
        f.stock( "rock", 1, start );
    }
    SECTION( "unrelated inventory does not renew route attempts" ) {
        REQUIRE( f.actor->i_add( item( itype_id( "rock" ), calendar::turn ) ) );
    }
    f.tick( 10 );
    CHECK( task_state( "journey" ) == "blocked" );
    CHECK( task_object( control::status() ).get_array( "receipts" ).size() == failed_operations );
    CHECK( f.actor->pos_bub() == start );
    get_map().ter_set( start + tripoint_rel_ms::east, ter_str_id( "t_floor" ) );
    get_map().invalidate_map_cache( 0 );
    f.tick( 12 );
    CHECK( task_state( "journey" ) == "completed" );
    CHECK( f.actor->pos_bub() == target );
}

TEST_CASE( "actor_control_tasks_blocked_dependency_keeps_independent_work_available",
           "[actor_control][tasks][dependency]" )
{
    task_fixture f;
    const tripoint_bub_ms target( 62, 60, 0 );
    f.offer( "[{\"id\":\"stock\",\"kind\":\"gather\",\"args\":{\"item_type\":\"rock\",\"count\":1}},"
             "{\"id\":\"dependent\",\"kind\":\"move\",\"args\":" + f.position( target ) +
             ",\"depends_on\":[\"stock\"]},"
             "{\"id\":\"independent\",\"kind\":\"move\",\"args\":" + f.position( f.actor->pos_bub() ) + "}]" );
    f.tick( 12 );
    CHECK( task_state( "stock" ) == "blocked" );
    CHECK( task_state( "dependent" ) != "completed" );
    CHECK( task_state( "independent" ) == "completed" );
    CHECK( f.actor->pos_bub() != target );
    f.stock( "rock", 1, tripoint_bub_ms( 60, 61, 0 ) );
    f.tick( 20 );
    CHECK( task_state( "stock" ) == "completed" );
    CHECK( task_state( "dependent" ) == "completed" );
    CHECK( f.actor->pos_bub() == target );
}

TEST_CASE( "actor_control_tasks_failed_dependency_fails_dependent_without_stalling_independent_work",
           "[actor_control][tasks][dependency]" )
{
    task_fixture f;
    const tripoint_bub_ms target( 62, 60, 0 );
    f.offer( "[{\"id\":\"invalid\",\"kind\":\"craft\",\"args\":{\"recipe\":\"not_a_real_recipe\",\"batch\":1}},"
             "{\"id\":\"dependent\",\"kind\":\"move\",\"args\":" + f.position( target ) +
             ",\"depends_on\":[\"invalid\"]},"
             "{\"id\":\"independent\",\"kind\":\"move\",\"args\":" +
             f.position( f.actor->pos_bub() ) + "}]" );
    f.tick( 12 );
    CHECK( task_state( "invalid" ) == "failed" );
    CHECK( task_entry( "invalid" ).get_string( "reason" ) == "invalid_recipe" );
    CHECK( task_state( "dependent" ) == "failed" );
    CHECK( task_entry( "dependent" ).get_string( "reason" ) == "task_dependency_failed" );
    CHECK( task_state( "independent" ) == "completed" );
    CHECK( f.actor->pos_bub() != target );
    CHECK_FALSE( f.actor->activity );
}

TEST_CASE( "actor_control_tasks_craft_tracks_native_activity_and_never_duplicates_output",
           "[actor_control][tasks][crafting][save]" )
{
    task_fixture f;
    const recipe_id recipe( "bandages_makeshift" );
    REQUIRE( recipe.is_valid() );
    f.actor->learn_recipe( &recipe.obj() );
    item sheet( itype_id( "sheet_cotton" ), calendar::turn );
    sheet.set_owner( *f.actor );
    f.actor->i_add( sheet );
    f.offer( R"([{"id":"bandages","kind":"craft","args":{"recipe":"bandages_makeshift","batch":1}}])" );
    f.tick();
    REQUIRE( f.actor->activity );
    const activity_id activity = f.actor->activity.id();
    f.actor->set_moves( 100 );
    CHECK_FALSE( control::act( *f.actor, true ) );
    CHECK( f.actor->activity.id() == activity );
    CHECK( task_amount( *f.actor, "bandages_makeshift" ) == 0 );
    process_activity( *f.actor );
    REQUIRE_FALSE( f.actor->activity );
    f.tick( 3 );
    CHECK( task_state( "bandages" ) == "completed" );
    CHECK( task_amount( *f.actor, "sheet_cotton" ) == 0 );
    REQUIRE( task_amount( *f.actor, "bandages_makeshift" ) == 2 );
    const std::string completed = task_saved();
    control::deserialize( task_object( completed ) );
    f.sync();
    f.tick( 10 );
    CHECK( task_state( "bandages" ) == "completed" );
    CHECK( task_amount( *f.actor, "bandages_makeshift" ) == 2 );
}

TEST_CASE( "actor_control_tasks_restore_partial_collection_without_replaying_progress",
           "[actor_control][tasks][inventory][save]" )
{
    task_fixture f;
    f.stock( "rock", 1, tripoint_bub_ms( 60, 61, 0 ) );
    f.offer( R"([{"id":"stones","kind":"gather","args":{"item_type":"rock","count":2},"quantity_mode":"acquired"}])" );
    f.tick( 8 );
    REQUIRE( task_amount( *f.actor, "rock" ) == 1 );
    REQUIRE( task_entry( "stones" ).get_int( "progress" ) == 1 );
    const std::string partial = task_saved();
    control::deserialize( task_object( partial ) );
    f.sync();
    f.stock( "rock", 3, tripoint_bub_ms( 60, 61, 0 ) );
    f.tick( 16 );
    CHECK( task_state( "stones" ) == "completed" );
    CHECK( task_entry( "stones" ).get_int( "progress" ) == 2 );
    CHECK( task_amount( *f.actor, "rock" ) == 2 );
    CHECK( task_ground_amount( tripoint_bub_ms( 60, 61, 0 ), "rock" ) == 2 );
}

TEST_CASE( "actor_control_tasks_prioritized_craft_reconciles_old_native_effects_first",
           "[actor_control][tasks][crafting][lifecycle]" )
{
    task_fixture f;
    const recipe_id recipe( "bandages_makeshift" );
    f.actor->learn_recipe( &recipe.obj() );
    for( int index = 0; index < 3; ++index ) {
        item sheet( itype_id( "sheet_cotton" ), calendar::turn );
        sheet.set_owner( *f.actor );
        f.actor->i_add( sheet );
    }
    f.offer( R"([{"id":"original","kind":"craft","args":{"recipe":"bandages_makeshift","batch":1}}])" );
    f.tick();
    REQUIRE( f.actor->activity );
    bool original_completed = false;
    SECTION( "finished native output is acknowledged before the new craft starts" ) {
        process_activity( *f.actor );
        original_completed = true;
        REQUIRE( task_amount( *f.actor, "bandages_makeshift" ) == 2 );
    }
    SECTION( "interrupted native craft is preserved rather than started again" ) {
        f.actor->cancel_activity();
        REQUIRE( task_amount( *f.actor, "bandages_makeshift" ) == 0 );
    }
    REQUIRE_FALSE( f.actor->activity );
    f.offer( R"([{"id":"priority","kind":"craft","args":{"recipe":"bandages_makeshift","batch":1}}])",
             "prioritize" );
    for( int retry = 0; retry < 4 && !f.actor->activity; ++retry ) {
        f.tick();
    }
    REQUIRE( f.actor->activity );
    process_activity( *f.actor );
    f.tick( 8 );
    CHECK( task_state( "priority" ) == "completed" );
    CHECK( ( task_state( "original" ) == "completed" ) == original_completed );
    CHECK( task_amount( *f.actor, "bandages_makeshift" ) == ( original_completed ? 4 : 2 ) );
    CHECK( task_amount( *f.actor, "sheet_cotton" ) == 1 );
    CHECK_FALSE( f.actor->activity );
}

TEST_CASE( "actor_control_tasks_unknown_saved_schema_preserves_payload_without_takeover",
           "[actor_control][tasks][save]" )
{
    task_fixture f;
    f.offer( R"([{"id":"guard","kind":"guard","args":{}}])" );
    f.tick();
    const JsonObject current = task_object( task_saved() );
    std::string unsupported;
    SECTION( "future extension schema" ) {
        unsupported = R"({"schema_version":999,"unrecognized":"preserve-me"})";
    }
    SECTION( "extension with an unexpected JSON type" ) {
        unsupported = R"(["preserve-me"])";
    }
    std::string future = "{";
    for( const JsonMember &member : current ) {
        if( future.size() > 1 ) {
            future += ',';
        }
        future += control::quote( member.name() ) + ':';
        if( member.name() == "persistent_tasks" ) {
            future += unsupported;
        } else {
            future += control::stringify( member );
        }
    }
    future += '}';
    control::deserialize( task_object( future ) );
    CHECK( task_object( control::status() ).get_string( "state" ) == "unsupported_schema" );
    CHECK_FALSE( control::has_binding() );
    CHECK( control::stringify( task_object( task_saved() ).get_member( "persistent_tasks" ) ) ==
           control::stringify( json_loader::from_string( unsupported ) ) );
}

TEST_CASE( "actor_control_tasks_invalid_dependency_graph_is_rejected_without_replacing_work",
           "[actor_control][tasks][dependency]" )
{
    task_fixture f;
    f.offer( R"([{"id":"standing","kind":"guard","args":{}}])" );
    f.tick();
    REQUIRE( task_state( "standing" ) == "running" );
    const auto original_post = f.actor->guard_pos;
    const JsonObject request = f.request();
    std::string definitions;
    SECTION( "dependency references an unknown task" ) {
        definitions = R"([{"id":"new","kind":"guard","args":{},"depends_on":["missing"]}])";
    }
    SECTION( "two new tasks form a cycle" ) {
        definitions =
            R"([{"id":"one","kind":"guard","args":{},"depends_on":["two"]},{"id":"two","kind":"guard","args":{},"depends_on":["one"]}])";
    }
    std::string error;
    control::dispatch( "offer_tasks", "{\"context\":" + task_child( request, "context" ).str() +
                       ",\"mode\":\"prioritize\",\"tasks\":" + definitions + "}", error );
    CHECK( error == "invalid_task_dependency" );
    f.tick( 3 );
    CHECK( task_state( "standing" ) == "running" );
    CHECK( f.actor->guard_pos == original_post );
    const JsonObject debug = task_child( task_object( control::status( true ) ), "debug" );
    CHECK( debug.get_array( "tasks" ).size() == 1 );
    CHECK( debug.get_member( "task_candidate" ).test_null() );
}

TEST_CASE( "actor_control_tasks_append_and_prioritize_preserve_accepted_work",
           "[actor_control][tasks][lifecycle]" )
{
    task_fixture f;
    const tripoint_bub_ms target( 69, 60, 0 );
    f.offer( "[{\"id\":\"journey\",\"kind\":\"move\",\"args\":" + f.position( target ) + "}]" );
    f.tick();
    REQUIRE( f.actor->pos_bub() != target );
    const tripoint_bub_ms current = f.actor->pos_bub();
    const tripoint_bub_ms stock = current + tripoint_rel_ms::south;
    f.stock( "rock", 1, stock );
    SECTION( "newly accepted work appends without replacing the journey" ) {
        f.offer( R"([{"id":"stones","kind":"gather","args":{"item_type":"rock","count":1}}])" );
        f.tick();
        CHECK( task_amount( *f.actor, "rock" ) == 0 );
        CHECK( task_state( "journey" ) != "cancelled" );
        f.tick( 40 );
    }
    SECTION( "explicitly prioritized work pauses then resumes the journey" ) {
        f.offer( R"([{"id":"stones","kind":"gather","args":{"item_type":"rock","count":1}}])",
                 "prioritize" );
        f.tick();
        CHECK( f.actor->pos_bub() == current );
        CHECK( task_amount( *f.actor, "rock" ) == 1 );
        CHECK( task_state( "journey" ) != "cancelled" );
        f.tick( 40 );
    }
    CHECK( task_state( "journey" ) == "completed" );
    CHECK( task_state( "stones" ) == "completed" );
    CHECK( task_amount( *f.actor, "rock" ) == 1 );
}

TEST_CASE( "actor_control_tasks_referenced_receipts_survive_recent_history_limit",
           "[actor_control][tasks][inventory][save]" )
{
    task_fixture f;
    // Consume each collected unit between operations. The task must retain
    // actual acquired progress and receipts even after its stock was used.
    f.offer( R"([{"id":"stones","kind":"gather","args":{"item_type":"rock","count":521}}])" );
    const tripoint_bub_ms source( 60, 61, 0 );
    std::string first_operation;
    for( int index = 0; index < 520; ++index ) {
        CAPTURE( index );
        f.stock( "rock", 1, source );
        for( int retry = 0; retry < 4 && task_amount( *f.actor, "rock" ) == 0; ++retry ) {
            f.tick();
        }
        REQUIRE( task_amount( *f.actor, "rock" ) == 1 );
        REQUIRE( task_entry( "stones" ).get_int( "progress" ) == index + 1 );
        if( index == 0 ) {
            const JsonArray receipts = task_object( control::status() ).get_array( "receipts" );
            REQUIRE_FALSE( receipts.empty() );
            JsonObject first = receipts.get_object( 0 );
            first.allow_omitted_members();
            first_operation = first.get_string( "operation_id" );
        }
        for( const item_location &location : f.actor->all_items_loc() ) {
            if( location->typeId() == itype_id( "rock" ) ) {
                f.actor->i_rem( location.get_item() );
                break;
            }
        }
        REQUIRE( task_amount( *f.actor, "rock" ) == 0 );
    }
    REQUIRE_FALSE( first_operation.empty() );
    const JsonArray retained = task_object( control::status( false, first_operation ) ).get_array(
                                   "receipts" );
    REQUIRE( retained.size() == 1 );
    JsonObject receipt = retained.get_object( 0 );
    receipt.allow_omitted_members();
    CHECK( receipt.get_string( "state" ) == "succeeded" );
    control::deserialize( task_object( task_saved() ) );
    f.sync();
    f.stock( "rock", 2, source );
    f.tick( 16 );
    CHECK( task_state( "stones" ) == "completed" );
    CHECK( task_entry( "stones" ).get_int( "progress" ) == 521 );
    CHECK( task_amount( *f.actor, "rock" ) == 1 );
    CHECK( task_ground_amount( source, "rock" ) == 1 );
}

TEST_CASE( "actor_control_tasks_late_candidate_cannot_reanimate_cancelled_intent",
           "[actor_control][tasks][lifecycle]" )
{
    task_fixture f;
    f.stock( "rock", 1, tripoint_bub_ms( 60, 61, 0 ) );
    const JsonObject request = f.request();
    JsonObject incoming = request.get_array( "requirement_decisions" ).get_object( 0 );
    incoming.allow_omitted_members();
    const std::string candidate = "{\"context\":" + task_child( request, "context" ).str() +
                                  ",\"mode\":\"append\",\"tasks\":[{\"id\":\"stones\",\"kind\":\"gather\","
                                  "\"requirement_id\":" + control::quote( incoming.get_string( "requirement_id" ) ) +
                                  R"(,"args":{"item_type":"rock","count":1}}]})";
    task_rpc( "offer_tasks", candidate );
    control::cancel();
    f.tick( 8 );
    CHECK( task_amount( *f.actor, "rock" ) == 0 );
    std::string error;
    control::dispatch( "offer_tasks", candidate, error );
    CHECK_FALSE( error.empty() );
    f.tick( 8 );
    CHECK( task_amount( *f.actor, "rock" ) == 0 );
}

TEST_CASE( "actor_control_tasks_native_duties_preserve_identity_and_restore_on_stop",
           "[actor_control][tasks][npc]" )
{
    task_fixture f;
    const character_id identity = f.actor->getID();
    const npc_attitude attitude = f.actor->get_attitude();
    const npc_mission mission = f.actor->mission;
    const auto guard_position = f.actor->guard_pos;
    const int player_moves = get_avatar().get_moves();
    const time_point before = calendar::turn;
    SECTION( "following delegates to native follower logic" ) {
        f.offer( R"([{"id":"duty","kind":"follow","args":{}}])" );
        f.tick( 6 );
        CHECK( f.actor->get_attitude() == NPCATT_FOLLOW );
    }
    SECTION( "guarding delegates to native guard logic" ) {
        f.offer( R"([{"id":"duty","kind":"guard","args":{}}])" );
        f.tick( 6 );
        CHECK( f.actor->guard_pos.has_value() );
    }
    CHECK( task_state( "duty" ) == "running" );
    CHECK( f.actor->getID() == identity );
    CHECK( f.actor->is_player_ally() );
    CHECK( get_avatar().get_moves() == player_moves );
    CHECK( calendar::turn == before );
    control::stop();
    CHECK( f.actor->get_attitude() == attitude );
    CHECK( f.actor->mission == mission );
    CHECK( f.actor->guard_pos == guard_position );
}

TEST_CASE( "actor_control_tasks_cannot_revive_an_explicitly_refused_requirement",
           "[actor_control][tasks][social]" )
{
    task_fixture f;
    const JsonObject request = f.request();
    JsonObject incoming = request.get_array( "requirement_decisions" ).get_object( 0 );
    incoming.allow_omitted_members();
    const std::string requirement = incoming.get_string( "requirement_id" );
    task_rpc( "offer_plan", "{\"context\":" + task_child( request, "context" ).str() +
              ",\"steps\":[{\"id\":\"refuse\",\"action\":\"refuse\",\"requirement_id\":" +
              control::quote( requirement ) + R"(,"args":{"text":"I refuse that request."}}]})" );
    f.tick();
    const JsonObject next = f.request();
    std::string error;
    control::dispatch( "offer_tasks", "{\"context\":" + task_child( next, "context" ).str() +
                       ",\"mode\":\"append\",\"tasks\":[{\"id\":\"forbidden\",\"kind\":\"gather\","
                       "\"requirement_id\":" + control::quote( requirement ) +
                       R"(,"args":{"item_type":"rock","count":1}}]})", error );
    // Admission may reject immediately or at the safe adoption boundary.
    f.stock( "rock", 1, tripoint_bub_ms( 60, 61, 0 ) );
    f.tick( 8 );
    CHECK( task_amount( *f.actor, "rock" ) == 0 );
    const JsonObject debug = task_child( task_object( control::status( true ) ), "debug" );
    CHECK( debug.get_array( "tasks" ).empty() );
}

TEST_CASE( "actor_control_tasks_standing_duty_yields_to_finite_accepted_work_then_resumes",
           "[actor_control][tasks][npc]" )
{
    task_fixture f;
    const tripoint_bub_ms destination( 62, 60, 0 );
    f.offer( R"([{"id":"standing","kind":"guard","args":{}}])" );
    f.tick();
    REQUIRE( task_state( "standing" ) == "running" );
    const auto original_post = f.actor->guard_pos;
    f.offer( "[{\"id\":\"journey\",\"kind\":\"move\",\"args\":" +
             f.position( destination ) + "}]" );
    f.tick( 20 );
    CHECK( task_state( "journey" ) == "completed" );
    CHECK( task_state( "standing" ) == "running" );
    CHECK( f.actor->pos_bub() == destination );
    CHECK( f.actor->guard_pos == original_post );
}

TEST_CASE( "actor_control_tasks_cannot_adopt_candidate_on_multiplayer_proxy",
           "[actor_control][tasks][multiplayer]" )
{
    task_fixture f;
    f.stock( "rock", 1, tripoint_bub_ms( 60, 61, 0 ) );
    f.offer( R"([{"id":"stones","kind":"gather","args":{"item_type":"rock","count":1}}])" );
    f.actor->set_value( "mp_proxy", "1" );
    const int moves = f.actor->get_moves();
    CHECK_FALSE( control::act( *f.actor, false ) );
    CHECK( f.actor->get_moves() == moves );
    CHECK( task_amount( *f.actor, "rock" ) == 0 );
    CHECK( f.actor->get_value( "mp_proxy" ) == "1" );
}

TEST_CASE( "actor_control_tasks_terminal_retirement_keeps_new_work_available",
           "[actor_control][tasks][lifecycle]" )
{
    task_fixture f;
    for( int index = 0; index < 129; ++index ) {
        CAPTURE( index );
        const std::string id = "journey-" + std::to_string( index );
        f.offer( "[{\"id\":" + control::quote( id ) + ",\"kind\":\"move\",\"args\":" +
                 f.position( f.actor->pos_bub() ) + "}]" );
        f.tick();
        REQUIRE( task_state( id ) == "completed" );
    }
    const JsonObject debug = task_child( task_object( control::status( true ) ), "debug" );
    CHECK( debug.get_array( "tasks" ).size() <= 128 );
    CHECK( task_state( "journey-128" ) == "completed" );
}

TEST_CASE( "actor_control_tasks_ordinary_clock_position_and_needs_do_not_request_model_work",
           "[actor_control][tasks][runtime]" )
{
    task_fixture f;
    f.offer( R"([{"id":"standing","kind":"follow","args":{}}])" );
    f.tick();
    REQUIRE( task_state( "standing" ) == "running" );
    f.actor->setpos( get_map(), f.actor->pos_bub() + tripoint_rel_ms::east );
    f.actor->set_moves( 23 );
    f.actor->mod_hunger( 1 );
    f.actor->mod_thirst( 1 );
    calendar::turn += 1_hours;
    std::string error;
    CHECK( control::dispatch( "take_request", "{}", error ) == "null" );
    CHECK( error.empty() );
    CHECK( task_state( "standing" ) == "running" );
}

TEST_CASE( "actor_control_tasks_delayed_candidate_keeps_its_original_request_area",
           "[actor_control][tasks][lifecycle]" )
{
    task_fixture f;
    const tripoint_bub_ms stock( 62, 60, 0 );
    f.stock( "rock", 1, stock );
    f.offer( R"([{"id":"stones","kind":"gather","args":{"item_type":"rock","count":1},"constraints":{"max_distance":1}}])" );
    // Moving one tile while the reply waits must not move its authorized
    // collection area and make the previously out-of-area stock available.
    f.actor->setpos( get_map(), tripoint_bub_ms( 61, 60, 0 ) );
    f.tick( 8 );
    CHECK( task_state( "stones" ) == "blocked" );
    CHECK( task_amount( *f.actor, "rock" ) == 0 );
    CHECK( task_ground_amount( stock, "rock" ) == 1 );
}

TEST_CASE( "actor_control_tasks_blind_adjacent_player_cannot_observe_private_progress",
           "[actor_control][tasks][observation]" )
{
    task_fixture f;
    f.stock( "rock", 1, tripoint_bub_ms( 60, 61, 0 ) );
    f.offer( R"([{"id":"stones","kind":"gather","args":{"item_type":"rock","count":1}}])" );
    get_avatar().add_effect( efftype_id( "blind" ), 1_hours );
    get_avatar().recalc_sight_limits();
    REQUIRE( get_avatar().is_blind() );
    REQUIRE( rl_dist( get_avatar().pos_bub(), f.actor->pos_bub() ) == 1 );
    f.tick( 12 );
    CHECK( task_state( "stones" ) == "completed" );
    CHECK( task_amount( *f.actor, "rock" ) == 1 );
    CHECK( task_object( control::status() ).get_array( "player_progress" ).empty() );
}

TEST_CASE( "actor_control_tasks_completed_history_does_not_suppress_new_duty_discovery",
           "[actor_control][tasks][runtime]" )
{
    task_fixture f;
    task_rpc( "configure", "{\"profile_id\":\"task-tests\",\"personality\":" +
              std::string( task_policy ) +
              R"(,"limits":{"max_steps":5,"cooldown":0},"debug":{"enabled":true},"duties":{"allowed_tasks":["gather"],"item_types":["rock"],"max_distance":12}})" );
    f.sync();
    const tripoint_bub_ms source( 60, 61, 0 );
    f.stock( "rock", 1, source );
    f.offer( R"([{"id":"first","kind":"gather","args":{"item_type":"rock","count":1}}])" );
    f.tick( 3 );
    REQUIRE( task_state( "first" ) == "completed" );
    const JsonObject decision = task_rpc( "take_request" );
    task_rpc( "offer_tasks", "{\"context\":" + task_child( decision, "context" ).str() +
              R"(,"mode":"append","tasks":[]})" );
    f.tick();
    std::string error;
    CHECK( control::dispatch( "take_request", "{}", error ) == "null" );
    REQUIRE( error.empty() );
    f.stock( "rock", 1, source );
    const std::string discovered = control::dispatch( "take_request", "{}", error );
    REQUIRE( error.empty() );
    REQUIRE( discovered != "null" );
    CHECK( task_object( discovered ).get_string( "decision_reason" ) == "world_change" );
    CHECK( task_amount( *f.actor, "rock" ) == 1 );
    CHECK( task_ground_amount( source, "rock" ) == 1 );
}

TEST_CASE( "actor_control_tasks_prioritized_guard_keeps_old_finite_work_paused",
           "[actor_control][tasks][lifecycle]" )
{
    task_fixture f;
    std::string previous;
    SECTION( "running_native_move" ) {
        previous = "journey";
        f.offer( "[{\"id\":\"journey\",\"kind\":\"move\",\"args\":" +
                 f.position( tripoint_bub_ms( 69, 60, 0 ) ) + "}]" );
        f.tick();
        REQUIRE( task_state( previous ) == "running" );
    }
    SECTION( "queued_between_two_real_gather_steps" ) {
        previous = "stones";
        f.stock( "rock", 1, tripoint_bub_ms( 60, 61, 0 ) );
        f.stock( "rock", 1, tripoint_bub_ms( 61, 60, 0 ) );
        f.offer( R"([{"id":"stones","kind":"gather","args":{"item_type":"rock","count":2}}])" );
        f.tick();
        REQUIRE( task_entry( previous ).get_int( "progress" ) == 1 );
        REQUIRE( task_state( previous ) == "queued" );
    }
    const tripoint_bub_ms stopped_at = f.actor->pos_bub();
    const int stock = task_amount( *f.actor, "rock" );
    f.offer( R"([{"id":"standing","kind":"guard","args":{}}])", "prioritize" );
    f.tick( 12 );
    CHECK( task_state( previous ) == "paused" );
    CHECK( task_state( "standing" ) == "running" );
    CHECK( f.actor->pos_bub() == stopped_at );
    CHECK( task_amount( *f.actor, "rock" ) == stock );
}

TEST_CASE( "actor_control_tasks_prefetch_has_fresh_episode_identity_and_survives_restore",
           "[actor_control][tasks][runtime][save]" )
{
    task_fixture f;
    task_rpc( "configure", "{\"profile_id\":\"task-tests\",\"personality\":" +
              std::string( task_policy ) +
              R"(,"limits":{"max_steps":5,"cooldown":0},"debug":{"enabled":true},"duties":{"allowed_tasks":["gather"],"item_types":["rock"],"max_distance":12}})" );
    f.sync();
    const JsonObject initial = f.request();
    std::string requirement;
    for( JsonObject incoming : initial.get_array( "requirement_decisions" ) ) {
        incoming.allow_omitted_members();
        requirement = incoming.get_string( "requirement_id" );
    }
    REQUIRE_FALSE( requirement.empty() );
    const tripoint_bub_ms first( 60, 61, 0 );
    const tripoint_bub_ms second( 61, 60, 0 );
    f.stock( "rock", 1, first );
    task_rpc( "offer_tasks", "{\"context\":" + task_child( initial, "context" ).str() +
              R"(,"mode":"append","tasks":[{"id":"stones","kind":"gather","args":{"item_type":"rock","count":5},"requirement_id":)"
              +
              control::quote( requirement ) + "}]}" );
    f.tick();
    REQUIRE( task_entry( "stones" ).get_int( "progress" ) == 1 );
    f.stock( "rock", 1, second );
    f.tick();
    REQUIRE( task_entry( "stones" ).get_int( "progress" ) == 2 );
    const JsonObject prefetch = task_rpc( "take_request" );
    CHECK( prefetch.get_string( "decision_reason" ) == "task_boundary" );
    CHECK( prefetch.get_string( "decision_id" ) != initial.get_string( "decision_id" ) );
    task_rpc( "offer_tasks", "{\"context\":" + task_child( prefetch, "context" ).str() +
              R"(,"mode":"append","tasks":[]})" );
    f.stock( "rock", 1, first );
    f.tick();
    REQUIRE( task_entry( "stones" ).get_int( "progress" ) == 3 );
    std::string error;
    CHECK( control::dispatch( "take_request", "{}", error ) == "null" );
    REQUIRE( error.empty() );
    const std::string saved = task_saved();
    control::deserialize( task_object( saved ) );
    f.sync();
    f.stock( "rock", 1, second );
    f.tick();
    REQUIRE( task_entry( "stones" ).get_int( "progress" ) == 4 );
    CHECK( control::dispatch( "take_request", "{}", error ) == "null" );
    CHECK( error.empty() );
    CHECK( task_state( "stones" ) != "completed" );
}

TEST_CASE( "actor_control_game_profile_revokes_offline_autonomy_without_revoking_player_work",
           "[actor_control][tasks][runtime][configuration]" )
{
    task_fixture f;
    const std::string old_user = PATH_INFO::user_dir();
    const on_out_of_scope restore_user( [&]() {
        PATH_INFO::init_user_dir( old_user );
    } );
    PATH_INFO::init_user_dir( f.directory.u8string() );
    task_rpc( "configure", "{\"profile_id\":\"task-tests\",\"personality\":" +
              std::string( task_policy ) +
              R"(,"limits":{"max_steps":5,"cooldown":0},"debug":{"enabled":true},"duties":{"allowed_tasks":["gather"],"item_types":["rock"],"max_distance":12}})" );
    f.sync();
    const JsonObject decision = task_rpc( "take_request" );
    task_rpc( "offer_tasks", "{\"context\":" + task_child( decision, "context" ).str() +
              R"(,"tasks":[{"id":"own-stones","kind":"gather","args":{"item_type":"rock","count":3}},{"id":"queued-stones","kind":"gather","args":{"item_type":"rock","count":1}}]})" );
    f.stock( "rock", 4, tripoint_bub_ms( 65, 60, 0 ) );
    f.tick();
    REQUIRE( task_state( "own-stones" ) == "running" );
    f.offer( R"([{"id":"player-stones","kind":"gather","args":{"item_type":"rock","count":1}}])" );
    f.tick();
    REQUIRE( task_state( "player-stones" ) == "queued" );
    const JsonObject before = task_object( control::status() );
    const std::string old_policy = task_child( before, "context" ).get_string( "policy_version" );
    control::runtime_preferences preferences;
    preferences.profile_id = "task-tests";
    preferences.actor_id = f.actor->getID().get_value();
    preferences.configuration = R"({"llm":{},"paths":{"background":"background.md"}})";
    preferences.background = "Synthetic character";
    std::string error;
    REQUIRE_FALSE( control::managed_runtime_running() );
    REQUIRE( control::save_runtime_preferences( preferences, error ) );
    CHECK( task_child( task_object( control::status() ), "context" ).get_string(
               "policy_version" ) != old_policy );
    f.tick( 12 );
    CHECK( task_state( "own-stones" ) == "cancelled" );
    CHECK( task_state( "queued-stones" ) == "cancelled" );
    CHECK( task_state( "player-stones" ) == "completed" );
    CHECK( task_amount( *f.actor, "rock" ) == 1 );
    CHECK( task_ground_amount( tripoint_bub_ms( 65, 60, 0 ), "rock" ) == 3 );
    const std::string persisted = task_saved();
    control::deserialize( task_object( persisted ) );
    f.sync();
    f.tick( 8 );
    CHECK( task_state( "own-stones" ) == "cancelled" );
    CHECK( task_amount( *f.actor, "rock" ) == 1 );
}

TEST_CASE( "actor_control_game_profile_rejects_another_binding_before_writing",
           "[actor_control][tasks][runtime][configuration]" )
{
    task_fixture f;
    const std::string old_user = PATH_INFO::user_dir();
    const on_out_of_scope restore_user( [&]() {
        PATH_INFO::init_user_dir( old_user );
    } );
    PATH_INFO::init_user_dir( f.directory.u8string() );
    control::runtime_preferences preferences;
    preferences.profile_id = "task-tests";
    preferences.actor_id = f.actor->getID().get_value();
    preferences.configuration = R"({"llm":{},"paths":{"background":"background.md"}})";
    SECTION( "another_profile" ) {
        preferences.profile_id = "other-profile";
    }
    SECTION( "another_actor" ) {
        ++preferences.actor_id;
    }
    const std::string before = task_saved();
    std::string error;
    CHECK_FALSE( control::save_runtime_preferences( preferences, error ) );
    CHECK( error == "fixed_binding_conflict" );
    CHECK( task_saved() == before );
    CHECK_FALSE( std::filesystem::exists( control::runtime_profile_directory(
            preferences.profile_id ) / "config.json" ) );
}

TEST_CASE( "actor_control_player_withdrawal_is_scoped_and_survives_restore",
           "[actor_control][tasks][configuration][save]" )
{
    task_fixture f;
    const JsonObject initial = task_rpc( "take_request" );
    task_rpc( "offer_tasks", "{\"context\":" + task_child( initial, "context" ).str() +
              R"(,"tasks":[{"id":"private-guard","kind":"guard","args":{}}]})" );
    f.tick();
    f.stock( "rock", 1, tripoint_bub_ms( 65, 60, 0 ) );
    f.offer( R"([{"id":"other-request","kind":"gather","args":{"item_type":"rock","count":1}}])" );
    f.tick();
    std::string definitions = "[{\"id\":\"withdraw-me\",\"kind\":\"move\",\"args\":" +
                              f.position( tripoint_bub_ms( 68, 60, 0 ) ) + "}]";
    std::string expected;
    SECTION( "candidate_not_adopted" ) {
        expected = "candidate";
    }
    SECTION( "queued" ) {
        definitions = "[{\"id\":\"front\",\"kind\":\"move\",\"args\":" +
                      f.position( tripoint_bub_ms( 68, 60, 0 ) ) +
                      R"(},{"id":"withdraw-me","kind":"gather","args":{"item_type":"rock","count":1}}])";
        expected = "queued";
    }
    SECTION( "running" ) {
        expected = "running";
    }
    SECTION( "paused" ) {
        expected = "paused";
    }
    f.offer( definitions, "prioritize" );
    const std::string withdrawn = control::player_requirements().back().id;
    if( expected != "candidate" ) {
        f.tick();
        if( expected == "paused" ) {
            f.offer( R"([{"id":"priority-guard","kind":"guard","args":{}}])", "prioritize" );
            f.tick();
        }
        REQUIRE( task_state( "withdraw-me" ) == expected );
    }
    std::string error;
    REQUIRE( control::withdraw_requirement( withdrawn, error ) );
    REQUIRE( error.empty() );
    CHECK( task_state( "other-request" ) != "cancelled" );
    CHECK( task_state( "private-guard" ) != "cancelled" );
    if( expected != "candidate" ) {
        CHECK( task_state( "withdraw-me" ) == "cancelled" );
    }
    const std::string saved = task_saved();
    control::deserialize( task_object( saved ) );
    f.sync();
    f.tick( 20 );
    bool listed = false;
    for( const control::player_requirement &known : control::player_requirements() ) {
        if( known.id == withdrawn ) {
            CHECK( known.withdrawn );
            CHECK_FALSE( known.text.empty() );
            listed = true;
        }
    }
    CHECK( listed );
    CHECK( task_state( "other-request" ) != "cancelled" );
    CHECK( task_state( "private-guard" ) != "cancelled" );
    if( expected != "candidate" ) {
        CHECK( task_state( "withdraw-me" ) == "cancelled" );
    } else {
        for( JsonObject task : task_object( control::status() ).get_array( "task_summary" ) ) {
            task.allow_omitted_members();
            CHECK( task.get_string( "id" ) != "withdraw-me" );
        }
    }
    const JsonObject next = f.request();
    control::dispatch( "offer_tasks", "{\"context\":" + task_child( next, "context" ).str() +
                       R"(,"tasks":[{"id":"revived","kind":"follow","args":{},"requirement_id":)" +
                       control::quote( withdrawn ) + "}]}", error );
    CHECK( error == "requirement_withdrawn" );
    CHECK( control::withdraw_requirement( withdrawn, error ) );
}

TEST_CASE( "actor_control_player_withdrawal_blocks_only_its_dependency_branch",
           "[actor_control][tasks][dependency]" )
{
    task_fixture f;
    f.offer( R"([{"id":"missing","kind":"gather","args":{"item_type":"rock","count":1}}])" );
    const std::string withdrawn = control::player_requirements().back().id;
    f.tick();
    REQUIRE( task_state( "missing" ) == "blocked" );
    f.stock( "splinter", 1, tripoint_bub_ms( 65, 60, 0 ) );
    f.offer( R"([{"id":"dependent","kind":"follow","args":{},"depends_on":["missing"]},{"id":"independent","kind":"gather","args":{"item_type":"splinter","count":1}}])" );
    f.tick(); // Adopt the independent request before invalidating old candidates.
    REQUIRE( task_state( "dependent" ) == "blocked" );
    REQUIRE( task_state( "independent" ) == "running" );
    std::string error;
    REQUIRE( control::withdraw_requirement( withdrawn, error ) );
    f.tick( 8 );
    CHECK( task_state( "missing" ) == "cancelled" );
    CHECK( task_state( "dependent" ) == "failed" );
    CHECK( task_entry( "dependent" ).get_string( "reason" ) == "task_dependency_failed" );
    CHECK( task_state( "independent" ) == "completed" );
    CHECK( task_amount( *f.actor, "splinter" ) == 1 );
    CHECK( task_amount( *f.actor, "rock" ) == 0 );
}

TEST_CASE( "actor_control_player_withdrawal_stops_linked_legacy_steps_only",
           "[actor_control][tasks][legacy]" )
{
    task_fixture f;
    f.request();
    const std::string withdrawn = control::player_requirements().back().id;
    const JsonObject request = f.request();
    const std::string other = control::player_requirements().back().id;
    const std::string request_id = task_child( request, "context" ).get_string( "request_id" );
    const tripoint_bub_ms stock( 60, 61, 0 );
    f.stock( "rock", 1, stock );
    task_rpc( "offer_plan", "{\"context\":" + task_child( request, "context" ).str() +
              ",\"steps\":[{\"id\":\"moving\",\"action\":\"move\",\"args\":" +
              f.position( tripoint_bub_ms( 68, 60, 0 ) ) + ",\"requirement_id\":" +
              control::quote( withdrawn ) +
              "},{\"id\":\"waiting\",\"action\":\"wait\",\"args\":{},\"requirement_id\":" +
              control::quote( other ) +
              "},{\"id\":\"gathering\",\"action\":\"gather\",\"args\":" +
              f.position( stock ).substr( 0, f.position( stock ).size() - 1 ) +
              R"(,"item_type":"rock","count":1},"requirement_id":)" +
              control::quote( withdrawn ) + "}]}" );
    f.tick();
    std::string error;
    REQUIRE( control::withdraw_requirement( withdrawn, error ) );
    CHECK( task_object( control::status() ).get_int( "queue_length" ) == 1 );
    f.tick();
    calendar::turn += 1_turns;
    f.tick();
    CHECK( task_object( control::status() ).get_int( "queue_length" ) == 0 );
    CHECK( task_ground_amount( stock, "rock" ) == 1 );
    const JsonArray receipts = task_rpc( "status", "{\"operation_id\":" +
                                         control::quote( request_id + ".waiting" ) + "}" ).get_array( "receipts" );
    REQUIRE( receipts.size() == 1 );
    const JsonObject receipt = receipts.get_object( 0 );
    receipt.allow_omitted_members();
    CHECK( receipt.get_string( "state" ) == "succeeded" );
}

TEST_CASE( "actor_control_player_withdrawal_preserves_native_craft_effects_without_restart",
           "[actor_control][tasks][crafting][save]" )
{
    task_fixture f;
    const recipe_id recipe( "bandages_makeshift" );
    f.actor->learn_recipe( &recipe.obj() );
    item sheet( itype_id( "sheet_cotton" ), calendar::turn );
    sheet.set_owner( *f.actor );
    f.actor->i_add( sheet );
    f.offer( R"([{"id":"crafting","kind":"craft","args":{"recipe":"bandages_makeshift","batch":1}}])" );
    const std::string withdrawn = control::player_requirements().back().id;
    f.tick();
    REQUIRE( f.actor->activity );
    const int remaining = task_amount( *f.actor, "sheet_cotton" );
    SECTION( "interruptible_activity_keeps_spent_ingredients" ) {
        REQUIRE( f.actor->activity.is_interruptible() );
    }
    SECTION( "completed_effect_is_reconciled_before_withdrawal" ) {
        process_activity( *f.actor );
        REQUIRE_FALSE( f.actor->activity );
        REQUIRE( task_amount( *f.actor, "bandages_makeshift" ) == 2 );
    }
    const int produced = task_amount( *f.actor, "bandages_makeshift" );
    std::string error;
    REQUIRE( control::withdraw_requirement( withdrawn, error ) );
    CHECK_FALSE( f.actor->activity );
    const std::string saved = task_saved();
    control::deserialize( task_object( saved ) );
    f.sync();
    f.tick( 12 );
    CHECK( task_state( "crafting" ) == "cancelled" );
    CHECK( task_amount( *f.actor, "sheet_cotton" ) == remaining );
    CHECK( task_amount( *f.actor, "bandages_makeshift" ) == produced );
}

TEST_CASE( "actor_control_player_request_list_does_not_reveal_promise_or_refusal_truth",
           "[actor_control][tasks][observation]" )
{
    task_fixture f;
    const JsonObject request = f.request();
    const auto before = control::player_requirements();
    REQUIRE( before.size() == 1 );
    std::string action;
    SECTION( "false_promise" ) {
        action = "false_promise";
    }
    SECTION( "refusal" ) {
        action = "refuse";
    }
    SECTION( "real_task_acceptance" ) {
        action = "task";
    }
    SECTION( "request_waiting_for_decision" ) {
        action = "pending";
    }
    if( action == "task" ) {
        task_rpc( "offer_tasks", "{\"context\":" + task_child( request, "context" ).str() +
                  R"(,"tasks":[{"id":"accepted","kind":"follow","args":{},"requirement_id":)" +
                  control::quote( before.front().id ) + "}]}" );
    } else if( action != "pending" ) {
        task_rpc( "offer_plan", "{\"context\":" + task_child( request, "context" ).str() +
                  ",\"steps\":[{\"id\":\"answer\",\"action\":" + control::quote( action ) +
                  ",\"intent\":" + control::quote( action ) + ",\"requirement_id\":" +
                  control::quote( before.front().id ) + R"(,"args":{"text":"My answer."}}]})" );
    }
    f.tick();
    const auto after = control::player_requirements();
    REQUIRE( after.size() == before.size() );
    CHECK( after.front().id == before.front().id );
    CHECK( after.front().sequence == before.front().sequence );
    CHECK( after.front().text == before.front().text );
    CHECK_FALSE( after.front().withdrawn );
    // Old transcripts lack the request link; aged transcripts can lose it too.
    // Internal acceptance must not determine whether their public text exists.
    std::string legacy = "{";
    for( const JsonMember &member : task_object( task_saved() ) ) {
        legacy += ( legacy.size() == 1 ? "" : "," ) + control::quote( member.name() ) + ':';
        legacy += member.name() == "transcript" ?
                  R"([{"speaker":"player","text":"Please consider this task request."}])" :
                  control::stringify( member );
    }
    control::deserialize( task_object( legacy + '}' ) );
    const auto restored = control::player_requirements();
    REQUIRE( restored.size() == 1 );
    CHECK( restored.front().id == before.front().id );
    CHECK( restored.front().sequence == before.front().sequence );
    CHECK( restored.front().text.empty() );
    CHECK_FALSE( restored.front().withdrawn );
    std::string error;
    CHECK( control::withdraw_requirement( after.front().id, error ) );
    CHECK( control::player_requirements().front().withdrawn );
}

TEST_CASE( "actor_control_withdrawal_optional_save_field_is_typed_and_backward_compatible",
           "[actor_control][tasks][save]" )
{
    task_fixture f;
    f.request();
    const std::string id = control::player_requirements().back().id;
    std::string error;
    REQUIRE( control::withdraw_requirement( id, error ) );
    std::string saved = task_saved();
    const std::size_t key = saved.find( "\"withdrawn\"" );
    REQUIRE( key != std::string::npos );
    const std::size_t value = saved.find( "true", saved.find( ':', key ) );
    REQUIRE( value != std::string::npos );
    bool supported = false;
    SECTION( "old_save_without_field" ) {
        const std::size_t previous = saved.rfind( ',', key );
        REQUIRE( previous != std::string::npos );
        saved.erase( previous, value + 4 - previous );
        supported = true;
    }
    SECTION( "non_boolean_field_is_preserved_without_takeover" ) {
        saved.replace( value, 4, "\"wrong\"" );
    }
    control::deserialize( task_object( saved ) );
    if( supported ) {
        REQUIRE( control::player_requirements().size() == 1 );
        CHECK_FALSE( control::player_requirements().front().withdrawn );
    } else {
        CHECK( task_object( control::status() ).get_string( "state" ) == "unsupported_schema" );
        CHECK( control::stringify( json_loader::from_string( task_saved() ) ) ==
               control::stringify( json_loader::from_string( saved ) ) );
    }
}

TEST_CASE( "actor_control_model_candidates_replay_in_isolated_native_world",
           "[.actor_control_model_candidates]" )
{
    const char *directory = std::getenv( "CPH_COMPANION_MODEL_CANDIDATES" );
    REQUIRE( directory != nullptr );
    task_fixture f;
    const tripoint_bub_ms source( 60, 61, 0 );
    const auto replay = [&]( const std::string & name ) {
        const std::filesystem::path path = std::filesystem::path( directory ) /
                                           ( name + "-candidate.json" );
        std::ifstream input( path );
        REQUIRE( input.good() );
        std::ostringstream contents;
        contents << input.rdbuf();
        const JsonObject candidate = task_object( contents.str() );
        REQUIRE( candidate.get_array( "tasks" ).size() == 1 );
        const JsonObject next = f.request();
        std::string requirement;
        std::int64_t latest = -1;
        for( JsonObject incoming : next.get_array( "requirement_decisions" ) ) {
            incoming.allow_omitted_members();
            if( incoming.get_int64( "source_sequence" ) > latest ) {
                latest = incoming.get_int64( "source_sequence" );
                requirement = incoming.get_string( "requirement_id" );
            }
        }
        REQUIRE_FALSE( requirement.empty() );
        std::string tasks = "[";
        std::string candidate_id;
        for( JsonObject definition : candidate.get_array( "tasks" ) ) {
            definition.allow_omitted_members();
            candidate_id = definition.get_string( "id" );
            tasks += '{';
            for( const JsonMember &member : definition ) {
                tasks += control::quote( member.name() ) + ':';
                if( member.name() == "requirement_id" ) {
                    tasks += control::quote( requirement );
                } else if( member.name() == "args" && definition.get_string( "kind" ) == "gather" ) {
                    const JsonObject args = task_child( definition, "args" );
                    if( args.has_member( "x" ) ) {
                        const JsonObject position = task_object( f.position( source ) );
                        tasks += '{';
                        for( const JsonMember &argument : args ) {
                            if( tasks.back() != '{' ) {
                                tasks += ',';
                            }
                            tasks += control::quote( argument.name() ) + ':';
                            tasks += argument.name() == "x" || argument.name() == "y" ||
                                     argument.name() == "z" ?
                                     control::stringify( position.get_member( argument.name() ) ) :
                                     control::stringify( argument );
                        }
                        tasks += '}';
                    } else {
                        tasks += control::stringify( member );
                    }
                } else {
                    tasks += control::stringify( member );
                }
                tasks += ',';
            }
            tasks.back() = '}';
        }
        tasks += ']';
        const JsonObject result = task_rpc( "offer_tasks", "{\"context\":" +
                                            task_child( next, "context" ).str() + ",\"mode\":" +
                                            control::quote( candidate.get_string( "mode", "append" ) ) +
                                            ",\"tasks\":" + tasks + "}" );
        CHECK( result.get_bool( "accepted" ) );
        CHECK( result.get_string( "state" ) == "candidate" );
        return candidate_id;
    };
    SECTION( "gather" ) {
        f.stock( "rock", 3, source );
        const std::string id = replay( "gather" );
        f.tick( 8 );
        CHECK( task_state( id ) == "completed" );
        CHECK( task_entry( id ).get_int( "progress" ) == 2 );
        CHECK( task_amount( *f.actor, "rock" ) == 2 );
        CHECK( task_ground_amount( source, "rock" ) == 1 );
    }
    SECTION( "prefetch" ) {
        f.stock( "rock", 1, source );
        f.offer( R"([{"id":"gather-active","kind":"gather","args":{"item_type":"rock","count":2}}])" );
        f.tick();
        REQUIRE( task_entry( "gather-active" ).get_int( "progress" ) == 1 );
        const std::string id = replay( "prefetch" );
        f.tick();
        CHECK( task_amount( *f.actor, "rock" ) == 1 );
        CHECK( task_state( id ) != "running" );
        f.stock( "rock", 1, source );
        f.tick( 8 );
        CHECK( task_state( "gather-active" ) == "completed" );
        CHECK( task_amount( *f.actor, "rock" ) == 2 );
        CHECK( task_state( id ) == "running" );
        CHECK( f.actor->get_attitude() == NPCATT_FOLLOW );
    }
    SECTION( "change_goal" ) {
        f.stock( "rock", 1, source );
        f.offer( R"([{"id":"gather-active","kind":"gather","args":{"item_type":"rock","count":2}}])" );
        f.tick();
        REQUIRE( task_entry( "gather-active" ).get_int( "progress" ) == 1 );
        REQUIRE( task_state( "gather-active" ) == "queued" );
        f.stock( "rock", 2, source );
        const std::string id = replay( "change_goal" );
        f.tick( 8 );
        CHECK( task_state( "gather-active" ) == "paused" );
        CHECK( task_entry( "gather-active" ).get_int( "progress" ) == 1 );
        CHECK( task_amount( *f.actor, "rock" ) == 1 );
        CHECK( task_ground_amount( source, "rock" ) == 2 );
        CHECK( task_state( id ) == "running" );
        CHECK( f.actor->guard_pos.has_value() );
    }
}
