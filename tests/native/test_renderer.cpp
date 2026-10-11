#include "renderer.h"
#include "render_memory.h"
#include "render_esphome.h"
#include "image_allocator.h"
#include "esp_heap_caps.h"

#include <algorithm>
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <map>
#include <string>
#include <vector>

using namespace esphome::stream_deck;
namespace r = esphome::stream_deck::rendering;
namespace v = esphome::stream_deck::visual;
namespace p = esphome::stream_deck::protocol;
namespace fake_heap {
bool fail = false;
size_t attempts = 0;
std::map<void *, size_t> live;
}
void *heap_caps_malloc(size_t size, uint32_t caps) {
  assert(caps == (MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  fake_heap::attempts++;
  if (fake_heap::fail) return nullptr;
  void *memory = std::malloc(size);
  assert(memory);
  fake_heap::live[memory] = size;
  return memory;
}
void heap_caps_free(void *memory) {
  assert(fake_heap::live.count(memory));
  std::memset(memory, 0xdd, fake_heap::live.at(memory));
  fake_heap::live.erase(memory);
  std::free(memory);
}

std::vector<uint8_t> read(const std::filesystem::path &path) {
  std::ifstream input(path, std::ios::binary);
  assert(input.good());
  return {std::istreambuf_iterator<char>(input), {}};
}
void finish(r::Renderer &renderer) {
  size_t steps = 0;
  while (renderer.busy()) { renderer.step(); assert(++steps <= 216); }
  assert(renderer.phase() == r::Phase::DONE);
}
std::vector<uint8_t> output(r::Renderer &renderer) {
  TestImageAllocator allocator;
  const auto image = renderer.copy_image(1, allocator);
  assert(image && p::valid_bmp(image->data, image->size));
  return {image->data, image->data + image->size};
}
std::array<uint8_t, 3> pixel(const std::vector<uint8_t> &image, unsigned x, unsigned y) {
  const auto *data = image.data() + 54 + (y * 72 + 71 - x) * 3;
  return {data[2], data[1], data[0]};
}

void test_orientation_and_work_slices() {
  r::Workspace workspace;
  r::Renderer renderer(workspace);
  TestImageAllocator allocator;
  const auto rgb = read("tests/fixtures/rendering/asymmetric.rgb");
  r::PixelView source{rgb.data(), rgb.size(), 216, 72, 72, r::PixelFormat::RGB};
  assert(renderer.begin({}, source));
  for (unsigned step = 0; step < 216; step++) {
    assert(renderer.busy() && !renderer.copy_image(1, allocator));
    assert(!renderer.begin({}, {}));  // No replacing a busy job or its borrowed pixels.
    renderer.step();
  }
  assert(renderer.phase() == r::Phase::DONE && allocator.allocations == 0);
  auto image = renderer.copy_image(1, allocator);
  const auto expected = read("tests/fixtures/asymmetric.native.bmp");
  assert(std::equal(expected.begin(), expected.end(), image->data));
  std::vector<uint8_t> report(p::REPORT_SIZE);
  for (int page = 1; page <= 2; page++) {
    assert(p::image_page(0, page, *image, report.data(), report.size()));
    assert(report == read("tests/fixtures/key_0_page_" + std::to_string(page) + ".bin"));
  }
  assert(renderer.background().bytes == r::RGB_BYTES);
  assert(std::equal(rgb.begin(), rgb.end(), renderer.background().data));
  auto overlap = renderer.background();
  assert(!renderer.begin({}, overlap) && renderer.error() == v::Error::DECODE_FAILED);
  assert(renderer.begin({}));
  finish(renderer);
  assert(std::equal(expected.begin(), expected.end(), image->data));  // Workspace reuse cannot mutate a retained image.
}

void test_alpha_and_scaling() {
  r::Workspace workspace;
  r::Renderer renderer(workspace);
  // Opaque red next to fully transparent blue: interpolated pixels must never
  // acquire blue. Contain leaves exactly 18 background rows above and below.
  const uint8_t rgba[] = {255, 0, 0, 255, 0, 0, 255, 0};
  v::State state; state.background_color = 0x00ff00;
  r::PixelView source{rgba, sizeof(rgba), 8, 2, 1, r::PixelFormat::RGBA};
  assert(renderer.begin(state, source)); finish(renderer);
  const auto image = output(renderer);
  const std::array<uint8_t, 3> green{0, 255, 0}, red{255, 0, 0};
  assert(pixel(image, 0, 17) == green && pixel(image, 0, 54) == green);
  assert(pixel(image, 0, 18) == red && pixel(image, 71, 18) == green);
  for (unsigned x = 0; x < 72; x++) {
    auto rgb = pixel(image, x, 36);
    assert(rgb[2] == 0 && unsigned(rgb[0]) + rgb[1] == 255);
  }
  const uint8_t half[] = {200, 100, 50, 128};
  state.background_color = 0x14283c;
  assert(renderer.begin(state, {half, 4, 4, 1, 1, r::PixelFormat::RGBA})); finish(renderer);
  const std::array<uint8_t, 3> half_expected{110, 70, 55};
  assert(pixel(output(renderer), 30, 30) == half_expected);
  const uint8_t bgra[] = {50, 100, 200, 128};
  assert(renderer.begin(state, {bgra, 4, 4, 1, 1, r::PixelFormat::BGRA})); finish(renderer);
  assert(pixel(output(renderer), 30, 30) == half_expected);
  // A three-pixel strip crops to the centre green pixel, without stretching
  // the whole strip to the tile or using a fixed decoder resize.
  const uint8_t strip[] = {255, 0, 0, 0, 255, 0, 0, 0, 255};
  state.fit = v::Fit::CROP;
  assert(renderer.begin(state, {strip, 9, 9, 3, 1, r::PixelFormat::RGB})); finish(renderer);
  auto cropped = output(renderer);
  assert(pixel(cropped, 36, 36)[1] >= 253);
  assert(pixel(cropped, 0, 0)[1] > 120 && pixel(cropped, 0, 0)[0] < 130);
}

void test_text_contract() {
  r::Workspace workspace;
  r::Renderer renderer(workspace);
  v::State state; state.background_color = 0xffffff;
  state.text.assign("Desk");
  assert(renderer.begin(state)); finish(renderer);
  auto labelled = output(renderer);
  bool black_outline = false;
  for (unsigned y = 0; y < 72; y++) for (unsigned x = 0; x < 72; x++) {
    auto rgb = pixel(labelled, x, y);
    if (rgb == std::array<uint8_t, 3>{0, 0, 0}) black_outline = true;
    if (x < 2 || x >= 70 || y >= 70) assert((rgb == std::array<uint8_t, 3>{255, 255, 255}));
  }
  assert(black_outline && !renderer.truncated() && renderer.substitutions() == 0);
  state.text.assign("Lamp \xf0\x9f\x92\xa1");
  assert(renderer.begin(state)); finish(renderer);
  assert(renderer.substitutions() == 1);
  auto fallback = output(renderer);
  state.text.assign("Lamp ?");
  assert(renderer.begin(state)); finish(renderer);
  assert(fallback == output(renderer));
  state.text.assign("Caf\xc3\xa9");
  for (unsigned size : {12, 16, 20}) {
    state.font = size;
    assert(renderer.begin(state)); finish(renderer);
    assert(renderer.substitutions() == 0 && !renderer.truncated());
    const auto *font = r::bundled_font(size);
    for (uint32_t c = 0x20; c <= 0xff; c++) {
      if (c >= 0x7f && c < 0xa0) continue;
      assert(font->find(c));
    }
  }
  state.text.assign("Supercalifragilistic desk controller display");
  assert(renderer.begin(state)); finish(renderer);
  assert(renderer.truncated());
  state.text.assign("A\nB\nC");
  assert(renderer.begin(state)); finish(renderer);
  assert(renderer.truncated());
  state.text.assign("");
  assert(renderer.begin(state)); finish(renderer);
  assert(!renderer.truncated());
  const auto blank = output(renderer);
  for (unsigned y = 0; y < 72; y++) for (unsigned x = 0; x < 72; x++)
    assert((pixel(blank, x, y) == std::array<uint8_t, 3>{255, 255, 255}));
}

void test_invalid_input_and_cancellation() {
  r::Workspace workspace;
  r::Renderer renderer(workspace);
  const uint8_t bytes[24]{};
  const r::PixelView good{bytes, sizeof(bytes), 12, 4, 2, r::PixelFormat::RGB};
  assert(r::valid_pixels(good));
  for (int kind = 0; kind < 9; kind++) {
    auto bad = good;
    switch (kind) {
      case 0: bad.data = nullptr; break;
      case 1: bad.width = 0; break;
      case 2: bad.height = 257; break;
      case 3: bad.width = std::numeric_limits<unsigned>::max(); break;
      case 4: bad.bytes--; break;
      case 5: bad.stride--; break;
      case 6: bad.stride = std::numeric_limits<size_t>::max(); break;
      case 7: bad.bytes = std::numeric_limits<size_t>::max(); break;
      case 8: bad.format = static_cast<r::PixelFormat>(255); break;
    }
    assert(!renderer.begin({}, bad));
    assert(renderer.phase() == r::Phase::FAILED && renderer.error() == v::Error::DECODE_FAILED);
  }
  v::State state;
  state.text.assign(std::string("bad\0text", 8));
  assert(!renderer.begin(state) && renderer.error() == v::Error::INVALID_TEXT);
  state.text.assign(std::string(49, 'x'));
  assert(!renderer.begin(state) && renderer.error() == v::Error::LIMIT_EXCEEDED);
  state.text.assign(""); state.font = 13;
  assert(!renderer.begin(state) && renderer.error() == v::Error::INVALID_FONT);
  state.font = 16; state.text_color = 0x1000000;
  assert(!renderer.begin(state) && renderer.error() == v::Error::INVALID_COLOR);
  for (unsigned count : {1, 73, 145}) {
    assert(renderer.begin({}, good));
    for (unsigned i = 0; i < count; i++) renderer.step();
    renderer.cancel();
    assert(renderer.step() == r::Phase::IDLE && !renderer.background().data);
  }
}

void test_store_commit_and_psram_failures() {
  TestImageAllocator images;
  Scheduler scheduler;
  v::Store store(1, scheduler);
  v::Command cmd;
  cmd.session = "0000000000000001"; cmd.revision = 1; cmd.fields = v::TEXT; cmd.text = "Old";
  assert(store.submit(cmd).accepted);
  v::RenderJob job;
  assert(store.next(job));
  r::Workspace workspace;
  r::Renderer renderer(workspace);
  assert(renderer.begin(job.state)); renderer.step();
  cmd.revision = 2; cmd.text = "New";
  assert(store.submit(cmd).accepted);
  finish(renderer);
  assert(!store.finish(job, renderer.copy_image(1, images)));
  assert(images.used_bytes() == 0);
  assert(store.next(job) && renderer.begin(job.state)); finish(renderer);
  images.fail = true;
  assert(!renderer.copy_image(2, images));
  assert(store.fail(job, v::Error::OUT_OF_MEMORY));
  assert(store.status(0)->rendered_revision == 0);
  cmd.revision = 3;
  images.fail = false;
  assert(store.submit(cmd).accepted && store.next(job) && renderer.begin(job.state)); finish(renderer);
  assert(store.finish(job, renderer.copy_image(3, images)));
  assert(store.status(0)->rendered_revision == 3 && images.used_bytes() > p::IMAGE_SIZE);

  {
    r::PsramWorkspace psram;
    fake_heap::fail = true;
    assert(!psram.acquire() && psram.get() == nullptr);
    r::PsramImageAllocator allocator;
    assert(!ImageRef::copy(p::blank_image(), 1, allocator) && allocator.used_bytes() == 0);
    fake_heap::fail = false;
    assert(psram.acquire());
    const auto calls = fake_heap::attempts;
    assert(psram.acquire() && fake_heap::attempts == calls);
    std::vector<ImageRef> refs;
    while (auto image = ImageRef::copy(p::blank_image(), refs.size() + 1, allocator)) {
      refs.push_back(std::move(image));
      assert(refs.size() < 40);
    }
    assert(refs.size() >= 30 && allocator.used_bytes() <= v::MAX_NATIVE_BYTES);
    refs.clear();
    assert(allocator.used_bytes() == 0);
  }
  assert(fake_heap::live.empty());
}

void test_esphome_adapter() {
  using namespace esphome::image;
  const uint8_t bgra[] = {3, 2, 1, 128};
  r::PixelView view;
  Image source(bgra, 1, 1, IMAGE_TYPE_RGB, TRANSPARENCY_ALPHA_CHANNEL);
  assert(r::from_esphome_image(source, view) && view.format == r::PixelFormat::BGRA && view.bytes == 4);
  Image rgb(bgra, 1, 1, IMAGE_TYPE_RGB, TRANSPARENCY_OPAQUE);
  assert(r::from_esphome_image(rgb, view) && view.format == r::PixelFormat::BGR && view.bytes == 3);
  for (auto source : {Image(bgra, 1, 1, IMAGE_TYPE_RGB, TRANSPARENCY_CHROMA_KEY),
                      Image(bgra, 1, 1, IMAGE_TYPE_RGB565, TRANSPARENCY_OPAQUE),
                      Image(nullptr, 1, 1, IMAGE_TYPE_RGB, TRANSPARENCY_OPAQUE),
                      Image(bgra, 257, 1, IMAGE_TYPE_RGB, TRANSPARENCY_OPAQUE)})
    assert(!r::from_esphome_image(source, view));
}

void snapshots(const std::filesystem::path &directory, bool record) {
  const auto rgb = read("tests/fixtures/rendering/asymmetric.rgb");
  std::vector<uint8_t> rgba(18 * 9 * 4);
  for (unsigned y = 0; y < 9; y++) for (unsigned x = 0; x < 18; x++) {
    const auto offset = (y * 18 + x) * 4;
    rgba[offset] = x * 15; rgba[offset + 1] = y * 31; rgba[offset + 2] = 220;
    rgba[offset + 3] = x < 6 ? 0 : x < 12 ? 128 : 255;
  }
  r::Workspace workspace;
  r::Renderer renderer(workspace);
  const auto save = [&](const char *name, const v::State &state, r::PixelView source = {}) {
    assert(renderer.begin(state, source)); finish(renderer);
    const auto result = output(renderer);
    const auto path = directory / (std::string(name) + ".native.bmp");
    if (record) {
      std::ofstream file(path, std::ios::binary);
      file.write(reinterpret_cast<const char *>(result.data()), result.size());
      assert(file.good());
    } else assert(result == read(path));
  };
  v::State state; state.background_color = 0x102030;
  save("empty", state);
  save("asymmetric", state, {rgb.data(), rgb.size(), 216, 72, 72, r::PixelFormat::RGB});
  const r::PixelView alpha{rgba.data(), rgba.size(), 18 * 4, 18, 9, r::PixelFormat::RGBA};
  save("alpha_contain", state, alpha);
  state.fit = v::Fit::CROP;
  save("alpha_crop", state, alpha);
  state.text.assign("Caf\xc3\xa9");
  for (unsigned size : {12, 16, 20}) {
    state.font = size;
    const auto name = "font_" + std::to_string(size);
    save(name.c_str(), state);
  }
  state.font = 16; state.text.assign("Desk\nReady");
  save("two_lines", state);
  state.text.assign("Supercalifragilistic desk controller display");
  save("truncated", state);
  state.text.assign("Lamp \xf0\x9f\x92\xa1");
  save("unsupported", state);
  state.text.assign("Desk"); state.text_color = 0xffdc40; state.outline_color = 0;
  save("combined", state, {rgb.data(), rgb.size(), 216, 72, 72, r::PixelFormat::RGB});
}

int main(int argc, char **argv) {
  test_orientation_and_work_slices();
  test_alpha_and_scaling();
  test_text_contract();
  test_invalid_input_and_cancellation();
  test_store_commit_and_psram_failures();
  test_esphome_adapter();
  if (argc == 3 && std::string(argv[1]) == "--record") snapshots(argv[2], true);
  else { assert(argc == 1); snapshots("tests/fixtures/rendering", false); }
  std::cout << "Renderer, font, source bounds, PSRAM ownership and native output tests passed\n";
}
