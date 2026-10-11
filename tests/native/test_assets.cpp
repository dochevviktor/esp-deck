#include "asset_png.h"
#include "asset_policy.h"
#include "asset_pipeline.h"
#include "visual_api.h"
#include "image_allocator.h"
#include "../fixtures/png/cases.h"
#include <cassert>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
#include <deque>
#include <map>
#include <variant>

using namespace esphome::stream_deck;
namespace a = esphome::stream_deck::assets;
namespace v = esphome::stream_deck::visual;
std::vector<uint8_t> read(const std::string &name) {
  std::ifstream file("tests/fixtures/png/" + name, std::ios::binary); assert(file.good());
  return {std::istreambuf_iterator<char>(file), {}};
}
void finish(a::PngDecoder &decoder) {
  unsigned steps = 0;
  while (decoder.phase() == a::PngDecoder::Phase::VALIDATE || decoder.phase() == a::PngDecoder::Phase::INFLATE ||
         decoder.phase() == a::PngDecoder::Phase::ROWS) { decoder.step(); assert(++steps < 2500); }
}
void png_tests() {
  TestImageAllocator allocator(v::MAX_GRAPHICS_BYTES);
  a::PngDecoder decoder(allocator);
  for (const auto &fixture : VALID_PNGS) {
    const auto png = read(std::string(fixture.name) + ".png"), expected = read(std::string(fixture.name) + ".rgba");
    assert(decoder.begin(png.data(), png.size())); finish(decoder);
    if (decoder.phase() != a::PngDecoder::Phase::DONE) std::cerr << "Failed PNG: " << fixture.name << '\n';
    assert(decoder.phase() == a::PngDecoder::Phase::DONE);
    const auto pixels = decoder.pixels();
    assert(pixels.width == fixture.width && pixels.height == fixture.height && pixels.bytes == expected.size());
    assert(std::equal(expected.begin(), expected.end(), pixels.data));
    decoder.cancel(); assert(allocator.used_bytes() == 0);
  }
  for (const auto *name : INVALID_PNGS) {
    const auto png = read(std::string(name) + ".png");
    if (decoder.begin(png.data(), png.size())) finish(decoder);
    if (decoder.phase() != a::PngDecoder::Phase::FAILED) std::cerr << "Accepted invalid PNG: " << name << '\n';
    assert(decoder.phase() == a::PngDecoder::Phase::FAILED && !decoder.pixels().data && allocator.used_bytes() == 0);
  }
  const auto png = read("rgba.png");
  for (size_t cut = 0; cut < png.size(); cut++) {
    if (decoder.begin(png.data(), cut)) finish(decoder);
    assert(decoder.phase() == a::PngDecoder::Phase::FAILED && allocator.used_bytes() == 0);
  }
  for (unsigned steps : {0, 3, 10, 100}) {
    const auto large = read("maximum.png");
    assert(decoder.begin(large.data(), large.size()));
    for (unsigned i = 0; i < steps; i++) decoder.step();
    decoder.cancel(); assert(allocator.used_bytes() == 0);
  }
  allocator.fail = true;
  assert(decoder.begin(png.data(), png.size())); finish(decoder);
  assert(decoder.error() == v::Error::OUT_OF_MEMORY && allocator.used_bytes() == 0);
  assert(!decoder.begin(png.data(), v::MAX_ENCODED_BYTES + 1) && decoder.error() == v::Error::LIMIT_EXCEEDED);
}
void policy_tests() {
  a::OriginPolicy policy;
  assert(!policy.allows("http://ha.local/icon.png"));
  assert(policy.add("http://ha.local:8123") && policy.add("https://ASSETS.example:443"));
  assert(policy.allows("http://HA.local:8123/local/deck.png"));
  assert(policy.allows("https://assets.example/a%20b.png"));
  for (const char *url : {"http://ha.local/a", "https://ha.local:8123/a", "http://ha.local:8123.evil/a",
                          "http://ha.local.evil:8123/a", "http://user@ha.local:8123/a", "http://ha.local:8123/a?token=secret",
                          "http://ha.local:8123/a#x", "file:///a", "http://ha.local:8123\\@evil/a"})
    assert(!policy.allows(url));
  assert(!policy.add("http://ha.local/path") && !policy.add("https://ha.local/"));
  assert(policy.add("http://one.local") && policy.add("http://two.local"));
  assert(!policy.add("http://three.local") && policy.add("http://one.local:80"));
}
class FakeFetcher : public a::Fetcher {
 public:
  bool start(std::string_view url, uint8_t *output, size_t capacity, uint64_t token) override {
    assert(!pending); pending = true; cancelled = false; calls++;
    url_ = url; output_ = output; capacity_ = capacity; token_ = token;
    return true;
  }
  bool poll(a::FetchResult &result) override {
    if (results.empty()) return false;
    result = results.front(); results.pop_front();
    if (result.token == token_) pending = false;
    return true;
  }
  void cancel() override { assert(pending); cancelled = true; }
  void complete(const std::vector<uint8_t> &bytes, v::Error error = v::Error::NONE, int status = 200) {
    assert(pending && bytes.size() <= capacity_);
    std::copy(bytes.begin(), bytes.end(), output_);
    results.push_back({token_, error, bytes.size(), status});
  }
  bool pending{false}, cancelled{false}; unsigned calls{0};
  uint64_t token_{0}; uint8_t *output_{nullptr}; size_t capacity_{0}; std::string url_;
  std::deque<a::FetchResult> results;
};
v::Command command(int key, int revision, const char *asset_revision = "one", const char *text = "Desk") {
  v::Command cmd;
  cmd.session = "0000000000000001"; cmd.key = key; cmd.revision = revision; cmd.fields = v::IMAGE | v::TEXT;
  cmd.image_url = "http://ha.local:8123/local/desk.png"; cmd.image_revision = asset_revision; cmd.text = text;
  return cmd;
}
void settle(a::Pipeline &pipeline, uint32_t &now) {
  for (unsigned i = 0; i < 2500; i++) { pipeline.loop(now++); if (pipeline.idle()) return; }
  assert(false);
}
void pipeline_tests() {
  TestImageAllocator memory(v::MAX_GRAPHICS_BYTES);
  a::Pool native(memory, v::MAX_NATIVE_BYTES);
  Scheduler scheduler;
  v::Store store(1, scheduler);
  FakeFetcher fetch;
  a::OriginPolicy policy; assert(policy.add("http://ha.local:8123"));
  a::Pipeline pipeline(store, fetch, memory, native, policy);
  uint32_t now = 0;
  const auto png = read("rgba.png");
  assert(store.submit(command(0, 1)).accepted);
  pipeline.loop(now++); assert(fetch.pending && fetch.calls == 1);
  // Label replacement while the first background is downloading reuses that
  // transfer; a stale completion cannot finish the current request.
  auto label = command(0, 2); label.fields = v::TEXT; label.text = "New";
  assert(store.submit(label).accepted);
  fetch.results.push_back({fetch.token_ + 50, v::Error::NONE, png.size(), 200});
  pipeline.loop(now++); assert(fetch.pending);
  fetch.complete(png);
  settle(pipeline, now);  // Superseded first label, useful cached background.
  assert(store.status(0)->phase == v::Phase::QUEUED);
  settle(pipeline, now);
  assert(store.status(0)->rendered_revision == 2 && fetch.calls == 1 && pipeline.cache_hits() == 1);
  for (int key = 1; key < 15; key++) {
    assert(store.submit(command(key, 1)).accepted); settle(pipeline, now);
  }
  assert(fetch.calls == 1);  // Shared backgrounds across keys.
  scheduler.attach(1); Job usb;
  while (scheduler.next(usb)) assert(scheduler.complete(usb));
  usb = {};
  scheduler.detach(); scheduler.attach(3);
  while (scheduler.next(usb)) assert(scheduler.complete(usb));
  usb = {}; assert(fetch.calls == 1);
  // Fill fifteen independently pinned backgrounds and churn the spare slot.
  for (int key = 0; key < 15; key++) {
    const auto revision = "asset-" + std::to_string(key);
    auto cmd = command(key, 3); cmd.image_revision = revision;
    assert(store.submit(cmd).accepted); pipeline.loop(now++);
    assert(fetch.pending); fetch.complete(png); settle(pipeline, now);
  }
  for (int revision = 4; revision < 25; revision++) {
    const auto asset = "replacement-" + std::to_string(revision);
    auto cmd = command(0, revision); cmd.image_revision = asset;
    assert(store.submit(cmd).accepted); pipeline.loop(now++);
    fetch.complete(png); settle(pipeline, now);
    assert(pipeline.cache_bytes() <= v::MAX_BACKGROUND_BYTES && memory.used_bytes() <= v::MAX_GRAPHICS_BYTES);
  }
  const auto calls = fetch.calls;
  auto retained_label = command(14, 4); retained_label.fields = v::TEXT; retained_label.text = "Cached";
  assert(store.submit(retained_label).accepted); settle(pipeline, now);
  assert(fetch.calls == calls);  // Eviction never removed this key's retained background.
  auto positioned = retained_label;
  positioned.revision = 5; positioned.fields = v::POSITION; positioned.v2 = true;
  positioned.context = "positioned"; positioned.text_align = 0; positioned.text_valign = 0;
  assert(store.submit(positioned).accepted); settle(pipeline, now);
  assert(fetch.calls == calls && store.status(14)->rendered_revision == 5);
  const auto last_rendered = store.status(0)->rendered_revision;
  auto invalid = command(0, 25, "bad");
  assert(store.submit(invalid).accepted); pipeline.loop(now++);
  fetch.complete(read("invalid_bad_crc.png")); settle(pipeline, now);
  assert(store.status(0)->phase == v::Phase::FAILED && store.status(0)->rendered_revision == last_rendered);
  invalid.revision = 26; invalid.image_revision = "missing";
  assert(store.submit(invalid).accepted); pipeline.loop(now++);
  fetch.complete({}, v::Error::HTTP_STATUS, 404); settle(pipeline, now);
  assert(store.status(0)->error == v::Error::HTTP_STATUS && pipeline.last_http_status() == 404);
  invalid.revision = 27; invalid.image_revision = "slow";
  assert(store.submit(invalid).accepted); pipeline.loop(now++);
  const auto held = memory.used_bytes();
  pipeline.loop(now + v::FETCH_TIMEOUT_MS);
  assert(fetch.cancelled && memory.used_bytes() == held && store.status(0)->error == v::Error::FETCH_TIMEOUT);
  pipeline.loop(now + 100000); assert(memory.used_bytes() == held);
  fetch.complete({}, v::Error::FETCH_FAILED); pipeline.loop(now++);
  assert(pipeline.idle() && memory.used_bytes() < held);
  invalid.revision = 28; invalid.image_url = "http://other.local/desk.png";
  const auto before = fetch.calls;
  const auto rejected = pipeline.submit(invalid);
  assert(!rejected.accepted && rejected.error == v::Error::ORIGIN_NOT_ALLOWED && rejected.revision == 27);
  assert(rejected.phase == store.status(0)->phase && store.status(0)->revision == 27);
  // The worker also checks policy defensively if a caller bypasses the public bridge.
  assert(store.submit(invalid).accepted); settle(pipeline, now);
  assert(fetch.calls == before && store.status(0)->error == v::Error::ORIGIN_NOT_ALLOWED);
  memory.fail = true;
  invalid = command(0, 29, "oom");
  assert(store.submit(invalid).accepted); settle(pipeline, now);
  assert(store.status(0)->error == v::Error::OUT_OF_MEMORY && store.status(0)->rendered_revision == last_rendered);
  memory.fail = false;
  invalid = command(0, 30, "cancel");
  assert(store.submit(invalid).accepted); pipeline.loop(now++);
  auto replacement = command(0, 31); replacement.image_url = ""; replacement.image_revision = "";
  assert(store.submit(replacement).accepted); pipeline.loop(now++);
  assert(fetch.cancelled);
  fetch.complete({}, v::Error::FETCH_FAILED); settle(pipeline, now); settle(pipeline, now);
  assert(store.status(0)->rendered_revision == 31 && pipeline.idle());
  pipeline.stop();
}
void api_tests() {
  TestImageAllocator memory(v::MAX_GRAPHICS_BYTES);
  a::Pool native(memory, v::MAX_NATIVE_BYTES);
  Scheduler scheduler;
  v::Store store(1, scheduler);
  FakeFetcher fetch;
  a::OriginPolicy policy; assert(policy.add("http://ha.local:8123"));
  a::Pipeline pipeline(store, fetch, memory, native, policy);
  const char *session = "0000000000000001";
  v::Api api(session, &store, &pipeline);
  uint32_t now = 0;
  auto status = api.get(session, 0);
  assert(status.accepted && status.status.phase == v::Phase::IDLE && status.status.revision == 0);
  assert(api.get("0000000000000002", 0).error == v::Error::WRONG_SESSION);
  assert(api.get(session, -1).error == v::Error::INVALID_KEY);
  assert(api.clear(session, 15, 1).error == v::Error::INVALID_KEY);
  assert(api.refresh(session, 0, 1, "new").error == v::Error::INVALID_URL);
  assert(v::Api("", nullptr, nullptr).set(command(0, 1)).error == v::Error::OUT_OF_MEMORY);

  auto cmd = command(0, 1);
  status = api.set(cmd);
  assert(status.accepted && status.status.phase == v::Phase::QUEUED && status.request_revision == 1);
  assert(status.status.revision == 1 && status.status.rendered_revision == 0);
  pipeline.loop(now++);
  assert(api.get(session, 0).status.phase == v::Phase::RENDERING);
  assert(api.set(cmd).accepted && fetch.calls == 1);  // Duplicate in flight.
  fetch.complete(read("rgba.png")); settle(pipeline, now);
  status = api.get(session, 0);
  assert(status.accepted && status.error == v::Error::NONE && status.status.rendered_revision == 1);
  scheduler.attach(1); Job job;
  while (scheduler.next(job)) assert(scheduler.complete(job));
  job = {};

  // Re-create the stateless API adapter as a different client/HA restart would.
  // Query current revision and replay all fields: unchanged tiles schedule no USB work.
  v::Api reconnected(session, &store, &pipeline);
  cmd.revision = reconnected.get(session, 0).status.revision + 1;
  assert(reconnected.set(cmd).status.phase == v::Phase::RENDERED);
  pipeline.loop(now++);
  assert(fetch.calls == 1 && !scheduler.next(job));
  auto label = cmd; label.revision++; label.fields = v::TEXT; label.text = "Renamed in HA";
  assert(api.set(label).accepted); settle(pipeline, now);
  assert(fetch.calls == 1 && api.get(session, 0).status.rendered_revision == 3);

  const auto rejected = api.set(cmd);  // Old revision cannot replace status or desired pixels.
  assert(!rejected.accepted && rejected.error == v::Error::STALE_REVISION && rejected.status.revision == 3);
  assert(rejected.request_revision == 2 && rejected.status.rendered_revision == 3);
  cmd.revision = 3;
  assert(api.set(cmd).error == v::Error::REVISION_CONFLICT);
  cmd.session = "0000000000000002"; cmd.revision = 4;
  assert(api.set(cmd).error == v::Error::WRONG_SESSION);
  cmd.session = session; cmd.image_url = "http://untrusted.local/a.png";
  assert(api.set(cmd).error == v::Error::ORIGIN_NOT_ALLOWED);
  assert(api.get(session, 0).status.revision == 3);

  assert(api.refresh(session, 0, 4, "").error == v::Error::INVALID_IMAGE_REVISION);
  assert(api.refresh(session, 0, 4, "two").accepted);
  pipeline.loop(now++); assert(fetch.calls == 2);
  fetch.complete({}, v::Error::FETCH_FAILED); settle(pipeline, now);
  status = api.get(session, 0);
  assert(status.accepted && status.error == v::Error::FETCH_FAILED && status.status.rendered_revision == 3);
  assert(api.refresh(session, 0, 4, "two").error == v::Error::FETCH_FAILED);
  pipeline.loop(now++); assert(fetch.calls == 2);  // Failed duplicate does not retry.
  assert(api.refresh(session, 0, 5, "two").accepted);
  pipeline.loop(now++); assert(fetch.calls == 3);
  fetch.complete(read("rgba.png")); settle(pipeline, now);
  assert(store.desired(0)->text.view() == "Renamed in HA");
  assert(api.get(session, 0).status.rendered_revision == 5);

  // Same boot/session survives deck detach; no new HTTP request to restore tiles.
  scheduler.detach(); scheduler.attach(3);
  while (scheduler.next(job)) assert(scheduler.complete(job));
  job = {}; assert(fetch.calls == 3 && api.get(session, 0).status.revision == 5);
  assert(api.clear(session, 0, 6).accepted); settle(pipeline, now);
  assert(store.desired(0)->text.empty() && store.desired(0)->image_url.empty());
  assert(api.clear(session, 0, 6).status.phase == v::Phase::RENDERED);
  assert(fetch.calls == 3);

  // Execute the same serializer used by the compiled api.respond lambdas.
  using Value = std::variant<std::string, int32_t, uint32_t, bool, const char *>;
  struct Object {
    std::map<std::string, Value> &values;
    Value &operator[](const char *key) { return values[key]; }
  };
  std::map<std::string, Value> values;
  api.get(session, 0).write(Object{values});
  assert(values.size() == 11 && std::get<std::string>(values["session"]) == session);
  assert(std::get<int32_t>(values["key"]) == 0 && std::get<int32_t>(values["request_revision"]) == 0);
  assert(std::get<bool>(values["accepted"]) && std::get<uint32_t>(values["revision"]) == 6);
  assert(std::get<uint32_t>(values["rendered_revision"]) == 6);
  assert(std::string(std::get<const char *>(values["phase"])) == "rendered");
  assert(std::string(std::get<const char *>(values["error"])) == "none");
  pipeline.stop();
}

int main() {
  png_tests(); policy_tests(); pipeline_tests(); api_tests();
  std::cout << "Bounded PNG, origin policy, cache, cancellation and visual pipeline tests passed\n";
}
