#include "cata_imgui.h"

#if defined(TILES) && !defined(TUI)

#include <cfloat>
#include <initializer_list>
#include <memory>
#include <string>
#include <vector>

#include "cata_catch.h"
#include "cata_scope_helpers.h"
#include "imgui/imgui.h"
#include "imgui/imgui_internal.h"
#include "sdl_geometry.h"
#include "sdl_renderer_recovery.h"
#include "sdl_wrappers.h"
#include "sdltiles.h"

namespace
{
class sdl_input_probe_window : public cataimgui::window
{
    public:
        sdl_input_probe_window() : window( "SDL input coordinate probe",
                                               ImGuiWindowFlags_NoTitleBar ) {}
        ImRect button;
        bool hovered = false;
        int activations = 0;

    protected:
        cataimgui::bounds get_bounds() override {
            const ImVec2 size = ImGui::GetIO().DisplaySize;
            return { 0, 0, size.x, size.y };
        }

        void draw_controls() override {
            const ImVec2 size = ImGui::GetIO().DisplaySize;
            ImGui::SetCursorPos( ImVec2( size.x * 0.75F, size.y * 0.75F ) );
            if( ImGui::Button( "Choose", ImVec2( 90, 36 ) ) ) {
                ++activations;
            }
            hovered = ImGui::IsItemHovered();
            button = ImRect( ImGui::GetItemRectMin(), ImGui::GetItemRectMax() );
        }
};

void run_sdl_input_frame( cataimgui::client &client, sdl_input_probe_window &window,
                          int buffer_w, int buffer_h, const std::vector<std::string> &errors )
{
    client.new_frame( buffer_w, buffer_h );
    window.draw();
    client.abort_frame();
    std::string diagnostics;
    for( const std::string &error : errors ) {
        diagnostics += error + "\n";
    }
    INFO( diagnostics );
    REQUIRE( errors.empty() );
    CHECK( ImGui::GetCurrentContext()->ErrorCountCurrentFrame == 0 );
}

void process_window_mouse_event( cataimgui::client &client, Uint32 type,
                                 const ImVec2 &buffer_point, int scale, int buffer_w, int buffer_h )
{
    SDL_Event event = {};
    event.type = type;
    if( type == SDL_EVENT_MOUSE_MOTION ) {
        event.motion.windowID = SDL_GetWindowID( get_sdl_window() );
        event.motion.x = buffer_point.x * scale;
        event.motion.y = buffer_point.y * scale;
    } else {
        event.button.windowID = SDL_GetWindowID( get_sdl_window() );
        event.button.button = SDL_BUTTON_LEFT;
        event.button.down = type == SDL_EVENT_MOUSE_BUTTON_DOWN;
        event.button.x = buffer_point.x * scale;
        event.button.y = buffer_point.y * scale;
    }
    // Use the exact production polling boundary: window coordinates are mapped
    // once, then process_input must forward them to the real SDL3 backend.
    convert_event_to_display_buffer_coords( &event );
    client.process_input( &event, buffer_w, buffer_h, scale );
}
} // namespace

TEST_CASE( "imgui_sdl3_scaled_mouse_reaches_lower_right_button",
           "[tiles][imgui][input][mouse][sdl3]" )
{
    ImGuiContext *previous = ImGui::GetCurrentContext();
    software_render_fixture renderer;
    // A missing backend must fail this integration check, not look like PASS.
    REQUIRE( renderer.available() );
    SDL_Window_Ptr borrowed_window( get_sdl_window() );
    on_out_of_scope restore_context_and_window( [&]() {
        borrowed_window.release();
        ImGui::SetCurrentContext( previous );
    } );
    // The client owns its new context; retain the previous one for cleanup.
    ImGui::SetCurrentContext( nullptr );
    GeometryRenderer_Ptr geometry = std::make_unique<DefaultGeometryRenderer>();

    for( const int scale : {
             1, 2, 4
         } ) {
        CAPTURE( scale );
        renderer_recovery_test_support::set_scaling_and_resize_window(
            scale, 800 * scale, 480 * scale );
        renderer_coordinator.drain_pending();
        REQUIRE( renderer_coordinator.is_render_allowed() );
        int buffer_w = 0;
        int buffer_h = 0;
        get_display_buffer_dims( &buffer_w, &buffer_h );
        REQUIRE( buffer_w == 800 );
        REQUIRE( buffer_h == 480 );

        std::vector<std::string> errors;
        cataimgui::client client( get_sdl_renderer(), borrowed_window, geometry );
        ImGuiContext *context = ImGui::GetCurrentContext();
        context->ErrorCallbackUserData = &errors;
        context->ErrorCallback = []( ImGuiContext *, void *data, const char *message ) {
            static_cast<std::vector<std::string> *>( data )->emplace_back( message );
        };
        ImGuiIO &io = ImGui::GetIO();
        // Match the production GUI/mono font slots even though this simple
        // probe only uses the default GUI font.
        io.Fonts->AddFontDefault();
        io.Fonts->AddFontDefault();
        unsigned char *pixels = nullptr;
        int atlas_w = 0;
        int atlas_h = 0;
        io.Fonts->GetTexDataAsRGBA32( &pixels, &atlas_w, &atlas_h );
        sdl_input_probe_window window;
        run_sdl_input_frame( client, window, buffer_w, buffer_h, errors );
        run_sdl_input_frame( client, window, buffer_w, buffer_h, errors );
        const ImVec2 target = window.button.GetCenter();
        REQUIRE( target.x > buffer_w * 0.5F );
        REQUIRE( target.y > buffer_h * 0.5F );

        process_window_mouse_event( client, SDL_EVENT_MOUSE_MOTION, target, scale, buffer_w, buffer_h );
        run_sdl_input_frame( client, window, buffer_w, buffer_h, errors );
        CHECK( io.MousePos.x == Approx( target.x ).margin( 1.0F ) );
        CHECK( io.MousePos.y == Approx( target.y ).margin( 1.0F ) );
        REQUIRE( window.hovered );
        process_window_mouse_event( client, SDL_EVENT_MOUSE_BUTTON_DOWN, target, scale,
                                    buffer_w, buffer_h );
        run_sdl_input_frame( client, window, buffer_w, buffer_h, errors );
        CHECK( window.activations == 0 );
        process_window_mouse_event( client, SDL_EVENT_MOUSE_BUTTON_UP, target, scale,
                                    buffer_w, buffer_h );
        run_sdl_input_frame( client, window, buffer_w, buffer_h, errors );
        CHECK( window.activations == 1 );

        // NewFrame also queues the real SDL3 backend's no-pointer sentinel.
        // It must survive tail normalization without float-to-int conversion.
        SDL_Event leave = {};
        leave.type = SDL_EVENT_WINDOW_MOUSE_LEAVE;
        leave.window.windowID = SDL_GetWindowID( get_sdl_window() );
        client.process_input( &leave, buffer_w, buffer_h, scale );
        run_sdl_input_frame( client, window, buffer_w, buffer_h, errors );
        CHECK( io.MousePos.x == -FLT_MAX );
        CHECK( io.MousePos.y == -FLT_MAX );
        CHECK_FALSE( window.hovered );
    }
}

#endif // TILES && !TUI
