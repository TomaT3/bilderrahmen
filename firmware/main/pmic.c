// Ansteuerung des PMIC TG28 (registerkompatibel zum AXP2101). Register und Bits geprüft gegen XPowersLib
// (lewisxhe, MIT), die Waveshares Demo verwendet; Ablauf wie in deren power_bsp.cpp und bsp_fac.h.
#include "pmic.h"

#include <driver/gpio.h>
#include <driver/i2c_master.h>
#include <esp_log.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include "board.h"

static const char *TAG = "pmic";
static i2c_master_dev_handle_t s_dev;

#define REG_STATUS1 0x00            // Bit 3: Akku erkannt
#define REG_SLEEP_WAKEUP_CTRL 0x26  // Bit 0 Schlaf, 2 Schienen wie vor dem Schlaf, 3 PWROK low, 4 Wecken über IRQ
#define REG_ADC_CHANNEL_CTRL 0x30   // Bit 0: Akkuspannung messen
#define REG_ADC_VBAT_H 0x34
#define REG_ADC_VBAT_L 0x35
#define REG_INTEN1 0x40   // 0x40..0x42
#define REG_INTSTS1 0x48  // 0x48..0x4A
#define REG_ICC_CHG_SET 0x62  // Ladestrom, Bits 0..4
#define REG_BAT_DET_CTRL 0x68  // Bit 0: Akkuerkennung
#define REG_DC_ONOFF 0x80     // Bit 1..4 = DC2..DC5
#define REG_LDO_ONOFF0 0x90   // ALDO1..4, BLDO1..2, CPUSLDO, DLDO1
#define REG_LDO_ONOFF1 0x91   // Bit 0 = DLDO2
#define CHG_CUR_500MA 11      // wie Waveshare (setChargerConstantCurr)

static int rd(uint8_t reg) {
    uint8_t v;
    if (i2c_master_transmit_receive(s_dev, &reg, 1, &v, 1, 100) != ESP_OK) return -1;
    return v;
}

static bool wr(uint8_t reg, uint8_t val) {
    uint8_t buf[2] = {reg, val};
    return i2c_master_transmit(s_dev, buf, 2, 100) == ESP_OK;
}

static void set_bits(uint8_t reg, uint8_t mask, bool on) {
    int v = rd(reg);
    if (v < 0) return;
    wr(reg, on ? (v | mask) : (v & ~mask));
}

bool pmic_init(void) {
    // Ein kurzer Low-Puls auf der IRQ-Leitung weckt den PMIC aus dem Schlaf (wie axp2101_irq_init der Demo)
    gpio_config_t io = {.pin_bit_mask = 1ULL << PMIC_IRQ_PIN, .mode = GPIO_MODE_OUTPUT, .pull_up_en = 1};
    gpio_config(&io);
    gpio_set_level(PMIC_IRQ_PIN, 0);
    vTaskDelay(pdMS_TO_TICKS(100));
    gpio_set_level(PMIC_IRQ_PIN, 1);
    vTaskDelay(pdMS_TO_TICKS(200));

    i2c_master_bus_config_t bus_cfg = {
        .i2c_port = 0,
        .sda_io_num = I2C_SDA_PIN,
        .scl_io_num = I2C_SCL_PIN,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    i2c_master_bus_handle_t bus;
    if (i2c_new_master_bus(&bus_cfg, &bus) != ESP_OK) return false;
    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = PMIC_I2C_ADDR,
        .scl_speed_hz = 100000,
    };
    if (i2c_master_bus_add_device(bus, &dev_cfg, &s_dev) != ESP_OK) return false;
    if (rd(REG_STATUS1) < 0) {
        ESP_LOGE(TAG, "PMIC antwortet nicht");
        s_dev = NULL;
        return false;
    }
    set_bits(REG_SLEEP_WAKEUP_CTRL, 0x01, false);  // Schlafmodus aus
    int icc = rd(REG_ICC_CHG_SET);
    if (icc >= 0) wr(REG_ICC_CHG_SET, (icc & 0xE0) | CHG_CUR_500MA);
    set_bits(REG_BAT_DET_CTRL, 0x01, true);
    set_bits(REG_ADC_CHANNEL_CTRL, 0x01, true);
    vTaskDelay(pdMS_TO_TICKS(50));  // erste ADC-Messung abwarten
    return true;
}

uint16_t pmic_battery_mv(void) {
    if (!s_dev) return 0;
    int st = rd(REG_STATUS1);
    if (st < 0 || !(st & 0x08)) return 0;
    int h = rd(REG_ADC_VBAT_H), l = rd(REG_ADC_VBAT_L);
    if (h < 0 || l < 0) return 0;
    return (uint16_t) (((h & 0x1F) << 8) | l);
}

void pmic_sleep(void) {
    if (!s_dev) return;
    for (int i = 0; i < 3; i++) wr(REG_INTEN1 + i, 0x00);
    for (int i = 0; i < 3; i++) wr(REG_INTSTS1 + i, 0xFF);
    set_bits(REG_SLEEP_WAKEUP_CTRL, 0x04, true);   // nach dem Wecken Schienen wie vor dem Schlaf
    set_bits(REG_SLEEP_WAKEUP_CTRL, 0x08, false);  // PWROK beim Wecken nicht auf low ziehen
    set_bits(REG_SLEEP_WAKEUP_CTRL, 0x10, true);   // Wecken über die IRQ-Leitung
    set_bits(REG_ADC_CHANNEL_CTRL, 0x01, false);
    set_bits(REG_BAT_DET_CTRL, 0x01, false);
    set_bits(REG_SLEEP_WAKEUP_CTRL, 0x01, true);  // Schlaf
    set_bits(REG_DC_ONOFF, 0x1E, false);          // DC2..DC5 aus, DC1 (ESP32) bleibt
    wr(REG_LDO_ONOFF0, 0x00);                     // ALDO1..4, BLDO1..2, CPUSLDO, DLDO1 aus
    set_bits(REG_LDO_ONOFF1, 0x01, false);        // DLDO2 aus
    ESP_LOGI(TAG, "PMIC schläft");
}
