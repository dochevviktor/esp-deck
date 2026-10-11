#include "runtime_v2.h"
#include "origin_provisioning.h"
#include "image_allocator.h"
#include <cassert>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <variant>

using namespace esphome::stream_deck;
namespace v = esphome::stream_deck::visual;
struct JsonData;
struct Json {
  std::shared_ptr<JsonData> data;
  Json();
  Json operator[](const char *key);
  Json operator[](size_t key);
  Json operator[](int key) { return (*this)[size_t(key)]; }
  template<typename T> void operator=(T value);
  int64_t number() const;
  std::string text() const;
};
struct JsonData { std::map<std::string, Json> children; std::variant<int64_t, std::string> value{int64_t(0)}; };
Json::Json() : data(std::make_shared<JsonData>()) {}
Json Json::operator[](const char *key) { return data->children[key]; }
Json Json::operator[](size_t key) { return (*this)[std::to_string(key).c_str()]; }
template<typename T> void Json::operator=(T value) {
  if constexpr (std::is_integral_v<T> || std::is_enum_v<T>) data->value = int64_t(value);
  else data->value = std::string(value);
}
int64_t Json::number() const { return std::get<int64_t>(data->value); }
std::string Json::text() const { return std::get<std::string>(data->value); }
void drain(Scheduler &scheduler) { Job job; while (scheduler.next(job)) assert(scheduler.complete(job)); }
const std::string SESSION = "1234567890123456", READER(32, 'a'), OLD(32, 'b'), NEW(32, 'c');
v::Command command(int revision, std::string_view context, std::string_view label = "A") {
  v::Command c; c.session = SESSION; c.key = 0; c.revision = revision; c.fields = v::TEXT;
  c.text = label; c.v2 = true; c.context = context; return c;
}
void render(v::Store &store, uint64_t version, TestImageAllocator &memory) {
  v::RenderJob job; assert(store.next(job));
  assert(store.finish(job, ImageRef::copy(protocol::blank_image(), version, memory)));
}
void input_tests() {
  TestImageAllocator memory; Scheduler scheduler;
  v::Store store(0x1234567890123456, scheduler); v::InputChannel channel(store);
  scheduler.attach(10); drain(scheduler);
  Json initial; channel.read(READER, 0, 1, initial);
  assert(store.submit(command(1, OLD)).accepted); render(store, 1, memory);
  assert(store.status(0)->phase == v::Phase::RENDERED && store.applied_revision(0) == 0);
  channel.sample({10, 1, false, scheduler.input_epoch()}, {1, 0, false}, 2);
  assert(channel.queued() == 0);  // Rendered is not applied.
  Job job; assert(scheduler.next(job) && job.kind == JobKind::PAGE1); assert(scheduler.complete(job));
  assert(store.applied_revision(0) == 0);
  assert(scheduler.next(job) && job.kind == JobKind::PAGE2); const Job obsolete = job;
  assert(scheduler.complete(job)); assert(store.applied_revision(0) == 1);
  const auto old_epoch = scheduler.input_epoch();
  channel.sample({10, 1, false, old_epoch}, {1, 0, false}, 3);
  Json press; channel.read(READER, 0, 4, press);
  assert(press["count"].number() == 1 && press["events"][size_t(0)]["context"].text() == OLD);
  assert(store.submit(command(2, NEW)).accepted);  // Same image, different binding.
  assert(store.applied_revision(0) == 2 && !scheduler.next(job));
  channel.sample({10, 0, false, old_epoch}, {0, 1, false}, 5);
  Json release; channel.read(READER, 1, 6, release);
  assert(release["events"][size_t(0)]["context"].text() == OLD);  // Captured pair.
  channel.sample({10, 1, false, old_epoch}, {1, 0, false}, 7);
  assert(channel.queued() == 0);  // Delayed IN from previous context.
  channel.sample({10, 1, false, scheduler.input_epoch()}, {1, 0, false}, 8);
  Json current; channel.read(READER, 2, 9, current);
  assert(current["events"][size_t(0)]["context"].text() == NEW);
  // A failed replacement keeps old pixels but cannot run the new binding.
  assert(store.submit(command(3, OLD, "Failure")).accepted);
  v::RenderJob failed; assert(store.next(failed)); assert(store.fail(failed, v::Error::FETCH_FAILED));
  assert(store.applied_revision(0) == 0);
  channel.sample({10, 1, false, scheduler.input_epoch()}, {1, 0, false}, 10);
  assert(channel.queued() == 0);
  scheduler.detach(); scheduler.attach(11);
  assert(!scheduler.complete(obsolete) && store.applied_revision(0) == 0);
  Json reconnected; channel.read(READER, 3, 11, reconnected);
  assert(reconnected["generation"].number() == 11 && reconnected["count"].number() == 0);
  assert(store.submit(command(4, NEW, "Recovered")).accepted); render(store, 2, memory); drain(scheduler);
  channel.read(READER, 0, 12, reconnected);
  for (int n = 0; n < 33; ++n) channel.sample({11, 1, false, scheduler.input_epoch()}, {1, 0, false}, 13);
  assert(channel.queued() == 0);  // Overflow clears the entire unreliable batch.
  Json overflow; channel.read(READER, 0, 14, overflow);
  channel.sample({11, 1, false, scheduler.input_epoch()}, {1, 0, false}, 15);
  Json expired; channel.read(READER, 0, 1015, expired);
  assert(expired["count"].number() == 0);  // No replay after reader lease expiry.
  channel.sample({11, 1, false, scheduler.input_epoch()}, {1, 0, false}, 1016);
  Json lost; channel.read(READER, 123, 1017, lost);
  assert(lost["count"].number() == 0);  // Lost response acknowledgement fails closed.
  channel.sample({11, 1, true, scheduler.input_epoch()}, {0, 0, true}, 1018);
  assert(channel.queued() == 0);
}

