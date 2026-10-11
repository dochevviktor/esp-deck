#pragma once

#include "protocol.h"

namespace esphome::stream_deck {

// All references and allocation accounting belong to the main loop. Workers
// must hand results back to that loop before copying/releasing an ImageRef.
// The injected allocator must outlive every reference to its allocations.
class ImageAllocator {
 public:
  explicit ImageAllocator(size_t limit) : limit_(limit) {}
  virtual ~ImageAllocator() = default;
  ImageAllocator(const ImageAllocator &) = delete;
  ImageAllocator &operator=(const ImageAllocator &) = delete;
  size_t used_bytes() const { return used_; }
  size_t limit_bytes() const { return limit_; }

 protected:
  // Return suitably aligned storage, or nullptr (no exceptions). On the ESP,
  // the renderer adapter must use PSRAM; USB retains its own internal buffers.
  virtual void *allocate_(size_t size) = 0;
  virtual void deallocate_(void *memory, size_t size) = 0;

 private:
  friend class ImageRef;
  void *allocate(size_t size);
  void deallocate(void *memory, size_t size);
  size_t limit_, used_{0};
};

// Immutable native BMP version. Copies retain storage; static assets require
// no allocation and must live for the firmware lifetime. Runtime data always
// enters through copy(), never through from_static().
class ImageRef {
 public:
  ImageRef() = default;
  static ImageRef from_static(const protocol::NativeImage *image);
  static ImageRef copy(const protocol::NativeImage &image, uint64_t version, ImageAllocator &allocator);
  ImageRef(const ImageRef &other);
  ImageRef(ImageRef &&other) noexcept;
  ImageRef &operator=(const ImageRef &other);
  ImageRef &operator=(ImageRef &&other) noexcept;
  ~ImageRef();
  const protocol::NativeImage *get() const { return image_; }
  const protocol::NativeImage *operator->() const { return image_; }
  const protocol::NativeImage &operator*() const { return *image_; }
  explicit operator bool() const { return image_ != nullptr; }
  uint64_t version() const;
  bool operator==(const ImageRef &other) const { return image_ == other.image_; }
  bool operator!=(const ImageRef &other) const { return !(*this == other); }

 private:
  struct Storage;
  void release_();
  const protocol::NativeImage *image_{nullptr};
  Storage *storage_{nullptr};
};
}  // namespace esphome::stream_deck
