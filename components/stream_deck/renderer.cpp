#include "renderer.h"

#include <algorithm>
#include <cstring>

namespace esphome::stream_deck::rendering {
namespace {
unsigned channels(PixelFormat format) {
  switch (format) {
    case PixelFormat::RGB: case PixelFormat::BGR: return 3;
    case PixelFormat::RGBA: case PixelFormat::BGRA: return 4;
  }
  return 0;
}
uint8_t channel(uint32_t rgb, unsigned index) { return uint8_t(rgb >> (16 - 8 * index)); }
uint8_t blend(uint8_t background, uint8_t foreground, unsigned alpha) {
  return uint8_t((unsigned(background) * (255 - alpha) + unsigned(foreground) * alpha + 127) / 255);
}
// Pixel-centre inverse mapping, quantized to 1/256 source pixel and clamped at
// the edges. Dimensions are bounded before entering this calculation.
unsigned coordinate(unsigned at, unsigned source, unsigned scaled) {
  const int fixed = int(((2 * at + 1) * source * 128) / scaled) - 128;
  return unsigned(std::clamp(fixed, 0, int((source - 1) * 256)));
}
}  // namespace

bool valid_pixels(const PixelView &view) {
  const auto count = channels(view.format);
  if (!count || !view.data || !view.width || !view.height ||
      view.width > visual::MAX_SOURCE_DIMENSION || view.height > visual::MAX_SOURCE_DIMENSION ||
      size_t(view.width) * view.height > visual::MAX_SOURCE_PIXELS) return false;
  const auto row = size_t(view.width) * count;
  // Bounds include row padding, not only the tightly-packed pixel count.
  if (view.stride < row || view.stride > visual::MAX_SOURCE_DIMENSION * 4 ||
      view.bytes > visual::MAX_SOURCE_PIXELS * 4) return false;
  return view.bytes >= (view.height - 1) * view.stride + row;
}

bool Renderer::reject_(visual::Error error) {
  phase_ = Phase::FAILED;
  error_ = error;
  source_ = {};
  placement_count_ = 0;
  return false;
}
void Renderer::cancel() {
  phase_ = Phase::IDLE;
  error_ = visual::Error::NONE;
  source_ = {};
  placement_count_ = 0;
}
bool Renderer::begin(const visual::State &state, PixelView source) {
  if (busy()) return false;
  cancel();
  truncated_ = false;
  substitutions_ = 0;
  font_ = bundled_font(state.font);
  if (!font_) return reject_(visual::Error::INVALID_FONT);
  if (state.text_color > 0xffffff || state.outline_color > 0xffffff || state.background_color > 0xffffff)
    return reject_(visual::Error::INVALID_COLOR);
  if (state.fit != visual::Fit::CONTAIN && state.fit != visual::Fit::CROP)
    return reject_(visual::Error::INVALID_FIT);
  if (source.data == nullptr) {
    if (source.width || source.height || source.bytes || source.stride) return reject_(visual::Error::DECODE_FAILED);
  } else {
    if (!valid_pixels(source)) return reject_(visual::Error::DECODE_FAILED);
    const auto src = reinterpret_cast<uintptr_t>(source.data);
    const auto ws = reinterpret_cast<uintptr_t>(&workspace_);
    // Checked without adding untrusted lengths to a pointer-sized integer.
    if ((src >= ws && src - ws < sizeof(Workspace)) || (src < ws && ws - src < source.bytes))
      return reject_(visual::Error::DECODE_FAILED);
  }
  if (!layout_(state.text.view())) return false;
  source_ = source;
  background_color_ = state.background_color;
  text_color_ = state.text_color;
  outline_color_ = state.outline_color;
  if (source.data) {
    const auto divisor = state.fit == visual::Fit::CONTAIN ? std::max(source.width, source.height)
                                                        : std::min(source.width, source.height);
    scaled_width_ = std::max(1U, unsigned((source.width * WIDTH + divisor / 2) / divisor));
    scaled_height_ = std::max(1U, unsigned((source.height * HEIGHT + divisor / 2) / divisor));
    origin_x_ = (int(WIDTH) - int(scaled_width_)) / 2;
    origin_y_ = (int(HEIGHT) - int(scaled_height_)) / 2;
  }
  std::memcpy(workspace_.native.data(), protocol::blank_image().data, 54);
  row_ = 0;
  phase_ = Phase::BACKGROUND;
  return true;
}

bool Renderer::layout_(std::string_view text) {
  std::array<uint32_t, visual::MAX_LABEL_CODEPOINTS> points;
  size_t count;
  const auto error = visual::decode_label(text, points, count);
  if (error != visual::Error::NONE) return reject_(error);
  for (size_t i = 0; i < count; i++) {
    if (points[i] != '\n' && !font_->find(points[i])) { points[i] = '?'; substitutions_++; }
  }
  struct Line { std::array<uint32_t, visual::MAX_LABEL_CODEPOINTS + 3> points{}; size_t count{0}; };
  std::array<Line, 2> lines;
  const auto bounds = [&](const Line &line, int &minimum) {
    minimum = 0;
    int pen = 0, maximum = 0;
    for (size_t n = 0; n < line.count; n++) {
      const auto &glyph = *font_->find(line.points[n]);
      minimum = std::min(minimum, pen + glyph.offset_x);
      maximum = std::max(maximum, pen + glyph.offset_x + glyph.width);
      pen += glyph.advance;
    }
    return std::max(maximum, pen) - minimum;
  };
  constexpr int INNER_WIDTH = WIDTH - 6;  // Two-pixel inset plus the one-pixel outline.
  size_t position = 0, line_count = 0;
  while (position < count && line_count < lines.size()) {
    auto &line = lines[line_count++];
    while (position < count && points[position] == ' ') position++;
    const auto start = position;
    size_t last_space = count;
    while (position < count && points[position] != '\n') {
      line.points[line.count++] = points[position];
      int minimum;
      if (bounds(line, minimum) > INNER_WIDTH) { line.count--; break; }
      if (points[position] == ' ') last_space = position;
      position++;
    }
    if (position < count && points[position] == '\n') {
      position++;
    } else if (position < count && last_space < position && last_space > start) {
      line.count = last_space - start;
      position = last_space + 1;
    }
    while (line.count && line.points[line.count - 1] == ' ') line.count--;
  }
  while (position < count && (points[position] == ' ' || points[position] == '\n')) position++;
  truncated_ = position < count;
  if (truncated_) {
    auto &last = lines[line_count - 1];
    for (;;) {
      last.points[last.count] = last.points[last.count + 1] = last.points[last.count + 2] = '.';
      last.count += 3;
      int minimum;
      if (bounds(last, minimum) <= INNER_WIDTH) break;
      last.count -= 3;
      if (!last.count) return reject_(visual::Error::RENDER_FAILED);
      last.count--;
    }
  }
  const int top = int(HEIGHT) - 3 - int(line_count) * font_->line_height;
  for (size_t line = 0; line < line_count; line++) {
    int minimum;
    const auto width = bounds(lines[line], minimum);
    int x = (int(WIDTH) - width) / 2 - minimum;
    const int y = top + int(line) * font_->line_height;
    for (size_t n = 0; n < lines[line].count; n++) {
      const auto *glyph = font_->find(lines[line].points[n]);
      placements_[placement_count_++] = {glyph, x + glyph->offset_x, y + glyph->offset_y};
      x += glyph->advance;
    }
  }
  return true;
}

void Renderer::background_row_() {
  for (unsigned x = 0; x < WIDTH; x++) {
    auto *out = workspace_.background.data() + (row_ * WIDTH + x) * 3;
    const int dx = int(x) - origin_x_, dy = int(row_) - origin_y_;
    if (!source_.data || dx < 0 || dy < 0 || unsigned(dx) >= scaled_width_ || unsigned(dy) >= scaled_height_) {
      for (unsigned c = 0; c < 3; c++) out[c] = channel(background_color_, c);
      continue;
    }
    const auto sx = coordinate(unsigned(dx), source_.width, scaled_width_);
    const auto sy = coordinate(unsigned(dy), source_.height, scaled_height_);
    const unsigned xs[] = {sx / 256, std::min(sx / 256 + 1, source_.width - 1)};
    const unsigned ys[] = {sy / 256, std::min(sy / 256 + 1, source_.height - 1)};
    const unsigned wx[] = {256 - sx % 256, sx % 256}, wy[] = {256 - sy % 256, sy % 256};
    uint32_t alpha = 0;
    uint64_t color[3]{};
    const auto bytes = channels(source_.format);
    const bool bgr = source_.format == PixelFormat::BGR || source_.format == PixelFormat::BGRA;
    for (unsigned j = 0; j < 2; j++) for (unsigned i = 0; i < 2; i++) {
      const auto *pixel = source_.data + ys[j] * source_.stride + xs[i] * bytes;
      const unsigned weighted_alpha = wx[i] * wy[j] * (bytes == 4 ? pixel[3] : 255);
      alpha += weighted_alpha;
      for (unsigned c = 0; c < 3; c++) color[c] += uint64_t(pixel[bgr ? 2 - c : c]) * weighted_alpha;
    }
    constexpr uint32_t DENOMINATOR = 255 * 65536;
    for (unsigned c = 0; c < 3; c++) {
      // Interpolate premultiplied colour/alpha, then composite once. Hidden
      // colour in transparent source pixels cannot bleed into their neighbours.
      out[c] = uint8_t((color[c] + uint64_t(channel(background_color_, c)) * (DENOMINATOR - alpha) +
                        DENOMINATOR / 2) / DENOMINATOR);
    }
  }
}
void Renderer::mask_row_() {
  auto *row = workspace_.ink.data() + row_ * WIDTH;
  std::memset(row, 0, WIDTH);
  for (size_t n = 0; n < placement_count_; n++) {
    const auto &p = placements_[n];
    const int y = int(row_) - p.y;
    if (y < 0 || y >= p.glyph->height) continue;
    for (int x = std::max(0, p.x); x < std::min(int(WIDTH), p.x + p.glyph->width); x++)
      row[x] = std::max(row[x], font_->coverage(*p.glyph, unsigned(x - p.x), unsigned(y)));
  }
}
void Renderer::composite_row_() {
  for (unsigned x = 0; x < WIDTH; x++) {
    unsigned outline = 0;
    for (int y2 = std::max(0, int(row_) - 1); y2 <= std::min(int(HEIGHT) - 1, int(row_) + 1); y2++)
      for (int x2 = std::max(0, int(x) - 1); x2 <= std::min(int(WIDTH) - 1, int(x) + 1); x2++)
        outline = std::max(outline, unsigned(workspace_.ink[y2 * WIDTH + x2]));
    const auto ink = workspace_.ink[row_ * WIDTH + x];
    const auto *background = workspace_.background.data() + (row_ * WIDTH + x) * 3;
    // Native helper flips X/Y before a bottom-up BMP. The vertical flip and
    // BMP row order cancel, leaving front-view rows and reversed BGR columns.
    auto *out = workspace_.native.data() + 54 + (row_ * WIDTH + WIDTH - 1 - x) * 3;
    for (unsigned c = 0; c < 3; c++) {
      const auto edged = blend(background[c], channel(outline_color_, c), outline);
      out[2 - c] = blend(edged, channel(text_color_, c), ink);
    }
  }
}
Phase Renderer::step() {
  if (!busy()) return phase_;
  switch (phase_) {
    case Phase::BACKGROUND: background_row_(); break;
    case Phase::MASK: mask_row_(); break;
    case Phase::COMPOSITE: composite_row_(); break;
    default: break;
  }
  if (++row_ == HEIGHT) {
    row_ = 0;
    if (phase_ == Phase::BACKGROUND) { phase_ = Phase::MASK; source_ = {}; }
    else if (phase_ == Phase::MASK) phase_ = Phase::COMPOSITE;
    else phase_ = Phase::DONE;
  }
  return phase_;
}
ImageRef Renderer::copy_image(uint64_t version, ImageAllocator &allocator) const {
  if (phase_ != Phase::DONE) return {};
  return ImageRef::copy(protocol::NativeImage(workspace_.native.data(), workspace_.native.size()), version, allocator);
}
PixelView Renderer::background() const {
  if (phase_ != Phase::DONE) return {};
  return {workspace_.background.data(), RGB_BYTES, WIDTH * 3, WIDTH, HEIGHT, PixelFormat::RGB};
}
}  // namespace esphome::stream_deck::rendering
