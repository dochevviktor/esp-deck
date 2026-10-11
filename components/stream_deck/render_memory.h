#pragma once

#include "renderer.h"

namespace esphome::stream_deck::rendering {

// No internal-heap fallback: failure leaves the current tile unchanged. The
// allocator must outlive Scheduler/Store and every image it allocated.
class PsramImageAllocator final : public ImageAllocator {
 public:
  PsramImageAllocator() : ImageAllocator(visual::MAX_NATIVE_BYTES) {}
 protected:
  void *allocate_(size_t size) override;
  void deallocate_(void *memory, size_t size) override;
};

class PsramWorkspace {
 public:
  PsramWorkspace() = default;
  ~PsramWorkspace();
  PsramWorkspace(const PsramWorkspace &) = delete;
  PsramWorkspace &operator=(const PsramWorkspace &) = delete;
  // Call after PSRAM initialization, not during static construction. Exactly
  // one allocation, reused for successive tiles; this owner outlives Renderer.
  bool acquire();
  Workspace *get() const { return workspace_; }
 private:
  Workspace *workspace_{nullptr};
};
}  // namespace esphome::stream_deck::rendering
