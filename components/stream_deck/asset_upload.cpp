#include "asset_upload.h"

#include <cstring>

namespace esphome::stream_deck::assets {
namespace {
int digit(char c) {
  if (c >= 'A' && c <= 'Z') return c - 'A';
  if (c >= 'a' && c <= 'z') return c - 'a' + 26;
  if (c >= '0' && c <= '9') return c - '0' + 52;
  if (c == '+') return 62;
  if (c == '/') return 63;
  return -1;
}
bool decode(std::string_view input, std::array<uint8_t, UploadCache::CHUNK_BYTES> &out, size_t &size) {
  size = 0;
  if (input.size() > ((out.size() + 2) / 3) * 4 || input.size() % 4) return false;
  for (size_t i = 0; i < input.size(); i += 4) {
    const int a = digit(input[i]), b = digit(input[i + 1]);
    const int c = input[i + 2] == '=' ? 0 : digit(input[i + 2]);
    const int d = input[i + 3] == '=' ? 0 : digit(input[i + 3]);
    const bool pad2 = input[i + 2] == '=', pad1 = input[i + 3] == '=';
    const size_t count = pad2 ? 1 : pad1 ? 2 : 3;
    if (a < 0 || b < 0 || c < 0 || d < 0 || size + count > out.size() ||
        (pad2 && (!pad1 || (b & 15))) || (pad1 && !pad2 && (c & 3)) ||
        ((pad1 || pad2) && i + 4 != input.size())) return false;
    out[size++] = uint8_t((a << 2) | (b >> 4));
    if (count > 1) out[size++] = uint8_t((b << 4) | (c >> 2));
    if (count > 2) out[size++] = uint8_t((c << 6) | d);
  }
  return true;
}
bool tile_png(const Buffer &png) {
  static const uint8_t header[] = {137,80,78,71,13,10,26,10, 0,0,0,13, 'I','H','D','R',
                                  0,0,0,72, 0,0,0,72};
  // Full CRC/chunk/deflate validation remains in the sliced production decoder.
  return png.size() >= 33 && std::memcmp(png.data(), header, sizeof(header)) == 0 && png.data()[28] == 0;
}
}
int UploadCache::find_(std::string_view id) const {
  for (size_t i = 0; i < entries_.size(); ++i)
    if (entries_[i].png && entries_[i].id.view() == id) return int(i);
  return -1;
}
int UploadCache::reserve_() const {
  int oldest = -1;
  for (size_t i = 0; i < entries_.size(); ++i) {
    const auto &entry = entries_[i];
    if (!entry.png) return int(i);
    bool pinned = false;
    for (size_t key = 0; key < protocol::KEY_COUNT; ++key)
      pinned |= visual::uploaded_asset_id(store_.desired(key)->image_url.view()) == entry.id.view();
    if (!pinned && (oldest < 0 || entry.used < entries_[oldest].used)) oldest = int(i);
  }
  return oldest;
}
void UploadCache::reset_() { receiving_.reset(); id_.assign(""); received_ = 0; }
void UploadCache::expire(uint32_t now) {
  if (receiving_ && (uint32_t(now - progress_) >= IDLE_MS || uint32_t(now - started_) >= TOTAL_MS)) reset_();
}
UploadCache::Response UploadCache::receive(std::string_view session, std::string_view id, int32_t offset,
                                          int32_t total, std::string_view base64, uint32_t now) {
  if (!store_.matches_session(session)) return {"wrong_session"};
  if (!visual::valid_asset_id(id)) return {"invalid_artwork_id"};
  if (total <= 0 || size_t(total) > MAX_BYTES || offset < 0 || offset > total) return {"upload_size"};
  if (!verify_) return {"upload_unavailable"};
  std::array<uint8_t, CHUNK_BYTES> chunk;
  size_t length;
  if (!decode(base64, chunk, length)) return {"invalid_chunk"};
  if (length > size_t(total - offset) || (length == 0 && offset != 0)) return {"upload_offset"};
  expire(now);
  const int cached = find_(id);
  if (cached >= 0) {
    auto &entry = entries_[cached];
    if (entry.png.size() != size_t(total) || (length && std::memcmp(entry.png.data() + offset, chunk.data(), length)))
      return {"upload_conflict"};
    entry.used = ++clock_;
    return {"none", size_t(total), true};
  }
  if (id != id_.view()) {
    if (offset != 0) return {"upload_offset"};
    reset_();
    if (!receiving_.allocate(memory_, size_t(total))) return {"out_of_memory"};
    id_.assign(id); started_ = progress_ = now;
  }
  if (receiving_.size() != size_t(total)) return {"upload_conflict"};
  if (size_t(offset) > received_) return {"upload_offset", received_};
  if (size_t(offset) < received_) {
    if (length > received_ - size_t(offset) || (length && std::memcmp(receiving_.data() + offset, chunk.data(), length)))
      return {"upload_conflict", received_};
    return {"none", received_};  // Identical retries and begin/probe are idempotent.
  }
  if (length) {
    std::memcpy(receiving_.data() + received_, chunk.data(), length);
    received_ += length; progress_ = now;
  }
  if (received_ != receiving_.size()) return {"none", received_};
  if (!verify_(receiving_.data(), receiving_.size(), id)) { reset_(); return {"upload_hash_mismatch"}; }
  if (!tile_png(receiving_)) { reset_(); return {"unsupported_png"}; }
  const int slot = reserve_();
  if (slot < 0) { reset_(); return {"out_of_memory"}; }
  auto &entry = entries_[slot];
  entry.png = std::move(receiving_); entry.id.assign(id); entry.used = ++clock_;
  reset_();
  return {"none", size_t(total), true};
}
bool UploadCache::copy(std::string_view id, Buffer &destination) {
  const int index = find_(id);
  if (index < 0) return false;
  auto &entry = entries_[index];
  if (!destination.allocate(memory_, entry.png.size())) return false;
  std::memcpy(destination.data(), entry.png.data(), entry.png.size());
  entry.used = ++clock_;
  return true;
}
size_t UploadCache::bytes() const {
  size_t total = receiving_.size();
  for (const auto &entry : entries_) total += entry.png.size();
  return total;
}
}  // namespace esphome::stream_deck::assets
