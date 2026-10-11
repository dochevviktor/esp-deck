// Miniz from the exact pngle 1.1.0 pin used by ESPHome, with bytewise loads
// enabled for portable sanitizer tests. Disable heap APIs and prefix exports
// to avoid ESP-IDF ROM/miniz collisions. See third_party/manifest.json.
#define MINIZ_NO_MALLOC
#define MINIZ_USE_UNALIGNED_LOADS_AND_STORES 0
#define mz_adler32 deck_miniz_adler32
#define mz_crc32 deck_miniz_crc32
#define mz_free deck_miniz_free
#define tinfl_decompress deck_miniz_decompress
#define tinfl_decompress_mem_to_heap deck_miniz_to_heap
#define tinfl_decompress_mem_to_mem deck_miniz_to_mem
#define tinfl_decompress_mem_to_callback deck_miniz_to_callback
#include "third_party/miniz.inc"
#include "asset_inflate.h"

size_t deck_inflate_state_size(void) { return sizeof(tinfl_decompressor); }
void deck_inflate_init(void *state) { tinfl_init((tinfl_decompressor *) state); }
int deck_inflate_step(void *state, const uint8_t *input, size_t *input_size,
                      uint8_t *output_start, uint8_t *output_next, size_t *output_size, int more_input) {
  return tinfl_decompress((tinfl_decompressor *) state, input, input_size, output_start, output_next, output_size,
      TINFL_FLAG_PARSE_ZLIB_HEADER | TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF |
      (more_input ? TINFL_FLAG_HAS_MORE_INPUT : 0));
}
uint32_t deck_png_crc(uint32_t crc, const uint8_t *bytes, size_t size) { return (uint32_t) mz_crc32(crc, bytes, size); }
