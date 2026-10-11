#pragma once
#include <cstddef>
#include <cstdint>

namespace esphome::image {
enum ImageType { IMAGE_TYPE_BINARY, IMAGE_TYPE_GRAYSCALE, IMAGE_TYPE_RGB, IMAGE_TYPE_RGB565 };
enum Transparency { TRANSPARENCY_OPAQUE, TRANSPARENCY_CHROMA_KEY, TRANSPARENCY_ALPHA_CHANNEL };
class Image {
 public:
  Image(const uint8_t *data, int width, int height, ImageType type, Transparency transparency)
      : data_(data), width_(width), height_(height), type_(type), transparency_(transparency) {}
  ImageType get_type() const { return type_; }
  int get_bpp() const { return type_ == IMAGE_TYPE_RGB ? (transparency_ == TRANSPARENCY_ALPHA_CHANNEL ? 32 : 24) : 16; }
  bool has_transparency() const { return transparency_ != TRANSPARENCY_OPAQUE; }
  int get_width() const { return width_; }
  int get_height() const { return height_; }
  size_t get_width_stride() const { return (width_ * get_bpp() + 7U) / 8; }
  const uint8_t *get_data_start() const { return data_; }
 private:
  const uint8_t *data_;
  int width_, height_;
  ImageType type_;
  Transparency transparency_;
};
}  // namespace esphome::image
