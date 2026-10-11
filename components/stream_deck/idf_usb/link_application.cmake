# ESPHome 2026.9.0 discovers built-ins by SDK directory. This build-local usb
# override is therefore absent from its clean-build src REQUIRES list. Attach
# the public IDF target explicitly, after IDF has created all component targets.
# No SDK edits or cached discovery results are needed. DEFER is available in
# the pinned CMake 3.30.2 toolchain.
function(stream_deck_link_application_usb)
    idf_component_get_property(deck_application src COMPONENT_LIB)
    if(NOT TARGET "${deck_application}" OR NOT TARGET idf::usb)
        message(FATAL_ERROR "Stream Deck requires ESPHome src and IDF usb component targets")
    endif()
    target_link_libraries(${deck_application} PUBLIC idf::usb)
endfunction()

cmake_language(DEFER DIRECTORY "${CMAKE_SOURCE_DIR}" CALL stream_deck_link_application_usb)
