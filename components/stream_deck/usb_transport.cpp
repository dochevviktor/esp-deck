#include "usb_transport.h"

#include <cstring>

#include "esphome/core/log.h"
#include "freertos/task.h"
#include "esp_intr_alloc.h"

namespace esphome::stream_deck {
static const char *const TAG = "stream_deck.usb";
static constexpr uint32_t OUTPUT_DEADLINE_MS = 3000;
static constexpr uint32_t RECOVERY_DELAY_MS = 5000;

bool USBTransport::setup() {
  usb_host_config_t host{};
  host.intr_flags = ESP_INTR_FLAG_LEVEL1;
  auto err = usb_host_install(&host);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Host install failed: %s", esp_err_to_name(err));
    return false;
  }
  usb_host_client_config_t client{};
  client.is_synchronous = false;
  client.max_num_event_msg = 8;
  client.async.client_event_callback = client_event_;
  client.async.callback_arg = this;
  err = usb_host_client_register(&client, &client_);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Client registration failed: %s", esp_err_to_name(err));
    usb_host_uninstall();
    return false;
  }
  if (xTaskCreate(library_task_, "deck_usb", 4096, nullptr, 5, nullptr) != pdPASS) {
    ESP_LOGE(TAG, "Cannot allocate USB library task");
    usb_host_client_deregister(client_);
    client_ = nullptr;
    usb_host_uninstall();
    return false;
  }
  installed_ = true;
  ESP_LOGI(TAG, "USB host installed; VBUS is externally supplied and unswitched");
  return true;
}

void USBTransport::library_task_(void *) {
  // Lives until MCU reset. Never touches entities or transport-owned buffers.
  for (;;) {
    uint32_t flags = 0;
    usb_host_lib_handle_events(pdMS_TO_TICKS(100), &flags);
    if (flags & USB_HOST_LIB_EVENT_FLAGS_NO_CLIENTS) usb_host_device_free_all();
  }
}

void USBTransport::client_event_(const usb_host_client_event_msg_t *event, void *arg) {
  auto *self = static_cast<USBTransport *>(arg);
  if (event->event == USB_HOST_CLIENT_EVENT_DEV_GONE && event->dev_gone.dev_hdl == self->device_)
    self->gone_ = true;
  // Discovery uses the address list, including devices enumerated before registration.
}
void USBTransport::input_done_(usb_transfer_t *transfer) {
  auto *self = static_cast<USBTransport *>(transfer->context);
  self->input_pending_ = false;
  self->input_done_flag_ = true;
  self->captured_epoch_ = self->input_epoch_ ? *self->input_epoch_ : 0;
  if (transfer->status == USB_TRANSFER_STATUS_NO_DEVICE) self->gone_ = true;
}
void USBTransport::output_done_(usb_transfer_t *transfer) {
  auto *self = static_cast<USBTransport *>(transfer->context);
  self->output_pending_ = false;
  self->output_done_flag_ = true;
  if (transfer->status == USB_TRANSFER_STATUS_NO_DEVICE) self->gone_ = true;
}

