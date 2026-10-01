#pragma once
#ifndef CATA_SRC_ACTOR_CONTROL_PROTOCOL_H
#define CATA_SRC_ACTOR_CONTROL_PROTOCOL_H

#include <string>
#include <vector>

#include "actor_control_types.h"

class JsonValue;

namespace cata::actor_control
{
/** Validate the same bounded schema used by the external runtime. */
bool validate_schema( const JsonValue &value, const JsonValue &schema, std::string &error );
bool parse_plan( const std::string &json, std::vector<action_step> &steps, std::string &error );
std::string quote( const std::string &text );
std::string stringify( const JsonValue &value );
std::string capability_catalog();
bool is_behavior( const std::string &name );
} // namespace cata::actor_control

#endif // CATA_SRC_ACTOR_CONTROL_PROTOCOL_H
