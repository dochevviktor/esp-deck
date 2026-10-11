#include "asset_policy.h"

namespace esphome::stream_deck::assets {
bool url_origin(std::string_view url, Origin &origin, bool origin_only) {
  if (!visual::valid_url(url)) return false;
  Origin candidate;
  candidate.tls = url.substr(0, 8) == "https://";
  const size_t start = candidate.tls ? 8 : 7;
  const auto slash = url.find('/', start);
  if (origin_only && slash != std::string_view::npos) return false;
  const auto authority = url.substr(start, slash == std::string_view::npos ? slash : slash - start);
  const auto colon = authority.find(':');
  const auto host = authority.substr(0, colon);
  char normalized[254]{};
  for (size_t i = 0; i < host.size(); i++)
    normalized[i] = host[i] >= 'A' && host[i] <= 'Z' ? host[i] - 'A' + 'a' : host[i];
  candidate.host.assign({normalized, host.size()});
  candidate.port = candidate.tls ? 443 : 80;
  if (colon != std::string_view::npos) {
    unsigned port = 0;
    for (char c : authority.substr(colon + 1)) port = port * 10 + unsigned(c - '0');
    candidate.port = uint16_t(port);
  }
  origin = candidate;
  return true;
}
bool OriginPolicy::add(std::string_view origin) {
  Origin parsed;
  if (!url_origin(origin, parsed, true)) return false;
  for (size_t i = 0; i < count_; i++) if (origins_[i] == parsed) return true;
  if (count_ == origins_.size()) return false;
  origins_[count_++] = parsed;
  return true;
}
bool OriginPolicy::allows(std::string_view url) const {
  Origin parsed;
  if (!url_origin(url, parsed)) return false;
  for (size_t i = 0; i < count_; i++) if (origins_[i] == parsed) return true;
  return false;
}
}  // namespace esphome::stream_deck::assets
