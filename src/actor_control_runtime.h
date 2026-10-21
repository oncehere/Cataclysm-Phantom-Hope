#pragma once
#ifndef CATA_SRC_ACTOR_CONTROL_RUNTIME_H
#define CATA_SRC_ACTOR_CONTROL_RUNTIME_H

#include <filesystem>
#include <string>
#include <vector>

namespace cata::actor_control
{
// These are the editable fields of the existing companion profile, not a
// second configuration format. API keys are deliberately absent.
struct runtime_preferences {
    std::string profile_id;
    int actor_id = -1;
    std::string endpoint;
    std::string model;
    std::string background;
    std::vector<std::string> duties;
    std::vector<std::string> item_types;
    std::vector<std::string> recipes;
    int max_distance = 12;
    std::string configuration;
};

std::filesystem::path runtime_profile_directory( const std::string &profile_id );
bool read_runtime_preferences( const std::string &profile_id, int actor_id,
                               runtime_preferences &result, std::string &error );
bool save_runtime_preferences( const runtime_preferences &value, std::string &error );
bool bundled_runtime_available();
bool managed_runtime_running();
// The caller invokes this only after an explicit player Start command. The
// key enters only this child's environment; never the game environment/files.
bool start_managed_runtime( const std::string &profile_id, const std::string &api_key,
                            std::string &error );
} // namespace cata::actor_control
#endif
