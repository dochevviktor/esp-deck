#include "scheduler.h"

#include <algorithm>
#include <cmath>

namespace esphome::stream_deck {
Scheduler::Scheduler() { desired_.fill(ImageRef::from_static(&protocol::blank_image())); }
void Scheduler::attach(uint32_t generation) {
  input_barrier();
  generation_ = generation;
  attached_ = reset_pending_ = true;
  busy_ = page2_pending_ = false;
  applied_brightness_ = -1;
  active_ = {};
  applied_.fill({});
  cursor_ = 0;
}
void Scheduler::detach() {
  input_barrier();
  attached_ = busy_ = page2_pending_ = false;
  // The transport's independent Job retains any image awaiting cancellation.
  active_ = {};
  applied_.fill({});
}
bool Scheduler::set_image(int key, const ImageRef &image) {
  if (protocol::wire_key(key) < 0 || !image)
    return false;
  if (desired_[key] != image) {
    desired_[key] = image;
    revisions_[key]++;
  }
  return true;
}
bool Scheduler::set_image(int key, const NativeImage *image) {
  return set_image(key, ImageRef::from_static(image));
}
bool Scheduler::set_brightness(float percent) {
  if (!std::isfinite(percent)) return false;
  brightness_ = uint8_t(std::lround(std::clamp(percent, 0.0f, 100.0f)));
  return true;
}
void Scheduler::redraw() { for (auto &revision : revisions_) revision++; }
bool Scheduler::next(Job &job) {
  if (!attached_ || busy_) return false;
  if (page2_pending_) {
    active_.kind = JobKind::PAGE2;
  } else {
    active_ = {};
    if (reset_pending_) active_.kind = JobKind::RESET;
    else if (applied_brightness_ != brightness_) {
      active_.kind = JobKind::BRIGHTNESS;
      active_.brightness = brightness_;
    } else {
      bool found = false;
      for (size_t n = 0; n < protocol::KEY_COUNT; n++) {
        const auto key = uint8_t((cursor_ + n) % protocol::KEY_COUNT);
        if (desired_[key] != applied_[key] || revisions_[key] != applied_revisions_[key]) {
          active_.kind = JobKind::PAGE1;
          active_.key = key;
          active_.image = desired_[key];
          active_.revision = revisions_[key];
          found = true;
          break;
        }
      }
      if (!found) return false;
    }
  }
  active_.generation = generation_;
  active_.sequence = ++sequence_;
  job = active_;
  busy_ = true;
  return true;
}
bool Scheduler::complete(const Job &job) {
  if (!attached_ || !busy_ || job.generation != generation_ || job.sequence != active_.sequence)
    return false;
  busy_ = false;
  switch (active_.kind) {
    case JobKind::RESET: reset_pending_ = false; break;
    case JobKind::BRIGHTNESS: applied_brightness_ = active_.brightness; break;
    case JobKind::PAGE1: page2_pending_ = true; break;
    case JobKind::PAGE2:
      input_barrier();
      page2_pending_ = false;
      applied_[active_.key] = active_.image;
      applied_revisions_[active_.key] = active_.revision;
      cursor_ = (active_.key + 1) % protocol::KEY_COUNT;
      break;
  }
  if (!page2_pending_) active_ = {};
  return true;
}

void InputQueue::push(uint32_t generation, uint16_t mask, uint32_t epoch) {
  bool resync = false;
  if (count_ == CAPACITY) {
    clear();
    overflows_++;
    resync = true;
  }
  reports_[(head_ + count_) % CAPACITY] = {generation, mask, resync, epoch};
  count_++;
  high_water_ = std::max(high_water_, count_);
}
bool InputQueue::pop(InputReport &report) {
  if (!count_) return false;
  report = reports_[head_];
  head_ = (head_ + 1) % CAPACITY;
  count_--;
  return true;
}
KeyEdges KeyTracker::update(uint16_t mask, bool resync) {
  KeyEdges edges{};
  mask &= 0x7fff;
  if (!synchronized_ || resync) {
    edges.sync = true;
    synchronized_ = true;
    armed_ = uint16_t(~mask) & 0x7fff;
  } else {
    edges.pressed = mask & ~mask_ & armed_;
    edges.released = mask_ & ~mask & armed_;
    armed_ |= uint16_t(~mask) & 0x7fff;
  }
  mask_ = mask;
  return edges;
}
}  // namespace esphome::stream_deck
