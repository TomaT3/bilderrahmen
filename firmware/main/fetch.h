#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum { FETCH_IMAGE, FETCH_NOT_MODIFIED, FETCH_ERROR } fetch_result_t;

typedef struct {
    uint32_t sleep_s;  // aus X-Sleep-Seconds, 0 wenn nicht gesendet
    char etag[64];
    uint8_t *buf;      // nur bei FETCH_IMAGE, im PSRAM
    size_t len;
} fetch_out_t;

// Im WLAN anmelden (Timeout 20 s). rssi wird bei Erfolg gesetzt.
bool wifi_connect(int *rssi);
void wifi_stop(void);

// GET <FRAME_BASE_URL>/frame/<FRAME_ID>/image.bin mit Basic Auth, If-None-Match und den X-Frame-*-Headern
fetch_result_t fetch_image(const char *etag, uint16_t battery_mv, int rssi, const char *wakeup, fetch_out_t *out);
