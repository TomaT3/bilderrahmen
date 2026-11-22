#pragma once

#include <stdbool.h>
#include <stdint.h>

// TG28/AXP2101 wecken und einrichten. Gibt false zurück, wenn er nicht antwortet.
bool pmic_init(void);
// Akkuspannung in mV, 0 wenn kein Akku erkannt wird
uint16_t pmic_battery_mv(void);
// Wie Waveshares axp_basic_sleep_start(): PMIC in den Schlaf, alle Schienen außer DC1 (ESP32) aus.
// Beim nächsten Start weckt pmic_init() ihn über die IRQ-Leitung wieder.
void pmic_sleep(void);
