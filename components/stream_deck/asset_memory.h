#pragma once
#include "runtime_image.h"
#include <utility>

namespace esphome::stream_deck::assets {
// All graphics sub-pools charge the same root; operations stay on the main loop.
class Pool final : public ImageAllocator {
 public:
  Pool(ImageAllocator &root, size_t limit) : ImageAllocator(limit), root_(root) {}
 protected:
  void *allocate_(size_t size) override { return root_.allocate(size); }
  void deallocate_(void *memory, size_t size) override { root_.deallocate(memory, size); }
 private:
  ImageAllocator &root_;
};

class Buffer {
 public:
  Buffer() = default;
  Buffer(const Buffer &) = delete;
  Buffer &operator=(const Buffer &) = delete;
  Buffer(Buffer &&other) noexcept { *this = std::move(other); }
  Buffer &operator=(Buffer &&other) noexcept {
    if (this != &other) {
      reset();
      allocator_ = std::exchange(other.allocator_, nullptr);
      data_ = std::exchange(other.data_, nullptr);
      size_ = std::exchange(other.size_, 0);
    }
    return *this;
  }
  ~Buffer() { reset(); }
  bool allocate(ImageAllocator &allocator, size_t size) {
    // No implicit replacement while another stage may still borrow the bytes.
    if (data_ || size == 0) return false;
    auto *data = static_cast<uint8_t *>(allocator.allocate(size));
    if (!data) return false;
    data_ = data; size_ = size; allocator_ = &allocator;
    return true;
  }
  void reset() {
    if (data_) allocator_->deallocate(data_, size_);
    data_ = nullptr; size_ = 0; allocator_ = nullptr;
  }
  uint8_t *data() { return data_; }
  const uint8_t *data() const { return data_; }
  size_t size() const { return size_; }
  explicit operator bool() const { return data_ != nullptr; }
 private:
  ImageAllocator *allocator_{nullptr};
  uint8_t *data_{nullptr};
  size_t size_{0};
};
}  // namespace esphome::stream_deck::assets
