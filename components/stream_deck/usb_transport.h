#pragma once

#include "scheduler.h"
#include "usb/usb_host.h"

namespace esphome::stream_deck {

// Only the library daemon runs on a separate task. All client functions, this
// object's state, and completion callbacks are owned by the ESPHome loop task.
class USBTransport {
 public:
  bool setup();
  void loop(uint32_t now);
  void shutdown();
  void dump_status() const;
  bool attached() const { return device_ != nullptr && claimed_ && !closing_ && probe_index_ == PROBE_COUNT; }
  uint32_t generation() const { return generation_; }
  void set_input_report_id(int id) { input_report_id_ = id; }
  void set_usb_diagnostics(bool enabled) { usb_diagnostics_ = enabled; }
  bool send(const Job &job, uint32_t now);
  bool take_completion(Job &job);
  bool pop_input(InputReport &report) { return input_queue_.pop(report); }
  uint32_t errors() const { return errors_; }
  uint32_t malformed_inputs() const { return malformed_inputs_; }
  uint32_t overflows() const { return input_queue_.overflows(); }
  size_t queue_high_water() const { return input_queue_.high_water(); }

 protected:
  static void library_task_(void *arg);
  static void client_event_(const usb_host_client_event_msg_t *event, void *arg);
  static void input_done_(usb_transfer_t *transfer);
  static void output_done_(usb_transfer_t *transfer);
  void discover_(uint32_t now);
  void begin_recovery_(uint32_t now, const char *reason);
  void drain_(uint32_t now);
  void handle_input_();
  void handle_output_(uint32_t now);
  void start_probe_(uint32_t now);
  void handle_probe_(uint32_t now);
  void dump_probe_(size_t index) const;
  bool submit_input_();
  bool submit_output_();
  void fail_(uint32_t now, const char *operation, esp_err_t error);

  usb_host_client_handle_t client_{nullptr};
  usb_device_handle_t device_{nullptr};
  usb_transfer_t *input_{nullptr}, *output_{nullptr};
  protocol::Interface interface_{};
  InputQueue input_queue_{};
  Job job_{};
  uint32_t generation_{0}, input_generation_{0}, output_generation_{0};
  uint32_t errors_{0}, malformed_inputs_{0};
  uint32_t completed_reports_{0};
  static constexpr size_t PROBE_COUNT = 4, PROBE_MAX_SIZE = 320;
  struct ProbeResult {
    bool attempted{false};
    int status{-1}, actual{0};
    size_t requested{0}, captured{0};
    uint8_t data[PROBE_MAX_SIZE]{};
  } probes_[PROBE_COUNT]{};
  size_t probe_index_{PROBE_COUNT};
  uint8_t control_mps_{64};
  int first_input_length_{0};
  char first_input_hex_[3 * 32 + 1]{};
  uint32_t next_discovery_{0}, output_started_{0}, recovery_started_{0}, last_drain_warning_{0};
  size_t output_remaining_{0}, output_chunk_{0};
  int input_report_id_{-1};
  bool installed_{false}, claimed_{false}, stopped_{false};
  bool closing_{false}, gone_{false}, port_disabled_{false};
  bool input_pending_{false}, output_pending_{false};
  bool input_done_flag_{false}, output_done_flag_{false}, completion_ready_{false};
  bool output_control_{false}, logged_input_id_{false};
  bool usb_diagnostics_{false};
};
}  // namespace esphome::stream_deck
