#include "render_font.h"

namespace esphome::stream_deck::rendering {
const Glyph *Font::find(uint32_t codepoint) const {
  size_t lo = 0, hi = glyph_count;
  while (lo < hi) {
    const auto mid = lo + (hi - lo) / 2;
    if (glyphs[mid].codepoint < codepoint) lo = mid + 1;
    else hi = mid;
  }
  return lo < glyph_count && glyphs[lo].codepoint == codepoint ? &glyphs[lo] : nullptr;
}
uint8_t Font::coverage(const Glyph &glyph, unsigned x, unsigned y) const {
  if (x >= glyph.width || y >= glyph.height) return 0;
  const size_t pixel = y * glyph.width + x;
  const size_t offset = size_t(glyph.offset) + pixel / 2;
  if (offset >= bitmap_size) return 0;
  return uint8_t(((bitmap[offset] >> (pixel % 2 == 0 ? 4 : 0)) & 15) * 17);
}
}  // namespace esphome::stream_deck::rendering
