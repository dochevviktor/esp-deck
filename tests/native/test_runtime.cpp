#include "runtime_image.h"
#include "visual_state.h"
#include "image_allocator.h"

#include <cassert>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <string>
#include <vector>

using namespace esphome::stream_deck;
namespace p = esphome::stream_deck::protocol;
namespace v = esphome::stream_deck::visual;

std::vector<uint8_t> fixture(const std::string &name) {
  std::ifstream input("tests/fixtures/" + name, std::ios::binary);
  assert(input.good());
  return {std::istreambuf_iterator<char>(input), {}};
}

ImageRef owned(TestImageAllocator &allocator, uint64_t version) {
  auto bytes = fixture("asymmetric.native.bmp");
  return ImageRef::copy(p::NativeImage(bytes.data(), bytes.size()), version, allocator);
}

void drain(Scheduler &scheduler) {
  Job job;
  size_t count = 0;
  while (scheduler.next(job)) {
    assert(scheduler.complete(job));
    assert(++count < 100);
  }
}

void test_immutable_ownership() {
  TestImageAllocator allocator;
  const auto golden = fixture("asymmetric.native.bmp");
  auto bytes = golden;
  auto image = ImageRef::copy(p::NativeImage(bytes.data(), bytes.size()), 7, allocator);
  assert(image && image.version() == 7 && allocator.allocations == 1);
  const auto usage = allocator.used_bytes();
  assert(usage > p::IMAGE_SIZE);
  std::fill(bytes.begin(), bytes.end(), 0);  // Caller/render scratch is no longer an owner.
  assert(std::equal(golden.begin(), golden.end(), image->data));
  auto cache = image;
  image = {};
  assert(allocator.frees == 0 && cache.version() == 7);
  auto moved = std::move(cache);
  assert(!cache && moved && allocator.used_bytes() == usage);
  moved = moved;  // Self assignment must preserve the sole reference.
  assert(moved);
  moved = {};
  assert(allocator.frees == 1 && allocator.used_bytes() == 0);
  assert(!ImageRef::copy(p::blank_image(), 0, allocator));
  assert(!ImageRef::copy(p::NativeImage(nullptr, p::IMAGE_SIZE), 8, allocator));
  allocator.fail = true;
  assert(!owned(allocator, 8) && allocator.used_bytes() == 0);
  TestImageAllocator too_small(p::IMAGE_SIZE);
  assert(!owned(too_small, 8) && too_small.allocations == 0);
  TestImageAllocator one_image(usage);
  auto only = owned(one_image, 9);
  assert(only && !owned(one_image, 10));
  only = {};
  assert(owned(one_image, 10));  // Releasing the last reference restores budget.
}

void test_replacement_and_eviction() {
  for (const bool during_page_two : {false, true}) {
    TestImageAllocator allocator;
    Scheduler scheduler;
    scheduler.attach(1);
    drain(scheduler);
    auto cache = owned(allocator, 1);
    assert(scheduler.set_image(0, cache));
    Job job;
    assert(scheduler.next(job) && job.kind == JobKind::PAGE1);
    if (during_page_two) {
      assert(scheduler.complete(job));
      assert(scheduler.next(job) && job.kind == JobKind::PAGE2);
    }
    for (uint64_t version = 2; version <= 20; version++)
      assert(scheduler.set_image(0, owned(allocator, version)));
    cache = {};  // Evict the cache entry while USB owns the old version.
    assert(allocator.live.size() == 2);
    assert(job.image.version() == 1);
    std::vector<uint8_t> report(p::REPORT_SIZE);
    assert(p::image_page(0, during_page_two ? 2 : 1, *job.image, report.data(), report.size()));
    assert(report == fixture(during_page_two ? "key_0_page_2.bin" : "key_0_page_1.bin"));
    assert(scheduler.complete(job));
    if (!during_page_two) {
      assert(scheduler.next(job) && job.kind == JobKind::PAGE2 && job.image.version() == 1);
      assert(scheduler.complete(job));
    }
    job = {};
    assert(allocator.live.size() == 2);  // Applied version is retained until its replacement completes.
    assert(scheduler.next(job) && job.kind == JobKind::PAGE1 && job.image.version() == 20);
    assert(scheduler.complete(job));
    assert(scheduler.next(job) && job.kind == JobKind::PAGE2);
    assert(scheduler.complete(job));
    job = {};
    assert(allocator.live.size() == 1);
    assert(!scheduler.next(job));
    scheduler.redraw();
    do {
      assert(scheduler.next(job));
      if (job.key == 0) break;
      assert(scheduler.complete(job));
    } while (true);
    assert(job.image.version() == 20);
    const Job stale = job;  // Simulated transport/cancellation owner.
    scheduler.detach();
    assert(scheduler.set_image(0, &p::blank_image()));
    job = {};
    assert(allocator.live.size() == 1);
    scheduler.attach(2);
    assert(!scheduler.complete(stale));
    drain(scheduler);
    assert(stale.image.version() == 20);
  }
}

