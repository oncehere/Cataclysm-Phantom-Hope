#if defined(TILES)

#include <SDL3/SDL.h>
#include <vector>

#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "input.h"
#include "input_enums.h"
#include "sdl_gamepad.h"

namespace
{
bool dispatch_virtual_gamepad_events( SDL_JoystickID id, Uint32 expected )
{
    SDL_UpdateJoysticks();
    SDL_PumpEvents();
    SDL_Event event;
    std::vector<SDL_Event> other_devices;
    bool seen = false;
    while( SDL_PeepEvents( &event, 1, SDL_GETEVENT,
                           SDL_EVENT_GAMEPAD_AXIS_MOTION, SDL_EVENT_GAMEPAD_REMOVED ) > 0 ) {
        SDL_JoystickID event_id = event.gdevice.which;
        if( event.type == SDL_EVENT_GAMEPAD_AXIS_MOTION ) {
            event_id = event.gaxis.which;
        } else if( event.type == SDL_EVENT_GAMEPAD_BUTTON_DOWN ||
                   event.type == SDL_EVENT_GAMEPAD_BUTTON_UP ) {
            event_id = event.gbutton.which;
        }
        if( event_id != id ) {
            other_devices.push_back( event );
            continue;
        }
        seen = seen || event.type == expected;
        REQUIRE( gamepad::is_gamepad_event( event ) );
        gamepad::handle_event( event );
    }
    for( SDL_Event &other : other_devices ) {
        CHECK( SDL_PushEvent( &other ) );
    }
    return seen;
}
} // namespace

TEST_CASE( "sdl3_virtual_gamepad_maps_input_and_hotplug", "[tiles][gamepad][input][sdl3]" )
{
    REQUIRE_FALSE( gamepad::is_active() );
    REQUIRE( SDL_Init( SDL_INIT_GAMEPAD ) );
    const input_event saved_input = last_input;
    SDL_JoystickID id = 0;
    SDL_Joystick *joystick = nullptr;
    bool attached = false;
    on_out_of_scope cleanup( [&]() {
        gamepad::set_raw_input_mode( false );
        gamepad::quit();
        if( joystick ) {
            SDL_CloseJoystick( joystick );
        }
        if( attached ) {
            SDL_DetachVirtualJoystick( id );
        }
        SDL_QuitSubSystem( SDL_INIT_GAMEPAD );
        last_input = saved_input;
    } );

    SDL_VirtualJoystickDesc desc;
    SDL_INIT_INTERFACE( &desc );
    desc.type = SDL_JOYSTICK_TYPE_GAMEPAD;
    desc.naxes = SDL_GAMEPAD_AXIS_COUNT;
    desc.nbuttons = SDL_GAMEPAD_BUTTON_COUNT;
    desc.axis_mask = ( 1U << SDL_GAMEPAD_AXIS_COUNT ) - 1;
    desc.button_mask = ( 1U << SDL_GAMEPAD_BUTTON_COUNT ) - 1;
    desc.name = "CPH SDL3 regression gamepad";
    id = SDL_AttachVirtualJoystick( &desc );
    REQUIRE( id != 0 );
    attached = true;
    REQUIRE( SDL_IsGamepad( id ) );
    joystick = SDL_OpenJoystick( id );
    REQUIRE( joystick != nullptr );
    REQUIRE( SDL_SetJoystickVirtualAxis( joystick, SDL_GAMEPAD_AXIS_LEFT_TRIGGER,
                                         SDL_JOYSTICK_AXIS_MIN ) );
    REQUIRE( SDL_SetJoystickVirtualAxis( joystick, SDL_GAMEPAD_AXIS_RIGHT_TRIGGER,
                                         SDL_JOYSTICK_AXIS_MIN ) );
    REQUIRE( dispatch_virtual_gamepad_events( id, SDL_EVENT_GAMEPAD_ADDED ) );
    REQUIRE( gamepad::is_active() );
    gamepad::set_raw_input_mode( true );

    REQUIRE( SDL_SetJoystickVirtualButton( joystick, SDL_GAMEPAD_BUTTON_SOUTH, true ) );
    REQUIRE( dispatch_virtual_gamepad_events( id, SDL_EVENT_GAMEPAD_BUTTON_DOWN ) );
    CHECK( last_input.type == input_event_t::gamepad );
    CHECK( last_input.get_first_input() == JOY_A );
    REQUIRE( SDL_SetJoystickVirtualButton( joystick, SDL_GAMEPAD_BUTTON_SOUTH, false ) );
    CHECK( dispatch_virtual_gamepad_events( id, SDL_EVENT_GAMEPAD_BUTTON_UP ) );

    REQUIRE( SDL_SetJoystickVirtualAxis( joystick, SDL_GAMEPAD_AXIS_LEFTX, 28000 ) );
    REQUIRE( SDL_SetJoystickVirtualAxis( joystick, SDL_GAMEPAD_AXIS_LEFTY, -28000 ) );
    REQUIRE( dispatch_virtual_gamepad_events( id, SDL_EVENT_GAMEPAD_AXIS_MOTION ) );
    CHECK( gamepad::get_left_stick_direction() == gamepad::direction::NE );
    CHECK( last_input.get_first_input() == JOY_LS_UP_RIGHT );
    REQUIRE( SDL_SetJoystickVirtualAxis( joystick, SDL_GAMEPAD_AXIS_LEFTX, 0 ) );
    REQUIRE( SDL_SetJoystickVirtualAxis( joystick, SDL_GAMEPAD_AXIS_LEFTY, 0 ) );
    REQUIRE( dispatch_virtual_gamepad_events( id, SDL_EVENT_GAMEPAD_AXIS_MOTION ) );
    CHECK( gamepad::get_left_stick_direction() == gamepad::direction::NONE );

    REQUIRE( SDL_SetJoystickVirtualAxis( joystick, SDL_GAMEPAD_AXIS_RIGHT_TRIGGER,
                                         SDL_JOYSTICK_AXIS_MAX ) );
    REQUIRE( dispatch_virtual_gamepad_events( id, SDL_EVENT_GAMEPAD_AXIS_MOTION ) );
    CHECK( last_input.get_first_input() == JOY_RT );
    REQUIRE( SDL_SetJoystickVirtualAxis( joystick, SDL_GAMEPAD_AXIS_RIGHT_TRIGGER,
                                         SDL_JOYSTICK_AXIS_MIN ) );
    REQUIRE( dispatch_virtual_gamepad_events( id, SDL_EVENT_GAMEPAD_AXIS_MOTION ) );

    REQUIRE( SDL_DetachVirtualJoystick( id ) );
    attached = false;
    REQUIRE( dispatch_virtual_gamepad_events( id, SDL_EVENT_GAMEPAD_REMOVED ) );
    CHECK_FALSE( gamepad::is_active() );
}

#endif // TILES
