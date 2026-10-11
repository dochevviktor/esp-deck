#pragma once

#include "runtime_image.h"

namespace esphome::stream_deck {
using protocol::NativeImage;

enum class JobKind : uint8_t { RESET, BRIGHTNESS, PAGE1, PAGE2 };
struct Job {
  JobKind kind{JobKind::RESET};
  uint32_t generation{0};
  uint32_t sequence{0};
  uint8_t key{0};
  uint8_t brightness{30};
  ImageRef image{};
  uint64_t revision{0};
};

class Scheduler {
 public:
  Scheduler();
  void attach(uint32_t generation);
  void detach();
  bool set_image(int key, const ImageRef &image);
  // Compatibility entry point for firmware-lifetime static assets only.
  bool set_image(int key, const NativeImage *image);
  bool set_brightness(float percent);
  uint8_t brightness() const { return brightness_; }
  void redraw();
  bool next(Job &job);
  bool complete(const Job &job);
  bool initialized() const { return attached_ && !reset_pending_ && applied_brightness_ >= 0; }
  uint64_t image_revision(int key) const { return image_revisions_[key]; }
  bool applied(int key, uint64_t image_revision) const {
    return attached_ && applied_[key] && image_revisions_[key] == image_revision &&
        applied_revisions_[key] == revisions_[key];
  }
  uint32_t generation() const { return attached_ ? generation_ : 0; }
  // Sampled by the USB IN completion callback, before main-loop publication.
  const uint32_t *input_epoch_address() const { return &input_epoch_; }
  uint32_t input_epoch() const { return input_epoch_; }
  void input_barrier() { ++input_epoch_; }

 protected:
  std::array<ImageRef, protocol::KEY_COUNT> desired_{};
  std::array<ImageRef, protocol::KEY_COUNT> applied_{};
  std::array<uint64_t, protocol::KEY_COUNT> revisions_{};
  // Image identity and queued USB work are different: a forced redraw creates
  // new work but must not invalidate the Store's rendered image identity.
  std::array<uint64_t, protocol::KEY_COUNT> image_revisions_{};
  std::array<uint64_t, protocol::KEY_COUNT> applied_revisions_{};
  Job active_{};
  uint32_t generation_{0}, sequence_{0};
  uint32_t input_epoch_{1};
  uint8_t brightness_{30}, cursor_{0};
  int applied_brightness_{-1};
  bool attached_{false}, reset_pending_{true}, busy_{false}, page2_pending_{false};
};

struct InputReport { uint32_t generation; uint16_t mask; bool resync; uint32_t epoch{0}; };
class InputQueue {
 public:
  static constexpr size_t CAPACITY = 32;
  void push(uint32_t generation, uint16_t mask, uint32_t epoch = 0);
  bool pop(InputReport &report);
  void clear() { head_ = count_ = 0; }
  uint32_t overflows() const { return overflows_; }
  size_t high_water() const { return high_water_; }
 protected:
  std::array<InputReport, CAPACITY> reports_{};
  size_t head_{0}, count_{0}, high_water_{0};
  uint32_t overflows_{0};
};

struct KeyEdges { uint16_t pressed{0}; uint16_t released{0}; bool sync{false}; };
class KeyTracker {
 public:
  void reset() { synchronized_ = false; mask_ = armed_ = 0; }
  KeyEdges update(uint16_t mask, bool resync = false);
 protected:
  uint16_t mask_{0}, armed_{0};
  bool synchronized_{false};
};
}  // namespace esphome::stream_deck