void USBTransport::discover_(uint32_t now) {
  next_discovery_ = now + 1000;
  uint8_t addresses[8];
  int count = 0;
  if (usb_host_device_addr_list_fill(sizeof(addresses), addresses, &count) != ESP_OK) return;
  for (int i = 0; i < count; i++) {
    usb_device_handle_t device = nullptr;
    if (usb_host_device_open(client_, addresses[i], &device) != ESP_OK) continue;
    const usb_device_desc_t *desc = nullptr;
    if (usb_host_get_device_descriptor(device, &desc) != ESP_OK || desc->idVendor != 0x0fd9 ||
        desc->idProduct != 0x0060) {
      usb_host_device_close(client_, device);
      continue;
    }
    const usb_config_desc_t *config = nullptr;
    protocol::Interface found{};
    usb_device_info_t info{};
    const auto info_error = usb_host_device_info(device, &info);
    const auto config_error = usb_host_get_active_config_descriptor(device, &config);
    if (info_error != ESP_OK || info.speed != USB_SPEED_FULL || config_error != ESP_OK || config == nullptr ||
        !protocol::find_interface(reinterpret_cast<const uint8_t *>(config), config->wTotalLength, found)) {
      errors_++;
      ESP_LOGW(TAG, "Rejecting unsupported/ambiguous descriptors for 0FD9:0060");
      {
        ESP_LOGW(TAG, "Descriptor query: info=%s speed=%d (full=%d), config=%s",
                 esp_err_to_name(info_error), int(info.speed), int(USB_SPEED_FULL), esp_err_to_name(config_error));
        if (config_error == ESP_OK && config != nullptr) {
          // Bounded to 96 bytes per five-second discovery retry, including when
          // API logging connects late. These descriptors contain no serial text.
          const size_t captured = config->wTotalLength < 96 ? config->wTotalLength : 96;
          const auto *bytes = reinterpret_cast<const uint8_t *>(config);
          constexpr char HEX[] = "0123456789ABCDEF";
          for (size_t offset = 0; offset < captured; offset += 16) {
            char hex[3 * 16 + 1]{};
            const size_t count = captured - offset < 16 ? captured - offset : 16;
            for (size_t n = 0; n < count; n++) {
              const auto byte = bytes[offset + n];
              hex[3 * n] = HEX[byte >> 4];
              hex[3 * n + 1] = HEX[byte & 15];
              hex[3 * n + 2] = n + 1 < count ? ' ' : '\0';
            }
            ESP_LOGW(TAG, "Configuration bytes %u/%u: %s", unsigned(offset), unsigned(config->wTotalLength), hex);
          }
        }
      }
      usb_host_device_close(client_, device);
      next_discovery_ = now + RECOVERY_DELAY_MS;
      return;
    }
    device_ = device;
    interface_ = found;
    auto err = usb_host_interface_claim(client_, device_, found.number, found.alternate);
    if (err != ESP_OK) { fail_(now, "interface claim", err); return; }
    claimed_ = true;
    err = usb_host_transfer_alloc(found.in_packet_size, 0, &input_);
    if (err == ESP_OK) err = usb_host_transfer_alloc(protocol::CONTROL_SIZE, 0, &output_);
    if (err != ESP_OK) { fail_(now, "DMA transfer allocation", err); return; }
    generation_++;
    logged_input_id_ = false;
    completed_reports_ = 0;
    first_input_length_ = 0;
    first_input_hex_[0] = '\0';
    gone_ = completion_ready_ = false;
    control_mps_ = info.bMaxPacketSize0;
    // Every driver sends standard HID SET_IDLE before reporting attachment.
    // The bench option additionally captures the three read-only queries.
    probe_index_ = usb_diagnostics_ ? 0 : 1;
    for (auto &probe : probes_) probe = ProbeResult{};
    input_->device_handle = device_;
    input_->bEndpointAddress = found.in_endpoint;
    input_->callback = input_done_;
    input_->context = this;
    input_->num_bytes = found.in_packet_size;
    output_->device_handle = device_;
    output_->callback = output_done_;
    output_->context = this;
    ESP_LOGI(TAG, "Claimed HID interface %u alt %u, IN 0x%02X MPS %u, OUT 0x%02X MPS %u, HID descriptor %u bytes",
             found.number, found.alternate, found.in_endpoint, found.in_packet_size,
             found.out_endpoint, found.out_packet_size, found.report_descriptor_size);
    ESP_LOGI(TAG, "Output route: %s; report=8191, control allocation=%u bytes, config=%u, declared power=%u mA",
             found.out_endpoint ? "interrupt OUT (bounded packet batches)" : "EP0 SET_REPORT(Output)",
             unsigned(output_->data_buffer_size), info.bConfigurationValue, unsigned(config->bMaxPower) * 2);
    if (!submit_input_()) { fail_(now, "input submit", ESP_FAIL); return; }
    if (probe_index_ < PROBE_COUNT) start_probe_(now);
    return;
  }
}

