// Original-device framing adapted from Dean Camera's Python Stream Deck library.
// See THIRD_PARTY_NOTICES.md for upstream attribution and license text.
#include "protocol.h"

#include <algorithm>
#include <cmath>
#include <cstring>

namespace esphome::stream_deck::protocol {
namespace {
uint16_t le16(const uint8_t *p) { return uint16_t(p[0]) | (uint16_t(p[1]) << 8); }
uint32_t le32(const uint8_t *p) { return uint32_t(le16(p)) | (uint32_t(le16(p + 2)) << 16); }
constexpr std::array<uint8_t, IMAGE_SIZE> make_blank() {
  std::array<uint8_t, IMAGE_SIZE> data{};
  constexpr uint8_t header[] = {0x42, 0x4d, 0xf6, 0x3c, 0, 0, 0, 0, 0, 0, 0x36, 0, 0, 0,
      0x28, 0, 0, 0, 0x48, 0, 0, 0, 0x48, 0, 0, 0, 1, 0, 0x18, 0, 0, 0, 0, 0,
      0xc0, 0x3c, 0, 0, 0xc4, 0x0e, 0, 0, 0xc4, 0x0e, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
  for (size_t i = 0; i < sizeof(header); i++) data[i] = header[i];
  return data;
}
constexpr auto BLANK_DATA = make_blank();
const NativeImage BLANK{BLANK_DATA.data(), BLANK_DATA.size()};
}  // namespace

int wire_key(int logical) {
  return logical >= 0 && logical < int(KEY_COUNT) ? (logical / 5) * 5 + 4 - logical % 5 : -1;
}

bool decode_input(const uint8_t *data, size_t size, uint16_t &mask, int report_id) {
  if (data == nullptr || (size != INPUT_SIZE && size != INPUT_SIZE + 1)) return false;
  if (report_id >= 0 && data[0] != report_id) return false;
  // The desktop library truncates reads to 16 bytes. The captured S3 key report
  // is ID 1 + 15 key states + a zero reserved byte, matching the HID descriptor.
  // Do not decode other 17-byte input IDs (A0/A1) or arbitrary padding as keys.
  if (size == INPUT_SIZE + 1 && (data[0] != 1 || data[INPUT_SIZE] != 0)) return false;
  uint16_t decoded = 0;
  for (int key = 0; key < int(KEY_COUNT); key++) {
    const auto value = data[1 + wire_key(key)];
    if (value > 1) return false;
    if (value) decoded |= uint16_t(1U << key);
  }
  mask = decoded;
  return true;
}

bool valid_bmp(const uint8_t *data, size_t size) {
  return data != nullptr && size == IMAGE_SIZE && data[0] == 'B' && data[1] == 'M' &&
         le32(data + 2) == IMAGE_SIZE && le32(data + 6) == 0 && le32(data + 10) == 54 &&
         le32(data + 14) == 40 && le32(data + 18) == 72 && le32(data + 22) == 72 &&
         le16(data + 26) == 1 && le16(data + 28) == 24 && le32(data + 30) == 0 &&
         le32(data + 34) == 15552 && le32(data + 46) == 0 && le32(data + 50) == 0;
}

bool brightness(float percent, uint8_t *out, size_t size) {
  if (out == nullptr || size < FEATURE_SIZE || !std::isfinite(percent)) return false;
  std::memset(out, 0, FEATURE_SIZE);
  const uint8_t header[] = {0x05, 0x55, 0xaa, 0xd1, 0x01};
  std::memcpy(out, header, sizeof(header));
  out[5] = uint8_t(std::lround(std::clamp(percent, 0.0f, 100.0f)));
  return true;
}

bool device_reset(uint8_t *out, size_t size) {
  if (out == nullptr || size < FEATURE_SIZE) return false;
  std::memset(out, 0, FEATURE_SIZE);
  out[0] = 0x0b;
  out[1] = 0x63;
  return true;
}

bool stream_reset(uint8_t *out, size_t size) {
  if (out == nullptr || size < REPORT_SIZE) return false;
  std::memset(out, 0, REPORT_SIZE);
  out[0] = 0x02;
  return true;
}

bool image_page(int key, int page, const NativeImage &image, uint8_t *out, size_t size) {
  const int wire = wire_key(key);
  if (wire < 0 || page < 1 || page > 2 || out == nullptr || size < REPORT_SIZE ||
      !valid_bmp(image.data, image.size)) return false;
  std::memset(out, 0, REPORT_SIZE);
  out[0] = 2;
  out[1] = 1;
  out[2] = uint8_t(page);
  out[4] = uint8_t(page == 2);
  out[5] = uint8_t(wire + 1);
  std::memcpy(out + 16, image.data + (page - 1) * PAGE_SIZE, PAGE_SIZE);
  return true;
}

bool set_report_setup(uint8_t report_type, uint8_t report_id, uint8_t interface_number,
                      uint16_t length, uint8_t *out, size_t size) {
  if (out == nullptr || size < SETUP_SIZE || (report_type != 2 && report_type != 3) || report_id == 0)
    return false;
  const uint8_t setup[] = {0x21, 0x09, report_id, report_type, interface_number, 0,
                          uint8_t(length), uint8_t(length >> 8)};
  std::memcpy(out, setup, sizeof(setup));
  return true;
}

size_t interrupt_chunk(size_t remaining, uint16_t max_packet_size) {
  if (max_packet_size == 0 || (max_packet_size > 64 && max_packet_size != 512)) return 0;
  return std::min(remaining, size_t(max_packet_size) * 32);
}

const NativeImage &blank_image() { return BLANK; }

bool find_interface(const uint8_t *config, size_t size, Interface &result) {
  if (config == nullptr || size < 9 || config[0] != 9 || config[1] != 2 || le16(config + 2) != size)
    return false;
  Interface candidate{};
  bool hid = false;
  unsigned matches = 0, endpoints = 0, expected_endpoints = 0;
  auto finish = [&]() {
    if (!hid) return true;
    if (!candidate.in_endpoint || endpoints != expected_endpoints) return false;
    result = candidate;
    matches++;
    return true;
  };
  for (size_t offset = 9; offset < size;) {
    if (size - offset < 2) return false;
    const auto *d = config + offset;
    const auto length = d[0];
    if (length < 2 || length > size - offset) return false;
    if (d[1] == 4) {
      if (length < 9 || !finish()) return false;
      candidate = {};
      hid = d[5] == 3 && d[3] == 0;
      candidate.number = d[2];
      candidate.alternate = d[3];
      endpoints = 0;
      expected_endpoints = d[4];
    } else if (hid && d[1] == 0x21) {
      if (length < 6 || size_t(6 + 3 * d[5]) > length) return false;
      for (unsigned n = 0; n < d[5]; n++) {
        if (d[6 + 3 * n] == 0x22) candidate.report_descriptor_size = le16(d + 7 + 3 * n);
      }
    } else if (hid && d[1] == 5) {
      if (length < 7 || (d[3] & 3) != 3 || (d[2] & 0x0f) == 0 || (d[2] & 0x70)) return false;
      const auto mps = le16(d + 4);
      if (mps == 0 || d[6] == 0) return false;
      endpoints++;
      if (d[2] & 0x80) {
        if (candidate.in_endpoint || mps < INPUT_SIZE || mps > 64) return false;
        candidate.in_endpoint = d[2];
        candidate.in_packet_size = mps;
      } else {
        // Original 0060 advertises and may require a nonstandard 512-byte OUT
        // endpoint at full speed. The IDF periodic-OUT FIFO bias is mandatory.
        if (candidate.out_endpoint || (mps > 64 && mps != 512)) return false;
        candidate.out_endpoint = d[2];
        candidate.out_packet_size = mps;
      }
    }
    offset += length;
  }
  return finish() && matches == 1;
}
}  // namespace esphome::stream_deck::protocol
