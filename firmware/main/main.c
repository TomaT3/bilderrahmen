// Ablauf bei jedem Aufwachen: Akku messen, Bild holen, bei neuem Bild anzeigen, bis zur nächsten Weckzeit schlafen.
#include <string.h>

#include <driver/rtc_io.h>
#include <esp_log.h>
#include <esp_sleep.h>
#include <esp_timer.h>
#include <nvs_flash.h>

#include "board.h"
#include "epd.h"
#include "fetch.h"
#include "pmic.h"

static const char *TAG = "rahmen";

#define MIN_SLEEP_S 60
#define MAX_SLEEP_S 86400
#define RETRY_SLEEP_S 3600            // nach einem Fehler
#define RETRY_SLEEP_LONG_S (6 * 3600)  // ab dem dritten Fehler in Folge
#define WATCHDOG_US (180LL * 1000 * 1000)

// Überlebt den Deep Sleep (nicht aber einen Akkuwechsel; dann wird das Bild einmal neu geladen)
RTC_DATA_ATTR static char s_etag[64];
RTC_DATA_ATTR static uint8_t s_failures;

static void go_sleep(uint32_t seconds) {
    if (seconds < MIN_SLEEP_S) seconds = MIN_SLEEP_S;
    if (seconds > MAX_SLEEP_S) seconds = MAX_SLEEP_S;
    ESP_LOGI(TAG, "Schlafe %lu s", (unsigned long) seconds);
    esp_sleep_enable_timer_wakeup((uint64_t) seconds * 1000000ULL);
    rtc_gpio_pullup_en(KEY_BUTTON_PIN);
    rtc_gpio_pulldown_dis(KEY_BUTTON_PIN);
    esp_sleep_enable_ext1_wakeup_io(1ULL << KEY_BUTTON_PIN, ESP_EXT1_WAKEUP_ANY_LOW);
    pmic_sleep();
    esp_deep_sleep_start();
}

static void on_watchdog(void *arg) {
    // Hängt irgendetwas (WLAN, Server, Panel), trotzdem schlafen statt den Akku leer zu ziehen
    ESP_LOGE(TAG, "Zeitlimit erreicht");
    s_failures++;
    go_sleep(RETRY_SLEEP_S);
}

static const char *wakeup_reason(void) {
    switch (esp_sleep_get_wakeup_cause()) {
        case ESP_SLEEP_WAKEUP_TIMER: return "timer";
        case ESP_SLEEP_WAKEUP_EXT1: return "button";
        default: return "power-on";
    }
}

void app_main(void) {
    const esp_timer_create_args_t wd_args = {.callback = on_watchdog, .name = "watchdog"};
    esp_timer_handle_t wd;
    ESP_ERROR_CHECK(esp_timer_create(&wd_args, &wd));
    ESP_ERROR_CHECK(esp_timer_start_once(wd, WATCHDOG_US));

    const char *wakeup = wakeup_reason();
    if (!pmic_init()) ESP_LOGW(TAG, "Ohne PMIC weiter, Akkuspannung unbekannt");
    uint16_t battery_mv = pmic_battery_mv();
    ESP_LOGI(TAG, "Wecken: %s, Akku %u mV", wakeup, battery_mv);

    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    fetch_out_t out = {0};
    fetch_result_t result = FETCH_ERROR;
    int rssi = 0;
    if (wifi_connect(&rssi)) result = fetch_image(s_etag, battery_mv, rssi, wakeup, &out);
    wifi_stop();  // WLAN aus, bevor das Panel ~25 s lang neu zeichnet

    if (result == FETCH_IMAGE) {
        if (epd_show(out.buf, out.len)) {
            strlcpy(s_etag, out.etag, sizeof(s_etag));
        } else {
            result = FETCH_ERROR;
        }
    }

    esp_timer_stop(wd);
    if (result == FETCH_ERROR) {
        s_failures++;
        go_sleep(s_failures >= 3 ? RETRY_SLEEP_LONG_S : RETRY_SLEEP_S);
    }
    s_failures = 0;
    go_sleep(out.sleep_s ? out.sleep_s : RETRY_SLEEP_S);
}
