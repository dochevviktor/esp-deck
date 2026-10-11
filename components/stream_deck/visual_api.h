#pragma once

#include "asset_pipeline.h"
#include <string>

namespace esphome::stream_deck::visual {
// A bounded snapshot, never payload/URL text. Transport success means this
// response was delivered; accepted/error describe the visual operation.
struct Response {
  Text<16> session;
  int32_t key{0}, request_revision{0};
  bool accepted{false};
  Status status;
  Error error{Error::OUT_OF_MEMORY};

  // ArduinoJson is deliberately confined to the caller. Native tests can
  // exercise the exact response mapping without ESPHome/JSON/USB dependencies.
  template<typename Object> void write(Object root) const {
    root["session"] = std::string(session.view());  // JSON must own this temporary snapshot's text.
    root["key"] = key;
    root["request_revision"] = request_revision;
    root["accepted"] = accepted;
    root["revision"] = status.revision;
    root["rendered_revision"] = status.rendered_revision;
    root["phase"] = phase_name(status.phase);
    root["error"] = error_name(error);
  }
};

// Borrows the single boot-lifetime store/pipeline. No client/connection state,
// new worker, image storage or asynchronous response queue belongs here.
class Api {
 public:
  Api(std::string_view session, Store *store, assets::Pipeline *pipeline)
      : store_(store), pipeline_(pipeline) { session_.assign(session); }
  Response set(const Command &command);
  Response get(std::string_view session, int32_t key) const;
  Response clear(std::string_view session, int32_t key, int32_t revision);
  Response refresh(std::string_view session, int32_t key, int32_t revision, std::string_view image_revision);
 private:
  Response snapshot_(int32_t key, int32_t revision) const;
  Text<16> session_;
  Store *store_;
  assets::Pipeline *pipeline_;
};
}  // namespace esphome::stream_deck::visual
