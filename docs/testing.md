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
source-pinned compatibility hook completed all 32 startup reports from the host's
perspective, with zero reported USB errors. However, the owner then confirmed
only the logo/blank keys and no response to presses; no interrupt input was
captured. The IN-64 / OUT-64 attempt is not a functional success. An experimental
IN-64 / OUT-512 diagnostic build likewise showed no arrows or key reports after
two reconnects and a full-system power cycle. A retained crash backtrace identified
an additional physical-detach recovery defect. That path is corrected and
regression-tested; read-only EP0 diagnostics returned configuration 1, the same
267-byte HID descriptor as on desktop, and firmware 1.0.191203. The latest bench
build also sends standard HID SET_IDLE(0) before the descriptor read; the deck
acknowledges it successfully. During the next button test, real 17-byte ID-1 input
arrived and was rejected by the strict-16 decoder. That captured layout is now
accepted and regression-tested; end-to-end actions/rendering were then requested.
The owner's subsequent confirmation establishes visible RGB/arrow images and
seven press/release pairs across keys 0, 7 and 14, with two complete image pages
after each edge. This closes the initial functional display/input smoke test,
not the full hardware acceptance gates. The compatibility baseline is `84e2851`;
the diagnostic, HID startup and decoder changes are committed as `181c54a`.
The next owner-supplied test covers all 15 key indices and one successful
peripheral reconnect: full desired-image restoration and resumed input in
generation 3. The lightbulb-on-press and image-on-release behaviour is visually
confirmed. Firmware remained unchanged.

## Evidence categories

| Category | Result |
| --- | --- |
| Implemented | Codec, scheduler, USB transport/entities/images/recovery, diagnostics, desktop probe, private builds, a source-pinned IDF descriptor hook and standalone visual/input test |
| Unit-tested | 23 Python cases including native C++ suites, raw/normalized S3 descriptors, 64-/512-byte full-report transport simulation, physical-detach recovery, EP0 requests/lifetime and captured reply consistency, pinned artwork, build-hook guards and private staging |
| Compiled | All four numbered examples with synthetic credentials; examples 01, 02 and 04 also built privately for deployment, ESP-IDF 5.5.5 / ESPHome 2026.9.0 |
| Hardware-verified | Identity/flash, Wi-Fi, encrypted API/OTA, 8 MB PSRAM initialization, EP0 replies, 17-byte input, visible image feedback, press/release coverage for all 15 key indices, and one deck reconnect with full desired-image redraw and resumed input. Detailed mapping/visual/brightness checks, repeated recovery, ESP-only restarts, electrical and HA qualification remain pending |
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

All final commands passed in the implementation session. The later owner-confirmation
update changes documentation only; no firmware rebuild or upload was performed.
An initial sanitizer link attempt failed because this
machine lacks `/usr/lib64/libasan.so.8.0.0`. Local C++ tests ran with warnings as
errors and assertions enabled, without sanitizers. `SANITIZE=1` enables ASan/UBSan
on a machine with those runtimes; the CI workflow requests them. This document
does not claim a local sanitizer run passed.

Latest synthetic builds, including the IN-64 / OUT-512 experiment:

| Example | Static RAM estimate | Application flash estimate |
| --- | ---: | ---: |
| 01 USB probe | 108,371 B / 341,760 B | 783,987 B / 8,126,464 B |
| 02 keys/brightness | 110,563 B / 341,760 B | 814,279 B / 8,126,464 B |
| 03 images/HA | 111,027 B / 341,760 B | 869,975 B / 8,126,464 B |
| 04 standalone hardware test | 110,723 B / 341,760 B | 846,139 B / 8,126,464 B |

These linker estimates exclude runtime USB/task/network allocation and are not
free-heap measurements. The checker also verifies the actual generated control
cap (8192 for driver examples), periodic-OUT FIFO bias and disabled secondary USB
console. Firmware
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
  The standalone hardware example's native RGB/arrow artwork matches the pinned
  asymmetric BMP fixture exactly.
- Native C++ compares full reports, report IDs, padding, BMP split and setup bytes.
  It tests all key mappings, short/malformed input, simultaneous keys, duplicates,
  brightness bounds, invalid keys/assets and BMP headers. The real 17-byte S3
  key fixture decodes alongside the reference's 16-byte form; A0/A1 IDs, nonzero
  reserved byte and non-binary key values are rejected without changing state.
