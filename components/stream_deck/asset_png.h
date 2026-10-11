#pragma once
#include "asset_memory.h"
#include "renderer.h"

namespace esphome::stream_deck::assets {
// Strict non-interlaced PNG, all standard colour types and legal bit depths.
// CRC/chunk ordering is validated before allocation/inflate. The fixed input
// remains borrowed until DONE/cancel; every stage has a bounded work slice.
class PngDecoder {
 public:
  enum class Phase : uint8_t { IDLE, VALIDATE, INFLATE, ROWS, DONE, FAILED };
  explicit PngDecoder(ImageAllocator &allocator) : allocator_(allocator) {}
  bool begin(const uint8_t *data, size_t size);
  Phase step();
  void cancel();
  Phase phase() const { return phase_; }
  visual::Error error() const { return error_; }
  rendering::PixelView pixels() const;
  static constexpr size_t SLICE = 1024, MAX_CHUNKS = 256;
 private:
  bool fail_(visual::Error error = visual::Error::DECODE_FAILED);
  bool chunk_();
  void validate_();
  void inflate_();
  void row_();
  ImageAllocator &allocator_;
  Buffer inflater_, raw_, rgba_;
  const uint8_t *data_{nullptr};
  size_t size_{0}, offset_{0}, chunk_size_{0}, chunk_progress_{0}, chunk_count_{0};
  uint32_t chunk_type_{0}, crc_{0};
  size_t first_idat_{0}, idat_bytes_{0}, input_left_{0}, input_offset_{0}, segment_left_{0}, output_size_{0};
  size_t stride_{0}, expected_{0}, row_index_{0};
  unsigned width_{0}, height_{0}, depth_{0}, color_{0}, channels_{0}, palette_size_{0};
  std::array<uint8_t, 768> palette_{};
  std::array<uint8_t, 256> alpha_{};
  std::array<uint16_t, 3> transparent_{};
  bool ihdr_{false}, plte_{false}, trns_{false}, idat_{false}, idat_closed_{false};
  Phase phase_{Phase::IDLE};
  visual::Error error_{visual::Error::NONE};
};
}  // namespace esphome::stream_deck::assets
