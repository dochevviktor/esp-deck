#pragma once
namespace esphome::number {
class Number {
 public:
  virtual ~Number() = default;
  void publish_state(float) {}
 protected:
  virtual void control(float) = 0;
};
}
