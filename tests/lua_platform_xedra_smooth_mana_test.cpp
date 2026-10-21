#if defined(CATA_ENABLE_LUA_PLATFORM) && CATA_ENABLE_LUA_PLATFORM

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <variant>
#include <vector>

#include "avatar.h"
#include "calendar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "character_id.h"
#include "lua_platform_handle.h"
#include "lua_platform_hooks.h"
#include "lua_platform_loader.h"
#include "lua_platform_runtime.h"
#include "lua_platform_runtime_internal.h"
#include "magic.h"
#include "magic_enchantment.h"
#include "morale.h"
#include "npc.h"
#include "pimpl.h"
#include "player_helpers.h"
#include "type_id.h"

static const morale_type morale_perm_debug( "morale_perm_debug" );
static const trait_id trait_DREAMER( "DREAMER" );

namespace
{
namespace platform = cata::lua_platform;

std::shared_ptr<platform::runtime> require_smooth_mana_runtime()
{
    INFO( "This gameplay regression requires --mods xedra_evolved,xedra_smooth_mana" );
    REQUIRE( platform::is_enabled() );
    const std::shared_ptr<platform::runtime> owner =
        platform::detail::find_active_runtime( "xedra_smooth_mana" );
    REQUIRE( owner );
    return owner;
}

struct smooth_mana_fixture {
    avatar &player;
    std::shared_ptr<platform::runtime> owner;
    restore_on_out_of_scope<time_point> restore_turn;
    restore_on_out_of_scope<platform::script_persistent_state> restore_character_state;
    restore_on_out_of_scope<platform::script_persistent_state> restore_world_state;
    restore_on_out_of_scope<std::vector<platform::persistent_task>> restore_tasks;
    restore_on_out_of_scope<std::uint64_t> restore_next_task;
    restore_on_out_of_scope<bool> restore_ready;
    on_out_of_scope clear_player;

    explicit smooth_mana_fixture( bool dreamer = true ) :
        player( get_avatar() ), owner( require_smooth_mana_runtime() ),
        restore_turn( calendar::turn ),
        restore_character_state( owner->character_state ),
        restore_world_state( owner->world_state ), restore_tasks( owner->tasks ),
        restore_next_task( owner->next_task_id ), restore_ready( owner->world_is_ready ),
        clear_player( []() {
        clear_avatar();
    } ) {
        clear_avatar();
        // Begin at a future three-minute boundary after clear_avatar's body update.
        calendar::turn = time_point::from_turn( 1800000 );
        owner->character_state.clear();
        player.update_body( calendar::turn, calendar::turn );
        if( dreamer ) {
            REQUIRE( trait_DREAMER.is_valid() );
            player.set_mutation( trait_DREAMER );
        }
        set_morale( 0 );
        player.magic->set_mana( 0 );
        REQUIRE( player.magic->max_mana( player ) == 1000 );
        REQUIRE( owner->character_recurring_handlers.size() == 1 );
        platform::runtime_world_ready( true );
        platform::runtime_process_character_recurring( player );
    }

    void set_morale( int morale ) {
        player.clear_morale();
        if( morale != 0 ) {
            player.morale->set_permanent( morale_perm_debug, morale );
        }
        REQUIRE( player.get_morale_level() == morale );
        player.recalculate_enchantment_cache();
    }

    double recovery_factor() const {
        return std::max( 0.0, player.calculate_by_enchantment(
                             1000.0, enchant_vals::mod::REGEN_MANA ) ) / 1000.0;
    }

    double fraction() const {
        const auto found = owner->character_state.find( "fraction" );
        if( found == owner->character_state.end() ) {
            return 0.0;
        }
        if( const double *number = std::get_if<double>( &found->second ) ) {
            return *number;
        }
        if( const std::int64_t *number = std::get_if<std::int64_t>( &found->second ) ) {
            return static_cast<double>( *number );
        }
        FAIL( "fraction is not numeric" );
        return 0.0;
    }

    void tick( bool full_body = false ) {
        const time_point before = calendar::turn;
        calendar::turn += 3_minutes;
        if( full_body ) {
            player.update_body( before, calendar::turn );
        } else {
            player.magic->update_mana( player, to_turns<float>( 3_minutes ) );
        }
        platform::runtime_process_character_recurring( player );
    }

    void force_due_now() {
        player.set_value( owner->character_recurring_handlers.front().due_variable,
                          to_turn<double>( calendar::turn ) );
        platform::runtime_process_character_recurring( player );
    }
};
} // namespace

// Run explicitly with --mods xedra_evolved,xedra_smooth_mana. The ordinary
// engine and Lua suites do not need to load these optional gameplay Mods.
TEST_CASE( "xedra_smooth_mana_calm_fraction_recovers_through_body_updates",
           "[.][mods][xedra_smooth_mana]" )
{
    smooth_mana_fixture fixture;
    REQUIRE( fixture.recovery_factor() == Approx( 0.1 ).margin( 1e-8 ) );
    const std::array<int, 8> expected = {{ 0, 1, 1, 2, 3, 3, 4, 5 }};
    for( std::size_t index = 0; index < expected.size(); ++index ) {
        CAPTURE( index );
        fixture.tick( true );
        CHECK( fixture.player.get_morale_level() == 0 );
        CHECK( fixture.player.magic->available_mana() == expected[index] );
    }
    CHECK( fixture.fraction() == Approx( 0.0 ).margin( 1e-8 ) );
}

