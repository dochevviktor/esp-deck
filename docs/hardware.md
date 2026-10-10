# Wiring and hardware acceptance

Status: owner's topology documented; desktop descriptors, deck firmware and ESP
chip/flash identity read on 2026-10-10. Exact parts, current-path qualification
and all ESP32-to-deck tests remain pending. Both devices were attached separately
to the PC for this session.
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

## Desktop observations, 2026-10-10

Repository baseline: `b17edee`. Linux xHCI enumerated the deck as `0FD9:0060` at
480 Mbps and the Espressif USB Serial/JTAG device as `303A:1001` at 12 Mbps,
with `/dev/ttyACM0` available. An `esptool 5.3.1` `flash-id` query then identified
ESP32-S3 QFN56 revision v0.2, 16 MB flash (manufacturer `0x85`, device `0x2018`),
quad/3.3 V flash eFuse settings, and embedded 8 MB PSRAM (`AP_3v3`). This matches
the configured memory capacities; PSRAM boot initialization and a memory test
remain pending. The query ran a temporary RAM stub and reset the ESP afterward;
no flash was written and no eFuses were changed. PCB revision and installed
firmware are still unknown. MAC output was redacted.

Captured bytes and provenance are under `tests/fixtures/desktop_0060/`. Reproduce
the read-only deck probe with `.venv/bin/python tools/probe_desktop.py`. The tool
queries neither USB serial strings nor the serial-number feature report. No
kernel driver detachment, device reset or SET_REPORT is needed for this capture.

| Field | Active desktop configuration | Advertised other-speed configuration |
| --- | --- | --- |
| Speed | High speed, observed 480 Mbps | Full speed, not physically exercised |
| Configuration / HID interface / alternate | 1 / 0 / 0 | 1 / 0 / 0 |
| Interrupt IN | `0x81`, MPS 512, `bInterval=1` | `0x81`, MPS 64, `bInterval=1` |
| Interrupt OUT | `0x02`, MPS 512, `bInterval=1` | `0x02`, MPS 64, `bInterval=1` |
| `bMaxPower` declaration | 400 mA | 100 mA |
| Attributes | `0xe0`: self powered, remote wakeup | `0xe0`: self powered, remote wakeup |
| HID descriptor | HID 1.11, report descriptor 267 bytes | Same declaration |

Neither power declaration establishes actual consumption or qualifies the inlet.
The full-speed descriptor was retrieved with standard GET_DESCRIPTOR type 7
while the device remained at high speed. The native parser test changes only
that descriptor type to 2 and verifies the advertised interface/endpoints; it
also verifies that the high-speed configuration is rejected. This is compatible
with the chosen S3 transport at the descriptor level, not proof of enumeration
or complete 8191-byte interrupt output on the S3.

GET_REPORT(Feature 4), 17 bytes, returned firmware `1.0.191203`. The report
descriptor declares output ID `0x02` with 8190 payload bytes (8191 with ID),
feature IDs `0x03`, `0x04`, `0x05` and `0x0b` with 16 payload bytes, and input
IDs `0x01`, `0xa0`, `0xa1` with 16 payload bytes each (17 with ID).

Input length remains unresolved: the pinned Python library requests only 16
bytes, whereas this HID descriptor declares 17. Our decoder currently requires
exactly 16; capture a real press/release with a 512-byte hidraw read before
changing the contract. The descriptor's additional input IDs must not be assumed
to carry key states. A trial GET_REPORT(Input 1) with a 64-byte buffer returned
64 zero bytes, without the requested ID; this is not a validated initial-state
read. An initial 3-second observation and a subsequent 180-second passive capture
returned no interrupt reports. No physical key press was confirmed during those
windows; this does not establish behavior on reset or on first key press.

The ESP32 probe flash is pending confirmation of PC-only power. The local
`examples/secrets.yaml` appeared during this session; probe 01 and HA example 03
validate with it, without displaying credentials. This does not verify Wi-Fi
connectivity. Firmware validation builds use synthetic credentials and must not
be flashed for network testing. Runtime UART0, PSRAM detection and every
loaded-power gate remain open.

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

Record the unchecked items above. Desktop USB/HID descriptors and deck firmware
are recorded above; capture actual key input and confirm the descriptors again
on the S3. `lsusb -v` showed the HID report descriptor as unavailable even though
it was readable through sysfs, so that output alone was incomplete. Redact serial
numbers before sharing. Also record the owner's working Python-library revision
and intended HA entity. A targeted USB capture is optional if input observations
leave a concrete routing/report uncertainty.

References: [Seeed specifications and power guidance](https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/),
[Plus V1.1 schematic](https://files.seeedstudio.com/wiki/SeeedStudio-XIAO-ESP32S3/res/XIAO_ESP32S3_Plus_V1.1_SCH_260115.pdf),
and Sections 2 and 13 of the preserved handover. No parts-level review or load
measurement has been completed by this repository's software tests.
