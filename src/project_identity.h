#pragma once
#ifndef CATA_SRC_PROJECT_IDENTITY_H
#define CATA_SRC_PROJECT_IDENTITY_H

// The CMake-only Linux test identity is not a permanent application identity.
namespace project_identity
{
bool is_test();
const char *data_component();
const char *portable_directory();
const char *test_display_name();
} // namespace project_identity

#endif // CATA_SRC_PROJECT_IDENTITY_H