bool USBTransport::submit_input_() {
  input_generation_ = generation_;
  input_done_flag_ = false;
  const auto err = usb_host_transfer_submit(input_);
  input_pending_ = err == ESP_OK;
  return input_pending_;
}

void USBTransport::handle_input_() {
  input_done_flag_ = false;
  if (input_generation_ != generation_) return;
  if (input_->status != USB_TRANSFER_STATUS_COMPLETED) return;
  // Wi-Fi/API logging may connect after USB initialization. Retain one bounded
  // observation before decoding, so an unexpected length is still diagnosable.
  if (!logged_input_id_ && input_->actual_num_bytes > 0 &&
      size_t(input_->actual_num_bytes) <= input_->data_buffer_size) {
    first_input_length_ = input_->actual_num_bytes;
    constexpr char HEX[] = "0123456789ABCDEF";
    const size_t captured = first_input_length_ < 32 ? size_t(first_input_length_) : 32;
    for (size_t i = 0; i < captured; i++) {
      const uint8_t byte = input_->data_buffer[i];
      first_input_hex_[3 * i] = HEX[byte >> 4];
      first_input_hex_[3 * i + 1] = HEX[byte & 15];
      first_input_hex_[3 * i + 2] = i + 1 < captured ? ' ' : '\0';
    }
    logged_input_id_ = true;
    ESP_LOGI(TAG, "First input: length=%d, first <=32 bytes=%s", first_input_length_, first_input_hex_);
  }
  uint16_t mask = 0;
  if (!protocol::decode_input(input_->data_buffer, input_->actual_num_bytes, mask, input_report_id_)) {
    malformed_inputs_++;
    return;
  }
  input_queue_.push(generation_, mask, captured_epoch_);
}

void USBTransport::dump_status() const {
  ESP_LOGI(TAG, "USB status: attached=%s, generation=%lu, completed reports=%lu",
           attached() ? "yes" : "no", static_cast<unsigned long>(generation_),
           static_cast<unsigned long>(completed_reports_));
  if (attached()) {
    ESP_LOGI(TAG, "HID interface %u alt %u, IN 0x%02X MPS %u, OUT 0x%02X MPS %u, report descriptor %u bytes",
             interface_.number, interface_.alternate, interface_.in_endpoint, interface_.in_packet_size,
             interface_.out_endpoint, interface_.out_packet_size, interface_.report_descriptor_size);
  }
  if (logged_input_id_)
    ESP_LOGI(TAG, "First input: length=%d, first <=32 bytes=%s", first_input_length_, first_input_hex_);
  if (usb_diagnostics_)
    for (size_t i = 0; i < PROBE_COUNT; i++) dump_probe_(i);
}

