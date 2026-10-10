# Validation and remaining hardware gates

Initial software validation: 2026-10-10, without hardware, committed as `b17edee`.
Later on the same day, both devices were connected separately to the PC. Desktop
USB/HID descriptors, deck firmware and ESP chip/flash identity were read; no ESP
flash write was performed in that descriptor session (committed as `c5583e8`).
The subsequent deployment session compiled probe 01 with local credentials,
backed up all 16 MB and uploaded the factory image with hash verification. No
electrical measurement or live HA action has been performed. A further network
session verified Wi-Fi, encrypted API, initialized PSRAM and two encrypted OTA
updates. It captured a full-speed descriptor mismatch before any HID report
could be sent. A confirmed 20-second deck power removal did not change it. The
source-pinned compatibility fix now completes all 32 startup reports on hardware
with zero reported USB errors. Physical input/visual checks remain pending.
Deployment-tool, diagnostic and compatibility changes remain in the working tree.

## Evidence categories

| Category | Result |
| --- | --- |
| Implemented | Codec, scheduler, USB transport/entities/images/recovery, diagnostics, desktop probe, private builds and a source-pinned IDF descriptor compatibility hook |
| Unit-tested | 21 Python cases including native C++ suites, raw/normalized S3 descriptor fixtures, full-report production-transport simulation, build-hook source guards and private staging |
| Compiled | All three numbered examples with synthetic credentials; examples 01 and 02 also built privately for deployment, ESP-IDF 5.5.5 / ESPHome 2026.9.0 |
| Hardware-verified | Identity/flash, Wi-Fi, encrypted API/OTA, 8 MB PSRAM initialization, interface claim, full 8191-byte reset, brightness feature and 30 blank-image pages; physical key mapping/visual correctness remain pending |
| Remote CI | Workflow provided; not executed in this session |

Commands actually run:

```sh
.venv/bin/python tools/generate_reference_fixtures.py
.venv/bin/python tools/generate_reference_fixtures.py --check
.venv/bin/python tools/generate_demo_assets.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/check_firmware.py
.venv/bin/python tools/check_firmware.py --compile
.venv/bin/python -m pip check
```

All final commands passed. An initial sanitizer link attempt failed because this
machine lacks `/usr/lib64/libasan.so.8.0.0`. Local C++ tests ran with warnings as
errors and assertions enabled, without sanitizers. `SANITIZE=1` enables ASan/UBSan
on a machine with those runtimes; the CI workflow requests them. This document
does not claim a local sanitizer run passed.

Initial baseline builds after disabling the secondary USB console:

| Example | Static RAM estimate | Application flash estimate |
| --- | ---: | ---: |
| 01 USB probe | 108,371 B / 341,760 B | 783,987 B / 8,126,464 B |
| 02 keys/brightness | 109,083 B / 341,760 B | 812,095 B / 8,126,464 B |
| 03 images/HA | 109,555 B / 341,760 B | 867,699 B / 8,126,464 B |

These linker estimates exclude runtime USB/task/network allocation and are not
free-heap measurements. The checker also verifies the actual generated control
cap (8192 for driver examples) and disabled secondary USB console. Firmware
validation binaries remain ignored and contain synthetic credentials; do not
flash them. Explicit `--deploy` builds use local credentials and are stored
separately in private `.build/deploy/` directories.

The first deployment build used
`.venv/bin/python tools/check_firmware.py --compile --example 01_usb_probe --deploy`.
Its static RAM estimate is 108,371 B, application estimate 783,971 B, and merged
factory image is 849,616 B. The generated SDK disables the secondary USB console;
the image header identifies ESP32-S3, 16 MB flash, DIO and 80 MHz. Deployment
staging leaves local secrets untouched, sets the staged file to mode 0600, and
keeps raw compiler output inside the mode-0700 deployment directory. The two
additional host tests verify private secret staging, isolation from synthetic
validation builds, and rejection of an incomplete deployment command.

## What the automated tests establish

- The upstream encoder with a recording transport generated brightness 0/1/50/100,
  device-reset, stream-reset and both image reports for keys 0/4/5/10/14. Committed
  fixtures and their SHA-256 manifest reproduce byte-for-byte under the pins.
- Native C++ compares full reports, report IDs, padding, BMP split and setup bytes.
  It tests all key mappings, short/malformed input, simultaneous keys, duplicates,
  brightness bounds, invalid keys/assets and BMP headers.
- Scheduler tests cover change coalescing during an active image, consecutive
  pages, fairness, brightness between images, redraws, stale generations and
  disconnect during either page. Input tests cover rapid press/release order,
  held-at-connect suppression and explicit overflow resynchronization.
- The production USB transport, linked to a fake IDF, submits the full 8199-byte
  control operation and preserves all 8191 bytes across interrupt batches. Tests
  exercise discovered non-default endpoint/interface values, idle absence, wrong
  models, malformed input, short output, STALL, software deadline, retained
  buffers while cancellation is delayed, and reattachment afterward.
