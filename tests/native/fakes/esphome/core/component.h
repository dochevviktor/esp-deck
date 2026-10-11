#pragma once
#include "esphome/core/defines.h"
namespace esphome {
namespace setup_priority { constexpr float HARDWARE = 800; }
class Component {
 public:
  virtual ~Component() = default;
  virtual void setup() {}
  virtual void loop() {}
  virtual void dump_config() {}
  virtual void on_shutdown() {}
  virtual float get_setup_priority() const { return 0; }
  void status_set_error(const char *) {}
  void mark_failed() {}
};
}
