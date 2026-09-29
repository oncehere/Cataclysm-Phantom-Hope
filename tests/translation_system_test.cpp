#include <algorithm>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "filesystem.h"
#include "path_info.h"
#include "string_formatter.h"
#include "translation_document.h"
#include "translation_manager_impl.h"
#include "translations.h"

#if defined(LOCALIZE)

// A small MO fixture keeps catalog-discovery tests independent of installed
// languages and of an external msgfmt process at test runtime.
static void write_priority_catalog( const std::filesystem::path &path,
                                    const std::string &prefix, bool fallback )
{
    std::vector<std::pair<std::string, std::string>> messages = {
        {
            "", "Content-Type: text/plain; charset=UTF-8;\n"
            "Plural-Forms: nplurals=2; plural=n!=1;\n"
        },
        { "shared", prefix + " shared" },
        { "item\004shared", prefix + " context" },
        { std::string( "unit" ) + '\0' + "units", prefix + " unit" + '\0' + prefix + " units" },
        {
            std::string( "item\004unit" ) + '\0' + "units",
            prefix + " context unit" + '\0' + prefix + " context units"
        }
    };
    if( fallback ) {
        messages.emplace_back( "base only", "base fallback" );
    }
    std::sort( messages.begin(), messages.end() );
    std::filesystem::create_directories( path.parent_path() );
    std::ofstream output( path, std::ios::binary );
    REQUIRE( output.is_open() );
    const auto write_u32 = [&output]( std::uint32_t value ) {
        for( int i = 0; i < 4; ++i ) {
            output.put( static_cast<char>( value & 0xff ) );
            value >>= 8;
        }
    };
    const std::uint32_t count = static_cast<std::uint32_t>( messages.size() );
    for( const std::uint32_t value : {
             0x950412deU, 0U, count, 28U, 28U + count * 8, 0U, 0U
         } ) {
        write_u32( value );
    }
    std::uint32_t offset = 28 + count * 16;
    for( const bool originals : {
             true, false
         } ) {
        for( const std::pair<std::string, std::string> &message : messages ) {
            const std::string &text = originals ? message.first : message.second;
            write_u32( static_cast<std::uint32_t>( text.size() ) );
            write_u32( offset );
            offset += static_cast<std::uint32_t>( text.size() ) + 1;
        }
    }
    for( const bool originals : {
             true, false
         } ) {
        for( const std::pair<std::string, std::string> &message : messages ) {
            output << ( originals ? message.first : message.second ) << '\0';
        }
    }
    output.close();
    REQUIRE( output.good() );
}

TEST_CASE( "TranslationManager_discovers_maintained_catalog_priority",
           "[translations][translation_priority]" )
{
    const std::string language = "cph_priority_test";
    const std::filesystem::path core = std::filesystem::u8path( locale_dir() );
    const std::filesystem::path base = core / language;
    const std::filesystem::path maintained = core / "cph" / language;
    const std::filesystem::path user = std::filesystem::u8path( PATH_INFO::user_moddir() ) /
                                       "cph_translation_priority_test";
    // Never replace existing files, even when an earlier interrupted run left a
    // fixture behind. Each cleanup is limited to a directory created here.
    REQUIRE_FALSE( std::filesystem::exists( base ) );
    REQUIRE_FALSE( std::filesystem::exists( maintained ) );
    REQUIRE_FALSE( std::filesystem::exists( user ) );
    on_out_of_scope cleanup( [&]() {
        std::filesystem::remove_all( user );
        std::filesystem::remove_all( maintained );
        std::filesystem::remove_all( base );
    } );
    write_priority_catalog( base / "LC_MESSAGES/cataclysm-dda.mo", "base", true );
    write_priority_catalog( maintained / "LC_MESSAGES/cataclysm-dda.mo", "maintained", false );
    std::string expected = "maintained";

    SECTION( "maintained overrides base" ) {
    }
    SECTION( "user mods retain priority" ) {
        write_priority_catalog( user / language / "LC_MESSAGES/priority.mo", "user", false );
        expected = "user";
    }
    SECTION( "base works without maintained catalog" ) {
        std::filesystem::remove_all( maintained );
        expected = "base";
    }

    TranslationManager manager;
    REQUIRE( manager.GetAvailableLanguages().count( language ) == 1 );
    manager.SetLanguage( language );
    CHECK( std::string( manager.Translate( "shared" ) ) == expected + " shared" );
    CHECK( manager.TranslateWithContext( "item", "shared" ) == expected + " context" );
    CHECK( manager.TranslatePlural( "unit", "units", 1 ) == expected + " unit" );
    CHECK( manager.TranslatePlural( "unit", "units", 2 ) == expected + " units" );
    CHECK( manager.TranslatePluralWithContext( "item", "unit", "units", 1 ) ==
           expected + " context unit" );
    CHECK( manager.TranslatePluralWithContext( "item", "unit", "units", 2 ) ==
           expected + " context units" );
    CHECK( std::string( manager.Translate( "base only" ) ) == "base fallback" );
    CHECK( std::string( manager.Translate( "missing" ) ) == "missing" );
    manager.SetLanguage( "en" );
    CHECK( std::string( manager.Translate( "shared" ) ) == "shared" );
}

