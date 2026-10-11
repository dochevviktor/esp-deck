#pragma once
#include "visual_state.h"
#include <string>

namespace esphome::stream_deck::assets {
struct Origin {
  visual::Text<253> host;
  uint16_t port{0};
  bool tls{false};
  bool operator==(const Origin &other) const { return host == other.host && port == other.port && tls == other.tls; }
};
bool url_origin(std::string_view url, Origin &origin, bool origin_only = false);
class OriginPolicy {
 public:
  static constexpr size_t CAPACITY = 4;
  bool add(std::string_view origin);
  bool allows(std::string_view url) const;
  size_t size() const { return count_; }
  std::string at(size_t index) const {
    if (index >= count_) return {};
    const auto &origin = origins_[index];
    return std::string(origin.tls ? "https://" : "http://") + std::string(origin.host.view()) +
        ":" + std::to_string(origin.port);
  }
 private:
  std::array<Origin, CAPACITY> origins_{};
  size_t count_{0};
};
}  // namespace esphome::stream_deck::assets
