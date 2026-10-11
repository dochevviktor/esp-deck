#pragma once
#include "asset_pipeline.h"
#include "asset_http.h"
#include "esphome/core/defines.h"

#ifdef USE_STREAM_DECK_ASSETS
namespace esphome::stream_deck::assets {
class PsramMemory final : public ImageAllocator {
 public:
  PsramMemory() : ImageAllocator(visual::MAX_GRAPHICS_BYTES) {}
 protected:
  void *allocate_(size_t size) override;
  void deallocate_(void *memory, size_t size) override;
};
// Boot-lifetime service, like the USB host. Shutdown cancels and retains live
// workers/buffers until retirement or MCU reboot; never delete a running task.
struct Runtime {
  Runtime(uint64_t session, Scheduler &scheduler, ImageAllocator &memory, const OriginPolicy &policy)
      : images(memory, visual::MAX_NATIVE_BYTES), store(session, scheduler), pipeline(store, fetcher, memory, images, policy) {
    static const char hex[] = "0123456789abcdef";
    for (int n = 15; n >= 0; n--) { session_text[n] = hex[session & 15]; session >>= 4; }
  }
  Pool images;
  visual::Store store;
  HttpFetcher fetcher;
  Pipeline pipeline;
  char session_text[17]{};
};
}  // namespace esphome::stream_deck::assets
#endif