static void LoadMODocument( const char *path )
{
    volatile TranslationDocument document( path );
}

TEST_CASE( "TranslationDocument_loads_valid_MO", "[translations]" )
{
    const char *path = "./data/mods/TEST_DATA/lang/mo/ru/LC_MESSAGES/TEST_DATA.mo";
    CAPTURE( path );
    REQUIRE( file_exist( std::filesystem::u8path( path ) ) );
    REQUIRE_NOTHROW( LoadMODocument( path ) );
}

TEST_CASE( "TranslationDocument_rejects_invalid_MO", "[translations]" )
{
    const char *path = "./data/mods/TEST_DATA/lang/mo/ru/LC_MESSAGES/INVALID_RAND.mo";
    CAPTURE( path );
    REQUIRE( file_exist( std::filesystem::u8path( path ) ) );
    REQUIRE_THROWS_AS( LoadMODocument( path ), InvalidTranslationDocumentException );
}

TEST_CASE( "TranslationDocument_loads_all_core_MO", "[translations]" )
{
    const std::unordered_set<std::string> languages =
        TranslationManager::GetInstance().GetAvailableLanguages();
    for( const std::string &lang : languages ) {
        const std::string path = string_format( "./lang/mo/%s/LC_MESSAGES/cataclysm-dda.mo", lang );
        CAPTURE( path );
        REQUIRE( file_exist( path ) );
        REQUIRE_NOTHROW( LoadMODocument( path.c_str() ) );
    }
}

TEST_CASE( "No_string_buffer_overlap_in_TranslationDocument", "[translations]" )
{
    const std::unordered_set<std::string> languages =
        TranslationManager::GetInstance().GetAvailableLanguages();
    for( const std::string &lang : languages ) {
        const std::string path = string_format( "./lang/mo/%s/LC_MESSAGES/cataclysm-dda.mo", lang );
        CAPTURE( path );
        REQUIRE( file_exist( path ) );
        TranslationDocument document( path );
        // The following code walks through every string contained in the MO document
        // So AddressSanitizer can also detect memory access violation if there is any
        const std::size_t n = document.Count();
        const char *last_ending = nullptr;
        for( std::size_t i = 0; i < n; i++ ) {
            const char *str = document.GetOriginalString( i );
            CHECK( last_ending < str );
            last_ending = str + std::strlen( str );
        }
        last_ending = nullptr;
        for( std::size_t i = 0; i < n; i++ ) {
            const char *str = document.GetTranslatedString( i );
            CHECK( last_ending < str );
            last_ending = str + std::strlen( str );
        }
    }
}

BENCHMARK_TEST_CASE( "TranslationDocument_loading_benchmark", "[translations]" )
{
    BENCHMARK( "Load Russian" ) {
        return TranslationDocument( "./lang/mo/ru/LC_MESSAGES/cataclysm-dda.mo" );
    };
}

BENCHMARK_TEST_CASE( "TranslationManager_loading_benchmark", "[translations]" )
{
    BENCHMARK( "Load Russian" ) {
        TranslationManager manager;
        manager.LoadDocuments( std::vector<std::string> {"./lang/mo/ru/LC_MESSAGES/cataclysm-dda.mo"} );
        return manager.Translate( "battery" );
    };
}

