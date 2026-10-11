// CLI oracle for actual HA-normalized uploads: production decoder, exact RGBA.
#include "asset_png.h"
#include "image_allocator.h"
#include <cassert>
#include <fstream>
#include <iterator>
#include <vector>
using namespace esphome::stream_deck;
std::vector<uint8_t> read(const char *path) {
  std::ifstream file(path, std::ios::binary); assert(file.good());
  return {std::istreambuf_iterator<char>(file), {}};
}
int main(int argc, char **argv) {
  assert(argc > 1 && argc % 2 == 1);
  TestImageAllocator allocator(visual::MAX_GRAPHICS_BYTES);
  assets::PngDecoder decoder(allocator);
  for (int i = 1; i < argc; i += 2) {
    const auto png = read(argv[i]), expected = read(argv[i + 1]);
    assert(png.size() <= 32768 && expected.size() == 72 * 72 * 4);
    assert(decoder.begin(png.data(), png.size()));
    unsigned steps = 0;
    while (decoder.phase() != assets::PngDecoder::Phase::DONE && decoder.phase() != assets::PngDecoder::Phase::FAILED) {
      decoder.step(); assert(++steps < 2500);
    }
    assert(decoder.phase() == assets::PngDecoder::Phase::DONE);
    const auto view = decoder.pixels();
    assert(view.width == 72 && view.height == 72 && view.bytes == expected.size());
    assert(std::equal(expected.begin(), expected.end(), view.data));
    decoder.cancel(); assert(allocator.used_bytes() == 0);
  }
}
