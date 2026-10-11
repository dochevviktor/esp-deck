#pragma once
#include "asset_fetch.h"
#include <atomic>

namespace esphome::stream_deck::assets {
// Runs only on the dedicated worker. A matching result transfers buffer
// ownership back after HTTP/transport cleanup, never before.
FetchResult fetch_http(const char *url, uint8_t *output, size_t capacity, uint64_t token,
                       const std::atomic<bool> &cancelled, const char *ca_certificate = nullptr);

class HttpFetcher final : public Fetcher {
 public:
  bool start(std::string_view url, uint8_t *output, size_t capacity, uint64_t token) override;
  bool poll(FetchResult &result) override;
  void cancel() override { cancelled_.store(true, std::memory_order_release); }
  void set_ca_certificate(const char *certificate) { ca_certificate_ = certificate; }
 private:
  static void task_(void *arg);
  enum State : unsigned { IDLE, ACTIVE, FINISHED };
  std::atomic<unsigned> state_{IDLE};
  std::atomic<bool> cancelled_{false};
  void *task_handle_{nullptr};
  visual::Text<visual::MAX_URL_BYTES> url_;
  uint8_t *output_{nullptr};
  size_t capacity_{0};
  uint64_t token_{0};
  FetchResult result_{};
  const char *ca_certificate_{nullptr};
};
}  // namespace esphome::stream_deck::assets