BENCHMARK_TEST_CASE( "TranslationManager_translate_benchmark", "[translations]" )
{
    TranslationManager manager;

    // Russian
    REQUIRE( file_exist( std::filesystem::u8path( "./lang/mo/ru/LC_MESSAGES/cataclysm-dda.mo" ) ) );
    manager.LoadDocuments( std::vector<std::string> {"./lang/mo/ru/LC_MESSAGES/cataclysm-dda.mo"} );
    REQUIRE( strcmp( manager.Translate( "battery" ), "battery" ) != 0 );
    BENCHMARK( "Russian" ) {
        return manager.Translate( "battery" );
    };

    // Chinese
    REQUIRE( file_exist( std::filesystem::u8path( "./lang/mo/zh_CN/LC_MESSAGES/cataclysm-dda.mo" ) ) );
    manager.LoadDocuments( std::vector<std::string> {"./lang/mo/zh_CN/LC_MESSAGES/cataclysm-dda.mo"} );
    REQUIRE( strcmp( manager.Translate( "battery" ), "battery" ) != 0 );
    BENCHMARK( "Chinese" ) {
        return manager.Translate( "battery" );
    };

    // English
    manager.LoadDocuments( std::vector<std::string>() );
    REQUIRE( strcmp( manager.Translate( "battery" ), "battery" ) == 0 );
    BENCHMARK( "English" ) {
        return manager.Translate( "battery" );
    };
}

TEST_CASE( "TranslationManager_translates_message", "[translations]" )
{
    std::vector<std::string> files{"./data/mods/TEST_DATA/lang/mo/ru/LC_MESSAGES/TEST_DATA.mo"};
    TranslationManager manager;
    manager.LoadDocuments( files );
    std::string translated = manager.Translate( "battery" );
    CHECK( translated == "батарейка" );
}

TEST_CASE( "TranslationManager_returns_untranslated_message_as_is", "[translations]" )
{
    std::vector<std::string> files{"./data/mods/TEST_DATA/lang/mo/ru/LC_MESSAGES/TEST_DATA.mo"};
    TranslationManager manager;
    manager.LoadDocuments( files );
    const char *message = "__UnTrAnSlAtEd!!!__#";
    std::string translated = manager.Translate( message );
    CHECK( translated == message );
}

TEST_CASE( "TranslationManager_returns_empty_string_as_is", "[translations]" )
{
    std::vector<std::string> files{"./data/mods/TEST_DATA/lang/mo/ru/LC_MESSAGES/TEST_DATA.mo"};
    TranslationManager manager;
    manager.LoadDocuments( files );
    std::string translated = manager.Translate( "" );
    CHECK( translated.empty() );
}

TEST_CASE( "TranslationManager_translates_message_with_context", "[translations]" )
{
    std::vector<std::string> files{"./data/mods/TEST_DATA/lang/mo/ru/LC_MESSAGES/TEST_DATA.mo"};
    TranslationManager manager;
    manager.LoadDocuments( files );
    std::string translated_weapon_pike = manager.TranslateWithContext( "weapon", "pike" );
    CHECK( translated_weapon_pike == "пика" );
    std::string translated_fish_pike = manager.TranslateWithContext( "fish", "pike" );
    CHECK( translated_fish_pike == "щука" );
    std::string untranslated_unknown_pike = manager.TranslateWithContext( "!@#$", "pike" );
    CHECK( untranslated_unknown_pike == "pike" );
}

static void CheckPluralEvaluation( const TranslationPluralRulesEvaluator &evaluator,
                                   const std::function<std::size_t( std::size_t )> &ground_truth )
{
    for( std::size_t n = 0; n < 200; n++ ) {
        CHECK( evaluator.Evaluate( n ) == ground_truth( n ) );
    }
}

TEST_CASE( "TranslationPluralRulesEvaluator", "[translations]" )
{
    SECTION( "Arabic" ) {
        auto arabic_ground_truth = []( std::size_t n ) {
            return n == 0 ? 0 : n == 1 ? 1 : n == 2 ? 2 : n % 100 >= 3 && n % 100 <= 10 ? 3 : n % 100 >= 11 &&
                   n % 100 <= 99 ? 4 : 5;
        };
        const std::string arabic_rules =
            // NOLINTNEXTLINE(cata-text-style)
            "Plural-Forms: nplurals=6; plural=n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 && n%100<=99 ? 4 : 5;";
        TranslationPluralRulesEvaluator arabic_evaluator( arabic_rules );
        CheckPluralEvaluation( arabic_evaluator, arabic_ground_truth );
    }
    SECTION( "CJK" ) {
        auto cjk_ground_truth = []( std::size_t ) {
            return 0;
        };
        // NOLINTNEXTLINE(cata-text-style)
        const std::string cjk_rules = "Plural-Forms: nplurals=1; plural=0;";
        TranslationPluralRulesEvaluator cjk_evaluator( cjk_rules );
        CheckPluralEvaluation( cjk_evaluator, cjk_ground_truth );
    }
    SECTION( "Spanish" ) {
        auto spanish_ground_truth = []( std::size_t n ) {
            return n != 1;
        };
        // NOLINTNEXTLINE(cata-text-style)
        const std::string spanish_rules = "Plural-Forms: nplurals=2; plural=(n != 1);";
        TranslationPluralRulesEvaluator spanish_evaluator( spanish_rules );
        CheckPluralEvaluation( spanish_evaluator, spanish_ground_truth );
    }
    SECTION( "Russian" ) {
        auto russian_ground_truth = []( std::size_t n ) {
            return n % 10 == 1 && n % 100 != 11 ? 0 : n % 10 >= 2 && n % 10 <= 4 && ( n % 100 < 12 ||
                    n % 100 > 14 ) ? 1 : n % 10 == 0 || ( n % 10 >= 5 && n % 10 <= 9 ) || ( n % 100 >= 11 &&
                            n % 100 <= 14 ) ? 2 : 3;
        };
        const std::string russian_rules =
            // NOLINTNEXTLINE(cata-text-style)
            "Plural-Forms: nplurals=4; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<12 || n%100>14) ? 1 : n%10==0 || (n%10>=5 && n%10<=9) || (n%100>=11 && n%100<=14)? 2 : 3);";
        TranslationPluralRulesEvaluator russian_evaluator( russian_rules );
        CheckPluralEvaluation( russian_evaluator, russian_ground_truth );
    }
}

