#include "usb_transport.h"
#include "idf_usb/stream_deck_quirk.h"

#include <algorithm>
#include <cassert>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <set>
#include <vector>

using namespace esphome::stream_deck;
namespace p = esphome::stream_deck::protocol;
namespace fake {
usb_host_client_config_t client{};
int identity = 0;
bool port = true, physical = true, gone = false, hold_cancellation = false, claimed = false;
unsigned allocations = 0, frees = 0;
std::set<usb_transfer_t *> pending;
std::vector<usb_transfer_t *> completed;
std::vector<std::vector<uint8_t>> writes;
std::vector<uint8_t> config;
usb_device_desc_t descriptor{0x0fd9, 0x0060};
uint8_t interface_number = 3;

void reset(bool interrupt_out) {
  assert(pending.empty() && allocations == frees);
  port = physical = true; gone = hold_cancellation = claimed = false;
  writes.clear(); completed.clear();
  descriptor = {0x0fd9, 0x0060};
  interface_number = 3;
  config = {9,2,25,0,1,1,0,0x80,50, 9,4,3,0,1,3,0,0,0, 7,5,0x85,3,64,0,1};
  if (interrupt_out) {
    config.insert(config.end(), {7,5,6,3,64,0,1});
    config[2] = 32; config[13] = 2;
  }
}
usb_transfer_t *transfer(bool input) {
  for (auto *t : pending) if (bool(t->bEndpointAddress & 0x80) == input) return t;
  return nullptr;
}
void complete(usb_transfer_t *t, int actual = -1, usb_transfer_status_t status = USB_TRANSFER_STATUS_COMPLETED) {
  assert(t && pending.count(t));
  pending.erase(t);
  t->status = status;
  t->actual_num_bytes = actual < 0 ? t->num_bytes : actual;
  completed.push_back(t);
}
void cancel_all() {
  while (!pending.empty()) complete(*pending.begin(), 0, USB_TRANSFER_STATUS_NO_DEVICE);
}
void finish(USBTransport &transport, uint32_t now) {
  transport.shutdown();
  transport.loop(now + 1);
  assert(pending.empty() && allocations == frees);
}
}  // namespace fake

const char *esp_err_to_name(esp_err_t) { return "fake status"; }
esp_err_t usb_host_install(const usb_host_config_t *) { return ESP_OK; }
esp_err_t usb_host_uninstall() { return ESP_OK; }
esp_err_t usb_host_client_register(const usb_host_client_config_t *c, usb_host_client_handle_t *handle) {
  fake::client = *c; *handle = &fake::client; return ESP_OK;
}
esp_err_t usb_host_client_deregister(usb_host_client_handle_t) { return ESP_OK; }
esp_err_t usb_host_lib_handle_events(TickType_t, uint32_t *flags) { *flags = 0; return ESP_OK; }
esp_err_t usb_host_device_free_all() { return ESP_OK; }
esp_err_t usb_host_client_handle_events(usb_host_client_handle_t, TickType_t) {
  if (fake::gone) {
    usb_host_client_event_msg_t event{};
    event.event = USB_HOST_CLIENT_EVENT_DEV_GONE; event.dev_gone.dev_hdl = &fake::identity;
    fake::client.async.client_event_callback(&event, fake::client.async.callback_arg);
    fake::gone = false;
  }
  auto completed = std::move(fake::completed);
  fake::completed.clear();
  for (auto *t : completed) t->callback(t);
  return ESP_OK;
}
esp_err_t usb_host_device_addr_list_fill(int, uint8_t *addresses, int *count) {
  *count = fake::port && fake::physical ? 1 : 0; addresses[0] = 7; return ESP_OK;
}
esp_err_t usb_host_device_open(usb_host_client_handle_t, uint8_t, usb_device_handle_t *device) {
  *device = &fake::identity; return ESP_OK;
}
esp_err_t usb_host_device_close(usb_host_client_handle_t, usb_device_handle_t) {
  assert(!fake::claimed && fake::pending.empty()); return ESP_OK;
}
esp_err_t usb_host_get_device_descriptor(usb_device_handle_t, const usb_device_desc_t **desc) {
  *desc = &fake::descriptor; return ESP_OK;
}
esp_err_t usb_host_get_active_config_descriptor(usb_device_handle_t, const usb_config_desc_t **desc) {
  *desc = reinterpret_cast<const usb_config_desc_t *>(fake::config.data()); return ESP_OK;
}
esp_err_t usb_host_device_info(usb_device_handle_t, usb_device_info_t *info) {
  info->speed = USB_SPEED_FULL; info->bConfigurationValue = 1; return ESP_OK;
}
esp_err_t usb_host_interface_claim(usb_host_client_handle_t, usb_device_handle_t, uint8_t number, uint8_t alt) {
  assert(number == fake::interface_number && alt == 0); fake::claimed = true; return ESP_OK;
}
esp_err_t usb_host_interface_release(usb_host_client_handle_t, usb_device_handle_t, uint8_t number) {
  assert(number == fake::interface_number && fake::pending.empty()); fake::claimed = false; return ESP_OK;
}
esp_err_t usb_host_transfer_alloc(size_t size, int, usb_transfer_t **out) {
  *out = new usb_transfer_t{new uint8_t[size]{}, size}; fake::allocations++; return ESP_OK;
}
esp_err_t usb_host_transfer_free(usb_transfer_t *t) {
  if (!t) return ESP_OK;
  assert(!fake::pending.count(t)); delete[] t->data_buffer; delete t; fake::frees++; return ESP_OK;
}
esp_err_t usb_host_transfer_submit(usb_transfer_t *t) {
  assert(!fake::pending.count(t) && size_t(t->num_bytes) <= t->data_buffer_size);
  if (!(t->bEndpointAddress & 0x80)) {
    assert(t->num_bytes <= 64 * 32);
    fake::writes.emplace_back(t->data_buffer, t->data_buffer + t->num_bytes);
  }
  fake::pending.insert(t); return ESP_OK;
}
esp_err_t usb_host_transfer_submit_control(usb_host_client_handle_t, usb_transfer_t *t) {
  assert(t->bEndpointAddress == 0 && size_t(t->num_bytes) <= t->data_buffer_size);
  assert(t->num_bytes == 8 + t->data_buffer[6] + 256 * t->data_buffer[7]);
  assert(t->data_buffer[4] == fake::interface_number);  // Synthetic tests also exercise interface 3.
  fake::writes.emplace_back(t->data_buffer, t->data_buffer + t->num_bytes);
  fake::pending.insert(t); return ESP_OK;
}
esp_err_t usb_host_lib_set_root_port_power(bool enabled) {
  fake::port = enabled;
  if (!enabled) {
    fake::gone = true;
    if (!fake::hold_cancellation) fake::cancel_all();
  }
  return ESP_OK;
}
esp_err_t usb_host_endpoint_halt(usb_device_handle_t, uint8_t endpoint) { assert(endpoint); return ESP_OK; }
esp_err_t usb_host_endpoint_flush(usb_device_handle_t, uint8_t endpoint) { assert(endpoint); return ESP_OK; }