void USBTransport::start_probe_(uint32_t now) {
  // Standard HID initialization plus optional EP0 evidence, once per attachment.
  // Linux usbhid sends SET_IDLE(0, all reports) before reading the HID descriptor.
  // Never query the serial-number feature (ID 3) or reset the device firmware.
  auto &probe = probes_[probe_index_];
  const uint8_t requests[PROBE_COUNT][8] = {
    {0x80, 0x08, 0, 0, 0, 0, 1, 0},  // GET_CONFIGURATION (device recipient)
    {0x21, 0x0a, 0, 0, interface_.number, 0, 0, 0},  // SET_IDLE(0): report changes only
    {0x81, 0x06, 0, 0x22, interface_.number, 0, 0, 0},  // HID report descriptor
    {0xa1, 0x01, 4, 3, interface_.number, 0, 17, 0},  // GET_REPORT(Feature 4)
  };
  probe.requested = probe_index_ == 2 ? interface_.report_descriptor_size : (probe_index_ == 0 ? 1 : (probe_index_ == 1 ? 0 : 17));
  if ((probe.requested == 0 && probe_index_ != 1) || probe.requested > PROBE_MAX_SIZE ||
      (control_mps_ != 8 && control_mps_ != 16 && control_mps_ != 32 && control_mps_ != 64)) {
    fail_(now, "diagnostic request bounds", ESP_ERR_INVALID_ARG);
    return;
  }
  std::memset(output_->data_buffer, 0, output_->data_buffer_size);
  std::memcpy(output_->data_buffer, requests[probe_index_], protocol::SETUP_SIZE);
  output_->data_buffer[6] = uint8_t(probe.requested);
  output_->data_buffer[7] = uint8_t(probe.requested >> 8);
  output_->bEndpointAddress = 0;
  // IDF requires room for complete IN packets, while wLength remains exact.
  output_->num_bytes = protocol::SETUP_SIZE +
      ((probe.requested + control_mps_ - 1) / control_mps_) * control_mps_;
  output_control_ = true;
  output_generation_ = generation_;
  output_started_ = now;
  probe.attempted = true;
  if (!submit_output_()) fail_(now, "diagnostic control submit", ESP_FAIL);
}

void USBTransport::handle_probe_(uint32_t now) {
  auto &probe = probes_[probe_index_];
  probe.status = int(output_->status);
  probe.actual = output_->actual_num_bytes;
  if (probe.actual >= int(protocol::SETUP_SIZE) && size_t(probe.actual) <= output_->data_buffer_size) {
    const size_t size = size_t(probe.actual) - protocol::SETUP_SIZE;
    probe.captured = size < PROBE_MAX_SIZE ? size : PROBE_MAX_SIZE;
    std::memcpy(probe.data, output_->data_buffer + protocol::SETUP_SIZE, probe.captured);
  }
  if (output_->status != USB_TRANSFER_STATUS_COMPLETED ||
      probe.actual != int(probe.requested + protocol::SETUP_SIZE)) errors_++;
  dump_probe_(probe_index_);
  // USBH retires and clears a stalled EP0. A diagnostic STALL/short reply is
  // evidence, not a reason for an endless reset loop. Timeouts still recover.
  if (!usb_diagnostics_) {
    probe_index_ = PROBE_COUNT;
  } else if (++probe_index_ < PROBE_COUNT) {
    start_probe_(now);
  }
}

void USBTransport::dump_probe_(size_t index) const {
  static const char *const names[] = {"GET_CONFIGURATION", "SET_IDLE(0)", "HID report descriptor", "firmware feature 4"};
  const auto &probe = probes_[index];
  ESP_LOGI(TAG, "EP0 %s: attempted=%s status=%d requested=%u actual incl setup=%d",
           names[index], probe.attempted ? "yes" : "no", probe.status, unsigned(probe.requested), probe.actual);
  constexpr char HEX[] = "0123456789ABCDEF";
  for (size_t offset = 0; offset < probe.captured; offset += 16) {
    char hex[3 * 16 + 1]{};
    const size_t count = probe.captured - offset < 16 ? probe.captured - offset : 16;
    for (size_t n = 0; n < count; n++) {
      const auto byte = probe.data[offset + n];
      hex[3 * n] = HEX[byte >> 4];
      hex[3 * n + 1] = HEX[byte & 15];
      hex[3 * n + 2] = n + 1 < count ? ' ' : '\0';
    }
    ESP_LOGI(TAG, "EP0 probe %u bytes %u/%u: %s", unsigned(index), unsigned(offset), unsigned(probe.captured), hex);
  }
}

