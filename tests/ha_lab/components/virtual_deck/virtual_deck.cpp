#include "virtual_deck.h"
#include "asset_inflate.h"
#include "esphome/components/json/json_util.h"
#include "esphome/core/hal.h"
#include <algorithm>
#include <cerrno>
#include <csignal>
#include <cstdio>
#include <fcntl.h>
#include <fstream>
#include <spawn.h>
#include <sys/random.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

namespace esphome::virtual_deck {
uint64_t new_session() {
  // A one-shot override exercises numeric-looking sessions in real HA templates.
  std::ifstream override_file("/lab/next-session");
  uint64_t value = 0;
  if (override_file >> std::hex >> value && value != 0) {
    std::remove("/lab/next-session");
    return value;
  }
  if (getrandom(&value, sizeof(value), 0) != sizeof(value) || value == 0) std::abort();
  return value;
}

bool HostFetcher::start(std::string_view url, uint8_t *output, size_t capacity, uint64_t token) {
  if (child_ > 0) return false;
  int descriptors[2];
  if (pipe2(descriptors, O_CLOEXEC) != 0) return false;
  posix_spawn_file_actions_t actions;
  posix_spawn_file_actions_init(&actions);
  posix_spawn_file_actions_adddup2(&actions, descriptors[1], STDOUT_FILENO);
  posix_spawn_file_actions_addopen(&actions, STDERR_FILENO, "/dev/null", O_WRONLY, 0);
  std::string address(url);
  char *args[]{const_cast<char *>("python3"), const_cast<char *>("/lab/fetch_asset.py"), address.data(), nullptr};
  const int error = posix_spawnp(&child_, "python3", &actions, nullptr, args, environ);
  posix_spawn_file_actions_destroy(&actions);
  close(descriptors[1]);
  if (error != 0) { close(descriptors[0]); child_ = -1; return false; }
  pipe_ = descriptors[0];
  fcntl(pipe_, F_SETFL, O_NONBLOCK);
  output_ = output; capacity_ = capacity; size_ = header_size_ = 0;
  result_ = {token, visual::Error::NONE, 0, 0};
  cancelled_ = eof_ = false;
  return true;
}
void HostFetcher::cancel() {
  if (child_ > 0 && !cancelled_) kill(child_, SIGTERM);
  cancelled_ = true;
}
bool HostFetcher::poll(assets::FetchResult &result) {
  if (child_ <= 0) return false;
  uint8_t buffer[4096];
  const ssize_t count = read(pipe_, buffer, sizeof(buffer));
  if (count == 0 || (count < 0 && errno != EAGAIN && errno != EINTR)) eof_ = true;
  if (count > 0) {
    for (ssize_t n = 0; n < count; n++) {
      if (header_size_ < header_.size()) header_[header_size_++] = buffer[n];
      else if (size_ < capacity_) output_[size_++] = buffer[n];
      else { result_.error = visual::Error::LIMIT_EXCEEDED; cancel(); }
    }
  }
  // Never free the pipeline buffer while the child can still write into its pipe.
  if (!eof_ && !cancelled_) return false;
  int status = 0;
  if (waitpid(child_, &status, WNOHANG) == 0) return false;
  close(pipe_); pipe_ = -1; child_ = -1;
  if (result_.error == visual::Error::NONE) {
    if (cancelled_ || header_size_ != 8 || !WIFEXITED(status) || WEXITSTATUS(status) != 0)
      result_.error = visual::Error::FETCH_FAILED;
    else {
      auto word = [&](size_t offset) {
        uint32_t value = 0;
        for (size_t n = 0; n < 4; n++) value |= uint32_t(header_[offset + n]) << (8 * n);
        return value;
      };
      result_.http_status = int(word(0));
      switch (word(4)) {
        case 0: break;
        case 2: result_.error = visual::Error::HTTP_STATUS; break;
        case 3: result_.error = visual::Error::UNSUPPORTED_ENCODING; break;
        case 4: result_.error = visual::Error::LIMIT_EXCEEDED; break;
        default: result_.error = visual::Error::FETCH_FAILED; break;
      }
    }
  }
  result_.bytes = size_; result = result_;
  output_ = nullptr;
  return true;
}

void VirtualDeck::setup() {
  // Test commands are one-shot input, never a retained boot input state.
  std::remove("/lab/control.json");
  char text[17];
  snprintf(text, sizeof(text), "%016llx", static_cast<unsigned long long>(boot_));
  session_ = text;
  policy_.add("http://ha:8123");
  scheduler_.attach(generation_);
  session_sensor_->publish_state(session_);
  // Explicit simulated all-up report, not an assumption added to the driver.
  input_(0);
  snapshot_();
}
void VirtualDeck::input_(uint16_t mask, bool resync) {
  const auto edges = tracker_.update(mask, resync);
  for (size_t key = 0; key < protocol::KEY_COUNT; key++) {
    const auto bit = uint16_t(1U << key);
    const bool pressed = mask & bit;
    const bool edge = (edges.pressed | edges.released) & bit;
    if (edges.sync || (!edge && (!keys_[key]->has_state() || keys_[key]->state != pressed))) {
      keys_[key]->set_trigger_on_initial_state(false);
      keys_[key]->publish_initial_state(pressed);
    } else if (edge) keys_[key]->publish_state(pressed);
    if (edges.pressed & bit) { events_[key]->trigger("press"); edges_++; }
    if (edges.released & bit) { events_[key]->trigger("release"); edges_++; }
  }
}
void VirtualDeck::control_() {
  std::ifstream file("/lab/control.json", std::ios::binary);
  if (!file) return;
  std::string text(4097, '\0');
  file.read(text.data(), text.size());
  if (file.gcount() > 4096) return;
  text.resize(file.gcount());
  auto doc = json::parse_json(text);
  const auto seq = doc["sequence"].as<uint32_t>();
  if (seq <= control_sequence_) return;
  control_sequence_ = seq;
  if (doc["attached"].is<bool>()) {
    attached_ = doc["attached"].as<bool>();
    scheduler_.detach(); active_.reset(); tracker_.reset(); input_queue_.clear();
    for (auto *key : keys_) key->invalidate_state();
    if (attached_) scheduler_.attach(++generation_);
  }
  if (doc["delay_ms"].is<uint32_t>()) delay_ = std::min(doc["delay_ms"].as<uint32_t>(), uint32_t(5000));
  if (doc["fail_page"].is<int>()) fail_page_ = doc["fail_page"].as<int>();
  if (attached_) {
    for (auto value : doc["masks"].as<JsonArray>()) {
      if (value.is<uint16_t>() && value.as<uint16_t>() < 32768)
        input_queue_.push(generation_, value.as<uint16_t>());
    }
  }
  std::remove("/lab/control.json");
}
void VirtualDeck::snapshot_() {
  const auto text = json::build_json([&](JsonObject root) {
    root["session"] = session_;
    root["sequence"] = control_sequence_;
    root["attached"] = attached_;
    root["generation"] = generation_;
    root["reports"] = reports_;
    root["failed_reports"] = failed_reports_;
    root["edges"] = edges_;
    root["input_overflows"] = input_queue_.overflows();
    root["downloads"] = pipeline_.downloads();
    root["cache_hits"] = pipeline_.cache_hits();
    root["failures"] = pipeline_.failures();
    root["graphics_bytes"] = memory_.used_bytes();
    root["graphics_peak"] = memory_.peak_bytes();
    root["active_page"] = active_ ? int(active_->kind) - 1 : 0;
    auto tiles = root["tiles"].to<JsonArray>();
    for (int key = 0; key < 15; key++) {
      auto tile = tiles.add<JsonObject>();
      visual_api().get(session_, key).write(tile);
      tile["text"] = std::string(store_.desired(key)->text.view());
      tile["image_revision"] = std::string(store_.desired(key)->image_revision.view());
      tile["hash"] = tile_hashes_[key];
      tile["uploads"] = tile_uploads_[key];
    }
  });
  std::ofstream file("/lab/status.tmp", std::ios::binary);
  file.write(text.data(), text.size()); file.close();
  std::rename("/lab/status.tmp", "/lab/status.json");
}
void VirtualDeck::loop() {
  control_();
  InputReport input;
  while (input_queue_.pop(input)) {
    if (input.generation == generation_) input_(input.mask, input.resync);
  }
  // Reuse the bounded production pipeline; only networking and USB are adapted.
  for (int step = 0; step < 32; step++) {
    pipeline_.loop(millis());
    if (!pipeline_.needs_cpu()) break;
  }
  if (attached_) {
    if (!active_) {
      Job next;
      if (scheduler_.next(next)) { active_ = next; due_ = millis() + delay_; }
    }
    if (active_ && int32_t(millis() - due_) >= 0) {
      const auto job = *active_;
      if ((fail_page_ == 1 && job.kind == JobKind::PAGE1) || (fail_page_ == 2 && job.kind == JobKind::PAGE2)) {
        failed_reports_++; fail_page_ = 0;
        scheduler_.detach(); scheduler_.attach(++generation_);
        tracker_.reset(); input_queue_.clear();
        for (auto *key : keys_) key->invalidate_state();
      } else {
        std::array<uint8_t, protocol::REPORT_SIZE> bytes{};
        bool valid = false;
        if (job.kind == JobKind::RESET) valid = protocol::stream_reset(bytes.data(), bytes.size());
        else if (job.kind == JobKind::BRIGHTNESS)
          valid = protocol::brightness(job.brightness, bytes.data(), protocol::FEATURE_SIZE);
        else valid = protocol::image_page(job.key, job.kind == JobKind::PAGE1 ? 1 : 2,
                                           *job.image.get(), bytes.data(), bytes.size());
        if (!valid || !scheduler_.complete(job)) std::abort();
        reports_++;
        if (job.kind == JobKind::PAGE2) {
          tile_hashes_[job.key] = deck_png_crc(0, job.image.get()->data, job.image.get()->size);
          tile_uploads_[job.key]++;
        }
      }
      active_.reset();
    }
  }
  if (uint32_t(millis() - last_snapshot_) >= 100) { last_snapshot_ = millis(); snapshot_(); }
}
}  // namespace esphome::virtual_deck
