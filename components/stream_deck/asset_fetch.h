#pragma once
#include "visual_state.h"

namespace esphome::stream_deck::assets {
// Both ordinary artwork and the smaller origin probe use this fetch contract.
// The caller's actual capacity is the limit, bounded above by the global cap.
inline bool valid_fetch_capacity(size_t capacity) { return capacity > 0 && capacity <= visual::MAX_ENCODED_BYTES; }
struct FetchResult {
  uint64_t token{0};
  visual::Error error{visual::Error::NONE};
  size_t bytes{0};
  int http_status{0};
};
// One request owns the caller's buffer until a matching completion is polled,
// including cancellation. Callbacks/worker code never touch Store or ImageRef.
class Fetcher {
 public:
  virtual ~Fetcher() = default;
  virtual bool start(std::string_view url, uint8_t *output, size_t capacity, uint64_t token) = 0;
  virtual bool poll(FetchResult &result) = 0;
  virtual void cancel() = 0;
};
}  // namespace esphome::stream_deck::assets
