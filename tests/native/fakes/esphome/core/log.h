#pragma once
template<typename... Args> inline void fake_log(const char *, const char *, Args...) {}
#define ESP_LOGE(...) fake_log(__VA_ARGS__)
#define ESP_LOGW(...) fake_log(__VA_ARGS__)
#define ESP_LOGI(...) fake_log(__VA_ARGS__)
#define ESP_LOGD(...) fake_log(__VA_ARGS__)
#define ESP_LOGCONFIG(...) fake_log(__VA_ARGS__)
#define LOG_STR(value) value