bool USBTransport::send(const Job &job, uint32_t now) {
  if (!attached() || output_pending_ || output_done_flag_ || completion_ready_ || job.generation != generation_)
    return false;
  job_ = job;
  const bool feature = job.kind == JobKind::BRIGHTNESS;
  output_control_ = feature || interface_.out_endpoint == 0;
  const size_t offset = output_control_ ? protocol::SETUP_SIZE : 0;
  auto *data = output_->data_buffer + offset;
  const auto available = output_->data_buffer_size - offset;
  bool valid = false;
  switch (job.kind) {
    case JobKind::RESET: valid = protocol::stream_reset(data, available); break;
    case JobKind::BRIGHTNESS: valid = protocol::brightness(job.brightness, data, available); break;
    case JobKind::PAGE1: case JobKind::PAGE2:
      valid = job.image && protocol::image_page(job.key, job.kind == JobKind::PAGE1 ? 1 : 2,
                                               *job.image, data, available);
      break;
  }
  if (!valid) { fail_(now, "report encoding", ESP_ERR_INVALID_ARG); return false; }
  const size_t length = feature ? protocol::FEATURE_SIZE : protocol::REPORT_SIZE;
  output_remaining_ = length;
  if (output_control_) {
    protocol::set_report_setup(feature ? 3 : 2, data[0], interface_.number, length,
                               output_->data_buffer, output_->data_buffer_size);
    output_->bEndpointAddress = 0;
    output_->num_bytes = length + protocol::SETUP_SIZE;
    output_chunk_ = length;
  } else {
    output_->bEndpointAddress = interface_.out_endpoint;
    output_chunk_ = protocol::interrupt_chunk(length, interface_.out_packet_size);
    output_->num_bytes = output_chunk_;
  }
  output_generation_ = generation_;
  output_started_ = now;
  if (!submit_output_()) { fail_(now, "output submit", ESP_FAIL); return false; }
  return true;
}

bool USBTransport::submit_output_() {
  output_done_flag_ = false;
  const auto err = output_control_ ? usb_host_transfer_submit_control(client_, output_)
                                   : usb_host_transfer_submit(output_);
  output_pending_ = err == ESP_OK;
  return output_pending_;
}

void USBTransport::handle_output_(uint32_t now) {
  output_done_flag_ = false;
  if (output_generation_ != generation_) return;
  if (probe_index_ < PROBE_COUNT) { handle_probe_(now); return; }
  if (output_->status != USB_TRANSFER_STATUS_COMPLETED || output_->actual_num_bytes != output_->num_bytes) {
    ESP_LOGW(TAG, "Transfer status=%d, actual=%d, requested=%d", int(output_->status),
             output_->actual_num_bytes, output_->num_bytes);
    fail_(now, "short/failed output", ESP_FAIL);
    return;
  }
  output_remaining_ -= output_chunk_;
  if (output_remaining_) {
    // Continue the SAME HID report. No extra report IDs, headers, short packets
    // or ZLPs between batches. Each batch meets the pinned HCD's 32-QTD limit.
    std::memmove(output_->data_buffer, output_->data_buffer + output_chunk_, output_remaining_);
    output_chunk_ = protocol::interrupt_chunk(output_remaining_, interface_.out_packet_size);
    output_->num_bytes = output_chunk_;
    if (!submit_output_()) fail_(now, "interrupt continuation", ESP_FAIL);
  } else {
    completed_reports_++;
    completion_ready_ = true;
    ESP_LOGD(TAG, "Completed report kind=%u, bytes=%u, generation=%lu", unsigned(job_.kind),
             unsigned(job_.kind == JobKind::BRIGHTNESS ? protocol::FEATURE_SIZE : protocol::REPORT_SIZE),
             static_cast<unsigned long>(generation_));
  }
}

bool USBTransport::take_completion(Job &job) {
  if (!completion_ready_ || closing_) return false;
  job = job_;
  job_ = {};
  completion_ready_ = false;
  return true;
}

void USBTransport::fail_(uint32_t now, const char *operation, esp_err_t error) {
  errors_++;
  ESP_LOGW(TAG, "%s failed: %s", operation, esp_err_to_name(error));
  begin_recovery_(now, operation);
}

