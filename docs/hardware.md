# Wiring and hardware acceptance

Status: USB flashing, Wi-Fi, encrypted API, 8 MB PSRAM initialization and encrypted
OTA verified on 2026-10-10. The deck's invalid full-speed packet-size descriptor
persists after a confirmed 20-second power removal. The S3 claims an experimental
IN-64 / OUT-512 layout and reports completed writes, but those did not produce
visible images in the owner's tests. Two-way EP0 replies are verified. After HID
SET_IDLE startup, 17-byte key reports arrived and exposed a strict-16 decoder
bug, now corrected. Physical key/action mapping, visual image/brightness output,
loaded electrical qualification, reconnect recovery and HA tests remain pending.
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

Input length was unresolved at this desktop stage: the pinned Python library requests only 16
bytes, whereas this HID descriptor declares 17. Our decoder currently requires
exactly 16 at that point. A later S3 interrupt capture below establishes 17-byte
ID-1 input and justifies the decoder change. The descriptor's additional input IDs must not be assumed
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
documents the source-pinned, build-local IDF correction. This first attempt
normalized both endpoints of the known Original full-speed descriptor to MPS 64,
before IDF published its owned copy. The current experiment below supersedes it.

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
batch/control transfer before incrementing its report counter. These are
**host-side completions**, not proof the peripheral processed the reports. The
owner's subsequent observation below means the functional large-report gate is
still open. Brightness is requested state, not measured display output.

While two API clients were active, sampled internal free heap was 233,632–239,580 B
and the minimum counter reached 212,000 B. These are short-session measurements,
not a leak/soak result. No key input was captured in this session yet; a top-left
press/release test and visual confirmation of the blank displays were requested.
All electrical measurements and the remaining release tests stay pending.

## Logo retained and 512-byte OUT experiment, 2026-10-10

The owner pressed the top-left key twice and several other keys. Nothing visibly
changed; the displays stayed blank apart from the placeholder logo. The API
still reported USB ready, zero USB errors/queue overflows, queue high-water zero,
and no retained first-input report. Therefore the failure is not merely a
16-versus-17-byte decoder rejection: no nonempty interrupt input reached the
capture point before validation. Example 02 has no per-key visual action, but
the retained logo and lack of input leave functional output/input unproven.

The next experiment keeps IN MPS 64 and preserves the device's advertised OUT
MPS 512. The host uses the periodic-OUT FIFO allocation. Each 8191-byte output
now uses one 16-packet transfer rather than four batches of 64-byte packets.
The hypothesis is that short 64-byte OUT packets prevent the deck from assembling
its reports. This remains a hypothesis until visual or application-level
evidence confirms it; nonstandard full-speed packet framing is not qualified.

`examples/04_hardware_test.yaml` requests the pinned asymmetric RGB/TL/right-arrow
fixture on logical keys 0 (top-left), 7 (centre), and 14 (bottom-right) at startup.
The other keys get the blank image. Received press edges are logged and select
the yellow ON icon; release edges are logged and restore the arrow fixture.
There are no Home Assistant actions. Initial-state synchronization still
suppresses baseline/held-at-connect actions, so two deliberate press/release
pairs are requested for the initial input check.

The diagnostic image was compiled at `2026-10-10 21:33:56 +0200`, is 845,008 bytes,
and has SHA-256
`963cf20cc9f1bac1d74a80392d443a42e3aaa22831d8fa8d67b5e6099acdeab7`.
Encrypted OTA completed in 31.49 seconds total. After reboot the encrypted API
reported initialization complete, generation 1, 32 host report completions,
IN `0x81` MPS 64 and OUT `0x02` MPS 512 on interface 0/0. PSRAM was available at
8192 KB; Wi-Fi RSSI was around -42 to -43 dBm. Safe mode reported a successful
boot. No first-input snapshot was present. Visual patterns, button events and
brightness response were awaiting owner confirmation at this point.

The owner subsequently confirmed **no arrows and no button messages**, including
after two deck disconnect/reconnect cycles and one quick whole-system power cut
and restoration. The IN-64 / OUT-512 attempt therefore also failed the functional
display/input test. After this report the API still showed the same firmware,
generation 1, 32 host completions, zero USB errors/overflows and high-water zero.

