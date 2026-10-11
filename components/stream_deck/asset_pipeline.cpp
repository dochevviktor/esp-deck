#include "asset_pipeline.h"
#include <cstring>
#include <new>

namespace esphome::stream_deck::assets {
Pipeline::Pipeline(visual::Store &store, Fetcher &fetcher, ImageAllocator &memory, ImageAllocator &native,
                   const OriginPolicy &policy)
    : store_(store), fetcher_(fetcher), memory_(memory), policy_(policy), native_(native),
      cached_(memory, visual::MAX_BACKGROUND_BYTES - sizeof(entries_)), decoder_(memory) {
  key_entries_.fill(-1);
}
visual::Submission Pipeline::submit(const visual::Command &command) {
  if ((command.fields & visual::IMAGE) && !command.image_url.empty() && !policy_.allows(command.image_url)) {
    const auto *status = store_.status(command.key);
    return {false, visual::Error::ORIGIN_NOT_ALLOWED, status ? status->phase : visual::Phase::IDLE,
            status ? status->revision : 0};
  }
  return store_.submit(command);
}
int Pipeline::find_(const Identity &identity) {
  for (size_t i = 0; i < entries_.size(); i++)
    if (entries_[i].pixels && entries_[i].identity == identity) return int(i);
  return -1;
}
int Pipeline::reserve_() {
  int oldest = -1;
  for (size_t i = 0; i < entries_.size(); i++) {
    const auto &entry = entries_[i];
    if (entry.keys) continue;
    if (!entry.pixels) return int(i);
    if (oldest < 0 || entry.used < entries_[oldest].used) oldest = int(i);
  }
  if (oldest >= 0) entries_[oldest].pixels.reset();
  return oldest;
}
void Pipeline::render_(rendering::PixelView source) {
  if (!renderer_->begin(job_.state, source)) { fail_(renderer_->error()); return; }
  phase_ = Phase::RENDER;
}
void Pipeline::begin_(uint32_t now) {
  if (!store_.next(job_)) return;
  phase_ = Phase::RENDER;  // A job now exists even if setup fails.
  entry_ = -1; cache_miss_ = false; started_ = now;
  if (!workspace_) {
    if (!workspace_.allocate(memory_, sizeof(rendering::Workspace))) { fail_(visual::Error::OUT_OF_MEMORY); return; }
    auto *workspace = new (workspace_.data()) rendering::Workspace{};
    renderer_.emplace(*workspace);
  }
  if (job_.state.image_url.empty()) { render_({}); return; }
  if (!policy_.allows(job_.state.image_url.view())) { fail_(visual::Error::ORIGIN_NOT_ALLOWED); return; }
  const Identity identity(job_.state);
  entry_ = find_(identity);
  if (entry_ >= 0) {
    cache_hits_++; entries_[entry_].used = ++clock_;
    render_({entries_[entry_].pixels.data(), rendering::RGB_BYTES, rendering::WIDTH * 3,
             rendering::WIDTH, rendering::HEIGHT, rendering::PixelFormat::RGB});
    return;
  }
  entry_ = reserve_();
  if (entry_ < 0 || !encoded_.allocate(memory_, visual::MAX_ENCODED_BYTES)) { fail_(visual::Error::OUT_OF_MEMORY); return; }
  entries_[entry_].identity = identity;
  cache_miss_ = true;
  if (!fetcher_.start(job_.state.image_url.view(), encoded_.data(), encoded_.size(), job_.token)) {
    fail_(visual::Error::FETCH_FAILED); return;
  }
  downloads_++; phase_ = Phase::FETCH;
}
void Pipeline::retire_() {
  if (renderer_) renderer_->cancel();
  decoder_.cancel(); encoded_.reset();
  job_ = {}; entry_ = -1; phase_ = Phase::IDLE;
}
void Pipeline::fail_(visual::Error error) {
  if (store_.fail(job_, error)) failures_++;
  if (phase_ == Phase::FETCH) {
    fetcher_.cancel(); phase_ = Phase::DRAIN;  // The worker still owns encoded_.
  } else retire_();
}
bool Pipeline::superseded_asset_() const {
  const auto *desired = store_.desired(job_.key);
  return store_.status(job_.key)->revision != job_.revision && !(Identity(*desired) == Identity(job_.state));
}
void Pipeline::commit_() {
  if (cache_miss_) {
    auto &entry = entries_[entry_];
    if (!entry.pixels.allocate(cached_, rendering::RGB_BYTES)) { fail_(visual::Error::OUT_OF_MEMORY); return; }
    std::memcpy(entry.pixels.data(), renderer_->background().data, rendering::RGB_BYTES);
    entry.used = ++clock_;
  }
  // A superseded label may still leave a useful background for the newest
  // request. Never publish its BMP or unnecessarily fetch that asset again.
  if (store_.status(job_.key)->revision != job_.revision) {
    store_.fail(job_, visual::Error::RENDER_FAILED); retire_(); return;
  }
  auto image = renderer_->copy_image(++image_version_, native_);
  if (!image) { fail_(visual::Error::OUT_OF_MEMORY); return; }
  if (store_.finish(job_, image)) {
    const auto previous = key_entries_[job_.key];
    if (previous >= 0) entries_[previous].keys &= uint16_t(~(1U << job_.key));
    key_entries_[job_.key] = int8_t(entry_);
    if (entry_ >= 0) entries_[entry_].keys |= uint16_t(1U << job_.key);
  }
  retire_();
}
void Pipeline::loop(uint32_t now) {
  if (phase_ == Phase::DRAIN) {
    FetchResult result;
    if (fetcher_.poll(result) && result.token == job_.token) retire_();
    return;
  }
  if (phase_ == Phase::IDLE) { if (!stopped_) begin_(now); return; }
  if (superseded_asset_()) { fail_(visual::Error::RENDER_FAILED); return; }
  if (phase_ == Phase::FETCH) {
    if (uint32_t(now - started_) >= visual::FETCH_TIMEOUT_MS) { fail_(visual::Error::FETCH_TIMEOUT); return; }
    FetchResult result;
    if (!fetcher_.poll(result) || result.token != job_.token) return;
    // A matching result retires all worker access before the buffer is inspected.
    phase_ = Phase::PNG; last_http_status_ = result.http_status;
    if (result.error != visual::Error::NONE) { fail_(result.error); return; }
    if (result.bytes > encoded_.size()) { fail_(visual::Error::LIMIT_EXCEEDED); return; }
    if (!decoder_.begin(encoded_.data(), result.bytes)) fail_(decoder_.error());
    return;
  }
  if (phase_ == Phase::PNG) {
    const auto phase = decoder_.step();
    if (phase == PngDecoder::Phase::FAILED) fail_(decoder_.error());
    else if (phase == PngDecoder::Phase::DONE) { encoded_.reset(); render_(decoder_.pixels()); }
    return;
  }
  if (renderer_->step() == rendering::Phase::DONE) commit_();
}
void Pipeline::stop() {
  stopped_ = true;
  if (phase_ != Phase::IDLE && phase_ != Phase::DRAIN) fail_(visual::Error::FETCH_FAILED);
}
}  // namespace esphome::stream_deck::assets
