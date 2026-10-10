# Wiring and hardware acceptance

Status: USB flashing, Wi-Fi, encrypted API, 8 MB PSRAM initialization and encrypted
OTA verified on 2026-10-10. The deck's invalid full-speed packet-size descriptor
persists after a confirmed 20-second power removal. A targeted host-side fix is
deployed: the S3 claims the deck at MPS 64 and completes the full stream reset,
brightness request and all 30 blank-image pages. Physical key mapping, visual
image/brightness confirmation, loaded electrical qualification and HA tests remain pending.
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

The local `examples/secrets.yaml` appeared during the desktop session; probe 01
and HA example 03 validate with it, without displaying credentials. The initial
desktop session did not write flash; the subsequent authorized upload is below.

## First firmware upload, 2026-10-10

The owner confirmed the sequence: flash through PC USB-C, physically disconnect
the PC, attach the Stream Deck and then use a separate source sufficient for both
devices. This authorizes the PC flashing step; source/protection ratings and
loaded electrical measurements remain unverified.

Uploaded `examples/01_usb_probe.yaml` from repository baseline `c5583e8` with the
working-tree deployment-tool changes. It includes Wi-Fi with DHCP, encrypted API
logs, encrypted OTA, UART0 logging and stock USB enumeration of `0FD9:0060`.
Key decoding, brightness and images are deferred to the next firmware over OTA.

The deployment build used local credentials through:

```sh
.venv/bin/python tools/check_firmware.py --compile --example 01_usb_probe --deploy
```

It lives under private `.build/deploy/01_usb_probe/`; validation builds under
`.build/firmware/` still contain synthetic credentials and must not be uploaded.
The 849,616-byte factory image's SHA-256 is
`5fb06f4dc16c42ed438ec689bac8e048ddfb508a5a20c1fa496a263cbbef41dd`.

Before writing, the entire 16 MB flash was saved to ignored, mode-0600
`.build/backups/pre-probe-RFqYSN/flash.bin` and verified against the device's MD5.
Its SHA-256 is `53e18c9e68197fa13045269813bc86a94c5b8b6f02fee8ad5a906b4630c21ec0`.
This backup may contain prior credentials and must remain private. Initial stub
reads timed out at both 460800 and 115200 baud. ROM reads worked; a long single
read was interrupted for performance, then `.build/backup_flash_rom.py` used
bounded 1 MiB ROM reads and checked the full device hash. No dependency was changed.

The successful write used:

```sh
.venv/bin/esptool --chip esp32s3 --port /dev/ttyACM0 --baud 115200 --no-stub --after no-reset write-flash --no-progress 0 .build/deploy/01_usb_probe/build/firmware.factory.bin
```

esptool 5.3.1 erased `0x00000000..0x000cffff`, wrote 849,616 bytes, and reported
`Hash of data verified.` It exited successfully and left the ESP in its ROM
bootloader. No eFuses were changed. The planned power cycle starts the new
firmware; runtime USB Serial/JTAG will yield the native interface to USB host.

The owner subsequently supplied the DHCP address and network verification
continued as recorded below. Physical UART0 capture and every loaded-power gate
remain open; USB and CPU resets still do not switch peripheral VBUS.

## Network and S3 USB session, 2026-10-10

Encrypted API device information matched `streamdeck-original`, ESPHome 2026.9.0,
ESP32-S3 revision v0.2. The runtime configuration reported PSRAM initialized and
8192 KB available, UART0 at 115200, Wi-Fi connected, Noise API encryption enabled,
and OTA encryption required. This verifies PSRAM startup, not a load/soak test.

Initial signal was -88 to -89 dBm, with an API request timeout, a later API ping
timeout and one missing response in a five-ping ICMP check. Later logs reported
-36 to -44 dBm; a new five-ping check returned all five responses, and complete
API configuration dumps arrived promptly. The cause of the improvement was not
confirmed; no antenna or transmitter-power change is inferred from those logs.

Two encrypted OTA v2 uploads of example 02 succeeded, followed by API reconnection
to the new firmware. The first took 16.86 seconds total, and the diagnostic update
took 19.65 seconds. That diagnostic image was compiled at
`2026-10-10 20:08:51 +0200`, is 812,960 bytes, and has SHA-256
`5cf3e353f8596784bf0a1d4b5071dea0171ce8d7688a12341c4195944dc3c0d9`.
Safe-mode logs reported successful boot and reset the boot-loop counter. These
are development observations, not the complete warm-restart qualification.

The USB host finds the original VID/PID. Both `usb_host_device_info` and
`usb_host_get_active_config_descriptor` return `ESP_OK`; the speed is
`USB_SPEED_FULL` (numeric 1). Its actual 41-byte configuration is preserved in
`tests/fixtures/s3_0060/configuration_full_speed.hex` with provenance. It has one
HID interface, number/alternate 0/0, interrupt IN `0x81` and OUT `0x02`, both
with **MPS 512**, and a 400 mA declaration. The bytes match the desktop high-speed
configuration, despite the physical S3 link running at 12 Mbps. The previously
captured desktop other-speed descriptor instead advertised MPS 64 and 100 mA.

Before the compatibility fix, the driver rejected this active layout before
claiming an interface or allocating/submitting input/output transfers.
`attached=no`, generation 0 and
zero completed reports confirm that brightness, stream reset and image reports
have not run. The rising error counter represents repeated descriptor rejection
at five-second intervals, not a series of failed image writes. A fake-IDF
regression test reproduces this rejection using the S3-captured bytes and checks
that no interface is claimed and no transfer is submitted.

The owner then unplugged only the deck for at least 20 seconds and supplied the
same descriptor dump after reconnecting. The mismatch therefore persists across
physical peripheral power removal; it is not retained state from the desktop.

## Compatibility fix and successful reports, 2026-10-10

The [transport decision](decisions/usb-transport.md#original-full-speed-descriptor-compatibility)
documents the source-pinned, build-local IDF correction. It normalizes only the
known Original full-speed descriptor, before IDF publishes its owned copy.

The fixed example 02 was compiled at `2026-10-10 20:38:07 +0200` and deployed by
encrypted OTA in 22.18 seconds total. Its OTA image is 813,152 bytes, SHA-256
`eb3967f77651f266ec516fa1774f0fdd8d41b49da2a81620123321c315606b3d`.
After reboot the encrypted API reported:

```text
Stream initialization completed: yes
USB status: attached=yes, generation=1, completed reports=32
HID interface 0 alt 0, IN 0x81 MPS 64, OUT 0x02 MPS 64, report descriptor 267 bytes
Stream Deck USB ready: True
USB errors: 0
Input queue overflows: 0
Input queue high water: 0
Stream Deck brightness: 30
```

The 32 completions comprise one complete 8191-byte stream reset, one 17-byte
brightness feature and 30 complete 8191-byte blank-image pages (two per key).
The transport checks successful status and exact lengths for every interrupt
batch/control transfer before incrementing its report counter. This passes the
large-report transport gate for these bytes, not visual orientation/color checks.
The brightness value is requested state with successful transfer, not readback.

While two API clients were active, sampled internal free heap was 233,632–239,580 B
and the minimum counter reached 212,000 B. These are short-session measurements,
not a leak/soak result. No key input was captured in this session yet; a top-left
press/release test and visual confirmation of the blank displays were requested.
All electrical measurements and the remaining release tests stay pending.

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
