#pragma once
#include <vector>
namespace esphome::binary_sensor {
class BinarySensor {
 public:
  bool has_state() const { return valid; }
  void invalidate_state() { valid = false; }
  void set_trigger_on_initial_state(bool) {}
  void publish_initial_state(bool value) { valid = true; state = value; initial.push_back(value); }
  void publish_state(bool value) { valid = true; state = value; changes.push_back(value); }
  bool valid{false}, state{false};
  std::vector<bool> initial, changes;
};
}
#define LOG_BINARY_SENSOR(prefix, type, sensor) ((void) (sensor))