The API also retained an abort from the previous boot. Decoding against that
exact deployment ELF resolved the relevant stack to `root_port_recycle`
(`hub.c:493`) → `hub_port_recycle` → `usbh_event_callback` → `handle_free` →
`usbh_process` → `usb_host_lib_handle_events` → the USB library task. The previous
ELF/OTA image are retained privately under `.build/backups/usb-crash-8hEU6V/`.
The transport was requesting root-port power-off even after `DEV_GONE`; in the
pinned SDK this replaces the expected RECOVERY state with NOT_POWERED, which
`root_port_recycle` does not accept. The revised path lets IDF retire/recycle a
physically detached device and never requests another port-off for it. Native
tests cover detach both idle and during output and check no port-off call occurs.
This fixes a demonstrated recovery defect; it does not explain the original
missing display/input. Physical reconnect qualification must still be repeated.

## Two-way EP0 replies and HID startup test, 2026-10-10

The first control-diagnostic build (compiled `2026-10-10 21:49:46 +0200`, OTA size
846,144 bytes, SHA-256 `ae9bde16045fa1a6c0ad0ab1639bbc646fdd293231deca044a50df9fd7f63480`)
was uploaded successfully in 148.84 seconds, including 148.28 seconds transferring.
After reboot it retained three completed control replies with exact lengths:

| Request | Actual bytes, including 8-byte setup | Reply |
| --- | ---: | --- |
| GET_CONFIGURATION | 9 | Configuration 1 |
| HID report descriptor | 275 | All 267 bytes, equal to the desktop HID descriptor |
| GET_REPORT(Feature 4) | 25 | `04 55 aa d4 04` followed by firmware `1.0.191203` and two NULs |

The captured replies and provenance are saved in
`tests/fixtures/s3_0060/control_probes.json`. A fixture consistency test checks
lengths and equality to the earlier desktop evidence. These establish two-way
control traffic to the actual deck, not just cached descriptors or host write
completion. No serial feature was requested. The build still reported 32 output
completions and no retained interrupt input; no new physical display observation
was obtained during this short diagnostic step.

The next bench build adds the standard HID SET_IDLE(0, all reports) request before
fetching the HID descriptor, following Linux usbhid's initialization sequence.
It does not reset the device firmware or change external VBUS. This tests an
initialization difference from the desktop, not an established cause.

That build was compiled at `2026-10-10 21:53:55 +0200`, OTA size 846,208 bytes,
SHA-256 `7173e9bde3419dead1f2b9b674f4ec305eba2fad3c8f3e1107d5f7448eb101a8`.
Encrypted OTA succeeded in 103.81 seconds total. The subsequent API dump retained
a successful SET_IDLE completion (status 0, actual 8 bytes including setup), the
same configuration/HID/firmware replies, generation 1 and 32 output completions.
No first-input snapshot was initially present. The owner was asked to check the
patterns and perform two top-left press/release pairs without another power
cycle. Visual output, key receipt and physical-detach recovery remain unverified
on this latest build; the successful control request alone is not a fix claim.

During that requested key test, interrupt input **did arrive**. The first retained
report was 17 bytes:

```text
01 00 00 00 00 01 00 00 00 00 00 00 00 00 00 00 00
```

ID is 1, payload offset 5 is set (logical key 0 by the reference mapping), and
the trailing reserved byte is zero. The old decoder requires exactly 16 and
therefore rejects it: USB errors remained zero while malformed-input totals rose
through 6, 18, 30, 35 and 50. The raw bytes and build provenance are preserved in
`tests/fixtures/s3_0060/first_key_input.hex` and `control_probes.json`.

The revised decoder accepts both the reference's 16-byte form and this captured
17-byte form, enforcing ID 1 and a zero trailer for the latter. ESPHome defaults
its input ID filter to 1. Native tests exercise the captured packet, every logical
key, press/release through the production transport, bad states, nonzero trailers
and rejection of A0/A1. SET_IDLE is now part of every driver connection; the
extra three read-only queries remain optional. Receiving raw input is verified;
action delivery, all physical positions and visual output are separate gates.

The decoder-corrected example 04 was compiled at `2026-10-10 21:59:20 +0200` and
deployed successfully over encrypted OTA in 23.84 seconds total. Its OTA image
is 846,240 bytes, SHA-256
`69854221b91d08647a7f64e0fb6d35535896a085dfdf0aa763ca9c286e88ad12`.
The post-reboot API confirms that build, successful control probes, the expected
IN-64 / OUT-512 layout and 32 startup output completions. A new two-click input
and visual-feedback check has been requested without further unplugging.

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
