#pragma once
#ifndef USE_HOST
#error "The virtual deck must never be compiled into device firmware"
#endif

#include "visual_api.h"
#include "esphome/core/component.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/event/event.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include <optional>
#include <cstdlib>
#include <sys/types.h>

namespace esphome::virtual_deck {
using namespace stream_deck;
uint64_t new_session();

class HostMemory final : public ImageAllocator {
 public:
  HostMemory() : ImageAllocator(visual::MAX_GRAPHICS_BYTES) {}
 protected:
  void *allocate_(size_t size) override { return std::malloc(size); }
  void deallocate_(void *memory, size_t) override { std::free(memory); }
};

class HostFetcher final : public assets::Fetcher {
 public:
  bool start(std::string_view url, uint8_t *output, size_t capacity, uint64_t token) override;
  bool poll(assets::FetchResult &result) override;
  void cancel() override;
  size_t received_bytes{0}, last_download_bytes{0};
 private:
  pid_t child_{-1};
  int pipe_{-1};
  uint8_t *output_{nullptr};
  size_t size_{0}, capacity_{0}, header_size_{0};
  std::array<uint8_t, 8> header_{};
  assets::FetchResult result_{};
  bool cancelled_{false}, eof_{false};
};

class VirtualDeck final : public Component {
 public:
  void set_session_sensor(text_sensor::TextSensor *sensor) { session_sensor_ = sensor; }
  void set_key(int key, binary_sensor::BinarySensor *state, event::Event *edge) {
    keys_[key] = state; events_[key] = edge;
  }
  void setup() override;
  void loop() override;
  void on_shutdown() override { fetcher_.cancel(); }
  visual::Api visual_api() { return {session_, &store_, &pipeline_}; }
 private:
  void input_(uint16_t mask, bool resync = false);
  void control_();
  void snapshot_();
  HostMemory memory_;
  assets::Pool native_{memory_, visual::MAX_NATIVE_BYTES};
  stream_deck::Scheduler scheduler_;
  uint64_t boot_{new_session()};
  visual::Store store_{boot_, scheduler_};
  HostFetcher fetcher_;
  assets::OriginPolicy policy_;
  assets::Pipeline pipeline_{store_, fetcher_, memory_, native_, policy_};
  KeyTracker tracker_;
  InputQueue input_queue_;
  std::array<binary_sensor::BinarySensor *, protocol::KEY_COUNT> keys_{};
  std::array<event::Event *, protocol::KEY_COUNT> events_{};
  text_sensor::TextSensor *session_sensor_{nullptr};
  std::string session_;
  std::array<uint32_t, protocol::KEY_COUNT> tile_hashes_{};
  std::array<uint32_t, protocol::KEY_COUNT> tile_uploads_{};
  std::optional<Job> active_;
  uint32_t generation_{1}, reports_{0}, failed_reports_{0}, due_{0}, delay_{0}, last_snapshot_{0};
  uint32_t control_sequence_{0}, edges_{0};
  int fail_page_{0};
  bool attached_{true};
};
}  // namespace esphome::virtual_deck
