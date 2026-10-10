# Wiring and hardware acceptance

Status: owner's topology documented; exact parts, current-path qualification and
all physical tests pending. No board was attached during implementation.
The handover is the hardware source of truth; this is its operational checklist.

```text
ONE regulated 5 V source
    |
power-only breakout VBUS ---- input fault/reverse-current protection ---- XIAO 5V
power-only breakout GND ----------------------------------------------- XIAO GND
breakout D+ / D-: unconnected and insulated

XIAO onboard USB-C -- passive USB 2.0 C-male/A-female data adapter -- Stream Deck
                     shared externally powered VBUS and native USB data
```

The header 5V rail and onboard USB-C VBUS are tied in the published Plus V1.1
schematic. The deck load therefore travels through the board's 5 V path, not the
3.3 V regulator. That schematic establishes connectivity, not a guaranteed safe
peripheral current rating for the real board, wires or connectors.

Native data is already routed: GPIO19=D−, GPIO20=D+. The XIAO label **D19 is
GPIO11**, not GPIO19. No data wiring from the power breakout is needed.
The fixed CC pull-downs mean this is a dedicated prototype with a passive adapter,
not a general-purpose standards-compliant USB-C power source. Verify both adapter
orientations; avoid hubs, docks, charge-only adapters and active negotiation devices.

Use a qualified 5 V source supporting the combined board + deck load. The input
diode specified in Seeed's external-power guidance points **anode to source,
cathode to XIAO 5V** and carries both loads in this topology. Choose a suitable
low-drop/current-rated part or a validated reverse-current-blocking circuit, and
provide fault-current protection appropriate to the wiring and board path. Reverse
blocking alone is not overcurrent protection. Do not raise voltage to hide drops.

A PC used solely at the power breakout is still one source, but a standard data
port does not authorize an arbitrary high power-only load without enumeration.
Treat that as a separately qualified source-specific option. Do not connect the
inlet data pads to the host data pair to seek upstream power negotiation. No
battery, powered hub, Y cable or second supply belongs in the initial setup.

## Before first deck attachment

- [ ] Record actual Plus PCB revision and confirm nominal 16 MB flash / 8 MB PSRAM.
- [ ] Record source model, 5 V mode, continuous/peak rating and current limiting.
- [ ] Record inlet connector, wire gauge/length, protection parts and polarity.
- [ ] Record exact passive adapter and verify data/power continuity in both orientations.
- [ ] Check for shorts, common ground, correct VBUS polarity and isolated inlet D+/D−.
- [ ] Measure unloaded board and downstream USB-A VBUS.
- [ ] Confirm the breakout feed is physically disconnected before PC USB-C flashing.
- [ ] Confirm UART adapter is 3.3 V logic with its power pin left unconnected.

## Supervised loaded qualification

- [ ] Measure total operating/peak/startup current; do not substitute `bMaxPower`.
- [ ] Measure source, XIAO 5V and downstream USB-A voltages at 100% brightness with Wi-Fi active.
- [ ] Check protection dissipation, board/connector/wire heating and voltage margin.
- [ ] Capture hot-plug/startup voltage dips with a scope where available.
- [ ] Confirm memory detection, stable boot and absence of brownouts.
- [ ] Qualify repeated enumeration in both adapter orientations.
- [ ] Test cold power-up and ESP-only restart with the deck continuously powered.
- [ ] If the path fails qualification, document a complete revised protected wiring
  diagram before adopting a separately supplied peripheral path.

## Programming and logs

Host mode: native USB-C is dedicated to the Stream Deck. Flashing mode: disconnect
the inlet feed and deck adapter; PC USB-C is the only power/data connection. An
input diode does not isolate an externally energized USB-C port from a PC.
Label connectors, insulate exposed pads and provide strain relief. Never use
USB-A male-to-male cables between host-style sockets.

UART0 at 115200: D6/GPIO43 TX → adapter RX, common GND. Optional D7/GPIO44 RX ←
adapter TX. Leave adapter VCC open. BOOT/reset recovery and OTA commands are in
the README. USB root-port recovery changes controller state; it does not switch
this VBUS rail.

## Measurements to supply later

Record the unchecked items above, then obtain `lsusb -v -d 0fd9:0060` and `lsusb -t`
from the working desktop setup, plus the HID report descriptor where possible.
Missing-permission output may omit descriptors; do not treat it as complete.
Record interface numbers, endpoint directions/types/MPS, speed and declared power.
Redact serial numbers before sharing. Also record the working Python-library
revision, deck firmware and intended HA entity. A targeted USB capture is optional
if descriptors leave a concrete routing/report uncertainty.

References: [Seeed specifications and power guidance](https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/),
[Plus V1.1 schematic](https://files.seeedstudio.com/wiki/SeeedStudio-XIAO-ESP32S3/res/XIAO_ESP32S3_Plus_V1.1_SCH_260115.pdf),
and Sections 2 and 13 of the preserved handover. No parts-level review or load
measurement has been completed by this repository's software tests.
