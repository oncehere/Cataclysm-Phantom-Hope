#include <list>
#include <optional>

#include "avatar.h"
#include "cata_catch.h"
#include "character_attire.h"
#include "coordinates.h"
#include "item.h"
#include "item_location.h"
#include "map.h"
#include "map_helpers.h"
#include "map_selector.h"
#include "player_helpers.h"
#include "point.h"
#include "type_id.h"

TEST_CASE( "EOC_wear_event_removes_the_garment", "[eoc][wear][cdda_adaptation]" )
{
    clear_avatar();
    clear_map_without_vision();
    avatar &u = get_avatar();
    u.remove_value( "test_wear_event_removed" );
    map &here = get_map();
    const tripoint_bub_ms spot = u.pos_bub() + tripoint::east;
    const itype_id socks_id( "test_vanishing_socks" );
    item &socks = here.add_item_or_charges( spot, item( socks_id ) );
    const std::optional<std::list<item>::iterator> worn =
        u.wear( item_location( map_cursor( spot ), &socks ), false );
    CHECK( u.get_value( "test_wear_event_removed" ) == "yes" );
    REQUIRE( worn.has_value() );
    CHECK( *worn == u.worn.position_to_wear_new_item( item( socks_id ) ) );
    CHECK_FALSE( u.is_wearing( socks_id ) );
    CHECK_FALSE( u.has_amount( socks_id, 1 ) );
    CHECK( here.i_at( spot ).empty() );
}
