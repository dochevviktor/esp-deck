#include "stream_deck.h"

#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include "esp_heap_caps.h"

namespace esphome::stream_deck {
static const char *const TAG = "stream_deck";

void StreamDeck::setup() {
  if (connected_sensor_) connected_sensor_->publish_state(false);
  if (!transport_.setup()) {
    status_set_error(LOG_STR("USB host installation failed; check memory and ownership"));
    mark_failed();
  }
}

void StreamDeck::dump_config() {
  ESP_LOGCONFIG(TAG, "Stream Deck Original 0FD9:0060, 15 keys, 72x72 native BMP");
  ESP_LOGCONFIG(TAG, "  Desired brightness: %u%% (no readback)", scheduler_.brightness());
  ESP_LOGCONFIG(TAG, "  Native USB host, UART0 logs; external unswitched VBUS");
  ESP_LOGCONFIG(TAG, "  USB protocol/hardware qualification pending; see docs/testing.md");
  LOG_BINARY_SENSOR("  ", "USB ready", connected_sensor_);
}

void StreamDeck::disconnect_() {
  attached_ = ready_ = false;
  scheduler_.detach();
  tracker_.reset();
  if (connected_sensor_) connected_sensor_->publish_state(false);
  // Invalidation updates availability without a fabricated release transition.
  for (auto *key : keys_) if (key != nullptr) key->invalidate_state();
}

void StreamDeck::publish_input_(const InputReport &report) {
  if (report.generation != generation_) return;
  const auto edges = tracker_.update(report.mask, report.resync);
  for (uint8_t key = 0; key < protocol::KEY_COUNT; key++) {
    const uint16_t bit = uint16_t(1U << key);
    const bool pressed = (report.mask & bit) != 0;
    auto *sensor = keys_[key];
    const bool edge = ((edges.pressed | edges.released) & bit) != 0;
    if (sensor != nullptr) {
      if (edges.sync || (!edge && (!sensor->has_state() || sensor->state != pressed))) {
        // Suppress automation for initial/overflow synchronization and the first
        // release of a key that was already held when the session started.
        sensor->set_trigger_on_initial_state(false);
        sensor->publish_initial_state(pressed);
      } else if (edge) {
        sensor->publish_state(pressed);
      }
    }
    if (edges.pressed & bit) press_trigger_.trigger(key);
    if (edges.released & bit) release_trigger_.trigger(key);
  }
}

void StreamDeck::publish_diagnostics_() {
  const auto errors = transport_.errors();
  const auto malformed = transport_.malformed_inputs();
  const auto overflows = transport_.overflows();
  if (error_sensor_) error_sensor_->publish_state(errors + malformed);
  if (overflow_sensor_) overflow_sensor_->publish_state(overflows);
  if (high_water_sensor_) high_water_sensor_->publish_state(transport_.queue_high_water());
  if (heap_sensor_) heap_sensor_->publish_state(heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
  if (min_heap_sensor_) min_heap_sensor_->publish_state(heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
  if (errors != last_errors_ || malformed != last_malformed_ || overflows != last_overflows_) {
    ESP_LOGW(TAG, "Totals: USB errors=%lu malformed inputs=%lu queue overflows=%lu high-water=%u",
             static_cast<unsigned long>(errors), static_cast<unsigned long>(malformed),
             static_cast<unsigned long>(overflows), unsigned(transport_.queue_high_water()));
    last_errors_ = errors;
    last_malformed_ = malformed;
    last_overflows_ = overflows;
  }
}

void StreamDeck::loop() {
  const auto now = millis();
  transport_.loop(now);
  if (attached_ && (!transport_.attached() || transport_.generation() != generation_)) disconnect_();
  if (!attached_ && transport_.attached()) {
    generation_ = transport_.generation();
    scheduler_.attach(generation_);
    tracker_.reset();
    attached_ = true;
  }
  if (attached_) {
    Job completed;
    if (transport_.take_completion(completed)) scheduler_.complete(completed);
    InputReport input;
    // Drain in order: never collapse a short press/release to the latest state.
    while (transport_.pop_input(input)) publish_input_(input);
    Job job;
    if (scheduler_.next(job) && !transport_.send(job, now)) disconnect_();
    if (attached_ && !ready_ && scheduler_.initialized()) {
      ready_ = true;
      if (connected_sensor_) connected_sensor_->publish_state(true);
      ESP_LOGI(TAG, "USB ready: full 8191-byte stream reset and brightness completed");
    }
  }
  if (now - last_diagnostics_ >= 10000) {
    last_diagnostics_ = now;
    publish_diagnostics_();
  }
}
}  // namespace esphome::stream_deck
