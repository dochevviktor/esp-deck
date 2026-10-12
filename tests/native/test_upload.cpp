#include "asset_pipeline.h"
#include "image_allocator.h"
#include <cassert>
#include <fstream>
#include <iterator>
#include <iostream>
#include <vector>

using namespace esphome::stream_deck;
namespace a = esphome::stream_deck::assets;
namespace v = esphome::stream_deck::visual;
const char *SESSION = "0000000000000001";
struct Fixture { std::string id; std::vector<uint8_t> png; };
std::vector<Fixture> fixtures;
// Python hashlib supplies the independent hash/byte oracle. The encrypted host
// test additionally verifies SHA256 using the pinned Noise implementation.
bool verify(const uint8_t *data, size_t size, std::string_view id) {
  for (const auto &f : fixtures)
    if (f.id == id) return f.png.size() == size && std::equal(f.png.begin(), f.png.end(), data);
  return false;
}
std::string base64(const uint8_t *data, size_t size) {
  const char *alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  std::string result;
  for (size_t i = 0; i < size; i += 3) {
    const unsigned n = unsigned(data[i]) << 16 | (i + 1 < size ? unsigned(data[i + 1]) << 8 : 0) |
        (i + 2 < size ? data[i + 2] : 0);
    result += alphabet[n >> 18]; result += alphabet[(n >> 12) & 63];
    result += i + 1 < size ? alphabet[(n >> 6) & 63] : '=';
    result += i + 2 < size ? alphabet[n & 63] : '=';
  }
  return result;
}
a::UploadCache::Response send(a::UploadCache &cache, const Fixture &f, uint32_t now = 1) {
  auto response = cache.receive(SESSION, f.id, 0, f.png.size(), "", now);
  assert(std::string_view(response.error) == "none");
  for (size_t offset = response.received; offset < f.png.size(); offset += a::UploadCache::CHUNK_BYTES) {
    const auto length = std::min(a::UploadCache::CHUNK_BYTES, f.png.size() - offset);
    response = cache.receive(SESSION, f.id, offset, f.png.size(), base64(f.png.data() + offset, length), now);
    if (std::string_view(response.error) != "none") return response;
  }
  return response;
}
void expect(const a::UploadCache::Response &r, const char *error) { assert(std::string_view(r.error) == error); }
struct NoNetwork : a::Fetcher {
  bool start(std::string_view, uint8_t *, size_t, uint64_t) override { assert(false); return false; }
  bool poll(a::FetchResult &) override { assert(false); return false; }
  void cancel() override { assert(false); }
};
void transport() {
  TestImageAllocator memory(v::MAX_GRAPHICS_BYTES);
  Scheduler scheduler; v::Store store(1, scheduler); a::UploadCache cache(store, memory);
  const auto &f = fixtures[1]; assert(f.png.size() > 1024);
  expect(cache.receive(SESSION, f.id, 0, f.png.size(), "", 0), "upload_unavailable");
  cache.set_verifier(verify);
  expect(cache.receive("0000000000000002", f.id, 0, f.png.size(), "", 0), "wrong_session");
  expect(cache.receive(SESSION, "../x", 0, 1, "", 0), "invalid_artwork_id");
  for (int size : {-1, 0, 32769}) expect(cache.receive(SESSION, f.id, 0, size, "", 0), "upload_size");
  expect(cache.receive(SESSION, f.id, -1, f.png.size(), "", 0), "upload_size");
  expect(cache.receive(SESSION, f.id, 1, f.png.size(), "AAAA", 0), "upload_offset");
  for (const char *bad : {"A", "!!!!", "====", "AA=A", "AB==", "AAB=", "AA==AAAA", " AA="})
    expect(cache.receive(SESSION, f.id, 0, f.png.size(), bad, 0), "invalid_chunk");
  std::vector<uint8_t> oversized(1025, 0);
  expect(cache.receive(SESSION, f.id, 0, f.png.size(), base64(oversized.data(), oversized.size()), 0), "invalid_chunk");
  assert(memory.used_bytes() == 0);
  const auto chunk = base64(f.png.data(), 1024);
  auto r = cache.receive(SESSION, f.id, 0, f.png.size(), chunk, 0);
  assert(r.received == 1024 && !r.complete);
  assert(cache.receive(SESSION, f.id, 0, f.png.size(), chunk, 1).received == 1024);
  assert(cache.receive(SESSION, f.id, 0, f.png.size(), "", 2).received == 1024);
  expect(cache.receive(SESSION, f.id, 1025, f.png.size(), "AAAA", 2), "upload_offset");
  expect(cache.receive(SESSION, f.id, 0, f.png.size(), "AAAA", 2), "upload_conflict");
  cache.expire(a::UploadCache::IDLE_MS); assert(cache.bytes() == 0);
  assert(send(cache, f).complete);
  assert(send(cache, f).complete);  // Complete duplicate probes need no chunks.
  a::Buffer copy; assert(cache.copy(f.id, copy)); assert(copy.size() == f.png.size()); copy.reset();
  auto damaged = fixtures[0]; damaged.png[34] ^= 1;
  expect(send(cache, damaged), "upload_hash_mismatch");
  assert(!cache.copy(damaged.id, copy));
  auto small = fixtures[32]; expect(send(cache, small), "unsupported_png");
  memory.fail = true;
  expect(cache.receive(SESSION, fixtures[2].id, 0, fixtures[2].png.size(), "", 1), "out_of_memory");
  memory.fail = false;
  // A newer upload supersedes the receiving buffer. Old chunks cannot append.
  expect(cache.receive(SESSION, fixtures[2].id, 0, fixtures[2].png.size(), "", 1), "none");
  expect(cache.receive(SESSION, fixtures[3].id, 0, fixtures[3].png.size(), "", 2), "none");
  expect(cache.receive(SESSION, fixtures[2].id, 1, fixtures[2].png.size(), "AAAA", 3), "upload_offset");
  // Monotonic unsigned deadlines handle millis() wraparound.
  cache.expire(20000);
  expect(cache.receive(SESSION, fixtures[2].id, 0, fixtures[2].png.size(), "", 0xfffffff0), "none");
  cache.expire(15000); assert(cache.bytes() == f.png.size());
  assert(send(cache, fixtures.back(), 16000).complete);  // Exact 32 KiB admission.
}
v::Command command(int key, int revision, const std::string &url, const std::string &id) {
  v::Command cmd;
  cmd.session = SESSION; cmd.key = key; cmd.revision = revision; cmd.fields = v::IMAGE;
  cmd.image_url = url; cmd.image_revision = id; cmd.v2 = true; cmd.context = "binding";
  return cmd;
}
void retention() {
  TestImageAllocator memory(v::MAX_GRAPHICS_BYTES);
  Scheduler scheduler; v::Store store(1, scheduler); a::UploadCache cache(store, memory);
  cache.set_verifier(verify);
  for (int key = 0; key < 15; ++key) {
    assert(send(cache, fixtures[key]).complete);
    const std::string url = "asset://" + fixtures[key].id;
    assert(store.submit(command(key, 1, url, fixtures[key].id)).accepted);
  }
  a::Buffer borrowed; assert(cache.copy(fixtures[15].id, borrowed) == false);
  for (size_t index = 15; index < 32; ++index) assert(send(cache, fixtures[index]).complete);
  for (int key = 0; key < 15; ++key) {
    a::Buffer copy; assert(cache.copy(fixtures[key].id, copy));
    assert(std::equal(fixtures[key].png.begin(), fixtures[key].png.end(), copy.data()));
  }
  assert(cache.bytes() <= a::UploadCache::CAPACITY * a::UploadCache::MAX_BYTES);
}
void render() {
  TestImageAllocator memory(v::MAX_GRAPHICS_BYTES); a::Pool native(memory, v::MAX_NATIVE_BYTES);
  Scheduler scheduler; v::Store store(1, scheduler); NoNetwork fetch; a::OriginPolicy policy;
  a::Pipeline pipeline(store, fetch, memory, native, policy); pipeline.uploads().set_verifier(verify);
  const auto &f = fixtures[0]; const std::string url = "asset://" + f.id;
  auto cmd = command(0, 1, url, f.id);
  v::State state;
  cmd.v2 = false; cmd.context = ""; assert(v::apply_patch(cmd, state, state) == v::Error::INVALID_URL);
  cmd.v2 = true; cmd.context = "binding";
  assert(send(pipeline.uploads(), f).complete);
  assert(pipeline.submit(cmd).accepted);
  uint32_t now = 0;
  auto settle = [&]() { for (int i = 0; i < 4000; ++i) pipeline.loop(now++); };
  settle(); assert(store.status(0)->rendered_revision == 1 && pipeline.downloads() == 0);
  scheduler.attach(1); Job job;
  std::ifstream golden_file("tests/fixtures/asymmetric.native.bmp", std::ios::binary);
  const std::vector<uint8_t> golden{std::istreambuf_iterator<char>(golden_file), {}};
  while (scheduler.next(job)) {
    if (job.key == 0 && job.kind == JobKind::PAGE1)
      assert(std::equal(golden.begin(), golden.end(), job.image.get()->data));
    assert(scheduler.complete(job));
  }
  job = {};
  assert(store.applied_revision(0) == 1);
  cmd.revision = 2; cmd.fields = v::TEXT; cmd.text = "Label";
  assert(pipeline.submit(cmd).accepted); settle(); assert(pipeline.cache_hits() == 1);
  Job page1;
  assert(scheduler.next(page1) && page1.kind == JobKind::PAGE1);
  assert(scheduler.complete(page1));
  const auto image_revision = scheduler.image_revision(0);
  // An incomplete transfer doesn't touch desired/applied images. A missing or
  // malformed completed asset fails rendering while retaining the previous BMP.
  assert(pipeline.uploads().receive(SESSION, fixtures[1].id, 0, fixtures[1].png.size(), "", now).received == 0);
  assert(scheduler.image_revision(0) == image_revision);
  const std::string missing = "asset://" + fixtures[2].id;
  cmd = command(0, 3, missing, fixtures[2].id);
  assert(pipeline.submit(cmd).accepted); settle();
  assert(store.status(0)->error == v::Error::ARTWORK_MISSING && scheduler.image_revision(0) == image_revision);
  assert(send(pipeline.uploads(), fixtures.back(), now).complete);
  const std::string malformed = "asset://" + fixtures.back().id;
  cmd = command(0, 4, malformed, fixtures.back().id);
  assert(pipeline.submit(cmd).accepted); settle();
  assert(store.status(0)->error == v::Error::DECODE_FAILED && scheduler.image_revision(0) == image_revision);
  // Replace during sliced decode; only the latest request can reach USB.
  assert(send(pipeline.uploads(), fixtures[1], now).complete);
  const std::string noisy = "asset://" + fixtures[1].id;
  cmd = command(0, 5, noisy, fixtures[1].id); assert(pipeline.submit(cmd).accepted); pipeline.loop(now++);
  cmd = command(0, 6, url, f.id); cmd.fields |= v::TEXT; cmd.text = "Newest";
  assert(pipeline.submit(cmd).accepted); settle();
  assert(store.status(0)->rendered_revision == 6 && pipeline.downloads() == 0);
  Job page2;
  assert(scheduler.next(page2) && page2.kind == JobKind::PAGE2 && page2.image.get() == page1.image.get());
  assert(scheduler.complete(page2));
  assert(store.applied_revision(0) == 0);
  page1 = {}; page2 = {};
  assert(memory.used_bytes() <= v::MAX_GRAPHICS_BYTES);
}
int main(int argc, char **argv) {
  assert(argc == 2); std::ifstream index(std::string(argv[1]) + "/index"); std::string id;
  while (index >> id) {
    std::ifstream file(std::string(argv[1]) + "/" + id, std::ios::binary); assert(file.good());
    fixtures.push_back({id, {std::istreambuf_iterator<char>(file), {}}});
  }
  assert(fixtures.size() == 34);
  transport(); retention(); render();
  std::cout << "Bounded artwork transfer, retry, lifetime, eviction and rendering tests passed\n";
}
