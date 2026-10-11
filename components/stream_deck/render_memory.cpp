#include "render_memory.h"

#include "esp_heap_caps.h"
#include <new>

namespace esphome::stream_deck::rendering {
void *PsramImageAllocator::allocate_(size_t size) {
  return heap_caps_malloc(size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
}
void PsramImageAllocator::deallocate_(void *memory, size_t) { heap_caps_free(memory); }
bool PsramWorkspace::acquire() {
  if (workspace_ != nullptr) return true;
  auto *memory = heap_caps_malloc(sizeof(Workspace), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  if (memory == nullptr) return false;
  workspace_ = new (memory) Workspace{};
  return true;
}
PsramWorkspace::~PsramWorkspace() {
  if (workspace_ != nullptr) {
    workspace_->~Workspace();
    heap_caps_free(workspace_);
  }
}
}  // namespace esphome::stream_deck::rendering
