# CPH's maintained messages supplement the verified upstream catalogs.  The
# runtime recursively discovers LC_MESSAGES directories, so no base MO is edited.
if(NOT GETTEXT_MSGFMT_EXECUTABLE)
    message(FATAL_ERROR "CPH translations require gettext msgfmt when LOCALIZE is enabled.")
endif()

file(GLOB CPH_TRANSLATION_SOURCES CONFIGURE_DEPENDS "${CMAKE_SOURCE_DIR}/lang/cph/*.po")
set(CPH_TRANSLATION_OUTPUTS)
foreach(CPH_PO IN LISTS CPH_TRANSLATION_SOURCES)
    get_filename_component(CPH_LANGUAGE "${CPH_PO}" NAME_WE)
    set(CPH_MO_DIR "${CMAKE_SOURCE_DIR}/lang/mo/cph/${CPH_LANGUAGE}/LC_MESSAGES")
    set(CPH_MO "${CPH_MO_DIR}/cataclysm-dda.mo")
    add_custom_command(
        OUTPUT "${CPH_MO}"
        COMMAND ${CMAKE_COMMAND} -E make_directory "${CPH_MO_DIR}"
        COMMAND "${GETTEXT_MSGFMT_EXECUTABLE}" -c -o "${CPH_MO}" "${CPH_PO}"
        DEPENDS "${CPH_PO}"
        VERBATIM)
    list(APPEND CPH_TRANSLATION_OUTPUTS "${CPH_MO}")
endforeach()
add_custom_target(cph_translations ALL DEPENDS ${CPH_TRANSLATION_OUTPUTS})

if(RELEASE)
    if(CPH_TEST_IDENTITY AND USE_PREFIX_DATA_DIR)
        install(DIRECTORY "${CMAKE_SOURCE_DIR}/lang/mo/cph"
            DESTINATION "${CMAKE_INSTALL_DATADIR}/lang/mo")
    elseif(USE_PREFIX_DATA_DIR)
        install(DIRECTORY "${CMAKE_SOURCE_DIR}/lang/mo/cph" TYPE LOCALE)
    else()
        install(DIRECTORY "${CMAKE_SOURCE_DIR}/lang/mo/cph" DESTINATION lang/mo)
    endif()
endif()