struct Fetcher : assets::Fetcher {
  bool running{false}, cancelled{false}; uint8_t *output{}; size_t capacity{}; uint64_t token{};
  v::Error error{v::Error::NONE}; std::vector<uint8_t> bytes;
  bool start(std::string_view, uint8_t *data, size_t size, uint64_t id) override {
    assert(!running); output = data; capacity = size; token = id; return running = true;
  }
  bool poll(assets::FetchResult &result) override {
    if (!running) return false;
    if (cancelled) return false;  // Exercise cancellation drain retaining the buffer.
    assert(bytes.size() <= capacity);
    if (!bytes.empty()) std::memcpy(output, bytes.data(), bytes.size());
    result = {token, error, bytes.size(), 200}; running = false; return true;
  }
  void cancel() override { cancelled = true; }
};
void provisioning_tests() {
  TestImageAllocator memory; Scheduler scheduler; v::Store store(1, scheduler);
  assets::OriginPolicy policy; assert(policy.add("http://old"));
  Fetcher fetch; assets::Pipeline pipeline(store, fetch, memory, memory, policy);
  assets::OriginProvisioner provision(policy, pipeline, fetch, memory);
  int saves = 0;
  provision.set_save([](void *context, const assets::OriginRecord &record) {
    assets::OriginPolicy restored; assert(record.policy(restored) && restored.allows("https://new/a.png"));
    ++*static_cast<int *>(context); return true;
  }, &saves);
  assert(std::string(provision.begin("https://new", "https://other/a.png", 0)) == "origin_not_allowed");
  assert(std::string(provision.begin("https://new\n", "https://new/a.png", 0)) == "invalid_origins");
  assert(std::string(provision.begin("https://new", "https://new/a.png", 0)) == "none");
  assert(policy.allows("http://old/a.png") && !policy.allows("https://new/a.png"));
  fetch.error = v::Error::CLOCK_NOT_READY; provision.loop(1);
  assert(saves == 0 && std::string(provision.status()) == "clock_not_ready");
  fetch.error = v::Error::NONE;
  std::ifstream image("tests/fixtures/png/rgba.png", std::ios::binary);
  fetch.bytes = {std::istreambuf_iterator<char>(image), {}};
  assert(std::string(provision.begin("https://new", "https://new/a.png", 2)) == "none");
  for (int n = 0; n < 1000 && provision.busy(); ++n) provision.loop(3);
  assert(saves == 1 && std::string(provision.status()) == "verified");
  assert(policy.allows("https://new/a.png") && !policy.allows("http://old/a.png"));
  assert(!policy.allows("http://new/a.png") && !policy.allows("https://new:444/a.png"));
  Json caps; v::capabilities(caps, policy);
  assert(caps["protocol_version"].number() == 2 && caps["origins"][size_t(0)].text() == "https://new:443");
  assert(std::string(provision.begin("https://new", "https://new/a.png", 4)) == "none");
  provision.loop(15004); assert(provision.busy() && fetch.cancelled && saves == 1);
  assets::OriginRecord corrupt; corrupt.count = 5; assert(!corrupt.policy(policy));
}
void position_tests() {
  v::State base, result; auto cmd = command(1, OLD, "long label"); cmd.fields = v::POSITION | v::TEXT;
  for (int align = 0; align < 3; ++align) for (int valign = 0; valign < 3; ++valign) {
    cmd.text_x = 24; cmd.text_y = 48; cmd.text_width = 48; cmd.text_height = 24;
    cmd.text_align = align; cmd.text_valign = valign;
    assert(v::apply_patch(cmd, base, result) == v::Error::NONE);
    rendering::Workspace workspace; rendering::Renderer renderer(workspace);
    assert(renderer.begin(result)); while (renderer.busy()) renderer.step();
    assert(renderer.phase() == rendering::Phase::DONE);
    for (int y = 0; y < 72; ++y) for (int x = 0; x < 72; ++x)
      if (y < 47 || x < 23) for (int c = 0; c < 3; ++c)
        assert(workspace.native[54 + (y * 72 + 71 - x) * 3 + c] == 0);
  }
  cmd.text_width = 49; assert(v::apply_patch(cmd, base, result) == v::Error::INVALID_POSITION);
  cmd.v2 = false; assert(v::apply_patch(cmd, base, result) == v::Error::INVALID_FIELDS);
}
int main() { input_tests(); provisioning_tests(); position_tests(); std::cout << "V2 input fences, paired contexts, leases, provisioning and positions passed\n"; }
