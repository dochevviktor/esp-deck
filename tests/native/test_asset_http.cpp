#include "asset_http.h"
#include "http_test_api.h"
#include "freertos/task.h"
#include <algorithm>
#include <cassert>
#include <cstring>
#include <ctime>
#include <iostream>
#include <map>
#include <string>
#include <vector>
using namespace esphome::stream_deck;
namespace a = esphome::stream_deck::assets;
namespace v = esphome::stream_deck::visual;
struct FakeTransport {
  bool native{false}, tls{false}, verified{false}; void *context{nullptr};
  connect_func connect{}; io_read_func read{}; io_func write{}; trans_func close{}, destroy{};
  poll_func poll_read{}, poll_write{};
};
struct FakeClient { esp_http_client_config_t config; };
namespace fake {
uint64_t now = 0;
time_t wall_time = 1800000000;
unsigned delay = 0, connects = 0, transports = 0, clients = 0;
bool invalid_certificate = false, complete = true, fail_init = false;
size_t cursor = 0, cancel_after = SIZE_MAX;
int status = 200; int64_t length = 4;
std::string headers, wire;
std::vector<uint8_t> body;
std::atomic<bool> *cancel = nullptr;
std::map<std::string, std::string> request_headers;
bool used_bundle = false, used_custom_ca = false;
struct WorkerBlocked {};
struct Task { void (*function)(void *){nullptr}; void *argument{nullptr}; unsigned notifications{0}; } task;
bool fail_task = false;
unsigned task_creations = 0;
void drain_worker() {
  // Run the real worker until its next blocking wait. No host thread, race or
  // hardware timing is inferred from this deterministic FreeRTOS test double.
  try { task.function(task.argument); } catch (const WorkerBlocked &) { return; }
  assert(false);
}
void reset(size_t bytes = 4) {
  assert(transports == 0 && clients == 0);
  now = delay = connects = 0; cursor = 0; cancel_after = SIZE_MAX;
  wall_time = 1800000000;
  invalid_certificate = fail_init = false; complete = true; status = 200; length = int64_t(bytes);
  headers = "Content-Type: image/png\r\n"; body.assign(bytes, 0x5a); cancel = nullptr;
  used_bundle = used_custom_ca = false; request_headers.clear();
}
}
BaseType_t xTaskCreate(void (*function)(void *), const char *name, uint32_t stack,
                      void *argument, UBaseType_t priority, TaskHandle_t *handle) {
  assert(std::string(name) == "deck_assets" && stack == 8192 && priority == 1);
  if (fake::fail_task) return 0;
  fake::task = {function, argument, 0}; *handle = &fake::task; fake::task_creations++;
  return pdPASS;
}
void xTaskNotifyGive(TaskHandle_t handle) { assert(handle == &fake::task); fake::task.notifications++; }
uint32_t ulTaskNotifyTake(BaseType_t clear, TickType_t wait) {
  assert(clear == pdTRUE && wait == portMAX_DELAY);
  if (!fake::task.notifications) throw fake::WorkerBlocked{};
  const auto count = fake::task.notifications; fake::task.notifications = 0; return count;
}
extern "C" time_t time(time_t *result) noexcept {
  if (result) *result = fake::wall_time;
  return fake::wall_time;
}
int64_t esp_timer_get_time() { return int64_t(fake::now * 1000); }
esp_err_t esp_crt_bundle_attach(void *) { return ESP_OK; }
esp_transport_handle_t esp_transport_init() { fake::transports++; return new FakeTransport{}; }
esp_transport_handle_t esp_transport_tcp_init() { auto *t = esp_transport_init(); t->native = true; return t; }
esp_transport_handle_t esp_transport_ssl_init() { auto *t = esp_transport_tcp_init(); t->tls = true; return t; }
int esp_transport_destroy(esp_transport_handle_t t) { if (t->destroy) t->destroy(t); delete t; fake::transports--; return 0; }
int esp_transport_connect(esp_transport_handle_t t, const char *host, int port, int timeout) {
  if (!t->native) return t->connect(t, host, port, timeout);
  assert(timeout > 0 && timeout <= 5000); fake::connects++;
  if (t->tls) { assert(t->verified); if (fake::invalid_certificate) return -1; }
  return 0;
}
int esp_transport_read(esp_transport_handle_t t, char *buffer, int length, int timeout) {
  if (!t->native) return t->read(t, buffer, length, timeout);
  assert(timeout > 0 && timeout <= 500);
  fake::now += fake::delay;
  const auto size = std::min(size_t(length), fake::wire.size() - fake::cursor);
  std::memcpy(buffer, fake::wire.data() + fake::cursor, size); fake::cursor += size;
  if (fake::cancel && fake::cursor >= fake::cancel_after) fake::cancel->store(true);
  return int(size);
}
int esp_transport_write(esp_transport_handle_t t, const char *buffer, int length, int timeout) {
  return t->native ? length : t->write(t, buffer, length, timeout);
}
int esp_transport_close(esp_transport_handle_t t) { return t->native ? 0 : t->close(t); }
int esp_transport_poll_read(esp_transport_handle_t t, int timeout) { return t->native ? 1 : t->poll_read(t, timeout); }
int esp_transport_poll_write(esp_transport_handle_t t, int timeout) { return t->native ? 1 : t->poll_write(t, timeout); }
void *esp_transport_get_context_data(esp_transport_handle_t t) { return t->context; }
int esp_transport_set_context_data(esp_transport_handle_t t, void *data) { t->context = data; return 0; }
int esp_transport_set_default_port(esp_transport_handle_t, int) { return 0; }
int esp_transport_set_func(esp_transport_handle_t t, connect_func c, io_read_func r, io_func w, trans_func close,
                          poll_func pr, poll_func pw, trans_func destroy) {
  t->connect = c; t->read = r; t->write = w; t->close = close; t->poll_read = pr; t->poll_write = pw; t->destroy = destroy;
  return 0;
}
void esp_transport_ssl_set_cert_data(esp_transport_handle_t t, const char *cert, int length) {
  assert(t->tls && cert && length > 0); t->verified = true; fake::used_custom_ca = true;
}
void esp_transport_ssl_crt_bundle_attach(esp_transport_handle_t t, esp_err_t (*attach)(void *)) {
  assert(t->tls && attach == esp_crt_bundle_attach); t->verified = true; fake::used_bundle = true;
}
esp_http_client_handle_t esp_http_client_init(const esp_http_client_config_t *config) {
  assert(config->auth_type == HTTP_AUTH_TYPE_NONE && config->disable_auto_redirect);
  assert(config->max_authorization_retries == -1 && !config->skip_cert_common_name_check);
  assert(config->buffer_size == 1024 && config->buffer_size_tx == 1024);
  const bool tls = std::string(config->url).rfind("https://", 0) == 0;
  assert(config->transport_type == (tls ? HTTP_TRANSPORT_OVER_SSL : HTTP_TRANSPORT_OVER_TCP));
  assert(config->port == (tls ? 443 : 8123));
  if (fake::fail_init) return nullptr;
  fake::wire = "HTTP/1.1 " + std::to_string(fake::status) + " Reply\r\n" + fake::headers + "\r\n";
  fake::wire.append(reinterpret_cast<const char *>(fake::body.data()), fake::body.size());
  fake::clients++; return new FakeClient{*config};
}
esp_err_t esp_http_client_set_header(esp_http_client_handle_t, const char *key, const char *value) {
  fake::request_headers[key] = value; return ESP_OK;
}
esp_err_t esp_http_client_open(esp_http_client_handle_t c, int length) {
  assert(length == 0);
  if (esp_transport_connect(c->config.transport, "ha.local", c->config.port, c->config.timeout_ms) < 0) return ESP_FAIL;
  const char *request = "GET /icon.png HTTP/1.1\r\n\r\n";
  return esp_transport_write(c->config.transport, request, int(std::strlen(request)), 500) > 0 ? ESP_OK : ESP_FAIL;
}
int64_t esp_http_client_fetch_headers(esp_http_client_handle_t c) {
  std::string received; char ch;
  while (received.size() < 4 || received.substr(received.size() - 4) != "\r\n\r\n") {
    if (esp_transport_read(c->config.transport, &ch, 1, 500) != 1) return -1;
    received += ch;
  }
  size_t offset = 0;
  while (offset < fake::headers.size()) {
    const auto end = fake::headers.find("\r\n", offset), colon = fake::headers.find(':', offset);
    assert(end != std::string::npos && colon < end);
    auto key = fake::headers.substr(offset, colon - offset), value = fake::headers.substr(colon + 2, end - colon - 2);
    esp_http_client_event_t event{HTTP_EVENT_ON_HEADER, c->config.user_data, key.data(), value.data()};
    c->config.event_handler(&event); offset = end + 2;
  }
  return fake::length;
}
int esp_http_client_get_status_code(esp_http_client_handle_t) { return fake::status; }
esp_err_t esp_http_client_set_timeout_ms(esp_http_client_handle_t c, int timeout) { c->config.timeout_ms = timeout; return ESP_OK; }
int esp_http_client_read(esp_http_client_handle_t c, char *buffer, int length) {
  return esp_transport_read(c->config.transport, buffer, length, c->config.timeout_ms);
}
bool esp_http_client_is_complete_data_received(esp_http_client_handle_t) { return fake::complete && fake::cursor == fake::wire.size(); }
int esp_http_client_cleanup(esp_http_client_handle_t c) {
  esp_transport_close(c->config.transport); delete c; fake::clients--; return 0;
}