TEST_CASE( "TranslationManager_translates_plural_messages", "[translations]" )
{
    SECTION( "English" ) {
        std::vector<std::string> files;
        TranslationManager manager;
        manager.LoadDocuments( files );
        std::string translated_0_battery = manager.TranslatePlural( "battery", "batteries", 0 );
        CHECK( translated_0_battery == "batteries" );
        std::string translated_1_battery = manager.TranslatePlural( "battery", "batteries", 1 );
        CHECK( translated_1_battery == "battery" );
        std::string translated_2_battery = manager.TranslatePlural( "battery", "batteries", 2 );
        CHECK( translated_2_battery == "batteries" );
        std::string translated_3_battery = manager.TranslatePlural( "battery", "batteries", 3 );
        CHECK( translated_3_battery == "batteries" );
        std::string translated_4_battery = manager.TranslatePlural( "battery", "batteries", 4 );
        CHECK( translated_4_battery == "batteries" );
    }

    SECTION( "Russian" ) {
        std::vector<std::string> files{"./data/mods/TEST_DATA/lang/mo/ru/LC_MESSAGES/TEST_DATA.mo"};
        TranslationManager manager;
        manager.LoadDocuments( files );
        std::string translated_0_battery = manager.TranslatePlural( "battery", "batteries", 0 );
        CHECK( translated_0_battery == "батареек" );
        std::string translated_1_battery = manager.TranslatePlural( "battery", "batteries", 1 );
        CHECK( translated_1_battery == "батарейка" );
        std::string translated_2_battery = manager.TranslatePlural( "battery", "batteries", 2 );
        CHECK( translated_2_battery == "батарейки" );
        std::string translated_3_battery = manager.TranslatePlural( "battery", "batteries", 3 );
        CHECK( translated_3_battery == "батарейки" );
        std::string translated_4_battery = manager.TranslatePlural( "battery", "batteries", 4 );
        CHECK( translated_4_battery == "батарейки" );
    }
}

BENCHMARK_TEST_CASE( "TranslationPluralRulesEvaluatorPerformance", "[translations]" )
{
    TranslationManager manager;
    // Use the test catalog: release translation catalogs evolve independently
    // and are not guaranteed to keep this exact source string or translation.
    manager.LoadDocuments( std::vector<std::string> {
        "./data/mods/TEST_DATA/lang/mo/ru/LC_MESSAGES/TEST_DATA.mo"
    } );
    REQUIRE( strcmp( manager.TranslatePlural( "battery", "batteries", 1 ),
                     "батарейка" ) == 0 );
    BENCHMARK( "Russian plural rules evaluation" ) {
        return manager.TranslatePlural( "battery", "batteries", 1 );
    };
    manager.LoadDocuments( std::vector<std::string>() );
    REQUIRE( strcmp( manager.TranslatePlural( "battery", "batteries", 1 ), "battery" ) == 0 );
    BENCHMARK( "English plural rules evaluation" ) {
        return manager.TranslatePlural( "battery", "batteries", 1 );
    };
    manager.LoadDocuments( std::vector<std::string> {"./lang/mo/zh_CN/LC_MESSAGES/cataclysm-dda.mo"} );
    REQUIRE( strcmp( manager.TranslatePlural( "battery", "batteries", 1 ), "电池" ) == 0 );
    BENCHMARK( "Chinese plural rules evaluation" ) {
        return manager.TranslatePlural( "battery", "batteries", 1 );
    };
}

#endif
