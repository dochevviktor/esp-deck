#pragma once
#include "stream_deck.h"

namespace esphome::stream_deck {
template<typename... Ts> class SetImageAction : public Action<Ts...> {
 public:
  SetImageAction(StreamDeck *parent, const NativeImage *image) : parent_(parent), image_(image) {}
  TEMPLATABLE_VALUE(int, key)
  void play(const Ts &...x) override { parent_->set_image(this->key_.value(x...), image_); }
 protected:
  StreamDeck *parent_;
  const NativeImage *image_;
};
template<typename... Ts> class RedrawAction : public Action<Ts...> {
 public:
  explicit RedrawAction(StreamDeck *parent) : parent_(parent) {}
  void play(const Ts &...x) override { parent_->redraw(); }
 protected:
  StreamDeck *parent_;
};
}  // namespace esphome::stream_deck
