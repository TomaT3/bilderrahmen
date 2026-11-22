if(NOT EXISTS "${CMAKE_CURRENT_LIST_DIR}/secrets.h")
    message(FATAL_ERROR "firmware/main/secrets.h fehlt: secrets.example.h kopieren und ausfüllen")
endif()

idf_component_register(
    SRCS "main.c" "epd.c" "pmic.c" "fetch.c"
    INCLUDE_DIRS "."
    PRIV_REQUIRES esp_driver_spi esp_driver_gpio esp_driver_i2c esp_wifi esp_netif esp_event
                  esp_http_client esp-tls mbedtls nvs_flash esp_timer esp_hw_support esp_app_format
)