void test_allocation_failure_preserves_desired() {
  TestImageAllocator allocator;
  Scheduler scheduler;
  auto image = owned(allocator, 1);
  assert(scheduler.set_image(0, image));
  allocator.fail = true;
  assert(!scheduler.set_image(0, owned(allocator, 2)));
  scheduler.attach(1);
  Job job;
  assert(scheduler.next(job) && scheduler.complete(job));
  assert(scheduler.next(job) && scheduler.complete(job));
  assert(scheduler.next(job) && job.image == image);
}

constexpr uint64_t SESSION = 0x0123456789abcdefULL;
v::Command command(int revision, int fields, int key = 0) {
  v::Command cmd;
  cmd.session = "0123456789abcdef";
  cmd.key = key;
  cmd.revision = revision;
  cmd.fields = fields;
  return cmd;
}

void test_patch_contract() {
  v::State current, result;
  auto cmd = command(1, v::IMAGE | v::TEXT);
  cmd.image_url = "http://homeassistant.local:8123/local/streamdeck/desk.png";
  cmd.image_revision = "sha256:desk-v1";
  cmd.text = "Desk";
  assert(v::apply_patch(cmd, current, result) == v::Error::NONE);
  assert(result.image_url.view() == cmd.image_url && result.text.view() == "Desk");
  assert(result.font == 16 && result.text_color == 0xffffff && result.outline_color == 0);
  current = result;
  cmd = command(2, v::TEXT);
  cmd.text = "On";
  assert(v::apply_patch(cmd, current, result) == v::Error::NONE);
  assert(result.image_url == current.image_url && result.image_revision == current.image_revision);
  assert(result.text.view() == "On");
  cmd = command(3, v::IMAGE);
  assert(v::apply_patch(cmd, result, result) == v::Error::NONE);
  assert(result.image_url.empty() && result.image_revision.empty() && result.text.view() == "On");
  cmd = command(4, v::TEXT);
  assert(v::apply_patch(cmd, result, result) == v::Error::NONE && result.text.empty());
  cmd = command(5, v::FONT | v::TEXT_COLOR | v::OUTLINE_COLOR | v::BACKGROUND_COLOR | v::FIT);
  cmd.font = 20; cmd.text_color = "#12Ab34"; cmd.outline_color = "#010203";
  cmd.background_color = "#102030"; cmd.fit = "crop";
  assert(v::apply_patch(cmd, current, result) == v::Error::NONE);
  assert(result.font == 20 && result.text_color == 0x12ab34 && result.outline_color == 0x010203);
  assert(result.background_color == 0x102030 && result.fit == v::Fit::CROP);
}

void test_validation_is_atomic() {
  v::State state, output;
  auto invalid = [&](v::Command cmd, v::Error error) {
    output = state;
    assert(v::apply_patch(cmd, state, output) == error);
    assert(output == state);
  };
  invalid(command(1, 128), v::Error::INVALID_FIELDS);
  invalid(command(1, 0), v::Error::INVALID_FIELDS);
  auto cmd = command(1, v::TEXT_COLOR); cmd.text_color = "red";
  invalid(cmd, v::Error::INVALID_COLOR);
  cmd = command(1, v::FONT); cmd.font = 18;
  invalid(cmd, v::Error::INVALID_FONT);
  cmd = command(1, v::FIT); cmd.fit = "stretch";
  invalid(cmd, v::Error::INVALID_FIT);
  cmd = command(1, v::IMAGE);
  cmd.image_url = "http://ha.local/image.png";
  invalid(cmd, v::Error::INVALID_IMAGE_REVISION);
  cmd.image_revision = "v1";
  for (const auto *url : {"file:///etc/passwd", "http://user:secret@ha.local/a.png", "https://ha.local/a?q=secret",
                          "https://ha.local/a#x", "http:///x", "http://ha.local:99999/x", "http://ha.local/a b",
                          "http://ha.local/%xx", "http://ha.local\\@evil/a", "http://-ha.local/x"}) {
    cmd.image_url = url;
    invalid(cmd, v::Error::INVALID_URL);
  }
  std::string long_url(v::MAX_URL_BYTES + 1, 'a'); cmd.image_url = long_url;
  invalid(cmd, v::Error::LIMIT_EXCEEDED);
  cmd = command(1, v::TEXT);
  for (const std::string &text : {std::string("\xc0\xaf"), std::string("\xed\xa0\x80"), std::string("\xf4\x90\x80\x80"),
                                 std::string("\xe2\x82"), std::string("a\0b", 3), std::string("x\t")}) {
    cmd.text = text; invalid(cmd, v::Error::INVALID_TEXT);
  }
  const std::string too_many(v::MAX_LABEL_CODEPOINTS + 1, 'x'); cmd.text = too_many;
  invalid(cmd, v::Error::LIMIT_EXCEEDED);
  cmd.text = "Caf\xc3\xa9\n\xf0\x9f\x92\xa1";  // Valid unsupported glyphs survive validation for P2 substitution.
  assert(v::apply_patch(cmd, state, output) == v::Error::NONE);
}

