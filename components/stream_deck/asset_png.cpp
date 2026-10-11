#include "asset_png.h"
#include "asset_inflate.h"
#include <algorithm>
#include <cstdlib>
#include <cstring>

namespace esphome::stream_deck::assets {
namespace {
uint32_t be32(const uint8_t *p) { return uint32_t(p[0]) << 24 | uint32_t(p[1]) << 16 | uint32_t(p[2]) << 8 | p[3]; }
uint16_t be16(const uint8_t *p) { return uint16_t(p[0]) << 8 | p[1]; }
constexpr uint32_t IHDR = 0x49484452, PLTE = 0x504c5445, TRNS = 0x74524e53, IDAT = 0x49444154, IEND = 0x49454e44;
uint8_t paeth(unsigned a, unsigned b, unsigned c) {
  const int p = int(a) + int(b) - int(c);
  const int pa = std::abs(p - int(a)), pb = std::abs(p - int(b)), pc = std::abs(p - int(c));
  return uint8_t(pa <= pb && pa <= pc ? a : pb <= pc ? b : c);
}
}
void PngDecoder::cancel() {
  inflater_.reset(); raw_.reset(); rgba_.reset();
  data_ = nullptr; size_ = 0; phase_ = Phase::IDLE; error_ = visual::Error::NONE;
}
bool PngDecoder::fail_(visual::Error error) {
  cancel(); phase_ = Phase::FAILED; error_ = error;
  return false;
}
bool PngDecoder::begin(const uint8_t *data, size_t size) {
  cancel();
  static const uint8_t signature[] = {137, 80, 78, 71, 13, 10, 26, 10};
  if (!data || size < 45) return fail_();
  if (size > visual::MAX_ENCODED_BYTES) return fail_(visual::Error::LIMIT_EXCEEDED);
  if (std::memcmp(data, signature, sizeof(signature)) != 0) return fail_();
  data_ = data; size_ = size; offset_ = 8;
  chunk_type_ = 0; chunk_count_ = 0; first_idat_ = idat_bytes_ = 0;
  width_ = height_ = depth_ = color_ = channels_ = palette_size_ = 0;
  ihdr_ = plte_ = trns_ = idat_ = idat_closed_ = false;
  alpha_.fill(255); transparent_.fill(0);
  phase_ = Phase::VALIDATE;
  return true;
}
bool PngDecoder::chunk_() {
  const auto *p = data_ + offset_ + 8;
  if (!ihdr_ && chunk_type_ != IHDR) return fail_();
  if (chunk_type_ != IDAT && idat_) idat_closed_ = true;
  switch (chunk_type_) {
    case IHDR: {
      if (ihdr_ || chunk_size_ != 13) return fail_();
      width_ = be32(p); height_ = be32(p + 4); depth_ = p[8]; color_ = p[9];
      if (!width_ || !height_ || width_ > visual::MAX_SOURCE_DIMENSION || height_ > visual::MAX_SOURCE_DIMENSION ||
          size_t(width_) * height_ > visual::MAX_SOURCE_PIXELS) return fail_(visual::Error::LIMIT_EXCEEDED);
      if (p[10] != 0 || p[11] != 0) return fail_();
      if (p[12] != 0) return fail_(visual::Error::UNSUPPORTED_PNG);
      if (color_ == 0 && (depth_ == 1 || depth_ == 2 || depth_ == 4 || depth_ == 8 || depth_ == 16)) channels_ = 1;
      else if (color_ == 3 && (depth_ == 1 || depth_ == 2 || depth_ == 4 || depth_ == 8)) channels_ = 1;
      else if ((depth_ == 8 || depth_ == 16) && (color_ == 2 || color_ == 4 || color_ == 6))
        channels_ = color_ == 2 ? 3 : color_ == 4 ? 2 : 4;
      else return fail_();
      stride_ = (size_t(width_) * channels_ * depth_ + 7) / 8;
      expected_ = (stride_ + 1) * height_;
      ihdr_ = true;
      break;
    }
    case PLTE:
      if (plte_ || trns_ || idat_ || color_ == 0 || color_ == 4 || !chunk_size_ || chunk_size_ % 3 ||
          chunk_size_ > palette_.size() || (color_ == 3 && chunk_size_ / 3 > (1U << depth_))) return fail_();
      palette_size_ = unsigned(chunk_size_ / 3);
      std::memcpy(palette_.data(), p, chunk_size_); plte_ = true;
      break;
    case TRNS:
      if (trns_ || idat_ || color_ == 4 || color_ == 6) return fail_();
      if (color_ == 3) {
        if (!plte_ || !chunk_size_ || chunk_size_ > palette_size_) return fail_();
        std::memcpy(alpha_.data(), p, chunk_size_);
      } else {
        if (chunk_size_ != (color_ == 0 ? 2U : 6U)) return fail_();
        for (size_t i = 0; i < chunk_size_ / 2; i++) {
          transparent_[i] = be16(p + i * 2);
          if (transparent_[i] >= (1U << depth_)) return fail_();
        }
      }
      trns_ = true;
      break;
    case IDAT:
      if (idat_closed_ || (color_ == 3 && !plte_)) return fail_();
      if (!idat_) first_idat_ = offset_;
      idat_ = true; idat_bytes_ += chunk_size_;
      break;
    case IEND:
      if (!idat_ || !idat_bytes_ || chunk_size_ || offset_ + 12 != size_) return fail_();
      if (!inflater_.allocate(allocator_, deck_inflate_state_size()) || !raw_.allocate(allocator_, expected_ + 1) ||
          !rgba_.allocate(allocator_, size_t(width_) * height_ * 4)) return fail_(visual::Error::OUT_OF_MEMORY);
      deck_inflate_init(inflater_.data());
      input_left_ = idat_bytes_; input_offset_ = first_idat_; segment_left_ = output_size_ = row_index_ = 0;
      phase_ = Phase::INFLATE;
      break;
    case 0x6163544c: case 0x6663544c: case 0x66644154:  // APNG acTL/fcTL/fdAT
      return fail_(visual::Error::UNSUPPORTED_PNG);
    default:
      if (!(data_[offset_ + 4] & 0x20)) return fail_(visual::Error::UNSUPPORTED_PNG);
      // Ancillary metadata is CRC-checked but not interpreted (no gamma/profile transform).
      break;
  }
  return true;
}
void PngDecoder::validate_() {
  if (chunk_type_ == 0) {
    if (offset_ > size_ || size_ - offset_ < 12) { fail_(); return; }
    if (++chunk_count_ > MAX_CHUNKS) { fail_(visual::Error::LIMIT_EXCEEDED); return; }
    chunk_size_ = be32(data_ + offset_);
    if (chunk_size_ > size_ - offset_ - 12) { fail_(); return; }
    const auto *name = data_ + offset_ + 4;
    for (unsigned i = 0; i < 4; i++)
      if (!((name[i] >= 'A' && name[i] <= 'Z') || (name[i] >= 'a' && name[i] <= 'z'))) { fail_(); return; }
    if (name[2] & 0x20) { fail_(); return; }
    chunk_type_ = be32(name); chunk_progress_ = 0;
    crc_ = deck_png_crc(0, name, 4);
  }
  const auto bytes = std::min(SLICE, chunk_size_ - chunk_progress_);
  crc_ = deck_png_crc(crc_, data_ + offset_ + 8 + chunk_progress_, bytes);
  chunk_progress_ += bytes;
  if (chunk_progress_ != chunk_size_) return;
  if (crc_ != be32(data_ + offset_ + 8 + chunk_size_)) { fail_(); return; }
  if (!chunk_()) return;
  offset_ += chunk_size_ + 12;
  chunk_type_ = 0;
}
void PngDecoder::inflate_() {
  // Each call hands the allocation-free inflater <=1024 input/output bytes.
  // Non-wrapping output keeps its complete bounded history for back references.
  if (!segment_left_ && input_left_) {
    if (be32(data_ + input_offset_ + 4) != IDAT) { fail_(); return; }
    segment_left_ = be32(data_ + input_offset_);
    input_offset_ += 8;
    if (!segment_left_) { input_offset_ += 4; return; }
  }
  size_t in = std::min(SLICE, segment_left_);
  size_t out = std::min(SLICE, raw_.size() - output_size_);
  const int result = deck_inflate_step(inflater_.data(), data_ + input_offset_, &in,
                                      raw_.data(), raw_.data() + output_size_, &out, input_left_ > in);
  input_offset_ += in; segment_left_ -= in; input_left_ -= in; output_size_ += out;
  if (!segment_left_ && in) input_offset_ += 4;  // Skip this IDAT's already-validated CRC.
  if (result < 0 || output_size_ > expected_ || (!in && !out && result != 0)) { fail_(); return; }
  if (result == 0) {
    if (output_size_ != expected_ || input_left_ != 0) { fail_(); return; }
    inflater_.reset(); phase_ = Phase::ROWS;
  }
}
void PngDecoder::row_() {
  auto *row = raw_.data() + row_index_ * (stride_ + 1);
  const unsigned filter = *row++;
  if (filter > 4) { fail_(); return; }
  const auto *previous = row_index_ ? row - (stride_ + 1) : nullptr;
  const auto bpp = (channels_ * depth_ + 7) / 8;
  for (size_t x = 0; x < stride_; x++) {
    const unsigned a = x >= bpp ? row[x - bpp] : 0, b = previous ? previous[x] : 0;
    const unsigned c = previous && x >= bpp ? previous[x - bpp] : 0;
    if (filter == 1) row[x] += a;
    else if (filter == 2) row[x] += b;
    else if (filter == 3) row[x] += (a + b) / 2;
    else if (filter == 4) row[x] += paeth(a, b, c);
  }
  const unsigned maximum = (1U << depth_) - 1;
  for (unsigned x = 0; x < width_; x++) {
    unsigned samples[4]{};
    for (unsigned c = 0; c < channels_; c++) {
      const size_t sample = x * channels_ + c;
      samples[c] = depth_ == 16 ? be16(row + sample * 2) : depth_ == 8 ? row[sample] :
          (row[sample * depth_ / 8] >> (8 - depth_ - sample * depth_ % 8)) & maximum;
    }
    auto *out = rgba_.data() + (row_index_ * width_ + x) * 4;
    if (color_ == 3) {
      const auto index = samples[0];
      if (index >= palette_size_) { fail_(); return; }
      std::memcpy(out, palette_.data() + index * 3, 3); out[3] = alpha_[index];
      continue;
    }
    const bool grey = color_ == 0 || color_ == 4;
    for (unsigned c = 0; c < 3; c++) out[c] = uint8_t((samples[grey ? 0 : c] * 255 + maximum / 2) / maximum);
    out[3] = color_ == 4 || color_ == 6 ? uint8_t((samples[channels_ - 1] * 255 + maximum / 2) / maximum) : 255;
    if (trns_ && samples[0] == transparent_[0] && (grey || (samples[1] == transparent_[1] && samples[2] == transparent_[2])))
      out[3] = 0;
  }
  if (++row_index_ == height_) { raw_.reset(); data_ = nullptr; phase_ = Phase::DONE; }
}
PngDecoder::Phase PngDecoder::step() {
  switch (phase_) {
    case Phase::VALIDATE: validate_(); break;
    case Phase::INFLATE: inflate_(); break;
    case Phase::ROWS: row_(); break;
    default: break;
  }
  return phase_;
}
rendering::PixelView PngDecoder::pixels() const {
  if (phase_ != Phase::DONE) return {};
  return {rgba_.data(), rgba_.size(), width_ * 4U, width_, height_, rendering::PixelFormat::RGBA};
}
}  // namespace esphome::stream_deck::assets
