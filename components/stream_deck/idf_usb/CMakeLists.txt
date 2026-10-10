# Build the pinned IDF USB component with one source-copy patch. The original
# sources retain their Espressif Apache-2.0 headers and are never overwritten.
idf_build_get_property(deck_target IDF_TARGET)
idf_build_get_property(deck_idf IDF_PATH)
set(deck_usb "${deck_idf}/components/usb")
set(deck_patched "${CMAKE_CURRENT_BINARY_DIR}/usbh_stream_deck.c")

if(NOT CMAKE_BUILD_EARLY_EXPANSION)
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
        "${CMAKE_CURRENT_LIST_DIR}/prepare.py"
        "${deck_usb}/usbh.c" "${deck_usb}/usb_host.c"
        "${deck_usb}/Kconfig" "${deck_usb}/CMakeLists.txt"
    )
    if(NOT deck_target STREQUAL "esp32s3")
        message(FATAL_ERROR "Stream Deck USB compatibility component is ESP32-S3 only")
    endif()
    idf_build_get_property(deck_python PYTHON)
    execute_process(
        COMMAND "${deck_python}" "${CMAKE_CURRENT_LIST_DIR}/prepare.py" "${deck_usb}" "${deck_patched}"
        RESULT_VARIABLE deck_patch_result
    )
    if(NOT deck_patch_result EQUAL 0)
        message(FATAL_ERROR "Pinned Stream Deck USB source patch failed")
    endif()
endif()

set(deck_sources "${deck_patched}")
foreach(deck_source hcd_dwc.c enum.c hub.c usb_helpers.c usb_host.c usb_private.c usb_phy.c)
    list(APPEND deck_sources "${deck_usb}/${deck_source}")
endforeach()
if(CONFIG_USB_HOST_HUBS_SUPPORTED)
    list(APPEND deck_sources "${deck_usb}/ext_hub.c" "${deck_usb}/ext_port.c")
endif()
idf_component_register(
    SRCS ${deck_sources}
    INCLUDE_DIRS "${deck_usb}/include"
    PRIV_INCLUDE_DIRS "${deck_usb}/private_include" "."
    PRIV_REQUIRES esp_driver_gpio esp_mm
)
