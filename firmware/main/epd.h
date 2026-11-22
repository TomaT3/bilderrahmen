#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// Zeigt einen fertigen Panelpuffer (EPD_BUFFER_SIZE Bytes, 4 Bit pro Pixel, Controller-Farbcodes) an und
// legt das Panel danach schlafen. Dauert etwa 25 s. Gibt false zurück, wenn das Panel nicht reagiert.
bool epd_show(const uint8_t *buffer, size_t len);
