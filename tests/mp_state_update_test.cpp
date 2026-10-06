#include <chrono>
#include <filesystem>
#include <fstream>
#include <limits>
#include <memory>
#include <string>
#include <system_error>
#include <utility>

#include "avatar.h"
#include "calendar.h"
#include "cata_catch.h"
#include "cata_path.h"
#include "cata_scope_helpers.h"
#include "effect.h"
#include "field_type.h"
#include "game.h"
#include "item.h"
#include "map.h"
#include "map_helpers.h"
#include "mp_client_conn.h"
#include "mp_gamestate.h"
#include "options_helpers.h"
#include "path_info.h"
#include "player_helpers.h"
#include "pocket_type.h"
#include "type_id.h"
#include "units.h"
#include "worldfactory.h"

static const efftype_id effect_sleep( "sleep" );
static const field_type_str_id field_fd_acid( "fd_acid" );
static const field_type_str_id field_fd_fire( "fd_fire" );
static const itype_id itype_flashlight_on( "flashlight_on" );
static const itype_id itype_medium_battery_cell( "medium_battery_cell" );

namespace
{
class state_client_scope
{
    public:
        state_client_scope() : old_turn( calendar::turn ),
            was_client( cata_mp::is_client_mode() ) {
            cata_mp::mp_on_world_exit();
            clear_avatar();
            clear_map_without_vision();
            calendar::turn += 1000_turns;
            cata_mp::set_client_mode( true );
        }
        ~state_client_scope() {
            cata_mp::mp_on_world_exit();
            cata_mp::set_client_mode( was_client );
            calendar::turn = old_turn;
        }
        state_client_scope( const state_client_scope & ) = delete;
        state_client_scope &operator=( const state_client_scope & ) = delete;
    private:
        time_point old_turn;
        bool was_client;
};
} // namespace

TEST_CASE( "mp_state_sleep_grant_is_consumed_once_without_local_calendar_advance",
           "[multiplayer][mp_state][sleep]" )
{
    const state_client_scope mode;
    avatar &client = get_avatar();
    client.set_sleepiness( 1000 );
    client.add_effect( efftype_id( "blind" ), 1_days );
    client.add_effect( effect_sleep, 1_days );
    client.set_moves( 100 );
    const time_point host_turn = calendar::turn;
    REQUIRE( cata_mp::mp_client_consume_sleep_grant() );
    CHECK( client.get_moves() == 0 );
    CHECK( cata_mp::is_client_waiting_for_ack() );
    CHECK( cata_mp::get_client_turn_activity() == "MP_ASLEEP" );
    CHECK_FALSE( cata_mp::should_advance_calendar() );
    CHECK( calendar::turn == host_turn );
    const time_duration sleep_left = client.get_effect_dur( effect_sleep );
    const int hunger = client.get_hunger();
    client.set_moves( 100 );
    REQUIRE( cata_mp::mp_client_consume_sleep_grant() );
    CHECK( client.get_effect_dur( effect_sleep ) == sleep_left );
    CHECK( client.get_hunger() == hunger );
    CHECK( client.get_moves() == 0 );

    client.remove_effect( effect_sleep );
    // The regular action enrichment also clears the synthetic wire marker on
    // waking; its next idle packet must never keep reporting MP_ASLEEP.
    cata_mp::client_enrich_action( R"({"type":"action","action":"wait"})" );
    CHECK( cata_mp::get_client_turn_activity().empty() );
    CHECK_FALSE( cata_mp::mp_client_consume_sleep_grant() );
    CHECK( client.get_moves() == 0 );
}

TEST_CASE( "mp_state_client_upkeep_tracks_host_turns_and_bounds_catchup",
           "[multiplayer][mp_state][calendar]" )
{
    const state_client_scope mode;
    CHECK( cata_mp::mp_client_upkeep_ticks() == 1 );
    CHECK( cata_mp::mp_client_upkeep_ticks() == 0 );
    calendar::turn += 10_turns;
    CHECK( cata_mp::mp_client_upkeep_ticks() == 10 );
    CHECK( cata_mp::mp_client_upkeep_ticks() == 0 );
    calendar::turn += 1000_turns;
    CHECK( cata_mp::mp_client_upkeep_ticks() == 100 );
    calendar::turn -= 1_turns;
    CHECK( cata_mp::mp_client_upkeep_ticks() == 0 );
    CHECK( cata_mp::mp_should_run_client_prefix() );
    CHECK_FALSE( cata_mp::mp_should_run_client_prefix() );
    cata_mp::set_client_mode( false );
    CHECK( cata_mp::should_advance_calendar() );
    CHECK( cata_mp::mp_client_upkeep_ticks() == 1 );
    CHECK( cata_mp::mp_client_upkeep_ticks() == 1 );
}

