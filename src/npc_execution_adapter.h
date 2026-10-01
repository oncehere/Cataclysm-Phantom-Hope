#pragma once
#ifndef CATA_SRC_NPC_EXECUTION_ADAPTER_H
#define CATA_SRC_NPC_EXECUTION_ADAPTER_H

#include <string>
#include <vector>

#include "actor_control_types.h"

class Character;
class item;
class npc;

namespace cata::actor_control
{

/** Native execution seam.  All mutations are made on the normal game thread. */
class NpcExecutionAdapter
{
    public:
        static std::string observe( const npc &actor );
        static bool available( const npc &actor, const std::string &action );
        static execution_result execute( npc &actor, const action_step &step );
        /** Projects native pocket placement for the entire transaction without world mutation. */
        static bool can_receive_items( Character &recipient, const std::vector<item> &items );
        /** Remains available after external control and the MOD are removed. */
        static void open_native_management_menu( npc &actor );
        static bool has_native_management( const npc &actor );
        /** Called only by the human-facing native menu after reviewing the offer. */
        static execution_result resolve_player_trade( npc &actor, bool accepted );
};

} // namespace cata::actor_control

#endif // CATA_SRC_NPC_EXECUTION_ADAPTER_H
