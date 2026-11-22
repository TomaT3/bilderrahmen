# Firmware für den Waveshare ESP32-S3-PhotoPainter: holt einmal am Tag das Bild vom Dienst bilderrahmen.
cmake_minimum_required(VERSION 3.16)
set(PROJECT_VER "0.1.0")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(bilderrahmen-firmware)
