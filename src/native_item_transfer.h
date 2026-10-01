#pragma once
#ifndef CATA_SRC_NATIVE_ITEM_TRANSFER_H
#define CATA_SRC_NATIVE_ITEM_TRANSFER_H

#include <string>
#include <vector>

#include "item_location.h"
#include "type_id.h"

class Character;
class item;

namespace cata::native_item_transfer
{
struct request {
    itype_id type;
    int count = 1;
};

struct selection {
    item_location location;
    int count;
};

struct consent {
    bool seller = false;
    bool buyer = false;
};

struct item_variable {
    std::string name;
    std::string value;
};

/** Reserves pocket space for the entire batch without changing native inventory. */
bool can_receive( Character &recipient, const std::vector<item> &items );

/** Selects actual transferable stock. All checks finish before any mutation. */
bool select( Character &source, Character &recipient, const std::vector<request> &requests,
             std::vector<selection> &selected, int &price, std::string &error,
             consent required, const item_variable &constraint = {} );

/** Game-thread commit. Call only after every leg of a transaction was selected. */
std::vector<selection> commit( std::vector<selection> &selected, Character &recipient,
                               const item_variable &stamp = {} );
} // namespace cata::native_item_transfer

#endif // CATA_SRC_NATIVE_ITEM_TRANSFER_H