TEST_CASE( "mp_state_frozen_turn_does_not_repeat_field_damage_or_active_items",
           "[multiplayer][mp_state][field][active_item]" )
{
    const state_client_scope mode;
    const field_type_id hazard = GENERATE( field_fd_acid.id(), field_fd_fire.id() );
    map &here = get_map();
    avatar &client = get_avatar();
    client.setpos( here, tripoint_bub_ms( 60, 60, 0 ) );
    REQUIRE( here.add_field( client.pos_bub(), hazard, 3 ) );
    item battery( itype_medium_battery_cell );
    battery.ammo_set( battery.ammo_default(), 56 );
    item light( itype_flashlight_on );
    light.put_in( battery, pocket_type::MAGAZINE_WELL );
    light.active = true;
    const tripoint_bub_ms light_pos( 62, 60, 0 );
    item &ground_light = here.add_item_or_charges( light_pos, light );
    const int hp_before = client.get_hp();
    g->simulate_turn_suffix();
    const int hp_after_tick = client.get_hp();
    REQUIRE( hp_after_tick < hp_before );
    const units::energy light_after_tick = ground_light.energy_remaining();
    const time_point frozen_turn = calendar::turn;
    for( int poll = 0; poll < 5; ++poll ) {
        g->simulate_turn_suffix();
    }
    CHECK( client.get_hp() == hp_after_tick );
    CHECK( ground_light.energy_remaining() == light_after_tick );
    CHECK( calendar::turn == frozen_turn );
}

TEST_CASE( "mp_state_item_guards_never_apply_at_the_deferred_queue_cap",
           "[multiplayer][mp_state][item_refs]" )
{
    cata_mp::mp_on_world_exit();
    int applied = 0;
    {
        const cata_mp::mp_ui_item_ref_guard outer;
        {
            const cata_mp::mp_ui_item_ref_guard inner;
            for( int update = 0; update < 512; ++update ) {
                cata_mp::mp_defer_item_apply( [&applied]() {
                    ++applied;
                } );
            }
            cata_mp::mp_drain_deferred_item_applies_if_free();
            CHECK( applied == 0 );
        }
        CHECK( cata_mp::mp_ui_holds_item_refs() );
        CHECK( applied == 0 );
    }
    // The incomplete batch is discarded and requests authoritative recovery;
    // it must not execute its prefix after the outer guard releases either.
    CHECK( applied == 0 );
    {
        const cata_mp::mp_ui_item_ref_guard next;
        cata_mp::mp_defer_item_apply( [&applied]() {
            ++applied;
        } );
    }
    CHECK( applied == 1 );
}

TEST_CASE( "mp_state_activity_percentage_handles_maximum_move_counts",
           "[multiplayer][mp_state][activity]" )
{
    const state_client_scope mode;
    const int maximum = std::numeric_limits<int>::max();
    CHECK( cata_mp::mp_activity_percent_suffix( maximum, 0 ) == " 100%" );
    CHECK( cata_mp::mp_activity_percent_suffix( maximum, maximum ) == " 0%" );
    CHECK( cata_mp::mp_activity_percent_suffix( maximum, maximum / 2 ) == " 50%" );
}

TEST_CASE( "mp_state_rollback_discards_pre_rollback_callbacks_while_guarded",
           "[multiplayer][mp_state][item_refs]" )
{
    cata_mp::mp_on_world_exit();
    int stale_applied = 0;
    {
        const cata_mp::mp_ui_item_ref_guard menu;
        cata_mp::mp_defer_item_apply( [&stale_applied]() {
            ++stale_applied;
        } );
        cata_mp::mp_invalidate_deferred_item_batch();
        CHECK( cata_mp::mp_ui_holds_item_refs() );
        CHECK( stale_applied == 0 );
    }
    CHECK( stale_applied == 0 );
}

TEST_CASE( "mp_state_client_scratch_world_never_deletes_a_name_collision",
           "[multiplayer][mp_state][world][save]" )
{
    const std::string old_savedir = PATH_INFO::savedir();
    std::unique_ptr<worldfactory> old_factory = std::move( world_generator );
    const std::filesystem::path temporary = std::filesystem::temp_directory_path() /
                                            ( "cph-mp-scratch-test-" + std::to_string(
                                                    std::chrono::steady_clock::now().time_since_epoch().count() ) );
    REQUIRE( std::filesystem::create_directory( temporary ) );
    const on_out_of_scope cleanup( [&]() {
        world_generator = std::move( old_factory );
        PATH_INFO::set_savedir( old_savedir );
        cata_mp::mp_store_pending_welcome( "" );
        std::error_code error;
        std::filesystem::remove_all( temporary, error );
    } );
    PATH_INFO::set_savedir( temporary.u8string() + "/" );
    world_generator = std::make_unique<worldfactory>();
    const override_option compression( "WORLD_COMPRESSION2", "false" );
    const std::string old_name = "Co-op (auto) - DO NOT SELECT";
    WORLD *legacy = world_generator->make_new_world( old_name, { mod_id( "ccb" ) } );
    REQUIRE( legacy != nullptr );
    const std::filesystem::path sentinel = legacy->folder_path().get_unrelative_path() /
                                           "user-save.txt";
    std::ofstream( sentinel ) << "preserve this user content";
    cata_mp::mp_store_pending_welcome( R"({"type":"welcome","mods":["ccb"]})" );
    WORLD *scratch = cata_mp::mp_ensure_client_scratch_world();
    REQUIRE( scratch != nullptr );
    CHECK( scratch != legacy );
    CHECK( world_generator->get_world( old_name ) == legacy );
    CHECK( std::filesystem::exists( sentinel ) );
    CHECK( cata_mp::mp_ensure_client_scratch_world() == scratch );
    // A changed host mod order preserves the first marked scratch as well.
    cata_mp::mp_store_pending_welcome( R"({"type":"welcome","mods":["ccb","test_data"]})" );
    WORLD *second = cata_mp::mp_ensure_client_scratch_world();
    REQUIRE( second != nullptr );
    CHECK( second != scratch );
    CHECK( world_generator->get_world( scratch->world_name ) == scratch );
    CHECK( std::filesystem::exists( sentinel ) );
}
