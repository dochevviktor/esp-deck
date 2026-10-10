#include "protocol.h"
#include "scheduler.h"

#include <cassert>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <string>
#include <vector>

using namespace esphome::stream_deck;
namespace p = esphome::stream_deck::protocol;

std::vector<uint8_t> fixture(const std::string &name) {
  std::ifstream input("tests/fixtures/" + name, std::ios::binary);
  assert(input.good());
  return {std::istreambuf_iterator<char>(input), {}};
}

void test_protocol() {
  const int mapping[] = {4, 3, 2, 1, 0, 9, 8, 7, 6, 5, 14, 13, 12, 11, 10};
  for (int k = 0; k < 15; k++) assert(p::wire_key(k) == mapping[k]);
  assert(p::wire_key(-1) == -1 && p::wire_key(15) == -1);
  std::vector<uint8_t> output(p::REPORT_SIZE);
  for (int percent : {0, 1, 50, 100}) {
    assert(p::brightness(float(percent), output.data(), output.size()));
    const auto expected = fixture("brightness_" + std::to_string(percent) + ".bin");
    assert(std::equal(expected.begin(), expected.end(), output.begin()));
  }
  assert(p::brightness(-10, output.data(), output.size()) && output[5] == 0);
  assert(p::brightness(500, output.data(), output.size()) && output[5] == 100);
  assert(p::brightness(50.4f, output.data(), output.size()) && output[5] == 50);
  assert(!p::brightness(std::numeric_limits<float>::quiet_NaN(), output.data(), output.size()));
  assert(!p::brightness(50, output.data(), 16));
  assert(p::device_reset(output.data(), output.size()));
  const auto reset = fixture("device_reset.bin");
  assert(std::equal(reset.begin(), reset.end(), output.begin()));
  assert(p::stream_reset(output.data(), output.size()));
  assert(output == fixture("stream_reset.bin"));
  const auto bytes = fixture("asymmetric.native.bmp");
  p::NativeImage image(bytes.data(), bytes.size());
  assert(p::valid_bmp(image.data, image.size));
  assert(p::valid_bmp(p::blank_image().data, p::blank_image().size));
  for (int key : {0, 4, 5, 10, 14}) for (int page : {1, 2}) {
    assert(p::image_page(key, page, image, output.data(), output.size()));
    assert(output == fixture("key_" + std::to_string(key) + "_page_" + std::to_string(page) + ".bin"));
  }
  for (int key : {-1, 15, 255}) assert(!p::image_page(key, 1, image, output.data(), output.size()));
  assert(!p::image_page(0, 0, image, output.data(), output.size()));
  assert(!p::image_page(0, 3, image, output.data(), output.size()));
  assert(!p::image_page(0, 1, image, output.data(), p::REPORT_SIZE - 1));
  assert(!p::valid_bmp(bytes.data(), bytes.size() - 1));
  assert(!p::valid_bmp(nullptr, bytes.size()));
  for (size_t offset : {0, 2, 6, 10, 14, 18, 22, 26, 28, 30, 34, 46, 50}) {
    auto bad = bytes;
    bad[offset] ^= 0x80;
    assert(!p::valid_bmp(bad.data(), bad.size()));
  }
  uint8_t setup[8];
  const uint8_t expected[] = {0x21, 0x09, 0x02, 0x02, 0x03, 0, 0xff, 0x1f};
  assert(p::set_report_setup(2, 2, 3, 8191, setup, sizeof(setup)));
  assert(std::equal(std::begin(expected), std::end(expected), setup));
  assert(p::CONTROL_SIZE == 8199);
  for (uint16_t mps : {8, 16, 32, 64}) {
    size_t remaining = p::REPORT_SIZE, total = 0;
    while (remaining) {
      size_t size = p::interrupt_chunk(remaining, mps);
      assert(size > 0 && size <= size_t(mps) * 32);
      if (size < remaining) assert(size % mps == 0);
      remaining -= size;
      total += size;
    }
    assert(total == 8191);
  }
  assert(p::interrupt_chunk(8191, 0) == 0);
}

