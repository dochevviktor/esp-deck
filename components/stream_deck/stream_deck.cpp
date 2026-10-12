#include "stream_deck.h"

#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include "esp_heap_caps.h"
#ifdef USE_STREAM_DECK_ASSETS
#include "esp_random.h"
#include "esp_log.h"
#include <new>
#endif
#ifdef USE_STREAM_DECK_RUNTIME_API
#include "asset_upload_esphome.h"
#endif

namespace esphome::stream_deck {
static const char *const TAG = "stream_deck";

void StreamDeck::setup() {
  transport_.set_input_epoch(scheduler_.input_epoch_address());
  if (connected_sensor_) connected_sensor_->publish_state(false);
  if (!transport_.setup()) {
    status_set_error(LOG_STR("USB host installation failed; check memory and ownership"));
    mark_failed();
  }
#ifdef USE_STREAM_DECK_ASSETS
  // IDF's verbose HTTP logs include raw header values/paths. Report only our
  // bounded status codes and counters; credentials/signed URLs are unsupported.
  esp_log_level_set("HTTP_CLIENT", ESP_LOG_NONE);
  if (asset_storage_.allocate(asset_memory_, sizeof(assets::Runtime))) {
    const uint64_t session = uint64_t(esp_random()) << 32 | esp_random();
    assets_ = new (asset_storage_.data()) assets::Runtime(session, scheduler_, asset_memory_, asset_policy_);
    assets_->fetcher.set_ca_certificate(asset_ca_);
  } else ESP_LOGE(TAG, "Asset service PSRAM allocation failed; USB/API remain independent");
#endif
#ifdef USE_STREAM_DECK_RUNTIME_API
  if (assets_) assets_->pipeline.uploads().set_verifier(assets::verify_upload);
  origin_preferences_ = global_preferences->make_preference<assets::OriginRecord>(0x45534432);
  assets::OriginRecord saved;
  if (origin_preferences_.load(&saved)) saved.policy(asset_policy_);
  if (assets_) assets_->provisioning.set_save([](void *context, const assets::OriginRecord &record) {
    auto *self = static_cast<StreamDeck *>(context);
    if (!self->origin_preferences_.save(&record)) return false;
    // The pinned ESP32 sync drains all pending records, including failures.
    // Verify our own NVS record: an unrelated preference can make sync return
    // false even though this explicit provisioning transaction was persisted.
    global_preferences->sync();
    assets::OriginRecord saved;
    return self->origin_preferences_.load(&saved) && saved.version == record.version &&
        saved.count == record.count && saved.origins == record.origins;
  }, this);
  if (session_sensor_ && assets_) session_sensor_->publish_state(visual_session());
#endif
}

void StreamDeck::on_shutdown() {
#ifdef USE_STREAM_DECK_ASSETS
  if (assets_) assets_->pipeline.stop();
  if (assets_ && assets_->provisioning.busy()) assets_->fetcher.cancel();
  asset_loop_.stop();
#endif
  transport_.shutdown();
}

void StreamDeck::dump_config() {
  ESP_LOGCONFIG(TAG, "Stream Deck Original 0FD9:0060, 15 keys, 72x72 native BMP");
  ESP_LOGCONFIG(TAG, "  Desired brightness: %u%% (no readback)", scheduler_.brightness());
  ESP_LOGCONFIG(TAG, "  Native USB host, UART0 logs; external unswitched VBUS");
  ESP_LOGCONFIG(TAG, "  USB protocol/hardware qualification pending; see docs/testing.md");
  ESP_LOGCONFIG(TAG, "  Stream initialization completed: %s", ready_ ? "yes" : "no");
  transport_.dump_status();
#ifdef USE_STREAM_DECK_ASSETS
  ESP_LOGCONFIG(TAG, "  Asset loader: PNG, configured origins only, validated TLS, no redirects/retries");
  ESP_LOGCONFIG(TAG, "  Visual boot session: %s", visual_session());
#endif
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
#ifdef USE_STREAM_DECK_RUNTIME_API
  if (assets_) assets_->inputs.sample(report, edges, millis());
#endif
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
#ifdef USE_STREAM_DECK_KEY_EVENTS
    // Only real tracker edges. No snapshot on API subscribe/reconnect and no
    // application backlog for a client that wasn't connected at the time.
    if (key_events_[key]) {
      if (edges.pressed & bit) key_events_[key]->trigger("press");
      if (edges.released & bit) key_events_[key]->trigger("release");
    }
#endif
    if (edges.pressed & bit) press_trigger_.trigger(key);
    if (edges.released & bit) release_trigger_.trigger(key);
  }
}

void StreamDeck::publish_diagnostics_() {
#ifdef USE_STREAM_DECK_ASSETS
  if (assets_)
    ESP_LOGD(TAG, "Assets: downloads=%u cache hits=%u failures=%u HTTP=%d graphics=%u peak=%u bytes",
             unsigned(assets_->pipeline.downloads()), unsigned(assets_->pipeline.cache_hits()),
             unsigned(assets_->pipeline.failures()), assets_->pipeline.last_http_status(),
             unsigned(asset_memory_.used_bytes()), unsigned(asset_memory_.peak_bytes()));
#endif
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
    InputReport input;
    // Drain in order: never collapse a short press/release to the latest state.
    while (transport_.pop_input(input)) publish_input_(input);
    Job completed;
    if (transport_.take_completion(completed)) scheduler_.complete(completed);
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
#ifdef USE_STREAM_DECK_ASSETS
  if (assets_) {
    assets_->pipeline.uploads().expire(now);
    if (assets_->provisioning.busy()) assets_->provisioning.loop(now);
    else assets_->pipeline.loop(now);
    if (assets_->pipeline.needs_cpu()) asset_loop_.start();
    else asset_loop_.stop();
  }
#endif
}
}  // namespace esphome::stream_deck
