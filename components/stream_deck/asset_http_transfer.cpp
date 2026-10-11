#include "asset_http.h"
#include "asset_policy.h"
#include "esphome/core/defines.h"
#ifdef USE_STREAM_DECK_ASSETS
#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "esp_timer.h"
#include "esp_transport.h"
#include "esp_transport_tcp.h"
#include "esp_transport_ssl.h"
#include <algorithm>
#include <cstring>
#include <ctime>
#include <strings.h>

namespace esphome::stream_deck::assets {
namespace {
uint32_t now_ms() { return uint32_t(esp_timer_get_time() / 1000); }
constexpr size_t HEADER_LIMIT = 8192, WIRE_LIMIT = visual::MAX_ENCODED_BYTES + 65536;
// IDF's HTTP parser is reused; this transport boundary caps every blocking I/O
// operation and accumulated bytes, including slow header/chunk-framing streams.
struct BoundedTransport {
  const std::atomic<bool> &cancelled;
  esp_transport_handle_t underlying{nullptr};
  uint32_t started{now_ms()};
  size_t wire_bytes{0}, header_bytes{0}, parsed_header_bytes{0};
  bool headers{true};
  visual::Error error{visual::Error::NONE};
  bool stopped() {
    if (cancelled.load(std::memory_order_acquire)) error = visual::Error::FETCH_FAILED;
    else if (uint32_t(now_ms() - started) >= visual::FETCH_TIMEOUT_MS) error = visual::Error::FETCH_TIMEOUT;
    return error != visual::Error::NONE;
  }
  int timeout(int requested) {
    if (stopped()) return 1;
    const uint32_t elapsed = now_ms() - started;
    if (elapsed >= visual::FETCH_TIMEOUT_MS) return 1;
    return int(std::min(uint32_t(std::max(1, requested)), visual::FETCH_TIMEOUT_MS - elapsed));
  }
};
BoundedTransport &context(esp_transport_handle_t t) { return *static_cast<BoundedTransport *>(esp_transport_get_context_data(t)); }
int connect(esp_transport_handle_t t, const char *host, int port, int timeout) {
  auto &c = context(t); if (c.stopped()) return -1;
  const int result = esp_transport_connect(c.underlying, host, port, c.timeout(std::min(timeout, int(visual::CONNECT_TIMEOUT_MS))));
  return c.stopped() ? -1 : result;
}
int read(esp_transport_handle_t t, char *buffer, int length, int timeout) {
  auto &c = context(t); if (c.stopped()) return -1;
  const auto remaining = std::min(WIRE_LIMIT - c.wire_bytes, c.headers ? HEADER_LIMIT - c.header_bytes : WIRE_LIMIT);
  if (!remaining) { c.error = visual::Error::LIMIT_EXCEEDED; return -1; }
  const int result = esp_transport_read(c.underlying, buffer, int(std::min(size_t(length), remaining)), c.timeout(std::min(timeout, 500)));
  if (result > 0) { c.wire_bytes += result; if (c.headers) c.header_bytes += result; }
  return c.stopped() ? -1 : result;
}
int write(esp_transport_handle_t t, const char *buffer, int length, int timeout) {
  auto &c = context(t); if (c.stopped()) return -1;
  const int result = esp_transport_write(c.underlying, buffer, length, c.timeout(std::min(timeout, 500)));
  return c.stopped() ? -1 : result;
}
int close(esp_transport_handle_t t) { return esp_transport_close(context(t).underlying); }
int poll_read(esp_transport_handle_t t, int timeout) {
  auto &c = context(t); if (c.stopped()) return -1;
  return esp_transport_poll_read(c.underlying, c.timeout(std::min(timeout, 500)));
}
int poll_write(esp_transport_handle_t t, int timeout) {
  auto &c = context(t); if (c.stopped()) return -1;
  return esp_transport_poll_write(c.underlying, c.timeout(std::min(timeout, 500)));
}
int destroy(esp_transport_handle_t) { return 0; }  // Underlying handle has a separate owner.
esp_err_t event(esp_http_client_event_t *event) {
  auto &c = *static_cast<BoundedTransport *>(event->user_data);
  if (event->event_id == HTTP_EVENT_ON_HEADER) {
    const auto key = event->header_key, value = event->header_value;
    c.parsed_header_bytes += std::strlen(key) + std::strlen(value) + 4;
    if (c.parsed_header_bytes > HEADER_LIMIT) c.error = visual::Error::LIMIT_EXCEEDED;
    if (strcasecmp(key, "Content-Encoding") == 0 && strcasecmp(value, "identity") != 0)
      c.error = visual::Error::UNSUPPORTED_ENCODING;
    if (strcasecmp(key, "Content-Type") == 0 &&
        (strncasecmp(value, "image/png", 9) != 0 || (value[9] && value[9] != ';' && value[9] != ' ')))
      c.error = visual::Error::UNSUPPORTED_PNG;
  }
  return ESP_OK;  // IDF ignores handler errors; the transport checks c.error.
}
}

FetchResult fetch_http(const char *url, uint8_t *output, size_t capacity, uint64_t token,
                       const std::atomic<bool> &cancelled, const char *ca_certificate) {
  FetchResult result{token, visual::Error::FETCH_FAILED};
  Origin origin;
  if (!url || !output || capacity != visual::MAX_ENCODED_BYTES || !url_origin(url, origin)) return result;
  // A boot-default epoch cannot meaningfully validate certificate dates. The
  // normal probe waits for HA time; typed callers receive an explicit failure.
  if (origin.tls && std::time(nullptr) < 1609459200) {
    result.error = visual::Error::CLOCK_NOT_READY; return result;
  }
  BoundedTransport c{cancelled};
  if (c.stopped()) { result.error = c.error; return result; }
  c.underlying = origin.tls ? esp_transport_ssl_init() : esp_transport_tcp_init();
  auto *bounded = esp_transport_init();
  if (!c.underlying || !bounded) {
    if (c.underlying) esp_transport_destroy(c.underlying);
    if (bounded) esp_transport_destroy(bounded);
    result.error = visual::Error::OUT_OF_MEMORY; return result;
  }
  if (origin.tls) {
    if (ca_certificate) esp_transport_ssl_set_cert_data(c.underlying, ca_certificate, std::strlen(ca_certificate) + 1);
    else esp_transport_ssl_crt_bundle_attach(c.underlying, esp_crt_bundle_attach);
    // Do not call skip_common_name_check or enable any insecure TLS mode.
  }
  esp_transport_set_context_data(bounded, &c);
  esp_transport_set_default_port(bounded, origin.port);
  esp_transport_set_func(bounded, connect, read, write, close, poll_read, poll_write, destroy);
  esp_http_client_config_t config{};
  config.url = url; config.method = HTTP_METHOD_GET; config.auth_type = HTTP_AUTH_TYPE_NONE;
  config.port = origin.port;
  config.transport_type = origin.tls ? HTTP_TRANSPORT_OVER_SSL : HTTP_TRANSPORT_OVER_TCP;
  config.timeout_ms = visual::CONNECT_TIMEOUT_MS; config.disable_auto_redirect = true;
  config.max_authorization_retries = -1; config.buffer_size = 1024; config.buffer_size_tx = 1024;
  config.user_agent = "ESP-Deck/1"; config.event_handler = event; config.user_data = &c;
  config.transport = bounded;
  if (origin.tls) {
    if (ca_certificate) config.cert_pem = ca_certificate;
    else config.crt_bundle_attach = esp_crt_bundle_attach;
  }
  const auto client = esp_http_client_init(&config);
  if (!client) result.error = visual::Error::OUT_OF_MEMORY;
  else {
    const bool headers_ok = esp_http_client_set_header(client, "Accept", "image/png") == ESP_OK &&
        esp_http_client_set_header(client, "Accept-Encoding", "identity") == ESP_OK &&
        esp_http_client_set_header(client, "Cache-Control", "no-cache") == ESP_OK;
    if (headers_ok && esp_http_client_open(client, 0) == ESP_OK && !c.stopped()) {
      const auto length = esp_http_client_fetch_headers(client);
      c.headers = false;
      result.http_status = esp_http_client_get_status_code(client);
      if (length < 0 || c.stopped()) result.error = c.error == visual::Error::NONE ? visual::Error::FETCH_FAILED : c.error;
      else if (result.http_status != 200) result.error = visual::Error::HTTP_STATUS;
      else if (uint64_t(length) > capacity) result.error = visual::Error::LIMIT_EXCEEDED;
      else {
        esp_http_client_set_timeout_ms(client, 500);
        for (;;) {
          if (c.stopped()) { result.error = c.error; break; }
          uint8_t extra;
          const size_t room = capacity - result.bytes;
          const int got = esp_http_client_read(client, reinterpret_cast<char *>(room ? output + result.bytes : &extra),
                                               int(std::min(size_t(1024), room ? room : 1)));
          if (c.stopped()) { result.error = c.error; break; }
          if (got < 0) break;
          if (got == 0) {
            if (esp_http_client_is_complete_data_received(client) && (!length || uint64_t(length) == result.bytes))
              result.error = visual::Error::NONE;
            break;
          }
          if (size_t(got) > room) { result.error = visual::Error::LIMIT_EXCEEDED; break; }
          result.bytes += size_t(got);
        }
      }
    }
    if (c.error != visual::Error::NONE) result.error = c.error;
    esp_http_client_cleanup(client);  // Closes the custom transport; does not own/destroy it.
  }
  esp_transport_destroy(bounded);
  esp_transport_destroy(c.underlying);
  return result;
}
}  // namespace esphome::stream_deck::assets
#endif
