#pragma once
#ifndef CATA_SRC_ACTOR_CONTROL_TYPES_H
#define CATA_SRC_ACTOR_CONTROL_TYPES_H

#include <string>

namespace cata::actor_control
{

enum class execution_state : int {
    running,
    succeeded,
    failed
};

struct action_step {
    std::string id;
    std::string action;
    std::string args_json = "{}";
    std::string intent;
    /** Native output provenance resolved from an accepted preceding receipt. */
    std::string source_operation = {};
    /** Stable native incoming-message identity; never derived from its prose. */
    std::string requirement_id = {};
};

struct execution_result {
    execution_state state = execution_state::failed;
    std::string code;
    std::string detail_json = "{}";
    bool consumed_moves = false;
};

} // namespace cata::actor_control

#endif // CATA_SRC_ACTOR_CONTROL_TYPES_H
