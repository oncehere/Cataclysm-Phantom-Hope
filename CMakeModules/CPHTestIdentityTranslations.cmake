# Compiled resource bootstrap for the unpublished Linux identity test only.
set(CPH_TEST_TRANSLATION_ROOT "" CACHE PATH "Verified bootstrap_translations.py output directory")
if(NOT CPH_TEST_TRANSLATION_ROOT)
    message(FATAL_ERROR "CPH_TEST_IDENTITY requires CPH_TEST_TRANSLATION_ROOT with verified real MO inputs.")
endif()
find_package(Python3 COMPONENTS Interpreter REQUIRED)
execute_process(
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tools/project/bootstrap_translations.py
        --check --output ${CPH_TEST_TRANSLATION_ROOT}
    RESULT_VARIABLE CPH_TRANSLATIONS_RESULT
    OUTPUT_QUIET ERROR_VARIABLE CPH_TRANSLATIONS_ERROR)
if(NOT CPH_TRANSLATIONS_RESULT EQUAL 0)
    message(FATAL_ERROR "CPH translation input validation failed: ${CPH_TRANSLATIONS_ERROR}")
endif()
if(RELEASE)
    if(USE_PREFIX_DATA_DIR)
        set(CPH_TEST_MO_DESTINATION "${CMAKE_INSTALL_DATADIR}/lang/mo")
    else()
        set(CPH_TEST_MO_DESTINATION "lang/mo")
    endif()
    install(DIRECTORY ${CPH_TEST_TRANSLATION_ROOT}/lang/mo/
        DESTINATION ${CPH_TEST_MO_DESTINATION})
    file(READ ${CMAKE_SOURCE_DIR}/project/assets.lock.json CPH_ASSET_LOCK)
    string(JSON CPH_ASSET_COUNT LENGTH "${CPH_ASSET_LOCK}" files)
    math(EXPR CPH_ASSET_LAST "${CPH_ASSET_COUNT} - 1")
    foreach(CPH_ASSET_INDEX RANGE 0 ${CPH_ASSET_LAST})
        string(JSON CPH_ASSET_KIND GET "${CPH_ASSET_LOCK}" files ${CPH_ASSET_INDEX} kind)
        if(CPH_ASSET_KIND STREQUAL "notice")
            string(JSON CPH_ASSET_PATH GET "${CPH_ASSET_LOCK}" files ${CPH_ASSET_INDEX} path)
            get_filename_component(CPH_NOTICE_PARENT "${CPH_ASSET_PATH}" DIRECTORY)
            install(FILES ${CPH_TEST_TRANSLATION_ROOT}/${CPH_ASSET_PATH}
                DESTINATION ${CMAKE_INSTALL_DOCDIR}/translation-inputs/${CPH_NOTICE_PARENT})
        endif()
    endforeach()
endif()
