#pragma once
#include <string>
#include <vector>
namespace esphome::event {
class Event {
 public:
  void trigger(const std::string &type) { events.push_back(type); }
  std::vector<std::string> events;
};
}
