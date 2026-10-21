#include <memory>
#include <string>

#include "avatar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "character_id.h"
#include "dialogue.h"
#include "dialogue_helpers.h"
#include "event.h"
#include "event_bus.h"
#include "event_subscriber.h"
#include "lua_platform_runtime.h"
#include "magic.h"
#include "map_helpers.h"
#include "npc.h"
#include "npc_execution_adapter.h"
#include "pimpl.h"
#include "player_helpers.h"
#include "talker.h"
#include "type_id.h"

#if defined(CATA_ENABLE_LUA_PLATFORM) && CATA_ENABLE_LUA_PLATFORM
#include "lua_platform_runtime_internal.h"
#include "lua_platform_sol.h"
#endif

namespace
{
const spell_id spell_test_spell_pew( "test_spell_pew" );

class spellbook_observer : public event_subscriber
{
    public:
        int calls = 0;
        int calls_without_talker = 0;
        Character *caster = nullptr;
        bool has_beta = false;

        void notify( const cata::event &event ) override {
            if( event.type() == event_type::opens_spellbook ) {
                ++calls_without_talker;
            }
        }

        void notify( const cata::event &event, std::unique_ptr<talker> alpha,
                     std::unique_ptr<talker> beta ) override {
            if( event.type() == event_type::opens_spellbook ) {
                ++calls;
                caster = alpha ? alpha->get_character() : nullptr;
                has_beta = beta != nullptr;
                if( caster ) {
                    caster->magic->caster_level_adjustment = 3;
                }
            }
        }
};
} // namespace

TEST_CASE( "actor_control_spell_level_adjustment_uses_actual_caster",
           "[actor_control][magic][spell][level]" )
{
    clear_avatar();
    avatar &host = get_avatar();
    host.set_int_base( 4 );
    npc caster;
    caster.normalize();
    caster.set_int_base( 12 );

    spell_type &type = const_cast<spell_type &>( spell_test_spell_pew.obj() );
    const dbl_or_var original_max = type.max_level;
    const on_out_of_scope restore_type( [&type, &original_max]() {
        type.max_level = original_max;
    } );
    type.max_level.max.reset();
    type.max_level.min.val = runtime_dbl_provider{ []( const const_dialogue & context ) {
        return static_cast<double>( context.const_actor( false )->int_cur() );
    } };
    caster.magic->learn_spell( spell_test_spell_pew, caster, true );
    caster.magic->set_spell_level( spell_test_spell_pew, 2, &caster );
    spell &known = caster.magic->get_spell( spell_test_spell_pew );
    REQUIRE( known.get_max_level( host ) == 4 );
    REQUIRE( known.get_max_level( caster ) == 12 );

    caster.magic->clear_opens_spellbook_data();
    caster.magic->caster_level_adjustment = 100;
    caster.magic->evaluate_opens_spellbook_data( caster );
    CHECK( known.get_effective_level() == 12 );

    caster.magic->clear_opens_spellbook_data();
    caster.magic->caster_level_adjustment = -100;
    caster.magic->evaluate_opens_spellbook_data( caster );
    CHECK( known.get_effective_level() == 0 );
}

TEST_CASE( "actor_control_casting_preparation_carries_caster_and_queries_do_not_dispatch",
           "[actor_control][magic][spell][events]" )
{
    clear_avatar();
    clear_map_without_vision();
    avatar &host = get_avatar();
    npc caster;
    caster.normalize();
    // Deliberately not a tracked NPC: implicit ID lookup would fall back to the host.
    caster.setID( character_id( 6414 ), true );
    caster.magic->learn_spell( spell_test_spell_pew, caster, true );
    caster.magic->set_spell_level( spell_test_spell_pew, 2, &caster );
    spell &known = caster.magic->get_spell( spell_test_spell_pew );
    host.magic->caster_level_adjustment = 7;
    caster.magic->caster_level_adjustment = 90;
    known.set_temp_level_adjustment( 80 );
    spellbook_observer observer;
    get_event_bus().subscribe( &observer );

    cata::actor_control::NpcExecutionAdapter::observe( caster );
    CHECK( observer.calls == 0 );
    CHECK( caster.magic->caster_level_adjustment == 90 );
    CHECK( known.get_temp_level_adjustment() == 80 );

    caster.magic->prepare_casting( caster );
    CHECK( observer.calls == 1 );
    CHECK( observer.calls_without_talker == 0 );
    CHECK( observer.caster == &caster );
    CHECK_FALSE( observer.has_beta );
    CHECK( known.get_effective_level() == 5 );
    CHECK( host.magic->caster_level_adjustment == 7 );

    caster.magic->prepare_casting( caster );
    CHECK( observer.calls == 2 );
    CHECK( known.get_effective_level() == 5 );
    CHECK( host.magic->caster_level_adjustment == 7 );

    caster.evaluate_best_attack( nullptr );
    CHECK( observer.calls == 3 );
    CHECK( known.get_effective_level() == 5 );
    caster.magic->forget_spell( spell_test_spell_pew );
    caster.evaluate_best_attack( nullptr );
    CHECK( observer.calls == 3 );
}

#if defined(CATA_ENABLE_LUA_PLATFORM) && CATA_ENABLE_LUA_PLATFORM
TEST_CASE( "actor_control_spellbook_hook_query_checks_live_event_subscriptions",
           "[actor_control][magic][lua][platform]" )
{
    namespace platform = cata::lua_platform;
    clear_avatar();
    clear_map_without_vision();
    npc caster;
    caster.normalize();
    caster.magic->learn_spell( spell_test_spell_pew, caster, true );
    platform::clear_active_runtimes();
    const on_out_of_scope clear_runtimes( []() {
        platform::clear_active_runtimes();
    } );
    sol::state lua;
    const std::shared_ptr<platform::runtime> owner =
        platform::make_runtime( "spellbook_hook_query", 6415, lua );
    platform::set_active_runtimes( { owner } );
    owner->subscriptions["game:opens_spellbook"] = { "prepare" };
    CHECK_FALSE( platform::has_event_handler( event_type::opens_spellbook ) );
    owner->world_is_ready = true;
    CHECK( platform::has_event_handler( event_type::opens_spellbook ) );
    CHECK_FALSE( platform::has_event_handler( event_type::character_casts_spell ) );
    CHECK( cata::actor_control::NpcExecutionAdapter::validate_spell_cast(
               caster, spell_test_spell_pew, caster.pos_bub() ).code ==
           "npc_unsupported_spellbook_event" );
    CHECK( cata::actor_control::NpcExecutionAdapter::observe( caster ).find(
               "npc_unsupported_spellbook_event" ) != std::string::npos );
    owner->subscriptions["game:opens_spellbook"].clear();
    CHECK_FALSE( platform::has_event_handler( event_type::opens_spellbook ) );
    platform::clear_active_runtimes();
    CHECK_FALSE( platform::has_event_handler( event_type::opens_spellbook ) );
}
#endif
