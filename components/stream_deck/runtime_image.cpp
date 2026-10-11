#include "runtime_image.h"

#include <cstring>
#include <new>
#include <utility>

namespace esphome::stream_deck {

struct ImageRef::Storage {
  size_t references{1};
  ImageAllocator *allocator;
  uint64_t version;
  const protocol::NativeImage image;
  Storage(ImageAllocator *allocator, uint64_t version, const uint8_t *data)
      : allocator(allocator), version(version), image(data, protocol::IMAGE_SIZE) {}
};

void *ImageAllocator::allocate(size_t size) {
  if (size > limit_ - used_) return nullptr;
  auto *memory = allocate_(size);
  if (memory != nullptr) used_ += size;
  return memory;
}
void ImageAllocator::deallocate(void *memory, size_t size) {
  deallocate_(memory, size);
  used_ -= size;
}

ImageRef ImageRef::from_static(const protocol::NativeImage *image) {
  ImageRef result;
  if (image != nullptr && protocol::valid_bmp(image->data, image->size)) result.image_ = image;
  return result;
}
ImageRef ImageRef::copy(const protocol::NativeImage &image, uint64_t version, ImageAllocator &allocator) {
  ImageRef result;
  if (version == 0 || !protocol::valid_bmp(image.data, image.size)) return result;
  // A single fallible allocation includes both the reference count and pixels.
  auto *memory = allocator.allocate(sizeof(Storage) + protocol::IMAGE_SIZE);
  if (memory == nullptr) return result;
  auto *bytes = static_cast<uint8_t *>(memory) + sizeof(Storage);
  std::memcpy(bytes, image.data, image.size);
  result.storage_ = new (memory) Storage(&allocator, version, bytes);
  result.image_ = &result.storage_->image;
  return result;
}
ImageRef::ImageRef(const ImageRef &other) : image_(other.image_), storage_(other.storage_) {
  if (storage_ != nullptr) storage_->references++;
}
ImageRef::ImageRef(ImageRef &&other) noexcept
    : image_(std::exchange(other.image_, nullptr)), storage_(std::exchange(other.storage_, nullptr)) {}
ImageRef &ImageRef::operator=(const ImageRef &other) {
  if (this == &other) return *this;
  // Retain first, including when two handles reference the same allocation.
  if (other.storage_ != nullptr) other.storage_->references++;
  release_();
  image_ = other.image_;
  storage_ = other.storage_;
  return *this;
}
ImageRef &ImageRef::operator=(ImageRef &&other) noexcept {
  if (this == &other) return *this;
  release_();
  image_ = std::exchange(other.image_, nullptr);
  storage_ = std::exchange(other.storage_, nullptr);
  return *this;
}
ImageRef::~ImageRef() { release_(); }
void ImageRef::release_() {
  if (storage_ != nullptr && --storage_->references == 0) {
    auto *allocator = storage_->allocator;
    storage_->~Storage();
    allocator->deallocate(storage_, sizeof(Storage) + protocol::IMAGE_SIZE);
  }
  image_ = nullptr;
  storage_ = nullptr;
}
uint64_t ImageRef::version() const { return storage_ == nullptr ? 0 : storage_->version; }

}  // namespace esphome::stream_deck
