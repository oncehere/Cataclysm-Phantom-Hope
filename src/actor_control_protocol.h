#pragma once
#ifndef CATA_SRC_ACTOR_CONTROL_PROTOCOL_H
#define CATA_SRC_ACTOR_CONTROL_PROTOCOL_H

#include <string>
#include <vector>

#include "actor_control_types.h"

class JsonObject;
class JsonValue;

namespace cata::actor_control
{
/** Validate the same bounded schema used by the external runtime. */
bool validate_schema( const JsonValue &value, const JsonValue &schema, std::string &error );
bool parse_plan( const std::string &json, std::vector<action_step> &steps, std::string &error );
/** Validate a task offer; actor identity and durable dependency admission remain native. */
bool parse_tasks( const std::string &json, std::string &error );
/** Validate ordinary status queries and bounded, transient worker reports. */
bool parse_status_parameters( const std::string &json, std::string &error );
std::string quote( const std::string &text );
std::string stringify( const JsonValue &value );
std::string stringify( const JsonObject &object );
std::string capability_catalog();
std::string task_capability_catalog();
bool is_behavior( const std::string &name );
} // namespace cata::actor_control

#endif // CATA_SRC_ACTOR_CONTROL_PROTOCOL_H
