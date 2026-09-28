#include <string>

#include "cata_catch.h"
#include "translation_manager_impl.h"

#if defined(LOCALIZE)
TEST_CASE( "world_advanced_supplement_is_discovered_by_normal_translation_loading",
           "[world_advanced][translations]" )
{
    // A separate manager exercises recursive catalog discovery without changing
    // the global interface language or its cached translations.
    TranslationManager manager;
    REQUIRE( manager.GetAvailableLanguages().count( "zh_CN" ) == 1 );
    manager.SetLanguage( "zh_CN" );
    CHECK( std::string( manager.Translate( "Advanced world rules" ) ) == "世界高级规则" );
    CHECK( std::string( manager.Translate( "Temperature offset" ) ) == "环境气温偏移" );
    manager.SetLanguage( "en" );
    CHECK( std::string( manager.Translate( "Advanced world rules" ) ) == "Advanced world rules" );
}
#endif