- Scheduler tests cover change coalescing during an active image, consecutive
  pages, fairness, brightness between images, redraws, stale generations and
  disconnect during either page. Input tests cover rapid press/release order,
  held-at-connect suppression and explicit overflow resynchronization.
- The production USB transport, linked to a fake IDF, submits the full 8199-byte
  control operation and preserves all 8191 bytes across interrupt batches. Tests
  exercise discovered non-default endpoint/interface values, idle absence, wrong
  models, malformed input, short output, STALL, software deadline, retained
  buffers while cancellation is delayed, and reattachment afterward.
  Physical detach must not request root-port power-off again. Standard SET_IDLE
  and optional EP0 probes have exact setup bytes, MPS-rounded capacity, no scheduler interleaving, bounded
  capture and safe STALL/timeout/detach handling; their completions are not images.
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

The [first descriptor correction](hardware.md#compatibility-fix-and-successful-reports-2026-10-10)
produced 32 host startup completions: full reset, brightness and two blank-image
pages for every key. USB ready and zero errors/overflows were observed, but the
owner still saw the logo and no key report arrived after presses. Host completion
therefore does not establish the functional large-report gate.

The [next experiment](hardware.md#logo-retained-and-512-byte-out-experiment-2026-10-10)
preserves 512-byte OUT packet framing and uses the required periodic-OUT FIFO
bias. Example 04 was compiled and deployed over encrypted OTA; it reports the
expected IN-64 / OUT-512 layout and 32 startup completions, but the owner confirmed
no arrow patterns or button messages after reconnects and a whole-system power
cycle. Both packet-size-only attempts failed functional acceptance. A retained
`root_port_recycle` abort identified the separate detach recovery bug now covered
by the production-transport regression suite. All four examples compile with
synthetic secrets. The checker verifies both the FIFO setting and actual
compilation of the patched USBH source. Example 04 also catches an image-ID
code-generation ordering bug: a hub's image objects must exist before generating
its own press/release actions that reference those objects.

After adding HID startup and correcting the 17-byte decoder, the owner
[confirmed visible patterns and local key actions](hardware.md#first-confirmed-images-and-local-key-actions-2026-10-10).
The supplied excerpt has seven press/release pairs and 28 image-page completions
in generation 1. The current combined implementation works for that smoke test;
it does not isolate which output MPS is necessary or qualify all release gates.

The [subsequent all-key/reconnect test](hardware.md#all-keys-and-one-successful-peripheral-reconnect-2026-10-10)
covers every key index in generation 1, reinitialization and all 30 redraw pages
in generation 3, followed by further input. The owner confirms the expected
sequential redraw. This establishes one recovery without the prior abort, not
repeated recovery or ESP-only restart qualification. The first key-0 packet after
attachment is still a silent baseline; adding a display refresh timer would not
change that input policy.

Desktop descriptor collection is complete. Later S3 capture resolved the
16-versus-17-byte discrepancy: the physical key packet is 17 bytes, while the
pinned library reads only 16. See [hardware observations](hardware.md#two-way-ep0-replies-and-hid-startup-test-2026-10-10).
The desktop other-speed configuration is advertised evidence; the separate S3
fixture is a physical full-speed capture and differs as described above.
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
4. Run example 04 to display the asymmetric RGB/TL/arrow fixture on keys 0/7/14,
   then test numbered images on all 15 positions. Check mapping, both flips,
   BGR channels and both pages. Determine
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
- [ ] At least 20 peripheral unplug/replug cycles, including both image pages
  (one successful idle disconnect/reconnect recorded so far).
- [ ] 100 deliberate press/release pairs with no missing/duplicate intended actions
  under recorded test conditions; simultaneous holds and rapid clicks while redrawing.
- [ ] Overnight soak with periodic actual HA state changes.
- [ ] 100% brightness plus Wi-Fi stress on the final power/protection path.
- [ ] Record free/minimum internal heap, queue high-water/overflows and USB errors;
  demonstrate no growing resource leak or unexplained reset.
- [ ] Measure action latency and full-deck redraw duration; no performance claim yet.
- [ ] Record firmware commit, dependency pins, actual HA/deck versions and wiring revision.

Until these pass, this is a compiled development firmware, not a qualified release.
