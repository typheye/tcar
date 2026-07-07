file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/generated")
idf_component_register(SRCS "main.c" "route.c" "webui.c" "favicon.c"
                    INCLUDE_DIRS "${CMAKE_CURRENT_LIST_DIR}/include" "${CMAKE_CURRENT_BINARY_DIR}/generated"
                    REQUIRES esp_wifi esp_netif esp_event esp_http_server nvs_flash esp_driver_gpio esp_driver_tsens esp_timer esp_driver_ledc)

find_program(POWERSHELL_EXE powershell REQUIRED)
set(STATIC_DIR "${CMAKE_CURRENT_LIST_DIR}/static")
set(GENERATED_WEB_UI "${CMAKE_CURRENT_BINARY_DIR}/generated/web_ui.h")
add_custom_command(
    OUTPUT "${GENERATED_WEB_UI}"
    COMMAND ${POWERSHELL_EXE} -NoProfile -ExecutionPolicy Bypass -File "${CMAKE_SOURCE_DIR}/scripts/embed_static.ps1" "${STATIC_DIR}" "${GENERATED_WEB_UI}"
    DEPENDS "${CMAKE_SOURCE_DIR}/scripts/embed_static.ps1" "${STATIC_DIR}/index.html" "${STATIC_DIR}/style.css" "${STATIC_DIR}/app.js"
    VERBATIM)
add_custom_target(generate_web_ui DEPENDS "${GENERATED_WEB_UI}")
add_dependencies(${COMPONENT_LIB} generate_web_ui)

