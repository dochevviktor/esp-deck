#pragma once

#include "render_font.h"
#include "visual_state.h"

namespace esphome::stream_deck::rendering {
constexpr size_t WIDTH = 72, HEIGHT = 72, PIXELS = WIDTH * HEIGHT, RGB_BYTES = PIXELS * 3;

enum class PixelFormat : uint8_t { RGB, RGBA, BGR, BGRA };
// Borrowed top-to-bottom pixels, not an encoded/native BMP. The caller must
// keep them immutable/alive until DONE/cancel, and outside the workspace.
struct PixelView {
  const uint8_t *data{nullptr};
  size_t bytes{0}, stride{0};
  unsigned width{0}, height{0};
  PixelFormat format{PixelFormat::RGB};
};
bool valid_pixels(const PixelView &view);

// Caller-owned, never a 36 KiB local variable on the ESP loop stack. The ESP
// adapter allocates exactly one in PSRAM; native tests can use ordinary memory.
struct Workspace {
  std::array<uint8_t, RGB_BYTES> background;
  std::array<uint8_t, PIXELS> ink;
  std::array<uint8_t, protocol::IMAGE_SIZE> native;
};
enum class Phase : uint8_t { IDLE, BACKGROUND, MASK, COMPOSITE, DONE, FAILED };

class Renderer {
 public:
  explicit Renderer(Workspace &workspace) : workspace_(workspace) {}
  Renderer(const Renderer &) = delete;
  Renderer &operator=(const Renderer &) = delete;
  // A busy render is refused unchanged. Otherwise validates before work starts.
  bool begin(const visual::State &state, PixelView source = {});
  // Exactly one row of one stage per call, no allocation. Yield between calls.
  Phase step();
  void cancel();
  Phase phase() const { return phase_; }
  visual::Error error() const { return error_; }
  bool busy() const { return phase_ == Phase::BACKGROUND || phase_ == Phase::MASK || phase_ == Phase::COMPOSITE; }
  bool truncated() const { return truncated_; }
  unsigned substitutions() const { return substitutions_; }
  ImageRef copy_image(uint64_t version, ImageAllocator &allocator) const;
  // Completed, scaled/composited RGB background with no text, for P3 caching.
  PixelView background() const;

 private:
  struct Placement { const Glyph *glyph; int x, y; };
  bool layout_(const visual::State &state);
  uint8_t clip_x_{3}, clip_y_{3}, clip_width_{66}, clip_height_{66};
  void background_row_();
  void mask_row_();
  void composite_row_();
  bool reject_(visual::Error error);
  Workspace &workspace_;
  PixelView source_{};
  const Font *font_{nullptr};
  std::array<Placement, visual::MAX_LABEL_CODEPOINTS + 3> placements_{};
  size_t placement_count_{0};
  unsigned scaled_width_{0}, scaled_height_{0}, row_{0}, substitutions_{0};
  int origin_x_{0}, origin_y_{0};
  uint32_t background_color_{0}, text_color_{0xffffff}, outline_color_{0};
  bool truncated_{false};
  Phase phase_{Phase::IDLE};
  visual::Error error_{visual::Error::NONE};
};
}  // namespace esphome::stream_deck::rendering
