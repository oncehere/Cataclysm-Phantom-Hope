#include "cata_catch.h"
#include "cata_imgui.h"
#include "cata_scope_helpers.h"
#include "imgui/imgui.h"

TEST_CASE( "imgui_scroll_end_uses_updated_content_height", "[imgui][scroll]" )
{
    ImGuiContext *previous = ImGui::GetCurrentContext();
    ImGuiContext *context = ImGui::CreateContext();
    on_out_of_scope cleanup( [&]() {
        ImGui::DestroyContext( context );
        ImGui::SetCurrentContext( previous );
    } );
    ImGuiIO &io = ImGui::GetIO();
    io.IniFilename = nullptr;
    io.DisplaySize = ImVec2( 800, 600 );
    io.DeltaTime = 1.0F / 60.0F;
    unsigned char *pixels = nullptr;
    int width = 0;
    int height = 0;
    io.Fonts->GetTexDataAsRGBA32( &pixels, &width, &height );

    const auto frame = [&]( int rows, bool to_end ) {
        ImGui::NewFrame();
        ImGui::SetNextWindowSize( ImVec2( 200, 100 ), ImGuiCond_Always );
        ImGui::Begin( "changing_scroll_content" );
        if( to_end ) {
            cataimgui::scroll action = cataimgui::scroll::end;
            cataimgui::set_scroll( action );
            CHECK( action == cataimgui::scroll::none );
        }
        for( int i = 0; i < rows; ++i ) {
            ImGui::TextUnformatted( "row" );
        }
        ImGui::End();
        ImGui::Render();
    };

    frame( 1, false );
    frame( 80, true );

    ImGui::NewFrame();
    ImGui::SetNextWindowSize( ImVec2( 200, 100 ), ImGuiCond_Always );
    ImGui::Begin( "changing_scroll_content" );
    CHECK( ImGui::GetScrollMaxY() > 0 );
    CHECK( ImGui::GetScrollY() >= ImGui::GetScrollMaxY() - 1.0F );
    ImGui::End();
    ImGui::Render();
}
