#include "project_identity.h"

bool project_identity::is_test()
{
#if defined(CPH_TEST_IDENTITY) && defined(__linux__) && !defined(__ANDROID__)
    return true;
#else
    return false;
#endif
}

const char *project_identity::data_component()
{
    return is_test() ? "cph-isolation-test" : "cataclysm-dda";
}

const char *project_identity::portable_directory()
{
    return is_test() ? "./cph-isolation-test" : ".";
}

const char *project_identity::test_display_name()
{
    return "CPH Isolation Test";
}
