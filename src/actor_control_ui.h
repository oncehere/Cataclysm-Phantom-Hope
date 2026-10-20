#pragma once
#ifndef CATA_SRC_ACTOR_CONTROL_UI_H
#define CATA_SRC_ACTOR_CONTROL_UI_H

#include <string>

class JsonObject;

namespace cata::actor_control
{
// Player-facing rendering deliberately excludes private task/debug state.
std::string player_status_text( const JsonObject &value, bool runtime_running );
bool diagnostics_available( const JsonObject &value );
void open_menu();
} // namespace cata::actor_control

#endif // CATA_SRC_ACTOR_CONTROL_UI_H
