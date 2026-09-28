#pragma once
#ifndef CATA_SRC_WORLD_ADVANCED_OPTIONS_H
#define CATA_SRC_WORLD_ADVANCED_OPTIONS_H

#include <cstddef>
#include <map>
#include <optional>
#include <string>
#include <vector>

#include "options.h"
#include "translation.h"

class cata_path;
class JsonObject;
class JsonOut;

enum class world_advanced_target : int {
    external,
    region,
    climate
};

enum class world_advanced_type : int {
    boolean,
    integer,
    number,
    text
};

/** Menu limits apply only to explicit overrides, never to inherited mod data. */
struct world_advanced_definition {
    std::string id;
    world_advanced_target target;
    world_advanced_type type;
    translation name;
    translation group;
    translation help;
    translation unit;
    std::string default_value;
    double minimum = 0;
    double maximum = 0;
    double step = 1;

    options_manager::cOpt make_copt() const;
};

const std::vector<world_advanced_definition> &world_advanced_definitions();
const world_advanced_definition *find_world_advanced_definition( const std::string &id );
bool validate_world_advanced_scalar( const std::string &id, const std::string &value,
                                     std::string &error );

/** Sparse world-local choices.  An absent key always means inherit content defaults. */
class world_advanced_options
{
    public:
        world_advanced_options() = default;
        world_advanced_options( const world_advanced_options & ) = default;
        world_advanced_options( world_advanced_options && ) = default;
        world_advanced_options &operator=( const world_advanced_options &other );
        world_advanced_options &operator=( world_advanced_options &&other );
        bool set( const std::string &id, const std::string &value, std::string &error );
        void erase( const std::string &id );
        void clear();
        std::optional<std::string> find( const std::string &id ) const;
        bool empty() const;
        const std::map<std::string, std::string> &values() const;
        std::size_t revision() const;

        /** Cross-field validation; individual edits may temporarily be inconsistent. */
        bool validate( std::string &error ) const;
        void serialize( JsonOut &out ) const;
        void deserialize( const JsonObject &obj );
        /** Full file paths.  A missing file loads an empty set successfully. */
        bool save( const cata_path &file_path ) const;
        bool load( const cata_path &file_path );

    private:
        std::map<std::string, std::string> values_;
        std::size_t revision_ = 0;
};

void set_active_world_advanced_options( const world_advanced_options *options );
const world_advanced_options *active_world_advanced_options();
std::size_t world_advanced_options_revision();
std::optional<std::string> get_world_advanced_value( const std::string &id );
double world_advanced_number( const std::string &id, double fallback );
bool world_advanced_bool( const std::string &id, bool fallback );

#endif // CATA_SRC_WORLD_ADVANCED_OPTIONS_H