int main() {
  std::vector<uint8_t> output(v::MAX_ENCODED_BYTES);
  std::atomic<bool> cancelled{false};
  const auto run = [&](const char *url = "http://ha.local:8123/icon.png", const char *ca = nullptr) {
    const auto result = a::fetch_http(url, output.data(), output.size(), 42, cancelled, ca);
    assert(result.token == 42 && fake::transports == 0 && fake::clients == 0);
    return result;
  };
  fake::reset(); assert(run().error == v::Error::NONE);
  // P8 provisioning supplies 32 KiB, not the ordinary 128 KiB artwork buffer.
  // Exercise both production admission and the real worker/HTTP path together.
  {
    std::vector<uint8_t> probe(32768 + 2, 0xa5);
    a::HttpFetcher fetcher;
    assert(!fetcher.start("http://ha.local:8123/probe", probe.data() + 1, 0, 1));
    assert(!fetcher.start("http://ha.local:8123/probe", probe.data() + 1, v::MAX_ENCODED_BYTES + 1, 1));
    assert(!fetcher.start("http://ha.local:8123/probe", nullptr, 32768, 1));
    assert(fake::task_creations == 0);
    fake::fail_task = true;
    assert(!fetcher.start("http://ha.local:8123/probe", probe.data() + 1, 32768, 1));
    fake::fail_task = false;
    for (const auto bytes : {size_t(4), size_t(32768), size_t(32769)}) {
      for (const bool declared : {true, false}) {
        fake::reset(bytes);
        if (!declared) fake::length = 0;
        assert(fetcher.start("http://ha.local:8123/probe", probe.data() + 1, 32768, bytes));
        assert(!fetcher.start("http://ha.local:8123/probe", probe.data() + 1, 32768, 999));
        a::FetchResult result;
        assert(!fetcher.poll(result));
        fake::drain_worker();
        assert(fetcher.poll(result) && result.token == bytes);
        assert(result.error == (bytes <= 32768 ? v::Error::NONE : v::Error::LIMIT_EXCEEDED));
        assert(result.bytes <= 32768 && probe.front() == 0xa5 && probe.back() == 0xa5);
        assert(!fetcher.poll(result));
      }
    }
    fake::reset();
    assert(fetcher.start("http://ha.local:8123/probe", probe.data() + 1, 32768, 100));
    fetcher.cancel(); fake::drain_worker();
    a::FetchResult result;
    assert(fetcher.poll(result) && result.error == v::Error::FETCH_FAILED && result.token == 100);
    assert(fake::connects == 0 && fake::task_creations == 1);
    fake::reset();
    assert(fetcher.start("http://ha.local:8123/icon.png", output.data(), output.size(), 101));
    fake::drain_worker();
    assert(fetcher.poll(result) && result.error == v::Error::NONE && result.bytes == 4);
    assert(a::fetch_http("http://ha.local:8123/icon.png", output.data(), 0, 1, cancelled).error == v::Error::FETCH_FAILED);
    assert(a::fetch_http("http://ha.local:8123/icon.png", output.data(), v::MAX_ENCODED_BYTES + 1, 1, cancelled).error == v::Error::FETCH_FAILED);
  }
  assert(fake::request_headers.at("Cache-Control") == "no-cache" && fake::request_headers.at("Accept-Encoding") == "identity");
  fake::reset(); assert(run("https://ha.local/icon.png").error == v::Error::NONE && fake::used_bundle);
  fake::reset(); fake::wall_time = 0;
  assert(run("https://ha.local/icon.png").error == v::Error::CLOCK_NOT_READY && fake::connects == 0);
  fake::reset(); assert(run("https://ha.local/icon.png", "TEST CA").error == v::Error::NONE && fake::used_custom_ca);
  fake::reset(); fake::invalid_certificate = true;
  assert(run("https://ha.local/icon.png").error == v::Error::FETCH_FAILED && fake::connects == 1);
  fake::reset(); fake::status = 302; fake::headers += "Location: https://elsewhere.test/secret\r\n";
  assert(run().error == v::Error::HTTP_STATUS && fake::connects == 1);
  fake::reset(); fake::status = 401; assert(run().error == v::Error::HTTP_STATUS && fake::connects == 1);
  fake::reset(); fake::headers += "Content-Encoding: gzip\r\n";
  assert(run().error == v::Error::UNSUPPORTED_ENCODING);
  fake::reset(); fake::headers = "Content-Type: text/html\r\n"; assert(run().error == v::Error::UNSUPPORTED_PNG);
  fake::reset(); fake::headers += "Large: " + std::string(9000, 'x') + "\r\n";
  assert(run().error == v::Error::LIMIT_EXCEEDED);
  fake::reset(); fake::delay = 499; assert(run().error == v::Error::FETCH_TIMEOUT && fake::now < 16000);
  fake::reset(); fake::now = 0xfffff000; fake::delay = 499; assert(run().error == v::Error::FETCH_TIMEOUT);
  fake::reset(); fake::length = int64_t(v::MAX_ENCODED_BYTES + 1); assert(run().error == v::Error::LIMIT_EXCEEDED);
  fake::reset(v::MAX_ENCODED_BYTES + 1); fake::length = 0;
  assert(run().error == v::Error::LIMIT_EXCEEDED);  // Chunked/unknown-length byte counter.
  fake::reset(v::MAX_ENCODED_BYTES); fake::length = 0;
  assert(run().error == v::Error::NONE);
  fake::reset(); fake::length = 5; assert(run().error == v::Error::FETCH_FAILED);
  fake::reset(); fake::length = 0; fake::complete = false; assert(run().error == v::Error::FETCH_FAILED);
  fake::reset(); fake::cancel = &cancelled; fake::cancel_after = 8;
  assert(run().error == v::Error::FETCH_FAILED); cancelled.store(false);
  fake::reset(); fake::fail_init = true; assert(run().error == v::Error::OUT_OF_MEMORY);
  fake::reset(); assert(run("http://ha.local/icon.png?token=secret").error == v::Error::FETCH_FAILED && fake::connects == 0);
  std::cout << "Production HTTP guards, TLS configuration, deadlines, cancellation and cleanup passed with fake IDF\n";
}
