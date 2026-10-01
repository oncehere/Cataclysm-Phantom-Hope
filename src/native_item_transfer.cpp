#include "native_item_transfer.h"

#include <algorithm>
#include <climits>
#include <map>
#include <utility>

#include "character.h"
#include "character_attire.h"
#include "item.h"
#include "item_pocket.h"
#include "npc.h"
#include "npctrade.h"

namespace cata::native_item_transfer
{
bool can_receive( Character &recipient, const std::vector<item> &items )
{
    outfit projected_worn = recipient.worn;
    const item_location held = recipient.get_wielded_item();
    item projected_weapon = held ? *held : item();
    units::mass incoming = 0_gram;
    for( const item &portion : items ) {
        incoming += portion.weight();
        if( incoming > recipient.free_weight_capacity() ||
            incoming > recipient.weight_capacity() - recipient.weight_carried() ) {
            return false;
        }
        item_location weapon_location( recipient, &projected_weapon );
        std::pair<item_location, item_pocket *> selected =
            projected_weapon.best_pocket( portion, weapon_location, nullptr, false, true );
        projected_worn.best_pocket( recipient, portion, nullptr, selected, true );
        if( !selected.second ) {
            return false;
        }
        item *placed = nullptr;
        selected.second->add( portion, &placed );
        if( !placed ) {
            return false;
        }
        selected.second->on_contents_changed();
    }
    return true;
}

bool select( Character &source, Character &recipient, const std::vector<request> &requests,
             std::vector<selection> &selected, int &price, std::string &error,
             consent required, const item_variable &constraint )
{
    std::map<itype_id, int> counts;
    for( const request &entry : requests ) {
        if( entry.count < 1 || entry.count > 1000 || !entry.type.is_valid() ||
            ( counts.size() >= 32 && counts.count( entry.type ) == 0 ) ||
            counts[entry.type] > 1000 - entry.count ) {
            error = "invalid_item_request";
            return false;
        }
        counts[entry.type] += entry.count;
    }
    std::vector<selection> stock;
    int total = 0;
    std::vector<item> portions;
    for( const std::pair<const itype_id, int> &requested : counts ) {
        int remaining = requested.second;
        for( item_location location : source.all_items_loc() ) {
            if( remaining == 0 ) {
                break;
            }
            if( location->typeId() != requested.first || source.is_worn( *location ) ||
                ( location->is_container() && !location->empty() ) ||
                ( !constraint.name.empty() && location->get_var( constraint.name, "" ) !=
                  constraint.value ) ||
                ( required.seller && source.is_npc() &&
                  !source.as_npc()->wants_to_sell( location, 1, recipient ).success() ) ||
                ( required.buyer && recipient.is_npc() &&
                  !recipient.as_npc()->wants_to_buy( *location, 1, source ).success() ) ) {
                continue;
            }
            const int count = std::min( remaining, location->count_by_charges() ? location->charges : 1 );
            if( count < 1 ) {
                continue;
            }
            item portion = *location;
            if( portion.count_by_charges() ) {
                portion.charges = count;
            }
            if( !recipient.can_pickWeight( portion ) || !recipient.can_pickVolume( portion ) ) {
                error = "recipient_capacity";
                return false;
            }
            const int cost = std::max( 1, npc_trading::adjusted_price( location.get_item(), count,
                                       recipient, source ) );
            if( cost > INT_MAX - total ) {
                error = "trade_value_exceeded";
                return false;
            }
            total += cost;
            stock.push_back( { location, count } );
            portions.push_back( std::move( portion ) );
            remaining -= count;
        }
        if( remaining != 0 ) {
            error = constraint.name.empty() ? "inventory_or_consent_changed" : "source_output_unavailable";
            return false;
        }
    }
    if( !can_receive( recipient, portions ) ) {
        error = "recipient_capacity";
        return false;
    }
    selected = std::move( stock );
    price = total;
    return true;
}

std::vector<selection> commit( std::vector<selection> &selected, Character &recipient,
                               const item_variable &stamp )
{
    std::vector<selection> placed;
    for( selection &entry : selected ) {
        item transfer = *entry.location;
        if( transfer.count_by_charges() && transfer.charges > entry.count ) {
            transfer.charges = entry.count;
            entry.location->charges -= entry.count;
        } else {
            entry.location.remove_item();
        }
        transfer.set_owner( recipient );
        if( !stamp.name.empty() ) {
            transfer.set_var( stamp.name, stamp.value );
        }
        placed.push_back( { recipient.i_add( std::move( transfer ) ), entry.count } );
    }
    return placed;
}
} // namespace cata::native_item_transfer