void test_control_and_input() {
  fake::reset(false);
  USBTransport transport;
  assert(transport.setup());
  transport.loop(0);
  assert(transport.attached());
  Job job{JobKind::RESET, transport.generation(), 1};
  assert(transport.send(job, 1));
  const auto &wire = fake::writes.back();
  assert(wire.size() == 8199 && wire[2] == 2 && wire[3] == 2 && wire[8] == 2);
  assert(std::all_of(wire.begin() + 9, wire.end(), [](uint8_t b) { return b == 0; }));
  fake::complete(fake::transfer(false));
  transport.loop(2);
  Job done;
  assert(transport.take_completion(done) && done.generation == job.generation);
  auto *input = fake::transfer(true);
  input->data_buffer[0] = 0x7d; input->data_buffer[5] = 1;
  fake::complete(input, 16); transport.loop(3);
  InputReport report{};
  assert(transport.pop_input(report) && report.mask == 1);
  fake::complete(fake::transfer(true), 15); transport.loop(4);
  assert(!transport.pop_input(report) && transport.malformed_inputs() == 1);
  job.kind = JobKind::BRIGHTNESS; job.sequence++; job.brightness = 50;
  assert(transport.send(job, 5));
  assert(fake::writes.back().size() == 25 && fake::writes.back()[2] == 5 && fake::writes.back()[3] == 3);
  fake::complete(fake::transfer(false)); transport.loop(6);
  assert(transport.take_completion(done));
  fake::finish(transport, 7);
}

void test_interrupt_report_integrity() {
  fake::reset(true);
  USBTransport transport;
  assert(transport.setup()); transport.loop(0);
  std::ifstream f("tests/fixtures/asymmetric.native.bmp", std::ios::binary);
  std::vector<uint8_t> bytes{std::istreambuf_iterator<char>(f), {}};
  NativeImage image(bytes.data(), bytes.size());
  Job job{JobKind::PAGE1, transport.generation(), 1, 0, 30, &image};
  assert(transport.send(job, 1));
  uint32_t now = 2;
  while (fake::transfer(false)) { fake::complete(fake::transfer(false)); transport.loop(now++); }
  Job done;
  assert(transport.take_completion(done));
  assert(fake::writes.size() == 4);
  std::vector<uint8_t> joined;
  for (const auto &chunk : fake::writes) joined.insert(joined.end(), chunk.begin(), chunk.end());
  std::ifstream fixture("tests/fixtures/key_0_page_1.bin", std::ios::binary);
  const std::vector<uint8_t> expected{std::istreambuf_iterator<char>(fixture), {}};
  assert(joined == expected && joined.size() == 8191);
  fake::finish(transport, now);
}

