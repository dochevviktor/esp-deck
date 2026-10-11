#pragma once
#include "visual_state.h"

namespace esphome::stream_deck::assets {
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
