#pragma once

#include <cstddef>
#include <cstdint>

namespace esphome::stream_deck::rendering {

// Generated from ESPHome's pinned glyph_to_glyphinfo(), MSB-first 4-bit
// coverage with no per-row padding. No TTF/FreeType runs on the controller.
struct Glyph {
  uint32_t codepoint, offset;
  uint8_t advance, width, height;
  int8_t offset_x, offset_y;
};
struct Font {
  const Glyph *glyphs;
  size_t glyph_count;
  const uint8_t *bitmap;
  size_t bitmap_size;
  uint8_t size, line_height;
  const Glyph *find(uint32_t codepoint) const;
  uint8_t coverage(const Glyph &glyph, unsigned x, unsigned y) const;
};

// Only the three contract sizes, nullptr for other values.
const Font *bundled_font(unsigned size);
}  // namespace esphome::stream_deck::rendering
