#pragma once

#include "visual_api.h"

namespace esphome::stream_deck::visual {
// Pull delivery uses encrypted action responses, never an entity snapshot or
// a parallel API connection. The reader changes on every HA connection epoch.
// A lost/slow response or FIFO overflow resets the stream; inputs aren't retried.
class InputChannel {
 public:
  static constexpr uint32_t LEASE_MS = 1000;
  explicit InputChannel(Store &store) : store_(store) {}
  void reset() {
    count_ = 0; held_.fill({}); ++reset_;
  }
  void sample(const InputReport &report, const KeyEdges &edges, uint32_t now) {
    if (report.generation != store_.generation()) return;
    if (generation_ != store_.generation()) { reset(); generation_ = store_.generation(); }
    if (edges.sync || report.resync) { reset(); return; }
    if (reader_.empty() || uint32_t(now - last_read_) >= LEASE_MS) { reset(); return; }
    for (uint8_t key = 0; key < protocol::KEY_COUNT; ++key) {
      const auto bit = uint16_t(1U << key);
      if ((edges.pressed & bit) && report.epoch == store_.input_epoch() &&
          report.generation == generation_ && store_.applied_revision(key) && !store_.context(key).empty()) {
        held_[key] = {key, true, store_.applied_revision(key), generation_, {}, 0};
        held_[key].context.assign(store_.context(key));
        if (!push_(held_[key])) return;
      }
      if ((edges.released & bit) && !held_[key].context.empty()) {
        auto edge = held_[key]; held_[key] = {}; edge.pressed = false;
        if (!push_(edge)) return;
      }
    }
  }
  template<typename Object> void read(std::string_view reader, int32_t ack, uint32_t now, Object root) {
    root["accepted"] = false;
    if (reader.size() != 32 || ack < 0) { root["error"] = "invalid_reader"; return; }
    for (char c : reader) if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) {
      root["error"] = "invalid_reader"; return;
    }
    if (reader != reader_.view() || ack != int32_t(delivered_) || uint32_t(now - last_read_) >= LEASE_MS ||
        generation_ != store_.generation()) {
      reset(); reader_.assign(reader); generation_ = store_.generation(); sequence_ = delivered_ = 0;
    }
    last_read_ = now;
    root["accepted"] = true; root["error"] = "none";
    root["generation"] = generation_; root["reset"] = reset_;
    // Flat JSON arrays avoid dependency on ArduinoJson types in portable code.
    root["count"] = count_;
    for (size_t n = 0; n < count_; ++n) {
      auto item = root["events"][n];
      item["key"] = queue_[n].key; item["edge"] = queue_[n].pressed ? "press" : "release";
      item["revision"] = queue_[n].revision; item["generation"] = queue_[n].generation;
      item["context"] = std::string(queue_[n].context.view()); item["sequence"] = queue_[n].sequence;
    }
    root["sequence"] = sequence_;
    delivered_ = sequence_;
    count_ = 0;
  }
  uint32_t resets() const { return reset_; }
  size_t queued() const { return count_; }
 private:
  struct Edge {
    uint8_t key{0}; bool pressed{false}; uint32_t revision{0}, generation{0}; Text<32> context; uint32_t sequence{0};
  };
  bool push_(Edge edge) {
    if (count_ == queue_.size() || sequence_ == 0x7fffffff) { reset(); reader_.assign(""); return false; }
    edge.sequence = ++sequence_; queue_[count_++] = edge; return true;
  }
  Store &store_;
  std::array<Edge, 32> queue_{};
  std::array<Edge, protocol::KEY_COUNT> held_{};
  Text<32> reader_;
  size_t count_{0};
  uint32_t sequence_{0}, delivered_{0}, reset_{0}, generation_{0}, last_read_{0};
};

template<typename Object> void capabilities(Object root, const assets::OriginPolicy &policy) {
  root["protocol_version"] = 2; root["model"] = "0FD9:0060";
  root["keys"] = 15; root["width"] = 72; root["height"] = 72;
  root["visual_fields"] = V2_FIELDS;
  root["fonts"][0] = 12; root["fonts"][1] = 16; root["fonts"][2] = 20;
  root["label_bytes"] = MAX_LABEL_BYTES; root["label_codepoints"] = MAX_LABEL_CODEPOINTS;
  root["max_origins"] = assets::OriginPolicy::CAPACITY;
  root["max_encoded_bytes"] = MAX_ENCODED_BYTES; root["max_source_dimension"] = MAX_SOURCE_DIMENSION;
  root["text_box_min_width"] = 24; root["text_lines"] = 2; root["outline_pixels"] = 1;
  root["glyphs"] = "ASCII and Latin-1 printable; unsupported becomes ?";
  root["text_wrap"] = "word then glyph; two lines with ellipsis";
  root["text_clip"] = "ink clips to box; outline clips to key";
  root["probe_max_bytes"] = 32768;
  root["positioning"] = true; root["origin_provisioning"] = true;
  root["input_correlation"] = "pull_context_v2"; root["input_lease_ms"] = InputChannel::LEASE_MS;
  root["rendered"] = "scheduler_desired"; root["applied"] = "two_usb_reports_completed";
  root["display_readback"] = false;
  for (size_t i = 0; i < policy.size(); ++i) root["origins"][i] = policy.at(i);
}
}  // namespace esphome::stream_deck::visual
