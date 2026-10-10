#pragma once

#include "scheduler.h"
#include "usb_transport.h"
#include "esphome/core/automation.h"
#include "esphome/core/component.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/number/number.h"
#include "esphome/components/sensor/sensor.h"

namespace esphome::stream_deck {

class StreamDeck : public Component {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;
  void on_shutdown() override { transport_.shutdown(); }
  float get_setup_priority() const override { return setup_priority::HARDWARE; }
  void set_key_sensor(uint8_t key, binary_sensor::BinarySensor *sensor) { keys_[key] = sensor; }
  void set_connected_sensor(binary_sensor::BinarySensor *sensor) { connected_sensor_ = sensor; }
  void set_error_sensor(sensor::Sensor *sensor) { error_sensor_ = sensor; }
  void set_overflow_sensor(sensor::Sensor *sensor) { overflow_sensor_ = sensor; }
  void set_high_water_sensor(sensor::Sensor *sensor) { high_water_sensor_ = sensor; }
  void set_heap_sensor(sensor::Sensor *sensor) { heap_sensor_ = sensor; }
  void set_min_heap_sensor(sensor::Sensor *sensor) { min_heap_sensor_ = sensor; }
  void set_input_report_id(int id) { transport_.set_input_report_id(id); }
  bool set_image(int key, const NativeImage *image) { return scheduler_.set_image(key, image); }
  bool set_brightness(float percent) { return scheduler_.set_brightness(percent); }
  uint8_t brightness() const { return scheduler_.brightness(); }
  void redraw() { scheduler_.redraw(); }
  Trigger<uint8_t> *get_press_trigger() { return &press_trigger_; }
  Trigger<uint8_t> *get_release_trigger() { return &release_trigger_; }

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
  bool attached_{false}, ready_{false};
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
