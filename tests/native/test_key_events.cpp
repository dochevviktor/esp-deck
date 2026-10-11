#include "stream_deck.h"
#include <cassert>
#include <iostream>

using namespace esphome;
using namespace esphome::stream_deck;

// This test drives the production ESPHome publication method. USB itself has
// a separate production-transport test; don't install a fake bus for this one.
namespace esphome::stream_deck {
bool USBTransport::setup() { return true; }
void USBTransport::loop(uint32_t) {}
void USBTransport::shutdown() {}
void USBTransport::dump_status() const {}
bool USBTransport::send(const Job &, uint32_t) { return true; }
bool USBTransport::take_completion(Job &) { return false; }
}
size_t heap_caps_get_free_size(uint32_t) { return 0; }
size_t heap_caps_get_minimum_free_size(uint32_t) { return 0; }

class Deck : public StreamDeck {
 public:
  void input(uint16_t mask, uint32_t generation = 1, bool resync = false) {
    publish_input_({generation, mask, resync});
  }
  void attach(uint32_t generation) { generation_ = generation; }
  void detach() { disconnect_(); }
  void runtime() { runtime_visuals_ = true; }
};

int main() {
  Deck deck;
  std::array<binary_sensor::BinarySensor, 15> sensors;
  std::array<event::Event, 15> events;
  for (uint8_t key = 0; key < 15; key++) {
    deck.set_key_sensor(key, &sensors[key]); deck.set_key_event(key, &events[key]);
  }
  deck.attach(1);
  // Held at first report and its eventual release publish state, never events.
  deck.input(1); deck.input(0);
  assert(events[0].events.empty() && sensors[0].changes.empty() && sensors[0].has_state());
  for (uint8_t key = 0; key < 15; key++) {
    deck.input(1U << key); deck.input(1U << key); deck.input(0); deck.input(0);
    assert((events[key].events == std::vector<std::string>{"press", "release"}));
    assert((sensors[key].changes == std::vector<bool>{true, false}));
    events[key].events.clear();
  }
  assert(deck.get_press_trigger()->calls.size() == 15 && deck.get_release_trigger()->calls.size() == 15);
  // Multiple real edges are published, then detach invalidates without a release.
  deck.input(0x4001); deck.detach();
  assert(!sensors[0].has_state());
  assert((events[0].events == std::vector<std::string>{"press"}));
  assert((events[14].events == std::vector<std::string>{"press"}));
  deck.attach(3);
  deck.input(0, 1);  // Stale generation must not establish the new baseline.
  deck.input(0x4001, 3); deck.input(0, 3);
  assert(events[0].events.size() == 1 && events[14].events.size() == 1);
  deck.input(2, 3, true); deck.input(0, 3);  // Overflow synchronization also stays silent.
  assert(events[1].events.empty());
  deck.input(1, 3); deck.input(0, 3);
  assert((events[0].events == std::vector<std::string>{"press", "press", "release"}));
  // Direct static/runtime image writers cannot invalidate Store's state in P4.
  assert(deck.set_image(0, &protocol::blank_image()));
  deck.runtime();
  assert(!deck.set_image(0, &protocol::blank_image()));
  assert(!deck.set_image(0, ImageRef::from_static(&protocol::blank_image())));
  std::cout << "Production key publication: real edges, no baseline/held/stale/detach events; visual ownership passed\n";
}
