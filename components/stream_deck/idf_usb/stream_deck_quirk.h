#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

// The original 0060 returns this HS layout even on a confirmed full-speed link,
// including after a 20-second power removal. Normalize only this exact layout.
// Called on IDF's newly allocated, unpublished descriptor copy during enumeration.
static inline bool stream_deck_normalize_config(uint16_t vendor, uint16_t product, bool full_speed,
                                                uint8_t *config, size_t size) {
  static const uint8_t observed[] = {
      9, 2, 41, 0, 1, 1, 0, 0xe0, 0xc8,
      9, 4, 0, 0, 2, 3, 0, 0, 0,
      9, 0x21, 0x11, 1, 0, 1, 0x22, 0x0b, 1,
      7, 5, 0x81, 3, 0, 2, 1,
      7, 5, 0x02, 3, 0, 2, 1,
  };
  if (vendor != 0x0fd9 || product != 0x0060 || !full_speed || config == NULL ||
      size != sizeof(observed) || memcmp(config, observed, sizeof(observed)) != 0)
    return false;
  // wMaxPacketSize only: preserve the HID report lengths and power declaration.
  config[31] = config[38] = 64;
  config[32] = config[39] = 0;
  return true;
}
