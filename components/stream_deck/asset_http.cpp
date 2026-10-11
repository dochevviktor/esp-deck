#include "asset_http.h"
#include "esphome/core/defines.h"
#ifdef USE_STREAM_DECK_ASSETS
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace esphome::stream_deck::assets {
bool HttpFetcher::start(std::string_view url, uint8_t *output, size_t capacity, uint64_t token) {
  if (state_.load(std::memory_order_acquire) != IDLE || !output || !valid_fetch_capacity(capacity) ||
      !visual::valid_url(url)) return false;
  if (!task_handle_) {
    TaskHandle_t handle = nullptr;
    if (xTaskCreate(task_, "deck_assets", 8192, this, 1, &handle) != pdPASS) return false;
    task_handle_ = handle;
  }
  url_.assign(url); output_ = output; capacity_ = capacity; token_ = token;
  cancelled_.store(false, std::memory_order_release);
  state_.store(ACTIVE, std::memory_order_release);
  xTaskNotifyGive(static_cast<TaskHandle_t>(task_handle_));
  return true;
}
bool HttpFetcher::poll(FetchResult &result) {
  if (state_.load(std::memory_order_acquire) != FINISHED) return false;
  result = result_;
  state_.store(IDLE, std::memory_order_release);
  return true;
}
void HttpFetcher::task_(void *arg) {
  auto *self = static_cast<HttpFetcher *>(arg);
  for (;;) {
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    if (self->state_.load(std::memory_order_acquire) != ACTIVE) continue;
    self->result_ = fetch_http(self->url_.view().data(), self->output_, self->capacity_, self->token_,
                               self->cancelled_, self->ca_certificate_);
    self->state_.store(FINISHED, std::memory_order_release);
  }
}
}  // namespace esphome::stream_deck::assets
#endif