void USBTransport::begin_recovery_(uint32_t now, const char *reason) {
  if (closing_) return;
  ESP_LOGW(TAG, "USB recovery: %s; controller disconnect only, peripheral VBUS remains on", reason);
  closing_ = true;
  generation_++;
  input_queue_.clear();
  completion_ready_ = false;
  recovery_started_ = last_drain_warning_ = now;
  // A physical detach already puts IDF's port into RECOVERY and cancels its
  // transfers. Switching it to NOT_POWERED here makes root_port_recycle abort
  // when the device is freed (observed on IDF 5.5.5). Leave that recovery to IDF.
  // For a software fault while connected, a logical disconnect also retires
  // EP0, which the public endpoint halt/flush API cannot address. No VBUS switch.
  if (!gone_) {
    const auto err = usb_host_lib_set_root_port_power(false);
    port_disabled_ = err == ESP_OK;
    if (err != ESP_OK) ESP_LOGW(TAG, "Controller disconnect failed: %s; waiting for drain/unplug", esp_err_to_name(err));
  }
  if (!gone_ && claimed_ && input_pending_) {
    usb_host_endpoint_halt(device_, interface_.in_endpoint);
    usb_host_endpoint_flush(device_, interface_.in_endpoint);
  }
  if (!gone_ && claimed_ && output_pending_ && !output_control_) {
    usb_host_endpoint_halt(device_, interface_.out_endpoint);
    usb_host_endpoint_flush(device_, interface_.out_endpoint);
  }
}

void USBTransport::drain_(uint32_t now) {
  input_done_flag_ = output_done_flag_ = false;
  if (input_pending_ || output_pending_) {
    if (now - last_drain_warning_ >= 10000) {
      last_drain_warning_ = now;
      ESP_LOGW(TAG, "USB cancellation still pending; buffers retained. Unplug/replug the deck or reboot if persistent");
    }
    return;
  }
  // No transfer callback can still reference this job. Desired images survive
  // in the scheduler, while obsolete runtime versions can now be reclaimed.
  job_ = {};
  if (claimed_) {
    if (usb_host_interface_release(client_, device_, interface_.number) != ESP_OK) return;
    claimed_ = false;
  }
  if (device_ != nullptr) {
    if (usb_host_device_close(client_, device_) != ESP_OK) return;
    device_ = nullptr;
  }
  usb_host_transfer_free(input_); input_ = nullptr;
  usb_host_transfer_free(output_); output_ = nullptr;
  if (stopped_ || now - recovery_started_ < RECOVERY_DELAY_MS) return;
  if (port_disabled_) {
    if (usb_host_lib_set_root_port_power(true) != ESP_OK) return;
    port_disabled_ = false;
  }
  gone_ = closing_ = false;
  next_discovery_ = now + 1000;
}

void USBTransport::loop(uint32_t now) {
  if (!installed_) return;
  usb_host_client_handle_events(client_, 0);
  if (gone_ && !closing_) begin_recovery_(now, "device disconnected");
  if (closing_) { drain_(now); return; }
  if (stopped_) return;
  if (device_ == nullptr) {
    if (int32_t(now - next_discovery_) >= 0) discover_(now);
    return;
  }
  if (output_done_flag_) handle_output_(now);
  if (closing_) return;
  if (input_done_flag_) {
    const auto status = input_->status;
    handle_input_();
    if (status != USB_TRANSFER_STATUS_COMPLETED) { fail_(now, "input completion", ESP_FAIL); return; }
    if (!submit_input_()) { fail_(now, "input resubmit", ESP_FAIL); return; }
  }
  if (output_pending_ && now - output_started_ >= OUTPUT_DEADLINE_MS)
    fail_(now, "software output deadline", ESP_ERR_TIMEOUT);
}

void USBTransport::shutdown() {
  stopped_ = true;
  if (installed_) begin_recovery_(0, "shutdown");
}
}  // namespace esphome::stream_deck
