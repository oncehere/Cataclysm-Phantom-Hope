#include "npc_execution_adapter.h"

#include <algorithm>
#include <climits>
#include <map>
#include <sstream>
#include <set>
#include <string>
#include <utility>
#include <vector>

#include "actor_control.h"
#include "actor_control_protocol.h"
#include "avatar.h"
#include "bodypart.h"
#include "calendar.h"
#include "character.h"
#include "character_attire.h"
#include "character_id.h"
#include "coordinates.h"
#include "craft_command.h"
#include "craft_reservation.h"
#include "creature_tracker.h"
#include "damage.h"
#include "dialogue.h"
#include "effect_on_condition.h"
#include "enum_conversions.h"
#include "event.h"
#include "flexbuffer_json.h"
#include "game.h"
#include "item.h"
#include "item_location.h"
#include "json.h"
#include "json_loader.h"
#include "line.h"
#include "lua_platform_runtime.h"
#include "magic.h"
#include "magic_type.h"
#include "map.h"
#include "map_iterator.h"
#include "math_parser_diag_value.h"
#include "mission.h"
#include "monster.h"
#include "mp_gamestate.h"
#include "mtype.h"
#include "native_item_transfer.h"
#include "npc.h"
#include "npctalk.h"
#include "npctrade.h"
#include "output.h"
#include "player_activity.h"
#include "item_pocket.h"
#include "recipe.h"
#include "recipe_dictionary.h"
#include "skill.h"
#include "talker.h"
#include "translations.h"
#include "type_id.h"
#include "visitable.h"

