// Minimaler Treiber für das 7,3"-Spectra-6-Panel (E6) des PhotoPainter.
// Init-Sequenz und Refresh aus Waveshares display_bsp.cpp (github.com/wurongmin/ESP32-S3-PhotoPainter),
// Deep-Sleep-Befehl (0x07, 0xA5) aus Waveshares EPD_7in3e-Treiber.
#include "epd.h"

#include <driver/gpio.h>
#include <driver/spi_master.h>
#include <esp_log.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include "board.h"

static const char *TAG = "epd";
static spi_device_handle_t s_spi;

#define CHUNK 4096
#define BUSY_TIMEOUT_US (60LL * 1000 * 1000)

static bool wait_idle(void) {
    // BUSY = 1 heißt bereit
    int64_t start = esp_timer_get_time();
    while (!gpio_get_level(EPD_BUSY_PIN)) {
        if (esp_timer_get_time() - start > BUSY_TIMEOUT_US) {
            ESP_LOGE(TAG, "Panel bleibt busy");
            return false;
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    return true;
}

static void spi_write(const uint8_t *buf, size_t len) {
    spi_transaction_t t = {0};
    while (len) {
        size_t n = len > CHUNK ? CHUNK : len;
        t.length = 8 * n;
        t.tx_buffer = buf;
        ESP_ERROR_CHECK(spi_device_polling_transmit(s_spi, &t));
        buf += n;
        len -= n;
    }
}

static void send_cmd(uint8_t c) {
    gpio_set_level(EPD_DC_PIN, 0);
    gpio_set_level(EPD_CS_PIN, 0);
    spi_write(&c, 1);
    gpio_set_level(EPD_CS_PIN, 1);
}

static void send_data(const uint8_t *d, size_t len) {
    gpio_set_level(EPD_DC_PIN, 1);
    gpio_set_level(EPD_CS_PIN, 0);
    spi_write(d, len);
    gpio_set_level(EPD_CS_PIN, 1);
}

#define CMD(c, ...)                                \
    do {                                           \
        static const uint8_t _d[] = {__VA_ARGS__}; \
        send_cmd(c);                               \
        send_data(_d, sizeof(_d));                 \
    } while (0)

static void bus_init(void) {
    spi_bus_config_t bus = {
        .mosi_io_num = EPD_MOSI_PIN,
        .miso_io_num = -1,
        .sclk_io_num = EPD_SCK_PIN,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = CHUNK,
    };
    ESP_ERROR_CHECK(spi_bus_initialize(SPI3_HOST, &bus, SPI_DMA_CH_AUTO));
    spi_device_interface_config_t dev = {
        .clock_speed_hz = 40 * 1000 * 1000,
        .mode = 0,
        .spics_io_num = -1,  // CS steuern wir selbst
        .queue_size = 1,
        .flags = SPI_DEVICE_HALFDUPLEX,
    };
    ESP_ERROR_CHECK(spi_bus_add_device(SPI3_HOST, &dev, &s_spi));

    gpio_config_t out = {
        .pin_bit_mask = (1ULL << EPD_RST_PIN) | (1ULL << EPD_DC_PIN) | (1ULL << EPD_CS_PIN),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&out));
    gpio_config_t in = {
        .pin_bit_mask = 1ULL << EPD_BUSY_PIN,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&in));
    gpio_set_level(EPD_CS_PIN, 1);
}

static bool panel_init(void) {
    gpio_set_level(EPD_RST_PIN, 1);
    vTaskDelay(pdMS_TO_TICKS(50));
    gpio_set_level(EPD_RST_PIN, 0);
    vTaskDelay(pdMS_TO_TICKS(20));
    gpio_set_level(EPD_RST_PIN, 1);
    vTaskDelay(pdMS_TO_TICKS(50));
    if (!wait_idle()) return false;
    vTaskDelay(pdMS_TO_TICKS(50));

    CMD(0xAA, 0x49, 0x55, 0x20, 0x08, 0x09, 0x18);
    CMD(0x01, 0x3F);
    CMD(0x00, 0x5F, 0x69);
    CMD(0x03, 0x00, 0x54, 0x00, 0x44);
    CMD(0x05, 0x40, 0x1F, 0x1F, 0x2C);
    CMD(0x06, 0x6F, 0x1F, 0x17, 0x49);
    CMD(0x08, 0x6F, 0x1F, 0x1F, 0x22);
    CMD(0x30, 0x03);
    CMD(0x50, 0x3F);
    CMD(0x60, 0x02, 0x00);
    CMD(0x61, 0x03, 0x20, 0x01, 0xE0);  // 800 x 480
    CMD(0x84, 0x01);
    CMD(0xE3, 0x2F);
    send_cmd(0x04);  // POWER_ON
    return wait_idle();
}

bool epd_show(const uint8_t *buffer, size_t len) {
    if (len != EPD_BUFFER_SIZE) {
        ESP_LOGE(TAG, "Puffer hat %u statt %u Bytes", (unsigned) len, (unsigned) EPD_BUFFER_SIZE);
        return false;
    }
    bus_init();
    if (!panel_init()) return false;

    send_cmd(0x10);  // Bilddaten
    send_data(buffer, len);

    send_cmd(0x04);  // POWER_ON
    if (!wait_idle()) return false;
    CMD(0x06, 0x6F, 0x1F, 0x17, 0x49);
    CMD(0x12, 0x00);  // DISPLAY_REFRESH
    bool ok = wait_idle();
    CMD(0x02, 0x00);  // POWER_OFF
    ok = wait_idle() && ok;
    CMD(0x07, 0xA5);  // DEEP_SLEEP, aufwecken nur über Reset
    ESP_LOGI(TAG, "Bild angezeigt");
    return ok;
}
