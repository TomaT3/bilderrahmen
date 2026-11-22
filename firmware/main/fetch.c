#include "fetch.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

#include <esp_app_desc.h>
#include <esp_crt_bundle.h>
#include <esp_event.h>
#include <esp_heap_caps.h>
#include <esp_http_client.h>
#include <esp_log.h>
#include <esp_netif.h>
#include <esp_wifi.h>
#include <freertos/FreeRTOS.h>
#include <freertos/event_groups.h>
#include <mbedtls/base64.h>

#include "board.h"
#include "secrets.h"

static const char *TAG = "fetch";
static EventGroupHandle_t s_wifi_events;
#define WIFI_UP BIT0
#define WIFI_TIMEOUT_MS 20000

static void on_wifi(void *arg, esp_event_base_t base, int32_t id, void *data) {
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        esp_wifi_connect();  // bis zum Timeout weiter versuchen
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        xEventGroupSetBits(s_wifi_events, WIFI_UP);
    }
}

bool wifi_connect(int *rssi) {
    s_wifi_events = xEventGroupCreate();
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_wifi, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_wifi, NULL));
    wifi_config_t cfg = {0};
    strlcpy((char *) cfg.sta.ssid, WIFI_SSID, sizeof(cfg.sta.ssid));
    strlcpy((char *) cfg.sta.password, WIFI_PASSWORD, sizeof(cfg.sta.password));
    cfg.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &cfg));
    ESP_ERROR_CHECK(esp_wifi_start());

    EventBits_t bits = xEventGroupWaitBits(s_wifi_events, WIFI_UP, pdFALSE, pdTRUE, pdMS_TO_TICKS(WIFI_TIMEOUT_MS));
    if (!(bits & WIFI_UP)) {
        ESP_LOGE(TAG, "Kein WLAN nach %d s", WIFI_TIMEOUT_MS / 1000);
        return false;
    }
    wifi_ap_record_t ap;
    *rssi = esp_wifi_sta_get_ap_info(&ap) == ESP_OK ? ap.rssi : 0;
    ESP_LOGI(TAG, "WLAN verbunden, RSSI %d", *rssi);
    return true;
}

void wifi_stop(void) {
    esp_wifi_disconnect();
    esp_wifi_stop();
}

static esp_err_t on_http(esp_http_client_event_t *evt) {
    fetch_out_t *out = evt->user_data;
    if (evt->event_id != HTTP_EVENT_ON_HEADER) return ESP_OK;
    if (strcasecmp(evt->header_key, "X-Sleep-Seconds") == 0) {
        out->sleep_s = (uint32_t) strtoul(evt->header_value, NULL, 10);
    } else if (strcasecmp(evt->header_key, "ETag") == 0) {
        strlcpy(out->etag, evt->header_value, sizeof(out->etag));
    }
    return ESP_OK;
}

fetch_result_t fetch_image(const char *etag, uint16_t battery_mv, int rssi, const char *wakeup, fetch_out_t *out) {
    memset(out, 0, sizeof(*out));
    esp_http_client_config_t cfg = {
        .url = FRAME_BASE_URL "/frame/" FRAME_ID "/image.bin",
        .crt_bundle_attach = esp_crt_bundle_attach,
        .event_handler = on_http,
        .user_data = out,
        .timeout_ms = 30000,
        .buffer_size = 4096,
    };
    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (!client) return FETCH_ERROR;

    // Basic Auth selbst setzen, damit es schon beim ersten Request mitgeht
    const char *cred = FRAME_ID ":" FRAME_PASSWORD;
    unsigned char b64[160];
    size_t b64_len = 0;
    char header[200];
    if (mbedtls_base64_encode(b64, sizeof(b64) - 1, &b64_len, (const unsigned char *) cred, strlen(cred)) != 0) {
        esp_http_client_cleanup(client);
        return FETCH_ERROR;
    }
    b64[b64_len] = 0;
    snprintf(header, sizeof(header), "Basic %s", (char *) b64);
    esp_http_client_set_header(client, "Authorization", header);

    char value[16];
    snprintf(value, sizeof(value), "%u", battery_mv);
    esp_http_client_set_header(client, "X-Frame-Battery-Millivolts", value);
    snprintf(value, sizeof(value), "%d", rssi);
    esp_http_client_set_header(client, "X-Frame-WiFi-RSSI", value);
    esp_http_client_set_header(client, "X-Frame-Wakeup", wakeup);
    esp_http_client_set_header(client, "X-Frame-Firmware-Version", esp_app_get_description()->version);
    if (etag && etag[0]) esp_http_client_set_header(client, "If-None-Match", etag);

    fetch_result_t result = FETCH_ERROR;
    if (esp_http_client_open(client, 0) != ESP_OK) {
        ESP_LOGE(TAG, "Verbindung fehlgeschlagen");
        goto done;
    }
    int64_t length = esp_http_client_fetch_headers(client);
    int status = esp_http_client_get_status_code(client);
    ESP_LOGI(TAG, "HTTP %d, %lld Bytes, Schlaf %lu s", status, length, (unsigned long) out->sleep_s);
    if (status == 304) {
        result = FETCH_NOT_MODIFIED;
        goto done;
    }
    if (status != 200 || length != EPD_BUFFER_SIZE) goto done;

    out->buf = heap_caps_malloc(EPD_BUFFER_SIZE, MALLOC_CAP_SPIRAM);
    if (!out->buf) goto done;
    size_t total = 0;
    while (total < EPD_BUFFER_SIZE) {
        int n = esp_http_client_read(client, (char *) out->buf + total, EPD_BUFFER_SIZE - total);
        if (n <= 0) break;
        total += n;
    }
    if (total != EPD_BUFFER_SIZE) {
        ESP_LOGE(TAG, "Nur %u Bytes empfangen", (unsigned) total);
        free(out->buf);
        out->buf = NULL;
        goto done;
    }
    out->len = total;
    result = FETCH_IMAGE;

done:
    esp_http_client_close(client);
    esp_http_client_cleanup(client);
    return result;
}
