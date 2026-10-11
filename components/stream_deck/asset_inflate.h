#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
size_t deck_inflate_state_size(void);
void deck_inflate_init(void *state);
// 0: verified zlib end, 1: needs input, 2: needs output, negative: invalid stream.
int deck_inflate_step(void *state, const uint8_t *input, size_t *input_size,
                      uint8_t *output_start, uint8_t *output_next, size_t *output_size, int more_input);
uint32_t deck_png_crc(uint32_t crc, const uint8_t *bytes, size_t size);
#ifdef __cplusplus
}
#endif
