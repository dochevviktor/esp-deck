#pragma once
#include "asset_pipeline.h"
#include <vector>

namespace esphome::stream_deck::assets {
struct OriginRecord {
  uint32_t version{1};
  uint8_t count{0};
  std::array<std::array<char, 272>, OriginPolicy::CAPACITY> origins{};
  bool policy(OriginPolicy &result) const {
    if (version != 1 || count == 0 || count > origins.size()) return false;
    OriginPolicy candidate;
    for (size_t i = 0; i < count; ++i) {
      const auto end = std::memchr(origins[i].data(), 0, origins[i].size());
      if (!end || !candidate.add({origins[i].data(), size_t(static_cast<const char *>(end) - origins[i].data())}))
        return false;
    }
    result = candidate; return true;
  }
};

// Shares the existing bounded fetcher. Pipeline work is paused only while this
// explicit provisioning transaction owns it; USB/API processing continues.
class OriginProvisioner {
 public:
  using Save = bool (*)(void *, const OriginRecord &);
  OriginProvisioner(OriginPolicy &policy, Pipeline &pipeline, Fetcher &fetcher, ImageAllocator &memory)
      : policy_(policy), pipeline_(pipeline), fetcher_(fetcher), decoder_(memory) {}
  void set_save(Save save, void *context) { save_ = save; context_ = context; }
  const char *begin(std::string_view text, std::string_view url, uint32_t now) {
    if (text.empty() || text.size() > 1088) return "invalid_origins";
    std::vector<std::string> origins;
    while (!text.empty()) {
      if (origins.size() == OriginPolicy::CAPACITY) return "invalid_origins";
      const auto end = text.find('\n');
      origins.emplace_back(text.substr(0, end));
      if (end == std::string_view::npos) break;
      text.remove_prefix(end + 1);
      if (text.empty()) return "invalid_origins";
    }
    return begin(origins, url, now);
  }
  const char *begin(const std::vector<std::string> &origins, std::string_view url, uint32_t now) {
    if (busy_ || !pipeline_.idle()) return "busy";
    if (origins.empty() || origins.size() > OriginPolicy::CAPACITY) return "invalid_origins";
    OriginPolicy candidate;
    for (const auto &origin : origins) if (!candidate.add(origin)) return "invalid_origins";
    if (!candidate.allows(url)) return "origin_not_allowed";
    record_ = {}; record_.count = candidate.size();
    for (size_t i = 0; i < candidate.size(); ++i) {
      const auto value = candidate.at(i);
      std::memcpy(record_.origins[i].data(), value.c_str(), value.size() + 1);
    }
    if (!fetcher_.start(url, buffer_.data(), buffer_.size(), ++token_)) return "fetch_failed";
    started_ = now; busy_ = true; decoding_ = draining_ = false; status_ = "testing";
    return "none";
  }
  bool busy() const { return busy_; }
  const char *status() const { return status_; }
  void loop(uint32_t now) {
    if (!busy_) return;
    if (!decoding_) {
      if (!draining_ && uint32_t(now - started_) >= visual::FETCH_TIMEOUT_MS) {
        fetcher_.cancel(); draining_ = true; status_ = "fetch_timeout";
      }
      FetchResult result;
      if (!fetcher_.poll(result) || result.token != token_) return;
      if (draining_) { busy_ = false; return; }
      if (result.error != visual::Error::NONE) { finish_(visual::error_name(result.error)); return; }
      if (result.bytes > buffer_.size() || !decoder_.begin(buffer_.data(), result.bytes)) {
        finish_("decode_failed"); return;
      }
      decoding_ = true;
    }
    const auto phase = decoder_.step();
    if (phase == PngDecoder::Phase::FAILED) { finish_("decode_failed"); return; }
    if (phase != PngDecoder::Phase::DONE) return;
    if (!save_ || !save_(context_, record_)) { finish_("storage_failed"); return; }
    record_.policy(policy_);
    finish_("verified");
  }
 private:
  void finish_(const char *status) { status_ = status; decoder_.cancel(); busy_ = decoding_ = false; }
  OriginPolicy &policy_;
  Pipeline &pipeline_;
  Fetcher &fetcher_;
  PngDecoder decoder_;
  OriginRecord record_;
  std::array<uint8_t, 32768> buffer_{};
  Save save_{nullptr}; void *context_{nullptr};
  uint64_t token_{0}; uint32_t started_{0};
  bool busy_{false}, decoding_{false}, draining_{false};
  const char *status_{"idle"};
};
}  // namespace esphome::stream_deck::assets
