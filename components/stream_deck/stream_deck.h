#pragma once

#include "scheduler.h"
#include "usb_transport.h"
#include "asset_runtime.h"
#include "visual_api.h"
#include "esphome/core/automation.h"
#include "esphome/core/component.h"
#include "esphome/core/hal.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/number/number.h"
#include "esphome/components/sensor/sensor.h"
#ifdef USE_STREAM_DECK_RUNTIME_API
#include "esphome/components/text_sensor/text_sensor.h"
#include "esphome/core/preferences.h"
#endif
#ifdef USE_STREAM_DECK_KEY_EVENTS
#include "esphome/components/event/event.h"
#endif

namespace esphome::stream_deck {

class StreamDeck : public Component {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;
  void on_shutdown() override;
  float get_setup_priority() const override { return setup_priority::HARDWARE; }
  void set_key_sensor(uint8_t key, binary_sensor::BinarySensor *sensor) { keys_[key] = sensor; }
  void set_connected_sensor(binary_sensor::BinarySensor *sensor) { connected_sensor_ = sensor; }
  void set_error_sensor(sensor::Sensor *sensor) { error_sensor_ = sensor; }
  void set_overflow_sensor(sensor::Sensor *sensor) { overflow_sensor_ = sensor; }
  void set_high_water_sensor(sensor::Sensor *sensor) { high_water_sensor_ = sensor; }
  void set_heap_sensor(sensor::Sensor *sensor) { heap_sensor_ = sensor; }
  void set_min_heap_sensor(sensor::Sensor *sensor) { min_heap_sensor_ = sensor; }
  void set_input_report_id(int id) { transport_.set_input_report_id(id); }
  void set_usb_diagnostics(bool enabled) { transport_.set_usb_diagnostics(enabled); }
  bool set_image(int key, const NativeImage *image) { return !runtime_visuals_ && scheduler_.set_image(key, image); }
  bool set_image(int key, const ImageRef &image) { return !runtime_visuals_ && scheduler_.set_image(key, image); }
  bool set_brightness(float percent) { return scheduler_.set_brightness(percent); }
  uint8_t brightness() const { return scheduler_.brightness(); }
  void redraw() { scheduler_.redraw(); }
  Trigger<uint8_t> *get_press_trigger() { return &press_trigger_; }
  Trigger<uint8_t> *get_release_trigger() { return &release_trigger_; }
#ifdef USE_STREAM_DECK_KEY_EVENTS
  void set_key_event(uint8_t key, event::Event *entity) { key_events_[key] = entity; }
#endif
#ifdef USE_STREAM_DECK_RUNTIME_API
  void set_visual_session_sensor(text_sensor::TextSensor *sensor) { session_sensor_ = sensor; runtime_visuals_ = true; }
  visual::Api visual_api() {
    return {visual_session(), assets_ ? &assets_->store : nullptr, assets_ ? &assets_->pipeline : nullptr};
  }
  template<typename Object> void capabilities(Object root) {
    visual::capabilities(root, asset_policy_);
    root["session"] = visual_session();
    root["origin_probe"] = assets_ ? assets_->provisioning.status() : "unavailable";
  }
  template<typename Object> void read_inputs(std::string_view session, std::string_view reader, int32_t ack, Object root) {
    root["session"] = visual_session(); root["accepted"] = false;
    if (!assets_ || !assets_->store.matches_session(session)) { root["error"] = "wrong_session"; return; }
    assets_->inputs.read(reader, ack, millis(), root);
  }
  template<typename Object> void upload_artwork(std::string_view session, std::string_view asset_id,
      int32_t offset, int32_t total_size, std::string_view data, Object root) {
    root["session"] = visual_session();
    if (!assets_) { root["accepted"] = false; root["error"] = "upload_unavailable"; return; }
    assets_->pipeline.uploads().receive(session, asset_id, offset, total_size, data, millis()).write(root);
  }
  template<typename Object> void provision_origins(std::string_view session, std::string_view origins,
                                                  std::string_view url, Object root) {
    root["session"] = visual_session();
    const char *error = !assets_ || !assets_->store.matches_session(session) ? "wrong_session" :
        assets_->provisioning.begin(origins, url, millis());
    root["accepted"] = std::string_view(error) == "none"; root["error"] = error;
  }
#endif
#ifdef USE_STREAM_DECK_ASSETS
  void add_asset_origin(const std::string &origin) { asset_policy_.add(origin); }
  void set_asset_ca(const char *certificate) { asset_ca_ = certificate; }
  const char *visual_session() const { return assets_ ? assets_->session_text : ""; }
  visual::Submission submit_visual(const visual::Command &command) {
    if (!assets_) return {false, visual::Error::OUT_OF_MEMORY};
    return assets_->pipeline.submit(command);
  }
  const visual::Status *visual_status(int key) const { return assets_ ? assets_->store.status(key) : nullptr; }
#endif

 protected:
  void disconnect_();
  void publish_input_(const InputReport &report);
  void publish_diagnostics_();
  Scheduler scheduler_{};
  USBTransport transport_{};
  KeyTracker tracker_{};
  std::array<binary_sensor::BinarySensor *, protocol::KEY_COUNT> keys_{};
  binary_sensor::BinarySensor *connected_sensor_{nullptr};
  sensor::Sensor *error_sensor_{nullptr}, *overflow_sensor_{nullptr}, *high_water_sensor_{nullptr};
  sensor::Sensor *heap_sensor_{nullptr}, *min_heap_sensor_{nullptr};
  Trigger<uint8_t> press_trigger_, release_trigger_;
  uint32_t generation_{0}, last_diagnostics_{0}, last_errors_{0}, last_malformed_{0}, last_overflows_{0};
  bool attached_{false}, ready_{false}, runtime_visuals_{false};
#ifdef USE_STREAM_DECK_KEY_EVENTS
  std::array<event::Event *, protocol::KEY_COUNT> key_events_{};
#endif
#ifdef USE_STREAM_DECK_RUNTIME_API
  text_sensor::TextSensor *session_sensor_{nullptr};
  ESPPreferenceObject origin_preferences_;
#endif
#ifdef USE_STREAM_DECK_ASSETS
  assets::OriginPolicy asset_policy_;
  assets::PsramMemory asset_memory_;
  assets::Buffer asset_storage_;
  assets::Runtime *assets_{nullptr};
  const char *asset_ca_{nullptr};
  HighFrequencyLoopRequester asset_loop_;
#endif
};

class DeckBrightness : public number::Number, public Component {
 public:
  void set_parent(StreamDeck *parent) { parent_ = parent; }
  void setup() override { publish_state(parent_->brightness()); }
 protected:
  void control(float value) override {
    if (parent_->set_brightness(value)) publish_state(parent_->brightness());
  }
  StreamDeck *parent_{nullptr};
};
}  // namespace esphome::stream_deck
