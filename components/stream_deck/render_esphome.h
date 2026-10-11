#pragma once

#include "renderer.h"
#include "esphome/core/defines.h"

#ifdef USE_IMAGE
#include "esphome/components/image/image.h"

namespace esphome::stream_deck::rendering {
// Static Image and completed RuntimeImage share this interface. Accept the
// pinned RGB/BGR and RGB+alpha/BGRA layouts only, never chroma-key or RGB565.
// The image owns the source pixels until rendering completes/cancels. P3 must
// separately validate and bound the encoded input before creating that image.
inline bool from_esphome_image(const image::Image &image, PixelView &view) {
  if (image.get_type() != image::IMAGE_TYPE_RGB ||
      (image.get_bpp() != 24 && image.get_bpp() != 32) ||
      (image.get_bpp() == 24 && image.has_transparency())) return false;
  const auto width = image.get_width(), height = image.get_height();
  if (width <= 0 || height <= 0 || width > int(visual::MAX_SOURCE_DIMENSION) ||
      height > int(visual::MAX_SOURCE_DIMENSION)) return false;
  const auto stride = image.get_width_stride();
  PixelView candidate{image.get_data_start(), stride * height, stride, unsigned(width), unsigned(height),
                      image.get_bpp() == 24 ? PixelFormat::BGR : PixelFormat::BGRA};
  if (!valid_pixels(candidate)) return false;
  view = candidate;
  return true;
}
}  // namespace esphome::stream_deck::rendering
#endif
