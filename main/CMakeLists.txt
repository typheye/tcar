idf_component_register(SRCS "main.c" "favicon.c"
                    INCLUDE_DIRS "."
                    REQUIRES esp_wifi esp_netif esp_event esp_http_server nvs_flash driver esp_driver_tsens esp_timer esp_driver_ledc)