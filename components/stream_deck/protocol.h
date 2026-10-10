#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace esphome::stream_deck::protocol {

constexpr size_t KEY_COUNT = 15;
constexpr size_t INPUT_SIZE = 16;
constexpr size_t FEATURE_SIZE = 17;
constexpr size_t IMAGE_SIZE = 15606;
constexpr size_t PAGE_SIZE = 7803;
constexpr size_t REPORT_SIZE = 8191;
constexpr size_t SETUP_SIZE = 8;
constexpr size_t CONTROL_SIZE = SETUP_SIZE + REPORT_SIZE;

struct NativeImage {
  const uint8_t *data;
  size_t size;
  NativeImage(const uint8_t *data, size_t size) : data(data), size(size) {}
};

int wire_key(int logical);
bool decode_input(const uint8_t *data, size_t size, uint16_t &mask, int report_id = -1);
bool valid_bmp(const uint8_t *data, size_t size);
bool brightness(float percent, uint8_t *out, size_t size);
bool device_reset(uint8_t *out, size_t size);
bool stream_reset(uint8_t *out, size_t size);
bool image_page(int key, int page, const NativeImage &image, uint8_t *out, size_t size);
bool set_report_setup(uint8_t report_type, uint8_t report_id, uint8_t interface_number,
                      uint16_t length, uint8_t *out, size_t size);
// IDF 5.5.5 permits at most 32 interrupt packets per submitted transfer.
size_t interrupt_chunk(size_t remaining, uint16_t max_packet_size);
const NativeImage &blank_image();

struct Interface {
  uint8_t number{0};
  uint8_t alternate{0};
  uint8_t in_endpoint{0};
  uint8_t out_endpoint{0};
  uint16_t in_packet_size{0};
  uint16_t out_packet_size{0};
  uint16_t report_descriptor_size{0};
};
// One unambiguous HID interface at alternate setting 0, interrupt IN mandatory.
bool find_interface(const uint8_t *config, size_t size, Interface &result);

}  // namespace esphome::stream_deck::protocol
