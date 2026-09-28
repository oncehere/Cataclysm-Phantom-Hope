#pragma once
#ifndef CATA_SRC_WORLD_ADVANCED_RUNTIME_H
#define CATA_SRC_WORLD_ADVANCED_RUNTIME_H

#include <string>

// Called after selected core/mod content is loaded, before generating a world.
bool validate_active_world_advanced_options( std::string &error );

#endif
