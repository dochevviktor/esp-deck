#pragma once

#include "runtime_image.h"

#include <cassert>
#include <cstdlib>
#include <cstring>
#include <map>

// Fails explicitly, poisons freed memory and checks every owned allocation.
class TestImageAllocator : public esphome::stream_deck::ImageAllocator {
 public:
  explicit TestImageAllocator(size_t limit = 512 * 1024) : ImageAllocator(limit) {}
  ~TestImageAllocator() override { assert(live.empty() && used_bytes() == 0); }
  bool fail{false};
  size_t allocations{0}, frees{0};
  std::map<void *, size_t> live;

 protected:
  void *allocate_(size_t size) override {
    if (fail) return nullptr;
    void *memory = std::malloc(size);
    assert(memory);
    live[memory] = size;
    allocations++;
    return memory;
  }
  void deallocate_(void *memory, size_t size) override {
    assert(live.at(memory) == size);
    live.erase(memory);
    std::memset(memory, 0xdd, size);
    std::free(memory);
    frees++;
  }
};