- All example schemas pass; invalid keys, duplicate key/number bindings, malformed
  BMPs, initial-state triggers, other MCUs, Arduino and competing USB/logging
  ownership are rejected. Firmware compilation checks the real IDF signatures.

Mocks establish software behavior under the simulated event order. They do not
establish that this board/device sends the expected reports, that cancellation
always arrives, or that interrupt batching/EP0 requests work physically.

## First hardware session

The [network/S3 session](hardware.md#network-and-s3-usb-session-2026-10-10)
now confirms networking, PSRAM initialization and encrypted OTA. Its active
configuration reports 512-byte interrupt endpoints on a full-speed link. The
transport regression suite exercises those exact bytes at simulated full speed
and verifies rejection before any transfer, plus the five-second retry bound.
The owner confirmed persistence after a 20-second power-off. Additional tests
exercise the exact-layout correction, untouched unrelated layouts/IDs/speeds,
and an upstream-golden 8191-byte report through the corrected interface. Three
build-hook tests cover patch placement, source hashes and SDK preservation.

The [fixed firmware](hardware.md#compatibility-fix-and-successful-reports-2026-10-10)
completed 32 startup reports on the S3: full reset, brightness and two blank-image
pages for every key. The encrypted API reports USB ready, zero USB errors and
zero queue overflows. All three examples compile with synthetic secrets; the
checker verifies the corrected USBH source is actually compiled for driver
examples. Physical key mapping and visual/color/orientation checks are next.

Desktop descriptor collection is complete; results and the 16-versus-17-byte
input-report question are recorded in [hardware observations](hardware.md#desktop-observations-2026-10-10).
The full-speed configuration is advertised evidence, not a physical S3 capture.
Additional commands run for this session:

```sh
lsusb -v -d 0fd9:0060
lsusb -t
.venv/bin/python tools/probe_desktop.py
.venv/bin/esptool --chip esp32s3 --port /dev/ttyACM0 --baud 115200 flash-id
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/check_firmware.py --compile
```

Serial strings were redacted from displayed `lsusb` output, and MAC output was
redacted from `esptool`; the probe does not query device serials. Its optional
`--seconds 30` capture reads up to 512 bytes per report
to avoid hiding input length behind the reference library's 16-byte read buffer.
An additional 180-second passive hidraw capture returned zero reports; no key
press was confirmed, so input length and physical mapping remain unverified.
During that initial desktop session, probe 01 and HA example 03 also passed
configuration validation with the local secrets file after it appeared. That
output was withheld. The subsequent probe deployment used real local credentials;
its backup, upload command and verified image hash are recorded in
[the first upload record](hardware.md#first-firmware-upload-2026-10-10).

1. Complete the [power/wiring checklist](hardware.md), record parts/revision,
   and collect desktop configuration/HID descriptors. No topology redesign is
   required by the firmware.
2. Flash probe 01 in PC-only wiring. Return to host wiring and establish UART0
   logs, real flash/PSRAM detection, Wi-Fi/OTA and repeated enumeration. Test both
   adapter orientations with unloaded and loaded VBUS measurements.
3. Run example 02. Record discovered endpoints, MPS, report ID/length and exact
   output completion byte counts. The ready diagnostic only turns on after an
   **8191-byte** stream reset and brightness request succeed. Test brightness
   0, 1, 50, 100; a 17-byte brightness success alone is not the image gate.
4. Display the asymmetric RGB/TL/arrow fixture and then numbered images on all 15
   positions. Check mapping, both flips, BGR channels and both pages. Determine
   whether the deck supplies an initial key state before the first press; otherwise
   first-change baseline behavior needs a descriptor-supported initialization read.
5. Unplug during page 1 and page 2 and while holding multiple keys. Confirm no
   spurious action or stuck sensor, callbacks drain, and desired images/brightness
   return. Repeat with an ESP-only reset and OTA reboot while deck VBUS stays on.
6. Configure the real lamp entity in example 03. Verify one action per intended
   physical press, external HA state changes, unknown/unavailable feedback, HA/API/
   Wi-Fi outages, no command replay and continued OTA availability.

## Release qualification (all pending)

- [ ] 10 cold starts, recording electrical/USB behavior.
- [ ] 10 ESP-only warm restarts with deck continuously powered, including OTA.
- [ ] At least 20 peripheral unplug/replug cycles, including both image pages.
- [ ] 100 deliberate press/release pairs with no missing/duplicate intended actions
  under recorded test conditions; simultaneous holds and rapid clicks while redrawing.
- [ ] Overnight soak with periodic actual HA state changes.
- [ ] 100% brightness plus Wi-Fi stress on the final power/protection path.
- [ ] Record free/minimum internal heap, queue high-water/overflows and USB errors;
  demonstrate no growing resource leak or unexplained reset.
- [ ] Measure action latency and full-deck redraw duration; no performance claim yet.
- [ ] Record firmware commit, dependency pins, actual HA/deck versions and wiring revision.

Until these pass, this is a compiled development firmware, not a qualified release.
