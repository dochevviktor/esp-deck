#pragma once

#include "asset_memory.h"
#include "visual_state.h"

namespace esphome::stream_deck::assets {
// One receiving file and sixteen immutable PNGs, all charged to the graphics
// budget. The fifteen desired keys pin their sources; render jobs copy bytes
// before decoding so replacing an unreferenced entry cannot invalidate them.
class UploadCache {
 public:
  static constexpr size_t MAX_BYTES = 32768, CHUNK_BYTES = 1024, CAPACITY = protocol::KEY_COUNT + 1;
  static constexpr uint32_t IDLE_MS = 15000, TOTAL_MS = 60000;
  using Verify = bool (*)(const uint8_t *, size_t, std::string_view);
  struct Response {
    const char *error{"none"};
    size_t received{0};
    bool complete{false};
    template<typename Object> void write(Object root) const {
      root["accepted"] = std::string_view(error) == "none";
      root["error"] = error; root["received"] = received; root["complete"] = complete;
    }
  };
  UploadCache(visual::Store &store, ImageAllocator &memory) : store_(store), memory_(memory) {}
  void set_verifier(Verify verify) { verify_ = verify; }
  Response receive(std::string_view session, std::string_view id, int32_t offset, int32_t total,
                   std::string_view base64, uint32_t now);
  void expire(uint32_t now);
  bool contains(std::string_view id) const { return find_(id) >= 0; }
  bool copy(std::string_view id, Buffer &destination);
  size_t bytes() const;
 private:
  struct Entry { visual::Text<64> id; Buffer png; uint64_t used{0}; };
  int find_(std::string_view id) const;
  int reserve_() const;
  void reset_();
  visual::Store &store_;
  ImageAllocator &memory_;
  Verify verify_{nullptr};
  std::array<Entry, CAPACITY> entries_{};
  Buffer receiving_;
  visual::Text<64> id_;
  size_t received_{0};
  uint32_t started_{0}, progress_{0};
  uint64_t clock_{0};
};
}  // namespace esphome::stream_deck::assets
