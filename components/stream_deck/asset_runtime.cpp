#include "asset_runtime.h"
#ifdef USE_STREAM_DECK_ASSETS
#include "esp_heap_caps.h"
namespace esphome::stream_deck::assets {
void *PsramMemory::allocate_(size_t size) { return heap_caps_malloc(size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT); }
void PsramMemory::deallocate_(void *memory, size_t) { heap_caps_free(memory); }
}
#endif
