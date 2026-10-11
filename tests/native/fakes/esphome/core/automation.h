#pragma once
#include <tuple>
#include <vector>
namespace esphome {
template<typename... Args> class Trigger {
 public:
  void trigger(Args... args) { calls.emplace_back(args...); }
  std::vector<std::tuple<Args...>> calls;
};
}
