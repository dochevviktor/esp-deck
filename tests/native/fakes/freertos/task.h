#pragma once
#include <cstdint>
constexpr int pdPASS = 1;
#define pdMS_TO_TICKS(value) (value)
inline int xTaskCreate(void (*)(void *), const char *, uint32_t, void *, unsigned, void *) { return pdPASS; }
