#if defined(CATA_ENABLE_LUA_PLATFORM) && CATA_ENABLE_LUA_PLATFORM

#include <functional>
#include <memory>

#include "cata_catch.h"
#include "lua_platform_sol.h"

TEST_CASE( "lua_platform_same_signature_callbacks_destroy_their_own_captures",
           "[lua][platform][callbacks][gc]" )
{
    std::weak_ptr<int> first_observer;
    std::weak_ptr<int> second_observer;
    std::weak_ptr<int> third_observer;
    {
        sol::state lua;
        {
            const auto first = std::make_shared<int>( 1 );
            const auto second = std::make_shared<int>( 2 );
            const auto third = std::make_shared<int>( 3 );
            first_observer = first;
            second_observer = second;
            third_observer = third;
            const std::function<int()> read_first = [first]() {
                return *first;
            };
            const std::function<int()> read_second = [second]() {
                return *second;
            };
            const std::function<int()> read_third = [third]() {
                return *third;
            };
            auto larger = [read_first, read_second, read_third]( sol::this_state ) {
                return read_first() + read_second() + read_third();
            };
            auto smaller = [read_first]( sol::this_state ) {
                return read_first();
            };
            using large_functor = sol::function_detail::functor_function<decltype( larger ), false, true>;
            using small_functor = sol::function_detail::functor_function<decltype( smaller ), false, true>;
            // Check before binding so a regression fails without an unsafe Lua teardown.
            REQUIRE( sol::usertype_traits<large_functor>::user_gc_metatable() !=
                     sol::usertype_traits<small_functor>::user_gc_metatable() );
            lua.set_function( "larger", larger );
            lua.set_function( "smaller", smaller );
        }
        REQUIRE_FALSE( first_observer.expired() );
        REQUIRE_FALSE( second_observer.expired() );
        REQUIRE_FALSE( third_observer.expired() );
        REQUIRE( lua.get<sol::function>( "larger" ).call<int>() == 6 );
        REQUIRE( lua.get<sol::function>( "smaller" ).call<int>() == 1 );

        SECTION( "garbage_collection_releases_only_the_removed_callback" ) {
            lua["larger"] = sol::nil;
            lua.collect_garbage();
            CHECK_FALSE( first_observer.expired() );
            CHECK( second_observer.expired() );
            CHECK( third_observer.expired() );
            REQUIRE( lua.get<sol::function>( "smaller" ).call<int>() == 1 );
            lua["smaller"] = sol::nil;
            lua.collect_garbage();
            CHECK( first_observer.expired() );
        }
        SECTION( "closing_the_state_releases_both_callbacks" ) {
            // Keep both callbacks alive until lua_close invokes their destructors.
        }
    }
    CHECK( first_observer.expired() );
    CHECK( second_observer.expired() );
    CHECK( third_observer.expired() );
}

#endif
