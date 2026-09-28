#pragma once
#ifndef CATA_SRC_WORLD_ADVANCED_UI_H
#define CATA_SRC_WORLD_ADVANCED_UI_H

#include <string>

class world_advanced_options;

std::string world_advanced_value_label( const world_advanced_options *rules,
                                        const std::string &id );
void edit_world_advanced_rule( world_advanced_options &rules, const std::string &id );
void show_world_advanced_options( world_advanced_options &rules, bool editable );

#endif
