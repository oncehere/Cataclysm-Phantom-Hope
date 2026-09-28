set(VERSION_HEADER "${CMAKE_SOURCE_DIR}/src/version.h")
if(EXISTS "${VERSION_HEADER}")
    file(READ "${VERSION_HEADER}" VERSION_H)
endif()

if(DEFINED GIT_BINARY)
    set(GIT_EXECUTABLE "${GIT_BINARY}")
else()
    find_package(Git QUIET)
endif()

# Source archives must not inherit the identity of an enclosing repository.
if(NOT GIT_EXECUTABLE OR NOT EXISTS "${CMAKE_SOURCE_DIR}/.git")
    if(NOT VERSION_H MATCHES "(^|\n)[ \t]*#define VERSION \"[^\"\n]+\"")
        file(WRITE "${VERSION_HEADER}"
            "// NOLINT(cata-header-guard)\n#define VERSION \"NULL\"\n")
    endif()
    return()
endif()

# Let Git resolve ordinary checkouts, submodules and absolute worktree gitdirs.
execute_process(COMMAND "${GIT_EXECUTABLE}" rev-parse --verify HEAD
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    RESULT_VARIABLE GIT_RESULT
    OUTPUT_VARIABLE _sha1
    ERROR_VARIABLE GIT_ERROR
    OUTPUT_STRIP_TRAILING_WHITESPACE)
if(NOT GIT_RESULT STREQUAL "0" OR NOT _sha1 MATCHES "^[0-9a-f]+$")
    message(FATAL_ERROR "Git HEAD lookup failed: ${GIT_ERROR} (${GIT_RESULT})")
endif()

execute_process(COMMAND "${GIT_EXECUTABLE}" describe
    --tags --always --match "cdda-*" "${_sha1}"
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    RESULT_VARIABLE GIT_RESULT
    OUTPUT_VARIABLE GIT_VERSION
    ERROR_VARIABLE GIT_ERROR
    OUTPUT_STRIP_TRAILING_WHITESPACE)
if(NOT GIT_RESULT STREQUAL "0" OR NOT GIT_VERSION)
    message(FATAL_ERROR "Git describe failed: ${GIT_ERROR} (${GIT_RESULT})")
endif()

execute_process(COMMAND "${GIT_EXECUTABLE}" -c core.safecrlf=false
    diff --quiet --no-ext-diff --no-textconv "${_sha1}" --
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    RESULT_VARIABLE DIRTY_FLAG
    ERROR_VARIABLE GIT_ERROR)
if(DIRTY_FLAG STREQUAL "1")
    string(APPEND GIT_VERSION "-dirty")
elseif(NOT DIRTY_FLAG STREQUAL "0")
    message(FATAL_ERROR "Git dirty check failed: ${GIT_ERROR} (${DIRTY_FLAG})")
endif()

string(TIMESTAMP BUILD_DATE "%Y-%m-%d")
string(PREPEND GIT_VERSION "${BUILD_DATE}-")
message(NOTICE "${GIT_VERSION}")
set(EXPECTED_HEADER "// NOLINT(cata-header-guard)\n#define VERSION \"${GIT_VERSION}\"\n")
if(NOT VERSION_H STREQUAL EXPECTED_HEADER)
    file(WRITE "${VERSION_HEADER}" "${EXPECTED_HEADER}")
endif()

string(TIMESTAMP _timestamp %Y-%m-%d-%H%M)
file(WRITE "${CMAKE_SOURCE_DIR}/VERSION.txt" "\
build type: Release\n\
build number: ${_timestamp}\n\
commit sha: ${_sha1}\n\
commit url: https://github.com/CleverRaven/Cataclysm-DDA/commit/${_sha1}"
)