void test_input() {
  uint8_t report[16]{};
  report[0] = 0x7d;  // Synthetic header, not a claim about the physical report ID.
  uint16_t mask = 0xbeef;
  for (int key = 0; key < 15; key++) {
    report[1 + p::wire_key(key)] = 1;
    assert(p::decode_input(report, sizeof(report), mask));
    assert(mask == uint16_t((1U << (key + 1)) - 1));
  }
  assert(!p::decode_input(report, 15, mask) && mask == 0x7fff);
  assert(!p::decode_input(report, 17, mask));
  assert(!p::decode_input(report, 16, mask, 1));
  assert(p::decode_input(report, 16, mask, 0x7d));
  report[3] = 2;
  assert(!p::decode_input(report, 16, mask) && mask == 0x7fff);
  KeyTracker tracker;
  assert(tracker.update(1).sync);
  assert(tracker.update(1).pressed == 0);
  assert(tracker.update(0).released == 0);  // Held at connection: ignore its release.
  assert(tracker.update(3).pressed == 3);
  assert(tracker.update(3).pressed == 0);
  assert(tracker.update(0).released == 3);
  tracker.reset();
  assert(tracker.update(4).sync);
  assert(tracker.update(0).released == 0);
  InputQueue queue;
  queue.push(1, 0); queue.push(1, 1); queue.push(1, 0);
  InputReport item{};
  for (int state : {0, 1, 0}) { assert(queue.pop(item)); assert(item.mask == state); }
  assert(!queue.pop(item));
  for (size_t i = 0; i <= InputQueue::CAPACITY; i++) queue.push(2, 1);
  assert(queue.overflows() == 1 && queue.high_water() == InputQueue::CAPACITY);
  assert(queue.pop(item) && item.resync && item.generation == 2);
}

void test_scheduler() {
  Scheduler scheduler;
  Job job{}, old{};
  assert(!scheduler.next(job));
  assert(!scheduler.set_image(15, &p::blank_image()));
  assert(scheduler.set_brightness(50.0f));
  scheduler.attach(1);
  assert(scheduler.next(job) && job.kind == JobKind::RESET);
  assert(!scheduler.next(old));
  old = job;
  assert(scheduler.complete(job));
  assert(!scheduler.complete(job));
  assert(scheduler.next(job) && job.kind == JobKind::BRIGHTNESS && job.brightness == 50);
  assert(scheduler.complete(job) && scheduler.initialized());
  const auto bytes = fixture("asymmetric.native.bmp");
  NativeImage changed(bytes.data(), bytes.size());
  assert(scheduler.next(job) && job.kind == JobKind::PAGE1 && job.key == 0);
  auto first_image = job.image;
  assert(scheduler.set_image(0, &changed));
  assert(scheduler.set_brightness(100));
  assert(scheduler.complete(job));
  assert(scheduler.next(job) && job.kind == JobKind::PAGE2 && job.image == first_image);
  assert(scheduler.complete(job));
  assert(scheduler.next(job) && job.kind == JobKind::BRIGHTNESS && job.brightness == 100);
  assert(scheduler.complete(job));
  int pages = 0;
  while (scheduler.next(job)) { assert(scheduler.complete(job)); pages++; assert(pages < 40); }
  assert(pages == 30);  // Other 14 keys plus the newer image for key 0.
  assert(!scheduler.next(job));
  scheduler.redraw();
  assert(scheduler.next(job) && job.kind == JobKind::PAGE1);
  old = job;
  scheduler.detach();
  assert(!scheduler.complete(old));
  scheduler.attach(2);
  assert(scheduler.next(job) && job.kind == JobKind::RESET && job.generation == 2);
  assert(!scheduler.complete(old));
  assert(scheduler.complete(job));
  assert(scheduler.next(job) && job.kind == JobKind::BRIGHTNESS);
  assert(scheduler.complete(job));
  assert(scheduler.next(job) && job.kind == JobKind::PAGE1);
  assert(scheduler.complete(job));
  assert(scheduler.next(job) && job.kind == JobKind::PAGE2);
  old = job;
  scheduler.detach(); scheduler.attach(3);
  assert(scheduler.next(job) && job.kind == JobKind::RESET);
  assert(!scheduler.complete(old));
}

void test_descriptors() {
  // Synthetic descriptor deliberately uses interface 3 and endpoint 0x85.
  std::vector<uint8_t> config = {9,2,34,0,1,1,0,0x80,50, 9,4,3,0,1,3,0,0,0,
                               9,0x21,0x11,1,0,1,0x22,42,0, 7,5,0x85,3,64,0,1};
  p::Interface descriptor;
  assert(p::find_interface(config.data(), config.size(), descriptor));
  assert(descriptor.number == 3 && descriptor.in_endpoint == 0x85 && descriptor.in_packet_size == 64);
  assert(descriptor.out_endpoint == 0 && descriptor.report_descriptor_size == 42);
  assert(!p::find_interface(config.data(), config.size() - 1, descriptor));
  config.insert(config.end(), {7,5,0x06,3,64,0,1});
  config[2] = 41; config[13] = 2;
  assert(p::find_interface(config.data(), config.size(), descriptor));
  assert(descriptor.out_endpoint == 6 && descriptor.out_packet_size == 64);
  config[34] = 0;
  assert(!p::find_interface(config.data(), config.size(), descriptor));
}

int main() {
  test_protocol(); test_input(); test_scheduler(); test_descriptors();
  std::cout << "Protocol fixtures, input, scheduler and descriptor tests passed\n";
}
