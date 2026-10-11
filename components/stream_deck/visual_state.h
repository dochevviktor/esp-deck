#pragma once

#include "scheduler.h"

#include <cstring>
#include <string_view>

namespace esphome::stream_deck::visual {

// Contract v1. Network/decoder limits are requirements for the P2/P3 adapters;
// this module validates commands and schedules render work without doing I/O.
constexpr size_t MAX_URL_BYTES = 512, MAX_IMAGE_REVISION_BYTES = 64;
constexpr size_t MAX_LABEL_BYTES = 96, MAX_LABEL_CODEPOINTS = 48;
constexpr size_t MAX_ENCODED_BYTES = 128 * 1024, MAX_SOURCE_DIMENSION = 256, MAX_SOURCE_PIXELS = 65536;
constexpr size_t MAX_BACKGROUND_BYTES = 256 * 1024, MAX_NATIVE_BYTES = 512 * 1024;
constexpr size_t MAX_GRAPHICS_BYTES = 2 * 1024 * 1024;
constexpr uint32_t CONNECT_TIMEOUT_MS = 5000, FETCH_TIMEOUT_MS = 15000;
constexpr unsigned MAX_REDIRECTS = 0, MAX_RETRIES = 0;

enum Field : int32_t {
  IMAGE = 1, TEXT = 2, FONT = 4, TEXT_COLOR = 8, OUTLINE_COLOR = 16, BACKGROUND_COLOR = 32, FIT = 64,
  ALL_FIELDS = 127,
};
enum class Fit : uint8_t { CONTAIN, CROP };
enum class Phase : uint8_t { IDLE, QUEUED, RENDERING, RENDERED, FAILED };
enum class Error : uint8_t {
  NONE, INVALID_KEY, WRONG_SESSION, INVALID_REVISION, STALE_REVISION, REVISION_CONFLICT,
  INVALID_FIELDS, LIMIT_EXCEEDED, INVALID_URL, INVALID_IMAGE_REVISION, INVALID_TEXT,
  INVALID_FONT, INVALID_COLOR, INVALID_FIT, FETCH_FAILED, DECODE_FAILED, RENDER_FAILED, OUT_OF_MEMORY,
};
const char *error_name(Error error);
const char *phase_name(Phase phase);
// Shared strict UTF-8 boundary for validation and rendering. Output/count are
// usable only on success; there are never more than MAX_LABEL_CODEPOINTS.
Error decode_label(std::string_view text, std::array<uint32_t, MAX_LABEL_CODEPOINTS> &points, size_t &count);

template<size_t Capacity> class Text {
 public:
  bool assign(std::string_view value) {
    if (value.size() > Capacity) return false;
    if (!value.empty()) std::memcpy(data_.data(), value.data(), value.size());
    size_ = value.size();
    data_[size_] = '\0';
    return true;
  }
  std::string_view view() const { return {data_.data(), size_}; }
  bool empty() const { return size_ == 0; }
  bool operator==(const Text &other) const { return view() == other.view(); }
 private:
  std::array<char, Capacity + 1> data_{};
  size_t size_{0};
};

struct State {
  Text<MAX_URL_BYTES> image_url;
  Text<MAX_IMAGE_REVISION_BYTES> image_revision;
  Text<MAX_LABEL_BYTES> text;
  uint32_t text_color{0xffffff}, outline_color{0}, background_color{0};
  uint8_t font{16};
  Fit fit{Fit::CONTAIN};
  bool operator==(const State &other) const;
};

// Fixed native API argument list. Views are borrowed only during submit(). The
// presence mask distinguishes omitted fields from explicit empty-string clears.
struct Command {
  std::string_view session;
  int32_t key{0}, revision{0}, fields{0};
  std::string_view image_url, image_revision, text;
  int32_t font{16};
  std::string_view text_color, outline_color, background_color, fit;
};

// Transactional, including if base and result alias. Never partially changes
// result on validation failure. Session/key/revision are checked by Store.
Error apply_patch(const Command &command, const State &base, State &result);

struct Status {
  uint32_t revision{0}, rendered_revision{0};
  Phase phase{Phase::IDLE};
  Error error{Error::NONE};
};
struct Submission {
  bool accepted{false};
  Error error{Error::NONE};
  Phase phase{Phase::IDLE};
  uint32_t revision{0};  // Latest accepted revision; rejected commands do not change it.
};
struct RenderJob {
  uint64_t session{0}, token{0};
  uint8_t key{0};
  uint32_t revision{0};
  State state;
};

// One coalescing slot per key, one active worker, no growing job/event queues.
// This store lives for the ESP boot session, independently of USB generations
// or API clients. Only a successful complete tile reaches the USB scheduler.
class Store {
 public:
  Store(uint64_t session, Scheduler &scheduler) : session_(session), scheduler_(scheduler) {}
  Store(const Store &) = delete;
  Store &operator=(const Store &) = delete;
  Submission submit(const Command &command);
  const Status *status(int key) const;
  bool next(RenderJob &job);
  bool finish(const RenderJob &job, const ImageRef &image);
  bool fail(const RenderJob &job, Error error);

 private:
  struct Slot {
    State desired, rendered;
    Status status;
    int32_t fields{0};
  };
  bool matches_active_(const RenderJob &job) const;
  std::array<Slot, protocol::KEY_COUNT> slots_{};
  const uint64_t session_;
  Scheduler &scheduler_;
  uint64_t token_{0};
  uint32_t active_revision_{0};
  uint8_t active_key_{0}, cursor_{0};
  bool active_{false};
};
}  // namespace esphome::stream_deck::visual
