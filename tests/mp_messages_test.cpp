#if defined(CPH_MP_REAL_MESSAGES_TEST)
#include <string>
#include <vector>

#include "calendar.h"
#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "messages.h"
#include "options.h"

TEST_CASE( "mp_real_message_watermark_survives_the_display_limit_and_clear",
           "[multiplayer][messages]" )
{
    const std::string old_limit = get_options().get_option( "MESSAGE_LIMIT" ).getValue();
    const on_out_of_scope restore_limit( [&old_limit]() {
        get_options().get_option( "MESSAGE_LIMIT" ).setValue( old_limit );
    } );
    get_options().get_option( "MESSAGE_LIMIT" ).setValue( "3" );
    Messages::clear_messages();
    const unsigned long long start = Messages::appended_total();
    for( int i = 0; i < 8; ++i ) {
        Messages::add_msg( "MP retained message " + std::to_string( i ) );
    }
    // The existing log trims before append, retaining limit + 1 entries.
    CHECK( Messages::size() == 4 );
    CHECK( Messages::appended_total() == start + 8 );

    const unsigned long long watermark = Messages::appended_total();
    Messages::add_msg( "MP after the ring filled" );
    const auto recent = Messages::recent_messages(
                            static_cast<size_t>( Messages::appended_total() - watermark ) );
    REQUIRE( recent.size() == 1 );
    CHECK( recent.front().second == "MP after the ring filled" );
    Messages::clear_messages();
    CHECK( Messages::size() == 0 );
    CHECK( Messages::appended_total() == watermark + 1 );
    Messages::add_msg( "MP after clear" );
    CHECK( Messages::appended_total() == watermark + 2 );
}
#endif
