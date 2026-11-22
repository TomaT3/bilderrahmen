// Pinbelegung des Waveshare ESP32-S3-PhotoPainter, aus der Waveshare-Demo
// (github.com/wurongmin/ESP32-S3-PhotoPainter: bsp_config.h, power_bsp.h, boards/waveshare-s3-PhotoPainter/config.h)
#pragma once

#include <driver/gpio.h>

#define EPD_DC_PIN GPIO_NUM_8
#define EPD_CS_PIN GPIO_NUM_9
#define EPD_SCK_PIN GPIO_NUM_10
#define EPD_MOSI_PIN GPIO_NUM_11
#define EPD_RST_PIN GPIO_NUM_12
#define EPD_BUSY_PIN GPIO_NUM_13

#define I2C_SDA_PIN GPIO_NUM_47
#define I2C_SCL_PIN GPIO_NUM_48
#define PMIC_I2C_ADDR 0x34  // TG28, registerkompatibel zum AXP2101
#define PMIC_IRQ_PIN GPIO_NUM_21

#define KEY_BUTTON_PIN GPIO_NUM_4  // Taste "KEY": weckt den Rahmen und holt sofort neu

#define EPD_WIDTH 800
#define EPD_HEIGHT 480
#define EPD_BUFFER_SIZE (EPD_WIDTH * EPD_HEIGHT / 2)  // 4 Bit pro Pixel