void test_revisions_and_atomic_render_commit() {
  TestImageAllocator allocator;
  Scheduler scheduler;
  v::Store store(SESSION, scheduler);
  auto cmd = command(1, v::IMAGE | v::TEXT);
  cmd.image_url = "http://ha.local/desk.png"; cmd.image_revision = "1"; cmd.text = "Desk";
  assert(store.submit(cmd).accepted);
  assert(store.status(0)->phase == v::Phase::QUEUED);
  v::RenderJob old, job;
  assert(store.next(old) && old.revision == 1 && old.state.text.view() == "Desk");
  cmd = command(2, v::TEXT); cmd.text = "New";
  assert(store.submit(cmd).accepted);
  assert(!store.next(job));  // At most one active render, even if its result is now obsolete.
  assert(!store.finish(old, owned(allocator, 1)));
  assert(store.status(0)->phase == v::Phase::QUEUED);
  assert(store.next(job) && job.revision == 2 && job.state.text.view() == "New");
  assert(job.state.image_revision.view() == "1");
  auto rendered = owned(allocator, 2);
  assert(store.finish(job, rendered));
  assert(store.status(0)->phase == v::Phase::RENDERED && store.status(0)->rendered_revision == 2);
  scheduler.attach(1);
  drain(scheduler);
  auto duplicate = store.submit(cmd);
  assert(duplicate.accepted && duplicate.phase == v::Phase::RENDERED && !store.next(job));
  cmd.text = "Conflict";
  assert(store.submit(cmd).error == v::Error::REVISION_CONFLICT);
  cmd.revision = 1;
  assert(store.submit(cmd).error == v::Error::STALE_REVISION);
  cmd.revision = 0;
  assert(store.submit(cmd).error == v::Error::INVALID_REVISION);
  cmd.revision = 3; cmd.session = "ffffffffffffffff";
  assert(store.submit(cmd).error == v::Error::WRONG_SESSION);
  cmd.session = "0123456789abcdef";
  cmd.key = -1;
  assert(store.submit(cmd).error == v::Error::INVALID_KEY);
  assert(store.status(-1) == nullptr && store.status(15) == nullptr);
  cmd.key = 0; cmd.text = "New";  // New revision, unchanged complete visual: no new rendering/USB output.
  assert(store.submit(cmd).accepted && !store.next(job));
  assert(store.status(0)->rendered_revision == 3);
  Job usb;
  assert(!scheduler.next(usb));
  cmd.revision = 4; cmd.text = "Failed";
  assert(store.submit(cmd).accepted && store.next(job));
  assert(store.fail(job, v::Error::FETCH_FAILED));
  assert(store.status(0)->phase == v::Phase::FAILED && store.status(0)->rendered_revision == 3);
  assert(!scheduler.next(usb));  // Failed full tile never replaces the previously rendered image.
  assert(store.submit(cmd).accepted && !store.next(job));  // Duplicate failure does not retry.
  cmd.revision = 5;
  assert(store.submit(cmd).accepted && store.next(job));
  assert(!store.finish(old, rendered));  // Old completion must not release the current active job.
  v::RenderJob blocked;
  assert(!store.next(blocked));
  assert(store.finish(job, rendered));
  cmd.revision = 6; cmd.text = "Invalid result";
  assert(store.submit(cmd).accepted && store.next(job));
  assert(!store.finish(job, {}));
  assert(store.status(0)->phase == v::Phase::FAILED && store.status(0)->rendered_revision == 5);
  assert(store.status(0)->error == v::Error::RENDER_FAILED);
  cmd.revision = 7;
  assert(store.submit(cmd).accepted && store.next(job));
  allocator.fail = true;
  assert(!owned(allocator, 7));
  assert(store.fail(job, v::Error::OUT_OF_MEMORY));
  assert(store.status(0)->error == v::Error::OUT_OF_MEMORY && store.status(0)->rendered_revision == 5);
}

void test_coalescing_and_offline_lifecycle() {
  TestImageAllocator allocator;
  Scheduler scheduler;
  v::Store store(SESSION, scheduler);
  for (int key = 0; key < 15; key++) for (int revision = 1; revision <= 10; revision++) {
    auto cmd = command(revision, v::TEXT, key); cmd.text = "Offline";
    assert(store.submit(cmd).accepted);
  }
  v::RenderJob job;
  for (int key = 0; key < 15; key++) {
    assert(store.next(job) && job.key == key && job.revision == 10);
    assert(store.finish(job, owned(allocator, key + 1)));
  }
  assert(!store.next(job));
  scheduler.attach(1); drain(scheduler);
  scheduler.detach(); scheduler.attach(3); drain(scheduler);
  assert(!store.next(job));  // USB generations don't invalidate the visual session or create downloads.
  v::Store restarted(SESSION + 1, scheduler);
  assert(restarted.submit(command(11, v::TEXT)).error == v::Error::WRONG_SESSION);
}

int main() {
  test_immutable_ownership();
  test_replacement_and_eviction();
  test_allocation_failure_preserves_desired();
  test_patch_contract();
  test_validation_is_atomic();
  test_revisions_and_atomic_render_commit();
  test_coalescing_and_offline_lifecycle();
  std::cout << "Runtime ownership and visual contract tests passed\n";
}
