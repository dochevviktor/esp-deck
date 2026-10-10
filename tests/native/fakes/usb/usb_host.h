#pragma once
#include <cstddef>
#include <cstdint>

// Minimal fake surface for compiling the production transport on the host.
// Actual signatures are additionally checked by every ESP-IDF firmware build.
using esp_err_t = int;
using TickType_t = uint32_t;
constexpr int ESP_OK = 0, ESP_FAIL = -1, ESP_ERR_INVALID_ARG = 1, ESP_ERR_TIMEOUT = 2;
constexpr int ESP_ERR_INVALID_STATE = 3;
const char *esp_err_to_name(esp_err_t error);
using usb_host_client_handle_t = void *;
using usb_device_handle_t = void *;
enum usb_speed_t { USB_SPEED_LOW, USB_SPEED_FULL };
enum usb_transfer_status_t { USB_TRANSFER_STATUS_COMPLETED, USB_TRANSFER_STATUS_ERROR,
  USB_TRANSFER_STATUS_TIMED_OUT, USB_TRANSFER_STATUS_CANCELED, USB_TRANSFER_STATUS_STALL,
  USB_TRANSFER_STATUS_OVERFLOW, USB_TRANSFER_STATUS_SKIPPED, USB_TRANSFER_STATUS_NO_DEVICE };
struct usb_transfer_t {
  uint8_t *const data_buffer;
  const size_t data_buffer_size;
  int num_bytes{0}, actual_num_bytes{0};
  uint32_t flags{0};
  usb_device_handle_t device_handle{nullptr};
  uint8_t bEndpointAddress{0};
  usb_transfer_status_t status{USB_TRANSFER_STATUS_COMPLETED};
  uint32_t timeout_ms{0};
  void (*callback)(usb_transfer_t *){nullptr};
  void *context{nullptr};
};
constexpr int USB_HOST_CLIENT_EVENT_NEW_DEV = 0, USB_HOST_CLIENT_EVENT_DEV_GONE = 1;
constexpr uint32_t USB_HOST_LIB_EVENT_FLAGS_NO_CLIENTS = 1;
struct usb_host_client_event_msg_t {
  int event;
  struct { uint8_t address; } new_dev;
  struct { usb_device_handle_t dev_hdl; } dev_gone;
};
struct usb_host_config_t { int intr_flags{0}; };
struct usb_host_client_config_t {
  bool is_synchronous;
  int max_num_event_msg;
  struct {
    void (*client_event_callback)(const usb_host_client_event_msg_t *, void *);
    void *callback_arg;
  } async;
};
struct usb_device_desc_t { uint16_t idVendor, idProduct; };
struct __attribute__((packed)) usb_config_desc_t {
  uint8_t bLength, bDescriptorType;
  uint16_t wTotalLength;
  uint8_t bNumInterfaces, bConfigurationValue, iConfiguration, bmAttributes, bMaxPower;
};
struct usb_device_info_t { usb_speed_t speed; uint8_t bConfigurationValue; };
esp_err_t usb_host_install(const usb_host_config_t *);
esp_err_t usb_host_uninstall();
esp_err_t usb_host_client_register(const usb_host_client_config_t *, usb_host_client_handle_t *);
esp_err_t usb_host_client_deregister(usb_host_client_handle_t);
esp_err_t usb_host_lib_handle_events(TickType_t, uint32_t *);
esp_err_t usb_host_device_free_all();
esp_err_t usb_host_client_handle_events(usb_host_client_handle_t, TickType_t);
esp_err_t usb_host_device_addr_list_fill(int, uint8_t *, int *);
esp_err_t usb_host_device_open(usb_host_client_handle_t, uint8_t, usb_device_handle_t *);
esp_err_t usb_host_device_close(usb_host_client_handle_t, usb_device_handle_t);
esp_err_t usb_host_get_device_descriptor(usb_device_handle_t, const usb_device_desc_t **);
esp_err_t usb_host_get_active_config_descriptor(usb_device_handle_t, const usb_config_desc_t **);
esp_err_t usb_host_device_info(usb_device_handle_t, usb_device_info_t *);
esp_err_t usb_host_interface_claim(usb_host_client_handle_t, usb_device_handle_t, uint8_t, uint8_t);
esp_err_t usb_host_interface_release(usb_host_client_handle_t, usb_device_handle_t, uint8_t);
esp_err_t usb_host_transfer_alloc(size_t, int, usb_transfer_t **);
esp_err_t usb_host_transfer_free(usb_transfer_t *);
esp_err_t usb_host_transfer_submit(usb_transfer_t *);
esp_err_t usb_host_transfer_submit_control(usb_host_client_handle_t, usb_transfer_t *);
esp_err_t usb_host_lib_set_root_port_power(bool);
esp_err_t usb_host_endpoint_halt(usb_device_handle_t, uint8_t);
esp_err_t usb_host_endpoint_flush(usb_device_handle_t, uint8_t);