void test_deadline_retains_buffers_until_cancelled() {
  fake::reset(false);
  USBTransport transport;
  assert(transport.setup()); transport.loop(0);
  const auto generation = transport.generation();
  Job job{JobKind::RESET, generation, 1};
  assert(transport.send(job, 1));
  const auto before = fake::frees;
  fake::hold_cancellation = true;
  transport.loop(3001);
  assert(!transport.attached() && transport.generation() != generation);
  transport.loop(20000);
  assert(fake::frees == before && fake::pending.size() == 2);
  assert(!transport.take_completion(job));
  fake::cancel_all(); fake::hold_cancellation = false;
  transport.loop(20001);
  assert(fake::frees == before + 2);
  transport.loop(22000);
  assert(transport.attached() && transport.generation() != generation);
  assert(!transport.send(Job{JobKind::RESET, generation, 2}, 22001));
  fake::finish(transport, 23000);
}

void test_short_and_stalled_output() {
  for (const auto status : {USB_TRANSFER_STATUS_COMPLETED, USB_TRANSFER_STATUS_STALL}) {
    fake::reset(false);
    USBTransport transport;
    assert(transport.setup()); transport.loop(0);
    Job job{JobKind::RESET, transport.generation(), 1};
    assert(transport.send(job, 1));
    fake::complete(fake::transfer(false), 10, status);
    transport.loop(2);
    assert(!transport.attached() && transport.errors() == 1);
    assert(!transport.take_completion(job));
    fake::finish(transport, 3);
  }
}

void test_absence_and_wrong_model() {
  fake::reset(false); fake::physical = false;
  USBTransport transport;
  assert(transport.setup()); transport.loop(0);
  assert(!transport.attached());
  fake::physical = true; fake::descriptor.idProduct = 0x006d;
  transport.loop(1000); assert(!transport.attached() && fake::pending.empty());
  fake::descriptor.idProduct = 0x0060;
  transport.loop(2000); assert(transport.attached());
  fake::finish(transport, 2001);
}

std::vector<uint8_t> observed_config() {
  std::ifstream input("tests/fixtures/s3_0060/configuration_full_speed.hex");
  assert(input.good());
  std::vector<uint8_t> config;
  unsigned byte;
  while (input >> std::hex >> byte) {
    assert(byte <= 0xff);
    config.push_back(uint8_t(byte));
  }
  assert(input.eof() && config.size() == 41);
  return config;
}

void test_observed_full_speed_descriptor_rejection() {
  fake::reset(false);
  fake::config = observed_config();
  const auto allocations = fake::allocations;
  USBTransport transport;
  assert(transport.setup());
  transport.loop(0);  // Fake device_info reports FULL, just like the S3 capture.
  assert(!transport.attached() && transport.errors() == 1);
  assert(!fake::claimed && fake::pending.empty() && fake::writes.empty());
  assert(fake::allocations == allocations);
  transport.loop(4999);
  assert(transport.errors() == 1);  // Rejection diagnostics are rate bounded.
  transport.loop(5000);
  assert(transport.errors() == 2 && fake::writes.empty());
  fake::finish(transport, 5001);
}

void test_normalized_original_descriptor_transport() {
  fake::reset(false);
  fake::config = observed_config();
  // Emulate the SDK enumeration hook before clients can see the configuration.
  assert(stream_deck_normalize_config(0x0fd9, 0x0060, true, fake::config.data(), fake::config.size()));
  fake::interface_number = 0;
  USBTransport transport;
  assert(transport.setup());
  transport.loop(0);
  assert(transport.attached() && transport.errors() == 0);
  assert(fake::transfer(true)->bEndpointAddress == 0x81);
  assert(fake::transfer(true)->num_bytes == 64);
  Job job{JobKind::RESET, transport.generation(), 1};
  assert(transport.send(job, 1));
  uint32_t now = 2;
  while (fake::transfer(false)) {
    assert(fake::transfer(false)->bEndpointAddress == 0x02);
    fake::complete(fake::transfer(false));
    transport.loop(now++);
  }
  Job done;
  assert(transport.take_completion(done) && fake::writes.size() == 4);
  std::vector<uint8_t> joined;
  for (const auto &chunk : fake::writes) joined.insert(joined.end(), chunk.begin(), chunk.end());
  std::ifstream fixture("tests/fixtures/stream_reset.bin", std::ios::binary);
  const std::vector<uint8_t> expected{std::istreambuf_iterator<char>(fixture), {}};
  assert(joined == expected && joined.size() == 8191);
  job.kind = JobKind::BRIGHTNESS;
  job.sequence++;
  job.brightness = 30;
  assert(transport.send(job, now++));
  assert(fake::writes.back().size() == 25 && fake::writes.back()[4] == 0);
  fake::complete(fake::transfer(false));
  transport.loop(now++);
  assert(transport.take_completion(done));
  fake::finish(transport, now);
}

int main() {
  test_control_and_input(); test_interrupt_report_integrity();
  test_deadline_retains_buffers_until_cancelled(); test_short_and_stalled_output(); test_absence_and_wrong_model();
  test_observed_full_speed_descriptor_rejection();
  test_normalized_original_descriptor_transport();
  std::cout << "Production USB transport passed fake-IDF transfer and lifetime tests (no hardware)\n";
}