namespace cata::actor_control
{
namespace
{

execution_result result( execution_state state, const std::string &code,
                         bool consumed = false, const std::string &detail = "{}" )
{
    return { state, code, detail, consumed };
}

std::string value( const npc &actor, const std::string &key )
{
    const diag_value *stored = actor.maybe_get_value( "cph_ai." + key );
    return stored ? stored->to_string() : std::string();
}

std::string preview( const std::string &text, std::size_t maximum )
{
    std::size_t characters = 0;
    std::size_t byte = 0;
    for( ; byte < text.size(); ++byte ) {
        if( ( static_cast<unsigned char>( text[byte] ) & 0xc0 ) != 0x80 &&
            characters++ == maximum ) {
            break;
        }
    }
    return text.substr( 0, byte );
}

bool knows_information( const npc &actor, const JsonObject &args )
{
    const std::string text = args.get_string( "text" );
    const std::string id = args.get_string( "information_id", "" );
    if( text.empty() ) {
        return false;
    }
    try {
        const JsonArray records = json_loader::from_string( value( actor,
                                  "known_information" ) ).get_array();
        for( const JsonObject record : records ) {
            record.allow_omitted_members();
            const std::string kind = record.get_string( "kind", "" );
            if( ( kind == "statement" || kind == "belief" ) &&
                record.get_string( "text", "" ) == text &&
                ( id.empty() || record.get_string( "id", "" ) == id ) ) {
                return true;
            }
        }
    } catch( const std::exception & ) {
        // A missing or invalid cognition cache does not authorize disclosure.
    }
    return false;
}

void write_position( JsonOut &out, const tripoint_abs_ms &pos )
{
    out.start_object();
    out.member( "x", pos.x() );
    out.member( "y", pos.y() );
    out.member( "z", pos.z() );
    out.end_object();
}

void write_inventory( JsonOut &out, const Character &actor )
{
    struct inventory_count {
        int count = 0;
        int worn = 0;
        int wielded = 0;
    };
    std::map<std::string, inventory_count> counts;
    const item_location wielded = actor.get_wielded_item();
    actor.visit_items( [&counts, &actor, &wielded]( item * it, item * ) {
        if( counts.size() >= 128 && counts.count( it->typeId().str() ) == 0 ) {
            return VisitResponse::SKIP;
        }
        if( !it->is_null() ) {
            inventory_count &entry = counts[it->typeId().str()];
            const int amount = it->count_by_charges() ? it->charges : 1;
            entry.count += amount;
            entry.worn += actor.is_worn( *it ) ? amount : 0;
            entry.wielded += wielded && wielded.get_item() == it ? amount : 0;
        }
        return VisitResponse::NEXT;
    } );
    out.start_array();
    for( const std::pair<const std::string, inventory_count> &entry : counts ) {
        out.start_object();
        out.member( "item_type", entry.first );
        out.member( "count", entry.second.count );
        out.member( "worn", entry.second.worn );
        out.member( "wielded", entry.second.wielded );
        out.end_object();
    }
    out.end_array();
}

bool observes( const npc &actor, const map &here, const tripoint_bub_ms &pos )
{
    // Native sees() permits adjacent creatures even without sight, and its
    // minimum terrain sight range is one.  Neither shortcut conveys visual
    // knowledge to the companion.  Preserve actual clairvoyance when present.
    const bool clairvoyant = rl_dist( actor.pos_bub( here ), pos ) < actor.clairvoyance();
    return ( !actor.is_blind() || clairvoyant ) && actor.sees( here, pos );
}

bool observes( const npc &actor, const map &here, const Creature &creature )
{
    return observes( actor, here, creature.pos_bub( here ) ) && actor.sees( here, creature );
}

Character *visible_character( npc &actor, int id )
{
    Character *target = get_avatar().getID() == character_id( id ) ?
                        static_cast<Character *>( &get_avatar() ) : g->find_npc( character_id( id ) );
    return target && target != &actor && !target->is_dead_state() &&
           observes( actor, get_map(), *target ) ? target : nullptr;
}

bool near( const npc &actor, const Character &target )
{
    return rl_dist( actor.pos_abs(), target.pos_abs() ) <= 2;
}

execution_result move_towards( npc &actor, const tripoint_bub_ms &target, int distance,
                               const action_step *step = nullptr )
{
    map &here = get_map();
    if( !here.inbounds( target ) || !observes( actor, here, target ) ) {
        return result( execution_state::failed, "target_not_observed" );
    }
    if( rl_dist( actor.pos_bub(), target ) <= distance ) {
        return result( execution_state::succeeded, "arrived" );
    }
    const int before = actor.get_moves();
    if( !actor.update_path( target, true ) || actor.path.empty() ) {
        return result( execution_state::failed, "no_native_path" );
    }
    if( step && step->task_bounds_json != "{}" ) {
        const JsonObject bounds = json_loader::from_string( step->task_bounds_json ).get_object();
        const tripoint_abs_ms anchor( bounds.get_int( "x" ), bounds.get_int( "y" ), bounds.get_int( "z" ) );
        if( square_dist( anchor, here.get_abs( actor.path.front() ) ) > bounds.get_int( "radius" ) ) {
            return result( execution_state::failed, "task_path_outside_area" );
        }
    }
    actor.move_to_next();
    return result( rl_dist( actor.pos_bub(), target ) <= distance ?
                   execution_state::succeeded : execution_state::running,
                   "native_move", actor.get_moves() < before );
}

tripoint_bub_ms position_arg( const JsonObject &args )
{
    return get_map().get_bub( tripoint_abs_ms( args.get_int( "x" ),
                              args.get_int( "y" ), args.get_int( "z" ) ) );
}

std::string spell_support( const npc &actor, const spell &known )
{
    const spell_type &type = known.id().obj();
    if( known.energy_source() == magic_energy_type::hp ) {
        return "interactive_energy_source";
    }
    if( known.energy_source() == magic_energy_type::vitamin ||
        ( known.energy_source() == magic_energy_type::stamina && !actor.uses_stamina() ) ) {
        // Ordinary NPCs still have unlimited stamina. Vitamin/calorie handling
        // remains outside this checked interface, including NO_NPC_FOOD.
        return "npc_unsupported_energy_source";
    }
    if( type.effect_name != "attack" && type.effect_name != "recover_energy" ) {
        return "npc_unsupported_effect";
    }
    if( type.effect_name == "attack" && !type.dmg_type.is_null() &&
        ( !type.dmg_type.is_valid() || !type.dmg_type->onhit_eocs.empty() ||
          !type.dmg_type->ondamage_eocs.empty() ||
          cata::lua_platform::has_damage_type_handler( type.dmg_type.str() ) ) ) {
        return "npc_unsupported_damage_effect";
    }
    // Effects, failure callbacks and channels can open menus or depend on the avatar.
    // Do not infer safety from the outer spell's effect or from its Mod of origin.
    if( !type.additional_spells.empty() || !known.get_failure_eoc_ids().empty() ||
        known.is_channeling_spell() || type.channelling_turns != 0 ||
        !type.channel_spell.empty() || !type.channel_end_spell.empty() ||
        !type.channel_interrupt_spell.empty() ) {
        return "npc_unsupported_effect_chain";
    }
    if( type.magic_type && cata::lua_platform::has_magic_type_failure_handler(
            type.magic_type->str() ) ) {
        return "npc_unsupported_effect_chain";
    }
    if( known.has_components() ) {
        // Native spell selectors do not yet enforce craft reservations/ownership.
        return "npc_unsupported_components";
    }
    static const std::set<std::string> supported_flags = {
        "SILENT", "NO_EXPLOSION_SFX", "LOUD", "VERBAL", "SOMATIC", "NO_HANDS",
        "NO_PROJECTILE", "NO_LEGS", "CONCENTRATE", "TOUCH_REQUIRED", "RANDOM_DAMAGE",
        "RANDOM_DURATION", "NO_FAIL", "NON_MAGICAL", "PSIONIC", "SPLIT_DAMAGE",
        "PERCENTAGE_DAMAGE", "MUST_HAVE_CLASS_TO_LEARN", "EVOCATION_SPELL",
        "CONJURATION_SPELL", "ENHANCEMENT_SPELL", "ENERVATION_SPELL", "CONVEYANCE_SPELL",
        "RESTORATION_SPELL", "TRANSFORMATION_SPELL"
    };
    for( const std::string &flag : type.flags ) {
        if( !supported_flags.count( flag ) ) {
            return "npc_unsupported_spell_flag";
        }
    }
    const_dialogue context( get_const_talker_for( actor ), nullptr );
    if( known.shape() != spell_shape::blast || known.aoe( actor ) != 0 || type.field ||
        type.min_dot.evaluate( context ) != 0 || type.max_dot.evaluate( context ) != 0 ||
        type.dot_increment.evaluate( context ) != 0 ||
        type.min_bash_scaling.evaluate( context ) != 0 ||
        type.max_bash_scaling.evaluate( context ) != 0 ||
        type.bash_scaling_increment.evaluate( context ) != 0 ||
        known.get_amount_of_projectiles( actor ) > 1 ) {
        return "npc_unsupported_area_effect";
    }
    if( type.effect_name == "attack" && !known.effect_data().empty() ) {
        // Applying an arbitrary effect can itself install periodic EOC/teleport hooks.
        return "npc_unsupported_status_effect";
    }
    if( type.effect_name == "recover_energy" && known.effect_data() == "STAMINA" &&
        !actor.uses_stamina() ) {
        return "npc_unsupported_energy_source";
    }
    if( type.effect_name == "recover_energy" && known.effect_data() != "MANA" &&
        known.effect_data() != "STAMINA" &&
        known.effect_data() != "SLEEPINESS" &&
        known.effect_data() != "PAIN" && known.effect_data() != "HEALTH" ) {
        return "npc_unsupported_effect";
    }
    const auto &effects = effect_on_conditions::get_all();
    if( std::any_of( effects.begin(), effects.end(), []( const effect_on_condition & eoc ) {
    return eoc.type == eoc_type::EVENT && eoc.required_event == event_type::opens_spellbook;
    } ) || cata::lua_platform::has_event_handler( event_type::opens_spellbook ) ) {
        // Preparation is gameplay, not observation. Do not silently skip Mod
        // prerequisites or run unaudited scripts under a spell's permission.
        return "npc_unsupported_spellbook_event";
    }
    return {};
}

std::string spell_resources( const npc &actor, const spell &known )
{
    if( !actor.magic->has_enough_energy( actor, known ) ) {
        return "insufficient_spell_energy";
    }
    if( !known.can_cast( actor ) ) {
        return "native_spell_requirements";
    }
    return {};
}

Creature *spell_target_at( npc &actor, const tripoint_bub_ms &target )
{
    return actor.pos_bub() == target ? &actor :
           get_creature_tracker().creature_at<Creature>( target );
}

std::string spell_target_identity( const Creature &target )
{
    if( const Character *person = target.as_character() ) {
        return "character:" + std::to_string( person->getID().get_value() );
    }
    if( const monster *critter = target.as_monster() ) {
        return "monster:" + std::to_string( critter->uid().get_value() );
    }
    return {};
}

void write_abilities( JsonOut &out, const npc &actor )
{
    const std::vector<spell_id> known_ids = actor.magic->spells();
    out.member( "mana", actor.magic->available_mana() );
    out.member( "mana_max", actor.magic->max_mana( actor ) );
    out.member( "ability_count", known_ids.size() );
    out.member( "abilities_truncated", known_ids.size() > 64 );
    out.member( "abilities" );
    out.start_array();
    for( std::size_t index = 0; index < std::min<std::size_t>( 64, known_ids.size() ); ++index ) {
        const spell &known = actor.magic->get_spell( known_ids[index] );
        const std::string unsupported = spell_support( actor, known );
        const std::string unavailable = unsupported.empty() ? spell_resources( actor, known ) : unsupported;
        out.start_object();
        out.member( "id", known.id().str() );
        out.member( "name", preview( known.name(), 160 ) );
        out.member( "level", known.get_level() );
        out.member( "effect", known.id()->effect_name );
        out.member( "supported", unsupported.empty() );
        out.member( "reason", unavailable );
        out.member( "energy_source", io::enum_to_string( known.energy_source() ) );
        out.member( "energy_cost", known.energy_cost( actor ) );
        out.member( "casting_time_moves", known.casting_time( actor ) );
        out.member( "range", known.range( actor ) );
        out.member( "targets", known.id()->valid_targets );
        out.member( "failure_chance", known.spell_fail( actor ) );
        out.member( "castable", unavailable.empty() && !actor.activity && actor.get_moves() > 0 );
        out.end_object();
    }
    out.end_array();
}

execution_result cast_spell( npc &actor, const action_step &step, const JsonObject &args )
{
    for( const JsonMember &member : args ) {
        if( member.name() != "spell" && member.name() != "x" && member.name() != "y" &&
            member.name() != "z" ) {
            return result( execution_state::failed, "invalid_spell_arguments" );
        }
    }
    if( !args.has_string( "spell" ) || !args.has_int( "x" ) || !args.has_int( "y" ) ||
        !args.has_int( "z" ) ) {
        return result( execution_state::failed, "invalid_spell_arguments" );
    }
    const std::string active = value( actor, "spell_step" );
    const std::string completed = value( actor, "spell_completed_step" );
    if( active == step.id || completed == step.id ) {
        if( value( actor, "spell_args" ) != step.args_json ) {
            return result( execution_state::failed, "receipt_conflict" );
        }
        if( completed == step.id ) {
            const JsonObject receipt = json_loader::from_string( value( actor, "spell_result" ) ).get_object();
            return result( receipt.get_string( "state" ) == "succeeded" ?
                           execution_state::succeeded : execution_state::failed,
                           receipt.get_string( "code" ), false, receipt.get_string( "detail", "{}" ) );
        }
        return result( actor.activity.id() == activity_id( "ACT_SPELLCASTING" ) ?
                       execution_state::running : execution_state::failed,
                       actor.activity.id() == activity_id( "ACT_SPELLCASTING" ) ?
                       "native_spell_activity" : "spell_interrupted" );
    }
    if( actor.activity ) {
        return result( execution_state::failed, "actor_busy" );
    }
    if( actor.get_moves() <= 0 ) {
        return result( execution_state::failed, "no_native_moves" );
    }
    const spell_id id( args.get_string( "spell" ) );
    const tripoint_bub_ms target = position_arg( args );
    const execution_result checked = NpcExecutionAdapter::validate_spell_cast( actor, id, target );
    if( checked.state != execution_state::succeeded ) {
        return checked;
    }
    actor.magic->prepare_casting( actor );
    // Preparation may change level/cost. Keep the final native authorization
    // against the actual caster and never repeat preparation at completion.
    const execution_result prepared = NpcExecutionAdapter::validate_spell_cast( actor, id, target );
    if( prepared.state != execution_state::succeeded ) {
        return prepared;
    }
    spell &known = actor.magic->get_spell( id );
    if( !actor.cast_spell( known, false, target ) ) {
        return result( execution_state::failed, "native_spell_requirements" );
    }
    actor.activity.str_values = { "cph_ai.cast_spell", step.id };
    actor.set_value( "cph_ai.spell_step", step.id );
    actor.set_value( "cph_ai.spell_args", step.args_json );
    actor.set_value( "cph_ai.spell_target", spell_target_identity( *spell_target_at( actor, target ) ) );
    actor.remove_value( "cph_ai.spell_invalidated" );
    actor.remove_value( "cph_ai.spell_completed_step" );
    actor.remove_value( "cph_ai.spell_result" );
    return result( execution_state::running, "native_spell_started" );
}

using transfer_entry = cata::native_item_transfer::selection;

bool select_transfer( Character &source, Character &recipient, const JsonArray &requests,
                      std::vector<transfer_entry> &selected, int &price, std::string &error,
                      bool require_consent, const std::string &source_operation = {} )
{
    std::vector<cata::native_item_transfer::request> items;
    for( const JsonObject row : requests ) {
        items.push_back( { itype_id( row.get_string( "item_type" ) ), row.get_int( "count", 1 ) } );
    }
    const cata::native_item_transfer::item_variable constraint = source_operation.empty() ?
            cata::native_item_transfer::item_variable {} :
            cata::native_item_transfer::item_variable { "cph_ai_produced_step", source_operation };
    return cata::native_item_transfer::select( source, recipient, items, selected, price, error,
    { require_consent, require_consent }, constraint );
}

struct placed_output {
    std::string item_type;
    int count = 0;
    std::string location;
    tripoint_abs_ms position;
};

using output_summary = std::map<std::pair<std::string, std::string>, placed_output>;

void record_output( output_summary &outputs, const item_location &placed, int count )
{
    if( !placed ) {
        return;
    }
    const std::string location = placed.where_recursive() == item_location::type::character ?
                                 "actor" : "ground";
    placed_output &output = outputs[ { placed->typeId().str(), location }];
    output.item_type = placed->typeId().str();
    output.count += count;
    output.location = location;
    output.position = placed.pos_abs();
}

void write_outputs( JsonOut &out, const output_summary &outputs )
{
    out.member( "produced" );
    out.start_array();
    for( const std::pair<const std::pair<std::string, std::string>, placed_output> &entry : outputs ) {
        out.start_object();
        out.member( "item_type", entry.second.item_type );
        out.member( "count", entry.second.count );
        out.member( "location", entry.second.location );
        out.member( "x", entry.second.position.x() );
        out.member( "y", entry.second.position.y() );
        out.member( "z", entry.second.position.z() );
        out.end_object();
    }
    out.end_array();
}

output_summary transfer_selected( std::vector<transfer_entry> &selected, Character &recipient,
                                  const std::string &produced_step = {} )
{
    output_summary outputs;
    const cata::native_item_transfer::item_variable stamp = produced_step.empty() ?
            cata::native_item_transfer::item_variable {} :
            cata::native_item_transfer::item_variable { "cph_ai_produced_step", produced_step };
    for( const transfer_entry &placed : cata::native_item_transfer::commit( selected, recipient,
            stamp ) ) {
        record_output( outputs, placed.location, placed.count );
    }
    return outputs;
}

execution_result exchange( npc &actor, const action_step &step, const JsonObject &args,
                           bool human_confirmed = false )
{
    Character *target = visible_character( actor, args.get_int( "target" ) );
    if( !target || !near( actor, *target ) ) {
        return result( execution_state::failed, "trade_partner_unavailable" );
    }
    const std::string receipt_id = args.get_string( "receipt_id", step.id );
    const std::string key = "trade_receipt." + receipt_id;
    if( value( actor, "trade_rejected" ) == step.id ) {
        return result( execution_state::failed, "player_declined_trade" );
    }
    const std::string previous = value( actor, key );
    if( !previous.empty() ) {
        const bool same = previous == step.args_json &&
                          value( actor, "trade_source." + receipt_id ) == step.source_operation;
        return result( same ? execution_state::succeeded : execution_state::failed,
                       same ? "trade_already_committed" : "receipt_conflict", false,
                       same ? value( actor, "trade_result." + receipt_id ) : "{}" );
    }
    if( target->is_avatar() && !human_confirmed ) {
        actor.set_value( "cph_ai.pending_trade", step.args_json );
        actor.set_value( "cph_ai.pending_trade_id", step.id );
        actor.set_value( "cph_ai.pending_trade_source_operation", step.source_operation );
        return result( execution_state::running, "awaiting_player_trade_confirmation" );
    }
    std::vector<transfer_entry> give;
    std::vector<transfer_entry> take;
    int given_value = 0;
    int taken_value = 0;
    std::string error;
    if( !select_transfer( actor, *target, args.get_array( "give" ), give, given_value, error,
                          !human_confirmed, step.source_operation ) ||
        !select_transfer( *target, actor, args.get_array( "take" ), take, taken_value, error,
                          !human_confirmed ) ) {
        return result( execution_state::failed, error );
    }
    if( give.empty() && take.empty() ) {
        return result( execution_state::failed, "empty_trade" );
    }
    // Evaluate native beneficiaries after real stock and consent selection, even
    // when this offer was accepted earlier or confirmed by the player later.
    if( ( !give.empty() && !permits_item_aid( actor, *target ) ) ||
        ( !take.empty() && !permits_item_aid( actor, actor ) ) ) {
        return result( execution_state::failed, "behavior_disabled" );
    }
    if( !human_confirmed && given_value < taken_value ) {
        return result( execution_state::failed, "native_trade_rejected" );
    }
    transfer_selected( give, *target );
    const output_summary outputs = transfer_selected( take, actor, step.id );
    std::ostringstream details;
    JsonOut out( details );
    out.start_object();
    write_outputs( out, outputs );
    out.end_object();
    actor.set_value( "cph_ai." + key, step.args_json );
    actor.set_value( "cph_ai.trade_source." + receipt_id, step.source_operation );
    actor.set_value( "cph_ai.trade_result." + receipt_id, details.str() );
    actor.remove_value( "cph_ai.pending_trade" );
    actor.remove_value( "cph_ai.pending_trade_id" );
    actor.remove_value( "cph_ai.pending_trade_source_operation" );
    actor.mod_moves( -100 );
    return result( execution_state::succeeded, "trade_committed", true, details.str() );
}

execution_result gather( npc &actor, const action_step &step, const JsonObject &args,
                         bool theft = false )
{
    map &here = get_map();
    const tripoint_bub_ms target = position_arg( args );
    const itype_id id( args.get_string( "item_type" ) );
    const int count = args.get_int( "count", 1 );
    if( !id.is_valid() || count < 1 || count > 1000 || !here.inbounds( target ) ||
        !observes( actor, here, target ) || !here.sees_some_items( target, actor ) ) {
        return result( execution_state::failed, "gather_target_not_observed" );
    }
    std::vector<std::pair<item *, int>> selected;
    int remaining = count;
    for( item &candidate : here.i_at( target ) ) {
        if( remaining == 0 ) {
            break;
        }
        if( candidate.typeId() != id || ( !theft && !candidate.is_owned_by( actor, true ) ) ||
            ( !theft && craft_reservation::contains_reserved_or_live_craft( candidate ) ) ||
            ( !step.source_operation.empty() &&
              candidate.get_var( "cph_ai_produced_step", "" ) != step.source_operation ) ) {
            continue;
        }
        const int amount = std::min( remaining, candidate.count_by_charges() ? candidate.charges : 1 );
        item portion = candidate;
        if( portion.count_by_charges() ) {
            portion.charges = amount;
        }
        if( amount < 1 || !actor.can_pickWeight( portion ) || !actor.can_pickVolume( portion ) ) {
            return result( execution_state::failed, "gather_capacity" );
        }
        selected.emplace_back( &candidate, amount );
        remaining -= amount;
    }
    if( remaining != 0 ) {
        return result( execution_state::failed, step.source_operation.empty() ?
                       "gather_stock_changed" : "source_output_unavailable" );
    }
    std::vector<item> portions;
    for( const std::pair<item *, int> &entry : selected ) {
        item portion = *entry.first;
        if( portion.count_by_charges() ) {
            portion.charges = entry.second;
        }
        portions.push_back( std::move( portion ) );
    }
    if( !NpcExecutionAdapter::can_receive_items( actor, portions ) ) {
        return result( execution_state::failed, "gather_capacity" );
    }
    if( rl_dist( actor.pos_bub(), target ) > 1 ) {
        const execution_result movement = move_towards( actor, target, 1, &step );
        return movement.state == execution_state::succeeded ?
               result( execution_state::running, "approaching_gather_target", movement.consumed_moves ) :
               movement;
    }
    int cost = 0;
    output_summary outputs;
    for( const std::pair<item *, int> &entry : selected ) {
        item transfer = *entry.first;
        if( transfer.count_by_charges() && transfer.charges > entry.second ) {
            transfer.charges = entry.second;
            entry.first->charges -= entry.second;
        } else {
            here.i_rem( target, entry.first );
        }
        transfer.set_owner( actor );
        transfer.set_var( "cph_ai_produced_step", step.id );
        cost += actor.item_handling_cost( transfer );
        const item_location placed = actor.i_add( std::move( transfer ) );
        record_output( outputs, placed, entry.second );
    }
    actor.mod_moves( -std::max( 1, cost ) );
    std::ostringstream details;
    JsonOut out( details );
    out.start_object();
    out.member( "item_type", id.str() );
    out.member( "count", count );
    write_outputs( out, outputs );
    out.end_object();
    return result( execution_state::succeeded, theft ? "items_misappropriated" : "gathered",
                   true, details.str() );
}

execution_result attack( npc &actor, const JsonObject &args )
{
    Creature *target = nullptr;
    if( args.has_int( "target" ) ) {
        target = visible_character( actor, args.get_int( "target" ) );
    } else {
        const tripoint_bub_ms pos = position_arg( args );
        if( get_map().inbounds( pos ) ) {
            monster *candidate = get_creature_tracker().creature_at<monster>( pos );
            if( candidate && candidate->type->id.str() == args.get_string( "monster_type" ) &&
                observes( actor, get_map(), *candidate ) ) {
                target = candidate;
            }
        }
    }
    if( !target || target->is_dead_state() ) {
        return result( execution_state::failed, "attack_target_not_observed" );
    }
    if( rl_dist( actor.pos_bub(), target->pos_bub() ) > 1 ) {
        const execution_result movement = move_towards( actor, target->pos_bub(), 1 );
        return movement.state == execution_state::succeeded ?
               result( execution_state::running, "approaching_attack_target", movement.consumed_moves ) :
               movement;
    }
    const int before = actor.get_moves();
    actor.melee_attack( *target, true );
    return result( execution_state::succeeded, "native_attack", actor.get_moves() < before );
}

execution_result speak( npc &actor, const JsonObject &args, const std::string &code )
{
    if( actor.is_mute() ) {
        return result( execution_state::failed, "speaker_unavailable" );
    }
    const std::string text = args.get_string( "text" );
    if( text.empty() || text.size() > 16384 ) {
        return result( execution_state::failed, "invalid_dialogue_text" );
    }
    std::size_t length = 0;
    for( const unsigned char ch : text ) {
        if( ( ch < 32 && ch != '\n' && ch != '\t' ) || ch == 127 ) {
            return result( execution_state::failed, "invalid_dialogue_text" );
        }
        length += ( ch & 0xc0 ) != 0x80;
    }
    if( length > 4096 ) {
        return result( execution_state::failed, "invalid_dialogue_text" );
    }
    if( args.has_int( "target" ) ) {
        Character *target = visible_character( actor, args.get_int( "target" ) );
        if( !target || !near( actor, *target ) || !target->can_hear( actor.pos_bub(),
                actor.get_shout_volume() ) ) {
            return result( execution_state::failed, "listener_unavailable" );
        }
    }
    actor.say( text );
    actor.mod_moves( -100 );
    actor.set_value( "cph_ai.last_social_action", code );
    return result( execution_state::succeeded, code, true );
}

} // namespace

bool NpcExecutionAdapter::can_receive_items( Character &recipient, const std::vector<item> &items )
{
    return cata::native_item_transfer::can_receive( recipient, items );
}

execution_result NpcExecutionAdapter::validate_spell_cast( npc &actor, const spell_id &id,
        const tripoint_bub_ms &target, bool completing )
{
    if( actor.is_dead_state() || actor.maybe_get_value( "mp_proxy" ) ||
        cata_mp::is_partner_npc( actor.getID() ) ) {
        return result( execution_state::failed, "spell_actor_unavailable" );
    }
    if( completing && value( actor, "spell_invalidated" ) == "true" ) {
        return result( execution_state::failed, "spell_context_changed" );
    }
    if( !id.is_valid() || !actor.magic->knows_spell( id ) ) {
        return result( execution_state::failed, "spell_not_known" );
    }
    const spell &known = actor.magic->get_spell( id );
    const std::string unsupported = spell_support( actor, known );
    if( !unsupported.empty() ) {
        return result( execution_state::failed, unsupported );
    }
    map &here = get_map();
    if( !here.inbounds( target ) ||
        ( target != actor.pos_bub() && !observes( actor, here, target ) ) ) {
        return result( execution_state::failed, "spell_target_not_observed" );
    }
    Creature *recipient = spell_target_at( actor, target );
    if( !recipient || recipient->is_dead_state() ||
        ( recipient != &actor && !observes( actor, here, *recipient ) ) ) {
        return result( execution_state::failed, "spell_target_not_observed" );
    }
    const spell_type &type = id.obj();
    if( type.effect_name == "recover_energy" && recipient != &actor ) {
        return result( execution_state::failed, "npc_unsupported_spell_target" );
    }
    if( !known.is_target_in_range( actor, target ) || !known.is_valid_target( actor, target ) ||
        ( recipient != &actor && ( target.z() != actor.pos_bub().z() ||
                                  !here.sees( actor.pos_bub(), target, known.range( actor ) ) ) ) ) {
        return result( execution_state::failed, "invalid_spell_target" );
    }
    if( !known.has_flag( spell_flag::NO_PROJECTILE ) ) {
        for( const tripoint_bub_ms &point : line_to( actor.pos_bub(), target ) ) {
            if( here.impassable( point ) ) {
                // Native blast projectiles stop short at walls, including transparent ones.
                return result( execution_state::failed, "invalid_spell_target" );
            }
        }
    }
    const std::set<tripoint_bub_ms> area = known.effect_area( actor.pos_bub(), target, actor );
    if( area.size() != 1 || *area.begin() != target ) {
        return result( execution_state::failed, "npc_unsupported_area_effect" );
    }
    const_dialogue context( get_const_talker_for( actor ), nullptr );
    // Check the entire random-damage interval without sampling it during observation.
    const double damage_min = known.min_leveled_damage( actor ) * known.get_eoc_damage_multiplier();
    const double damage_max = type.max_damage.evaluate( context ) * known.get_eoc_damage_multiplier();
    const bool harmful = type.effect_name == "attack" && std::max( damage_min, damage_max ) > 0;
    if( type.effect_name == "recover_energy" && std::min( damage_min, damage_max ) < 0 ) {
        return result( execution_state::failed, "npc_unsupported_self_harm" );
    }
    if( !permits_spell_target( actor, *recipient, harmful ) ) {
        return result( execution_state::failed, "behavior_disabled" );
    }
    const std::string resources = spell_resources( actor, known );
    if( !resources.empty() ) {
        return result( execution_state::failed, resources );
    }
    // The same tile must not silently acquire a different creature during a cast.
    if( completing ) {
        if( value( actor, "spell_target" ).empty() ) {
            return result( execution_state::failed, "spell_context_changed" );
        }
        if( value( actor, "spell_target" ) != spell_target_identity( *recipient ) ) {
            return result( execution_state::failed, "spell_target_changed" );
        }
    }
    return result( execution_state::succeeded, "spell_validated" );
}

bool NpcExecutionAdapter::available( const npc &actor, const std::string &action )
{
    map &here = get_map();
    if( actor.is_dead_state() || !here.inbounds( actor.pos_bub() ) || actor.activity ) {
        return false;
    }
    if( action == "cast_spell" ) {
        if( actor.maybe_get_value( "mp_proxy" ) || cata_mp::is_partner_npc( actor.getID() ) ) {
            return false;
        }
        for( const spell_id &id : actor.magic->spells() ) {
            const spell &known = actor.magic->get_spell( id );
            if( spell_support( actor, known ).empty() && spell_resources( actor, known ).empty() ) {
                return true;
            }
        }
        return false;
    }
    if( action == "move" || action == "wait" || action == "refuse" ||
        action == "argue" || action == "lie_in_dialogue" ||
        action == "propose_own_goals" || action == "false_promise" ) {
        return true;
    }
    if( action == "craft" ) {
        for( const recipe *known : actor.get_learned_recipes() ) {
            if( actor.can_make( known ) && actor.can_start_craft( known,
                    recipe_filter_flags::no_rotten | recipe_filter_flags::no_favorite ) ) {
                return true;
            }
        }
        return false;
    }
    if( action == "leave_group" ) {
        return actor.is_player_ally();
    }
    if( action == "break_commitment" ) {
        return !value( actor, "commitment" ).empty() &&
               value( actor, "commitment_state" ) != "broken";
    }
    if( action == "conceal_information" || action == "disclose_known_information" ) {
        bool known = false;
        try {
            for( const JsonObject record : json_loader::from_string(
                     value( actor, "known_information" ) ).get_array() ) {
                record.allow_omitted_members();
                const std::string kind = record.get_string( "kind", "" );
                known |= ( kind == "statement" || kind == "belief" ) &&
                         !record.get_string( "text", "" ).empty();
            }
        } catch( const std::exception & ) {
            return false;
        }
        if( !known || action == "conceal_information" ) {
            return known;
        }
    }
    if( action == "sabotage" || action == "gather" || action == "misappropriate_items" ) {
        for( const tripoint_bub_ms &pos : here.points_in_radius( actor.pos_bub(),
                action == "sabotage" ? 1 : 12 ) ) {
            if( !here.inbounds( pos ) || !observes( actor, here, pos ) ) {
                continue;
            }
            if( action == "sabotage" && here.is_bashable( pos ) ) {
                return true;
            }
            if( action != "sabotage" && here.sees_some_items( pos, actor ) ) {
                for( const item &candidate : here.i_at( pos ) ) {
                    if( ( action == "misappropriate_items" || candidate.is_owned_by( actor, true ) ) &&
                        ( action == "misappropriate_items" ||
                          !craft_reservation::contains_reserved_or_live_craft( candidate ) ) &&
                        actor.can_pickWeight( candidate ) && actor.can_pickVolume( candidate ) ) {
                        return true;
                    }
                }
            }
        }
        return false;
    }
    if( action == "accept_mission" || action == "complete_mission" || action == "claim_reward" ) {
        for( const mission *task : mission::get_all_active() ) {
            const npc *issuer = g->find_npc( task->get_npc_id() );
            if( !task->supports_npc_assignment() || !issuer || issuer->is_dead_state() ||
                !near( actor, *issuer ) || !observes( actor, here, *issuer ) ) {
                continue;
            }
            if( action == "accept_mission" && !task->is_assigned() &&
                value( actor, "heard_mission." + std::to_string( task->get_id() ) ) ==
                std::to_string( issuer->getID().get_value() ) ) {
                return true;
            }
            if( action == "complete_mission" && task->is_complete( actor, issuer->getID() ) ) {
                return true;
            }
            if( action == "claim_reward" && task->get_assigned_npc_id() == actor.getID() &&
                task->get_status() == mission::mission_status::success && task->npc_reward_remaining() > 0 ) {
                return true;
            }
        }
        return false;
    }
    for( const Creature &creature : g->all_creatures() ) {
        if( &creature == &actor || creature.is_dead_state() || !observes( actor, here, creature ) ) {
            continue;
        }
        const Character *person = creature.as_character();
        if( action == "attack" && ( creature.is_monster() ||
                                    ( person && !person->is_avatar() && !actor.is_ally( *person ) ) ) ) {
            return true;
        }
        if( action == "attack_player" && creature.is_avatar() ) {
            return true;
        }
        if( action == "attack_allies" && person && person->as_npc() && actor.is_ally( *person ) ) {
            return true;
        }
        if( !person || !near( actor, *person ) ) {
            continue;
        }
        if( action == "talk" || action == "trade" || action == "disclose_known_information" ) {
            return true;
        }
        if( action == "transaction_fraud" && person->is_avatar() ) {
            return true;
        }
        if( action == "aid_conflicting_party" && person->as_npc() && person->as_npc()->is_enemy() ) {
            return true;
        }
    }
    return false;
}

std::string NpcExecutionAdapter::observe( const npc &actor )
{
    std::ostringstream data;
    JsonOut out( data );
    map &here = get_map();
    out.start_object();
    out.member( "actor" );
    out.start_object();
    out.member( "id", actor.getID().get_value() );
    out.member( "name", actor.get_name() );
    out.member( "position" );
    write_position( out, actor.pos_abs() );
    out.member( "moves", actor.get_moves() );
    out.member( "hp", actor.get_hp() );
    out.member( "hp_max", actor.get_hp_max() );
    out.member( "stamina", actor.get_stamina() );
    out.member( "stamina_max", actor.get_stamina_max() );
    out.member( "hunger", actor.get_hunger() );
    out.member( "thirst", actor.get_thirst() );
    out.member( "sleepiness", actor.get_sleepiness() );
    out.member( "pain", actor.get_pain() );
    out.member( "strength", actor.get_str() );
    out.member( "dexterity", actor.get_dex() );
    out.member( "intelligence", actor.get_int() );
    out.member( "perception", actor.get_per() );
    out.member( "stored_kcal", actor.get_stored_kcal() );
    out.member( "healthy_kcal", actor.get_healthy_kcal() );
    write_abilities( out, actor );
    out.member( "body" );
    out.start_array();
    int body_count = 0;
    for( const bodypart_id &part : actor.get_all_body_parts() ) {
        if( body_count++ == 128 ) {
            break;
        }
        out.start_object();
        out.member( "part", part.id().str() );
        out.member( "hp", actor.get_hp( part ) );
        out.member( "hp_max", actor.get_hp_max( part ) );
        out.member( "encumbrance", actor.encumb( part ) );
        out.end_object();
    }
    out.end_array();
    out.member( "skills" );
    out.start_array();
    int skill_count = 0;
    for( const std::pair<const skill_id, SkillLevel> &entry : actor.get_all_skills() ) {
        if( skill_count++ == 128 ) {
            break;
        }
        out.start_object();
        out.member( "skill", entry.first.str() );
        out.member( "practical", entry.second.level() );
        out.member( "knowledge", entry.second.knowledgeLevel() );
        out.end_object();
    }
    out.end_array();
    out.member( "inventory" );
    write_inventory( out, actor );
    out.member( "known_recipes" );
    out.start_array();
    std::vector<const recipe *> recipes;
    std::set<const recipe *> craftable;
    for( const recipe *known : actor.get_learned_recipes() ) {
        recipes.push_back( known );
        if( actor.can_make( known ) && actor.can_start_craft( known,
                recipe_filter_flags::no_rotten | recipe_filter_flags::no_favorite ) ) {
            craftable.insert( known );
        }
    }
    std::sort( recipes.begin(), recipes.end(), [&craftable]( const recipe * lhs, const recipe * rhs ) {
        const bool left_ready = craftable.count( lhs ) != 0;
        const bool right_ready = craftable.count( rhs ) != 0;
        return left_ready != right_ready ? left_ready : lhs->ident().str() < rhs->ident().str();
    } );
    if( recipes.size() > 128 ) {
        recipes.resize( 128 );
    }
    int recipe_count = 0;
    for( const recipe *known : recipes ) {
        if( recipe_count++ == 128 ) {
            break;
        }
        out.write( known->ident().str() );
    }
    out.end_array();
    out.member( "craftable_recipes" );
    out.start_array();
    recipe_count = 0;
    for( const recipe *known : recipes ) {
        if( recipe_count >= 128 ) {
            break;
        }
        if( craftable.count( known ) == 0 ) {
            continue;
        }
        ++recipe_count;
        out.start_object();
        out.member( "recipe", known->ident().str() );
        out.member( "item_type", known->result().str() );
        out.end_object();
    }
    out.end_array();
    out.member( "goal", preview( value( actor, "goal" ), 4096 ) );
    out.member( "goal_state", value( actor, "goal_state" ) );
    out.member( "commitment", preview( value( actor, "commitment" ), 4096 ) );
    out.member( "commitment_state", value( actor, "commitment_state" ) );
    out.member( "has_concealed_information", !value( actor, "concealed_information" ).empty() );
    out.end_object();
    out.member( "nearby" );
    out.start_object();
    out.member( "characters" );
    out.start_array();
    int character_count = 0;
    int mission_offer_count = 0;
    int trade_offer_count = 0;
    for( const Creature &creature : g->all_creatures() ) {
        if( &creature == &actor || ( !creature.is_avatar() && !creature.is_npc() ) ||
            !observes( actor, here, creature ) ) {
            continue;
        }
        if( character_count++ == 32 ) {
            break;
        }
        const Character &person = *creature.as_character();
        out.start_object();
        out.member( "id", person.getID().get_value() );
        out.member( "name", person.get_name() );
        out.member( "position" );
        write_position( out, person.pos_abs() );
        if( const npc *other = person.as_npc() ) {
            // Selecting a greeting is public; the NPC's private dialogue state is not.
            out.member( "topic", "TALK_FIRST_TOPIC" );
            out.member( "available_missions" );
            out.start_array();
            if( near( actor, *other ) ) {
                for( const mission *offer : other->chatbin.missions ) {
                    if( mission_offer_count >= 16 ) {
                        break;
                    }
                    if( offer && offer->supports_npc_assignment() && !offer->is_assigned() &&
                        value( actor, "heard_mission." + std::to_string( offer->get_id() ) ) ==
                        std::to_string( other->getID().get_value() ) ) {
                        ++mission_offer_count;
                        out.start_object();
                        out.member( "mission_id", offer->get_id() );
                        out.member( "type", offer->mission_id().str() );
                        out.member( "description", preview( offer->get_description(), 2048 ) );
                        out.end_object();
                    }
                }
            }
            out.end_array();
            out.member( "trade_offers" );
            out.start_array();
            if( near( actor, *other ) && value( actor, "heard_trade." +
                                                std::to_string( other->getID().get_value() ) ) == "true" ) {
                int offered_count = 0;
                npc *seller = g->find_npc( other->getID() );
                const std::vector<item_location> stock_items = seller ? seller->all_items_loc() :
                        std::vector<item_location>();
                for( const item_location &stock : stock_items ) {
                    if( offered_count >= 64 || trade_offer_count >= 128 ) {
                        break;
                    }
                    if( other->is_worn( *stock ) ||
                        !other->wants_to_sell( stock, 1, actor ).success() ) {
                        continue;
                    }
                    ++offered_count;
                    ++trade_offer_count;
                    out.start_object();
                    out.member( "item_type", stock->typeId().str() );
                    out.member( "count", stock->count_by_charges() ? stock->charges : 1 );
                    out.member( "unit_price", npc_trading::adjusted_price( stock.get_item(), 1,
                                actor, *other ) );
                    out.end_object();
                }
            }
            out.end_array();
        }
        out.end_object();
    }
    out.end_array();
    out.member( "monsters" );
    out.start_array();
    int monster_count = 0;
    for( const monster &creature : g->all_monsters() ) {
        if( !observes( actor, here, creature ) ) {
            continue;
        }
        if( monster_count++ == 64 ) {
            break;
        }
        out.start_object();
        out.member( "monster_type", creature.type->id.str() );
        out.member( "name", creature.get_name() );
        out.member( "position" );
        write_position( out, creature.pos_abs() );
        out.end_object();
    }
    out.end_array();
    out.member( "items" );
    out.start_array();
    int item_count = 0;
    for( const tripoint_bub_ms &pos : here.points_in_radius( actor.pos_bub(), 12 ) ) {
        if( item_count >= 128 ) {
            break;
        }
        if( !here.inbounds( pos ) || !observes( actor, here, pos ) ||
            !here.sees_some_items( pos, actor ) ) {
            continue;
        }
        for( const item &it : here.i_at( pos ) ) {
            if( item_count++ >= 128 ) {
                break;
            }
            out.start_object();
            out.member( "item_type", it.typeId().str() );
            out.member( "count", it.count_by_charges() ? it.charges : 1 );
            out.member( "available_to_take", it.is_owned_by( actor, true ) );
            out.member( "position" );
            write_position( out, here.get_abs( pos ) );
            out.end_object();
        }
    }
    out.end_array();
    out.end_object();
    out.member( "missions" );
    out.start_array();
    for( const mission *task : mission::get_all_active() ) {
        if( task->get_assigned_npc_id() != actor.getID() ) {
            continue;
        }
        out.start_object();
        out.member( "mission_id", task->get_id() );
        out.member( "type", task->mission_id().str() );
        out.member( "issuer_id", task->get_npc_id().get_value() );
        out.member( "assignee_id", actor.getID().get_value() );
        out.member( "status", static_cast<int>( task->get_status() ) );
        out.member( "reward_remaining", task->npc_reward_remaining() );
        out.end_object();
    }
    out.end_array();
    out.end_object();
    return data.str();
}

execution_result NpcExecutionAdapter::execute( npc &actor, const action_step &step )
{
    if( !step.requirement_id.empty() && step.action != "refuse" &&
        value( actor, "refused_requirement." + step.requirement_id ) == "true" ) {
        return result( execution_state::failed, "requirement_refused" );
    }
    try {
        if( actor.is_dead_state() ) {
            return result( execution_state::failed, "actor_dead" );
        }
        const JsonObject args = json_loader::from_string( step.args_json ).get_object();
        // The protocol validates the entire action schema before admission;
        // this execution branch intentionally reads only its relevant fields.
        args.allow_omitted_members();
        if( step.action == "cast_spell" ) {
            return cast_spell( actor, step, args );
        }
        if( step.action == "move" ) {
            return move_towards( actor, position_arg( args ), 0, &step );
        }
        if( step.action == "gather" ) {
            return gather( actor, step, args );
        }
        if( step.action == "attack" || step.action == "attack_player" ||
            step.action == "attack_allies" ) {
            if( step.action != "attack" ) {
                Character *target = args.has_int( "target" ) ?
                                    visible_character( actor, args.get_int( "target" ) ) : nullptr;
                if( !target || ( step.action == "attack_player" && !target->is_avatar() ) ||
                    ( step.action == "attack_allies" &&
                      ( !target->as_npc() || !actor.is_ally( *target ) ) ) ) {
                    return result( execution_state::failed, "social_attack_target_mismatch" );
                }
            }
            return attack( actor, args );
        }
        if( step.action == "wait" ) {
            const int turns = args.get_int( "turns", 1 );
            if( turns < 1 || turns > 600 ) {
                return result( execution_state::failed, "invalid_wait_duration" );
            }
            const std::string key = "wait." + step.id;
            const std::string deadline = value( actor, key );
            if( deadline.empty() ) {
                actor.set_value( "cph_ai." + key, std::to_string(
                                     to_turns<int>( calendar::turn - calendar::turn_zero ) + turns ) );
            } else if( to_turns<int>( calendar::turn - calendar::turn_zero ) >= std::stoi( deadline ) ) {
                actor.remove_value( "cph_ai." + key );
                return result( execution_state::succeeded, "wait_complete" );
            }
            actor.mod_moves( -actor.get_moves() );
            return result( execution_state::running, "waiting", true );
        }
        if( step.action == "craft" ) {
            const recipe_id id( args.get_string( "recipe" ) );
            const int batch = args.get_int( "batch", 1 );
            if( !id.is_valid() || batch < 1 || batch > 20 ) {
                return result( execution_state::failed, "invalid_recipe" );
            }
            const std::string active = value( actor, "craft_step" );
            if( active == step.id ) {
                if( actor.activity ) {
                    return result( execution_state::running, "native_craft_activity" );
                }
                actor.remove_value( "cph_ai.craft_step" );
                const bool completed = value( actor, "craft_completed_step" ) == step.id;
                return result( completed ? execution_state::succeeded : execution_state::failed,
                               completed ? "crafted" : "craft_interrupted", false,
                               completed ? value( actor, "craft_result" ) : "{}" );
            }
            if( actor.activity || !actor.has_recipe( &id.obj() ) ) {
                return result( execution_state::failed, "craft_unavailable" );
            }
            actor.set_value( "cph_ai.craft_step", step.id );
            actor.remove_value( "cph_ai.craft_completed_step" );
            actor.remove_value( "cph_ai.craft_result" );
            craft_command command( &id.obj(), batch, false, &actor, std::nullopt );
            if( !command.execute_for_npc() ) {
                actor.remove_value( "cph_ai.craft_step" );
                return result( execution_state::failed, "native_craft_requirements" );
            }
            return result( execution_state::running, "native_craft_started" );
        }
        if( step.action == "trade" || step.action == "transaction_fraud" ) {
            if( step.action == "transaction_fraud" ) {
                Character *target = visible_character( actor, args.get_int( "target" ) );
                if( !target || !target->is_avatar() ) {
                    return result( execution_state::failed, "fraud_requires_human_counterparty" );
                }
                if( value( actor, "pending_trade_id" ) != step.id ) {
                    const execution_result speech = speak( actor, args, "transaction_fraud_offer" );
                    if( speech.state != execution_state::succeeded ) {
                        return speech;
                    }
                }
            }
            return exchange( actor, step, args );
        }
        if( step.action == "accept_mission" || step.action == "complete_mission" ||
            step.action == "claim_reward" ) {
            mission *task = mission::find( args.get_int( "mission_id" ), true );
            if( !task || !task->supports_npc_assignment() ||
                ( args.has_int( "target" ) && task->get_npc_id() != character_id( args.get_int( "target" ) ) ) ) {
                return result( execution_state::failed, "mission_unavailable" );
            }
            bool success = false;
            std::string error = "mission_precondition_changed";
            if( step.action == "accept_mission" ) {
                success = value( actor, "heard_mission." + std::to_string( task->get_id() ) ) ==
                          std::to_string( task->get_npc_id().get_value() ) && task->assign( actor );
            } else if( step.action == "complete_mission" ) {
                success = task->wrap_up( actor );
            } else {
                success = task->claim_npc_reward( actor, itype_id( args.get_string( "item_type" ) ),
                                                  args.get_int( "count", 1 ), args.get_string( "receipt_id", step.id ), error );
            }
            if( success ) {
                actor.mod_moves( -100 );
            }
            return result( success ? execution_state::succeeded : execution_state::failed,
                           success ? step.action + "_committed" : error, success );
        }
        if( step.action == "talk" ) {
            if( !args.has_string( "topic" ) ) {
                return speak( actor, args, "spoken" );
            }
            Character *target = visible_character( actor, args.get_int( "target" ) );
            npc *other = target ? target->as_npc() : nullptr;
            if( !other || !near( actor, *other ) ) {
                return result( execution_state::failed, "dialogue_partner_unavailable" );
            }
            if( actor.is_mute() || other->is_mute() ||
                !actor.can_hear( other->pos_bub(), other->get_shout_volume() ) ||
                !other->can_hear( actor.pos_bub(), actor.get_shout_volume() ) ) {
                return result( execution_state::failed, "listener_unavailable" );
            }
            const std::string requested_topic = args.get_string( "topic" );
            const std::string topic = requested_topic == "TALK_FIRST_TOPIC" ?
                                      other->chatbin.first_topic : requested_topic;
            // Native mission topics have explicit actor-aware effects.  Other topics
            // are spoken using their native line but cannot run avatar-only UI effects.
            dialogue conversation( get_talker_for( actor ), get_talker_for( other ) );
            if( topic == "TALK_TRADE" ) {
                if( args.get_string( "option", "ask" ) != "ask" ) {
                    return result( execution_state::failed, "native_option_unavailable" );
                }
                actor.set_value( "cph_ai.heard_trade." + std::to_string( other->getID().get_value() ),
                                 "true" );
                other->say( _( "Here is what I can offer for trade." ) );
                actor.mod_moves( -100 );
                return result( execution_state::succeeded, "native_trade_offers_heard", true );
            }
            if( topic != other->chatbin.first_topic && topic != "TALK_MISSION_OFFER" &&
                topic != "TALK_MISSION_INQUIRE" ) {
                return result( execution_state::failed, "native_topic_unavailable" );
            }
            if( topic == "TALK_MISSION_OFFER" && !args.has_int( "mission_id" ) ) {
                if( args.get_string( "option", "ask" ) != "ask" ) {
                    return result( execution_state::failed, "native_option_unavailable" );
                }
                int offers = 0;
                for( mission *task : other->chatbin.missions ) {
                    if( offers >= 16 ) {
                        break;
                    }
                    if( task && task->supports_npc_assignment() && !task->is_assigned() ) {
                        ++offers;
                        actor.set_value( "cph_ai.heard_mission." + std::to_string( task->get_id() ),
                                         std::to_string( other->getID().get_value() ) );
                        other->say( task->dialogue_for_topic( "TALK_MISSION_OFFER" ) );
                    }
                }
                actor.mod_moves( -100 );
                return result( execution_state::succeeded, "native_mission_offers_heard", true );
            }
            if( args.has_int( "mission_id" ) ) {
                mission *task = mission::find( args.get_int( "mission_id" ), true );
                if( !task || task->get_npc_id() != other->getID() ) {
                    return result( execution_state::failed, "mission_unavailable" );
                }
                const std::string option = args.get_string( "option", "ask" );
                if( topic == "TALK_MISSION_OFFER" && option == "accept" ) {
                    if( value( actor, "heard_mission." + std::to_string( task->get_id() ) ) !=
                        std::to_string( other->getID().get_value() ) || !task->assign( actor ) ) {
                        return result( execution_state::failed, "mission_precondition_changed" );
                    }
                } else if( topic == "TALK_MISSION_INQUIRE" && option == "deliver" ) {
                    if( !task->wrap_up( actor ) ) {
                        return result( execution_state::failed, "mission_precondition_changed" );
                    }
                } else if( option != "ask" ) {
                    return result( execution_state::failed, "native_option_unavailable" );
                }
            } else if( args.has_string( "option" ) && args.get_string( "option" ) != "ask" ) {
                return result( execution_state::failed, "native_option_unavailable" );
            }
            const std::string line = args.has_int( "mission_id" ) ?
                                     mission::find( args.get_int( "mission_id" ), true )->dialogue_for_topic( topic ) :
                                     conversation.dynamic_line( talk_topic( topic ) );
            if( !line.empty() ) {
                other->say( line );
            }
            actor.mod_moves( -100 );
            return result( execution_state::succeeded, "native_dialogue", true );
        }
        if( step.action == "refuse" ) {
            if( step.requirement_id.empty() ) {
                return result( execution_state::failed, "refusal_requires_requirement" );
            }
            execution_result rejected = speak( actor, args, step.action );
            if( rejected.state == execution_state::succeeded ) {
                actor.set_value( "cph_ai.refused_requirement." + step.requirement_id, "true" );
                rejected.detail_json = "{\"requirement_id\":" + quote( step.requirement_id ) +
                                       ",\"decision\":\"refused\"}";
            }
            return rejected;
        }
        if( step.action == "argue" || step.action == "lie_in_dialogue" ) {
            return speak( actor, args, step.action );
        }
        if( step.action == "propose_own_goals" ) {
            execution_result spoken = speak( actor, args, step.action );
            if( spoken.state == execution_state::succeeded ) {
                actor.set_value( "cph_ai.goal", args.get_string( "text" ) );
                actor.set_value( "cph_ai.goal_state", "proposed" );
                std::ostringstream details;
                JsonOut event( details );
                event.start_object();
                event.member( "kind", "goal" );
                event.member( "text", args.get_string( "text" ) );
                event.member( "status", "proposed" );
                event.end_object();
                spoken.detail_json = details.str();
            }
            return spoken;
        }
        if( step.action == "false_promise" ) {
            const execution_result spoken = speak( actor, args, step.action );
            if( spoken.state == execution_state::succeeded ) {
                actor.set_value( "cph_ai.commitment", args.get_string( "text" ) );
                actor.set_value( "cph_ai.commitment_state", "false_promise" );
            }
            return spoken;
        }
        if( step.action == "break_commitment" ) {
            if( value( actor, "commitment" ).empty() ||
                value( actor, "commitment_state" ) == "broken" ) {
                return result( execution_state::failed, "no_active_commitment" );
            }
            const execution_result spoken = speak( actor, args, step.action );
            if( spoken.state == execution_state::succeeded ) {
                actor.set_value( "cph_ai.commitment_state", "broken" );
                if( value( actor, "goal" ) == value( actor, "commitment" ) ) {
                    actor.set_value( "cph_ai.goal_state", "broken" );
                    actor.remove_value( "cph_ai.goal" );
                }
            }
            return spoken;
        }
        if( step.action == "conceal_information" || step.action == "disclose_known_information" ) {
            const std::string text = args.get_string( "text" );
            if( !knows_information( actor, args ) ) {
                return result( execution_state::failed, "information_not_known" );
            }
            if( step.action == "conceal_information" ) {
                actor.set_value( "cph_ai.concealed_information", text );
                actor.set_value( "cph_ai.last_social_action", step.action );
                actor.mod_moves( -100 );
                return result( execution_state::succeeded, "information_concealed", true );
            }
            if( !args.has_int( "target" ) ) {
                return result( execution_state::failed, "listener_required" );
            }
            return speak( actor, args, "known_information_disclosed" );
        }
        if( step.action == "leave_group" ) {
            if( !actor.is_player_ally() ) {
                return result( execution_state::failed, "already_outside_player_group" );
            }
            talk_function::leave( actor );
            actor.mod_moves( -100 );
            return result( execution_state::succeeded, "left_group", true );
        }
        if( step.action == "aid_conflicting_party" || step.action == "misappropriate_items" ) {
            Character *target = args.has_int( "target" ) ?
                                visible_character( actor, args.get_int( "target" ) ) : nullptr;
            if( step.action == "misappropriate_items" && !target ) {
                return gather( actor, step, args, true );
            }
            if( !target || !near( actor, *target ) ||
                ( step.action == "aid_conflicting_party" && !target->as_npc() ) ) {
                return result( execution_state::failed, "social_target_unavailable" );
            }
            if( step.action == "aid_conflicting_party" &&
                !target->as_npc()->is_enemy() ) {
                return result( execution_state::failed, "party_not_conflicting" );
            }
            if( step.action == "misappropriate_items" &&
                ( target->is_avatar() || value( actor, "heard_trade." +
                                                std::to_string( target->getID().get_value() ) ) != "true" ) ) {
                return result( execution_state::failed, "inventory_theft_requires_observed_npc_stock" );
            }
            std::ostringstream request_data;
            JsonOut request_out( request_data );
            request_out.start_array();
            request_out.start_object();
            request_out.member( "item_type", args.get_string( "item_type" ) );
            request_out.member( "count", args.get_int( "count", 1 ) );
            request_out.end_object();
            request_out.end_array();
            std::vector<transfer_entry> selected;
            int price = 0;
            std::string error;
            Character &source = step.action == "aid_conflicting_party" ? actor : *target;
            Character &recipient = step.action == "aid_conflicting_party" ? *target : actor;
            if( !select_transfer( source, recipient, json_loader::from_string( request_data.str() ).get_array(),
                                  selected, price, error, step.action == "misappropriate_items" ) ) {
                return result( execution_state::failed, error );
            }
            transfer_selected( selected, recipient );
            actor.mod_moves( -100 );
            return result( execution_state::succeeded, step.action + "_committed", true );
        }
        if( step.action == "sabotage" ) {
            const tripoint_bub_ms target = position_arg( args );
            if( !get_map().inbounds( target ) || !observes( actor, get_map(), target ) ||
                rl_dist( actor.pos_bub(), target ) > 1 || !get_map().is_bashable( target ) ) {
                return result( execution_state::failed, "sabotage_target_unavailable" );
            }
            get_map().bash( target, actor.get_str(), false, false, false );
            actor.mod_moves( -100 );
            return result( execution_state::succeeded, "native_sabotage_attempt", true );
        }
        return result( execution_state::failed, "action_not_implemented" );
    } catch( const std::exception & ) {
        return result( execution_state::failed, "invalid_action_arguments" );
    }
}

bool NpcExecutionAdapter::has_native_management( const npc &actor )
{
    if( !value( actor, "pending_trade" ).empty() ) {
        return true;
    }
    for( const mission *task : mission::get_all_active() ) {
        if( task->get_assigned_npc_id() == actor.getID() ) {
            return true;
        }
    }
    return false;
}

execution_result NpcExecutionAdapter::resolve_player_trade( npc &actor, bool accepted )
{
    const std::string offer = value( actor, "pending_trade" );
    const std::string id = value( actor, "pending_trade_id" );
    if( offer.empty() || id.empty() ) {
        return result( execution_state::failed, "no_pending_player_offer" );
    }
    if( !accepted ) {
        actor.remove_value( "cph_ai.pending_trade" );
        actor.set_value( "cph_ai.trade_rejected", id );
        actor.remove_value( "cph_ai.pending_trade_id" );
        actor.remove_value( "cph_ai.pending_trade_source_operation" );
        return result( execution_state::failed, "player_declined_trade" );
    }
    try {
        const action_step step { id, "trade", offer, {},
                                 value( actor, "pending_trade_source_operation" ) };
        const JsonObject args = json_loader::from_string( offer ).get_object();
        args.allow_omitted_members();
        if( args.get_int( "target" ) != get_avatar().getID().get_value() ) {
            return result( execution_state::failed, "player_offer_target_mismatch" );
        }
        return exchange( actor, step, args, true );
    } catch( const std::exception & ) {
        return result( execution_state::failed, "invalid_player_offer" );
    }
}

void NpcExecutionAdapter::open_native_management_menu( npc &actor )
{
    uilist menu;
    menu.text = string_format( _( "%s: tasks and rewards" ), actor.get_name() );
    std::vector<mission *> tasks;
    for( mission *task : mission::get_all_active() ) {
        if( task->get_assigned_npc_id() == actor.getID() ) {
            tasks.push_back( task );
            menu.addentry( static_cast<int>( tasks.size() ) - 1, true, MENU_AUTOASSIGN,
                           string_format( "%s (%d)", task->name(), task->npc_reward_remaining() ) );
        }
    }
    const int trade_index = static_cast<int>( tasks.size() );
    if( !value( actor, "pending_trade" ).empty() ) {
        menu.addentry( trade_index, true, 't', _( "Review this NPC's trade offer" ) );
    }
    menu.query();
    if( menu.ret == trade_index && !value( actor, "pending_trade" ).empty() ) {
        const std::string offer = value( actor, "pending_trade" );
        if( query_yn( _( "Accept this inventory exchange?\n%s" ), offer ) ) {
            const execution_result committed = resolve_player_trade( actor, true );
            popup( "%s", committed.code );
        } else {
            resolve_player_trade( actor, false );
        }
        return;
    }
    if( menu.ret < 0 || menu.ret >= static_cast<int>( tasks.size() ) ) {
        return;
    }
    mission &task = *tasks[menu.ret];
    if( task.in_progress() ) {
        popup( "%s", task.wrap_up( actor ) ? _( "The NPC delivered the medicine." ) :
               _( "The NPC needs medicine and must stand near the mission giver." ) );
        return;
    }
    npc *issuer = g->find_npc( task.get_npc_id() );
    if( !issuer || task.npc_reward_remaining() <= 0 || !near( actor, *issuer ) ) {
        popup( _( "The original mission giver and remaining reward credit are required." ) );
        return;
    }
    uilist reward_menu;
    reward_menu.text = _( "Choose an item from the original giver for this NPC" );
    std::vector<item_location> stock = issuer->all_items_loc();
    for( int i = 0; i < static_cast<int>( stock.size() ); ++i ) {
        reward_menu.addentry( i, issuer->wants_to_sell( stock[i], 1, actor ).success(),
                              MENU_AUTOASSIGN, stock[i]->tname() );
    }
    reward_menu.query();
    if( reward_menu.ret >= 0 && reward_menu.ret < static_cast<int>( stock.size() ) ) {
        std::string error;
        const std::string receipt = "native-ui-" + std::to_string( task.get_id() ) + "-" +
                                    std::to_string( task.npc_reward_remaining() ) + "-" +
                                    stock[reward_menu.ret]->typeId().str();
        if( !task.claim_npc_reward( actor, stock[reward_menu.ret]->typeId(), 1, receipt, error ) ) {
            popup( "%s", error );
        }
    }
}

} // namespace cata::actor_control
