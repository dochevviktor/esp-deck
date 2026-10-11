#pragma once
#include <cstddef>
#include <cstdint>

constexpr uint32_t MALLOC_CAP_SPIRAM = 1U << 10;
constexpr uint32_t MALLOC_CAP_8BIT = 1U << 2;
constexpr uint32_t MALLOC_CAP_INTERNAL = 1U << 11;
void *heap_caps_malloc(size_t size, uint32_t caps);
void heap_caps_free(void *memory);
size_t heap_caps_get_free_size(uint32_t caps);
size_t heap_caps_get_minimum_free_size(uint32_t caps);
