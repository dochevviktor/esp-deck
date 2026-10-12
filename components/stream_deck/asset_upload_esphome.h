#pragma once
#include "esphome/components/sha256/sha256.h"
#include <string_view>

namespace esphome::stream_deck::assets {
inline bool verify_upload(const uint8_t *data, size_t size, std::string_view expected) {
  // Keep the hardware SHA object and aligned digest in one stack frame.
  sha256::SHA256 hash;
  hash.init(); hash.add(data, size); hash.calculate();
  return hash.equals_hex(std::string(expected).c_str());
}
}
