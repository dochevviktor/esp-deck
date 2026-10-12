#pragma once
#include "asset_fetch.h"
#include "asset_png.h"
#include "asset_policy.h"
#include "asset_upload.h"
#include <optional>

namespace esphome::stream_deck::assets {
class Pipeline {
 public:
  Pipeline(visual::Store &store, Fetcher &fetcher, ImageAllocator &memory, ImageAllocator &native,
           const OriginPolicy &policy);
  visual::Submission submit(const visual::Command &command);
  // Lifetime: drain a pending fetch before destroying this pipeline/its buffers.
  void loop(uint32_t now);
  void stop();
  bool idle() const { return phase_ == Phase::IDLE; }
  bool needs_cpu() const { return phase_ == Phase::PNG || phase_ == Phase::RENDER; }
  uint32_t cache_hits() const { return cache_hits_; }
  uint32_t downloads() const { return downloads_; }
  uint32_t failures() const { return failures_; }
  int last_http_status() const { return last_http_status_; }
  size_t cache_bytes() const { return cached_.used_bytes() + sizeof(entries_); }
  size_t native_bytes() const { return native_.used_bytes(); }
  UploadCache &uploads() { return uploads_; }
 private:
  static constexpr size_t CACHE_ENTRIES = protocol::KEY_COUNT + 1;
  enum class Phase : uint8_t { IDLE, FETCH, DRAIN, PNG, RENDER };
  struct Identity {
    visual::Text<visual::MAX_URL_BYTES> url;
    visual::Text<visual::MAX_IMAGE_REVISION_BYTES> revision;
    uint32_t background{0};
    visual::Fit fit{visual::Fit::CONTAIN};
    explicit Identity(const visual::State &state) : url(state.image_url), revision(state.image_revision),
        background(state.background_color), fit(state.fit) {}
    Identity() = default;
    bool operator==(const Identity &other) const {
      return url == other.url && revision == other.revision && background == other.background && fit == other.fit;
    }
  };
  struct Entry { Identity identity; Buffer pixels; uint64_t used{0}; uint16_t keys{0}; };
  static_assert(sizeof(Entry) * CACHE_ENTRIES + rendering::RGB_BYTES * CACHE_ENTRIES <= visual::MAX_BACKGROUND_BYTES);
  int find_(const Identity &identity);
  int reserve_();
  void begin_(uint32_t now);
  void fail_(visual::Error error);
  void retire_();
  void render_(rendering::PixelView source);
  void commit_();
  bool superseded_asset_() const;
  visual::Store &store_;
  Fetcher &fetcher_;
  ImageAllocator &memory_;
  const OriginPolicy &policy_;
  ImageAllocator &native_;  // Outlives every image retained by the USB scheduler.
  UploadCache uploads_;
  Pool cached_;
  Buffer workspace_, encoded_;
  PngDecoder decoder_;
  std::optional<rendering::Renderer> renderer_;
  std::array<Entry, CACHE_ENTRIES> entries_{};
  std::array<int8_t, protocol::KEY_COUNT> key_entries_{};
  visual::RenderJob job_{};
  Phase phase_{Phase::IDLE};
  int entry_{-1};
  bool cache_miss_{false}, stopped_{false};
  uint64_t clock_{0}, image_version_{0};
  uint32_t started_{0}, cache_hits_{0}, downloads_{0}, failures_{0};
  int last_http_status_{0};
};
}  // namespace esphome::stream_deck::assets