TEST_CASE( "xedra_smooth_mana_morale_curve_is_symmetric_and_continuous",
           "[.][mods][xedra_smooth_mana]" )
{
    const int morale = GENERATE( -100, -50, -36, -35, -34, -20, -1, 0, 1, 20, 34, 35, 36, 50, 100 );
    smooth_mana_fixture fixture;
    fixture.set_morale( morale );
    const double expected_factor = 0.1 + std::abs( morale ) / 41.0;
    REQUIRE( fixture.recovery_factor() == Approx( expected_factor ).margin( 1e-8 ) );
    const double pulse = 1000.0 * expected_factor / 160.0;
    for( int index = 1; index <= 8; ++index ) {
        CAPTURE( morale, index, expected_factor, pulse );
        fixture.tick();
        CHECK( fixture.player.magic->available_mana() ==
               static_cast<int>( std::floor( index * pulse + 1e-9 ) ) );
    }
}

TEST_CASE( "xedra_smooth_mana_fraction_does_not_bank_at_full_mana",
           "[.][mods][xedra_smooth_mana]" )
{
    smooth_mana_fixture fixture;
    fixture.tick();
    REQUIRE( fixture.fraction() == Approx( 0.625 ).margin( 1e-8 ) );
    fixture.player.magic->set_mana( 999 );
    fixture.tick();
    REQUIRE( fixture.player.magic->available_mana() == 1000 );
    CHECK( fixture.fraction() == 0.0 );
    for( int index = 0; index < 8; ++index ) {
        fixture.tick();
        CHECK( fixture.player.magic->available_mana() == 1000 );
        CHECK( fixture.fraction() == 0.0 );
    }
    fixture.player.magic->set_mana( 0 );
    fixture.tick();
    CHECK( fixture.player.magic->available_mana() == 0 );
    CHECK( fixture.fraction() == Approx( 0.625 ).margin( 1e-8 ) );
    fixture.tick();
    CHECK( fixture.player.magic->available_mana() == 1 );
}

TEST_CASE( "xedra_smooth_mana_repeated_tick_has_no_duplicate_fraction",
           "[.][mods][xedra_smooth_mana]" )
{
    smooth_mana_fixture fixture;
    fixture.tick();
    REQUIRE( fixture.player.magic->available_mana() == 0 );
    REQUIRE( fixture.fraction() == Approx( 0.625 ).margin( 1e-8 ) );
    for( int index = 0; index < 2; ++index ) {
        fixture.force_due_now();
        CHECK( fixture.player.magic->available_mana() == 0 );
        CHECK( fixture.fraction() == Approx( 0.625 ).margin( 1e-8 ) );
    }
}

TEST_CASE( "xedra_smooth_mana_non_dreamer_receives_no_fraction_supplement",
           "[.][mods][xedra_smooth_mana]" )
{
    smooth_mana_fixture fixture( false );
    REQUIRE_FALSE( fixture.player.has_trait( trait_DREAMER ) );
    fixture.owner->character_state["fraction"] = 0.9;
    for( int index = 1; index <= 8; ++index ) {
        fixture.tick();
        CHECK( fixture.player.magic->available_mana() == index * 6 );
        CHECK( fixture.fraction() == 0.0 );
    }
}

TEST_CASE( "xedra_smooth_mana_zero_effective_regen_receives_no_fraction_supplement",
           "[.][mods][xedra_smooth_mana]" )
{
    smooth_mana_fixture fixture;
    // A native cache penalty isolates the zero-rate guard without requiring
    // an unrelated item fixture. Avoid body updates that would rebuild it.
    fixture.player.enchantment_cache->add_value_mult( enchant_vals::mod::REGEN_MANA, -1.0f );
    REQUIRE( fixture.recovery_factor() == 0.0 );
    fixture.owner->character_state["fraction"] = 0.9;
    for( int index = 0; index < 8; ++index ) {
        fixture.tick();
        CHECK( fixture.player.magic->available_mana() == 0 );
        CHECK( fixture.fraction() == 0.0 );
    }
}

TEST_CASE( "xedra_smooth_mana_control_npc_clears_fraction_without_repeating_the_tick",
           "[.][mods][xedra_smooth_mana]" )
{
    smooth_mana_fixture fixture;
    fixture.tick();
    REQUIRE( fixture.fraction() == Approx( 0.625 ).margin( 1e-8 ) );
    REQUIRE( fixture.owner->character_state.count( "last_tick" ) == 1 );
    const platform::script_persistent_value last_tick =
        fixture.owner->character_state.at( "last_tick" );

    npc previous_character;
    previous_character.normalize();
    previous_character.setID( character_id( 733021 ), true );
    platform::register_npc_handle_identity( previous_character );
    const on_out_of_scope retire( [&]() {
        platform::retire_npc_handle_identity( previous_character );
    } );
    REQUIRE( platform::has_native_hook( "on_control_npc" ) );
    CHECK( platform::dispatch_native_hook( "on_control_npc", {
        { "avatar", static_cast<const Character *>( &fixture.player ) },
        { "npc", static_cast<const Character *>( &previous_character ) },
        { "debug", true }
    } ) );
    CHECK( fixture.fraction() == 0.0 );
    CHECK( fixture.owner->character_state.at( "last_tick" ) == last_tick );
    fixture.force_due_now();
    CHECK( fixture.fraction() == 0.0 );
    CHECK( fixture.player.magic->available_mana() == 0 );
    fixture.tick();
    CHECK( fixture.fraction() == Approx( 0.625 ).margin( 1e-8 ) );
    CHECK( fixture.player.magic->available_mana() == 0 );
}

#endif // CATA_ENABLE_LUA_PLATFORM
