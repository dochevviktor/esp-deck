# ESP Deck

ESPHome firmware for the **original 15-key Elgato Stream Deck (0FD9:0060)** on a
**Seeed XIAO ESP32-S3 Plus**. The external component reads keys, controls brightness
and sends locally rendered images over native USB. Home Assistant uses the
encrypted ESPHome API; encrypted OTA is configured.

Implemented: protocol, asynchronous USB transport, reconnect/recovery, all 15 key
entities, brightness, diagnostics, images and a state-driven HA lamp example.
Runtime foundations: validated visual patches/revisions and immutable owned image
versions retained safely through both USB pages and cancellation (P0/P1).
Local rendering (P2): aspect-preserving scaling, alpha composition, outlined
runtime labels with bundled fonts, native BMP encoding and PSRAM allocation.
Asset loading (P3): bounded HTTP(S), PNG decoding, retained background caching,
origin restrictions and TLS verification. HA controls (P4): generic visual/clear/
refresh/status API responses, boot-session diagnostic, physical key events and
HA-owned layout replay; no firmware binding to a particular HA entity.
P5 adds a private rootless HA lab and encrypted ESPHome host virtual deck.
P6 adds a locally installable [HA backend](docs/ha-integration.md) with guided
setup/presets, saved layouts, bindings, synchronization, admin APIs and repair.
P7 adds the bundled [5×3 visual editor and artwork library](docs/visual-editor.md):
PNG/JPEG upload/crop, pixel-tested previews, state rules and revocable asset delivery.
P8 adds [runtime v2](docs/runtime-v2.md): capability-aware positioning, verified
origin provisioning, eight pages/four sparse overlays and input correlated with
USB-applied tiles. v1 actions remain supported.
P9 adds a deterministic integration ZIP, local brand/licence assets, distribution
validators and archive installation/upgrade/backup/removal tests. See
[installation and release qualification](docs/release.md) for commands and the
remaining GitHub/HACS and physical gates.
The real ESP now runs example 05: [the physical lab session](docs/hardware-lab.md)
verified HA pairing, text/page USB completion and real light-binding actions.
Artwork fetching still needs a reachable route from the ESP back to the lab VM.
Compiled: all seven configurations on ESPHome 2026.9.0 / ESP-IDF 5.5.5, plus the
test-only ESPHome host executable.
Unit-tested: upstream byte fixtures, scheduler/input behavior, simulated USB
transfers, schema validation and captured desktop descriptors; 70 Python cases
including nine native executables and HA helper/replay templates, plus five
frontend tests (including all twenty renderer snapshots).
HA-tested: 62 real-HA engine tests with mocked native actions and 28 real
HA 2026.10.1/native-API/browser scenarios, including a clean lab startup.
Hardware-verified: desktop descriptors, ESP chip/flash identity, 8 MB PSRAM
initialization, Wi-Fi, encrypted API and encrypted OTA. The S3 enumerates the
deck at full speed. With the IN-64 / OUT-512 descriptor workaround, HID SET_IDLE
startup and corrected 17-byte input decoder, the owner now confirms visible
RGB/arrow images, lightbulbs while pressed and arrow images after release. Logs
cover every key 0..14 and one successful peripheral reconnect: the saved desired
images redraw across all 15 keys and key events resume in generation 3. Each
edge completes both 8191-byte image pages. Detailed mapping/visual checks,
brightness response, repeated reconnects, ESP-only restarts, electrical
qualification and full HA acceptance remain pending. See
[validation and remaining gates](docs/testing.md).

The original [handover](STREAM_DECK_ESPHOME_CODEX_HANDOVER.md) is preserved.
Start with the [hardware checklist](docs/hardware.md) before connecting anything.

The [Home Assistant runtime control plan](docs/implementation-plan.md) has P0–P8
software implemented and tested: [the contract](docs/runtime-visuals.md), owned
images, [rendering](docs/rendering.md), and [URL loading/cache](docs/asset-loading.md).
Example 05 adds [HA runtime controls and layout replay](docs/home-assistant.md).
Example 03 remains a fixed-entity demo; example 04 is preserved for private rollback.
P5's [isolated Podman HA lab](docs/ha-lab.md), P6's
[integration backend](docs/ha-integration.md) and P7's
[editor and 72×72 artwork pipeline](docs/visual-editor.md) run independently of
physical hardware. P8's [capabilities, provisioning and bounded pages/layers](docs/runtime-v2.md)
are also software-tested. P9's [release packaging and lifecycle checks](docs/release.md)
and local distribution metadata checks pass; physical qualification and online HACS distribution remain
open, and P3's
actual ESP asset-reachability check is still pending. See the
[HA/HACS architecture decision](docs/decisions/home-assistant-ux.md).
No firmware was uploaded for P0–P8. The local host suite also passes with
ASan/UBSan after installing the missing runtime and guarding the empty-buffer
copy in the P8 test fetcher. Both `libasan` and `libubsan` are now available;
see [the sanitizer follow-up](docs/testing.md).

## Develop and test without a board

From this repository, with Python 3.14, Git, C99 and C++17 compilers:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/generate_render_fonts.py --check
.venv/bin/python tools/generate_render_fixtures.py --check
.venv/bin/python tools/generate_png_fixtures.py --check
.venv/bin/python tools/check_firmware.py
.venv/bin/python tools/check_firmware.py --compile
npm ci --prefix frontend --ignore-scripts --no-audit --no-fund
npm run check --prefix frontend
npm test --prefix frontend
```

The checker defaults to isolated copies with synthetic Wi-Fi/API secrets. It
never reads the reference project's credentials or modifies a local
`secrets.yaml`. Validation builds/logs stay under `.build/firmware/`, ignored by
Git. **These synthetic builds are for validation; never flash them.**

For an explicitly requested device upload, `--deploy --example NAME` uses local
`examples/secrets.yaml` and puts the build in `.build/deploy/NAME/`. This directory
is private (mode 0700), its artifacts may contain credentials, and raw deployment
compiler output is kept in its private log. Both modes check USB console ownership
in the generated SDK configuration. `--deploy` requires `--compile` and one example.

The direct pins are in `requirements-dev.txt`; the resolved Python environment
is in `requirements-lock.txt`. Toolchain/source details are in
[versions](docs/versions.md). With both sanitizer runtimes (`libasan` and
`libubsan`) installed, run:

```sh
SANITIZE=1 UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 .venv/bin/python -m unittest discover -s tests -v
```

`SANITIZE=1` enables ASan/UBSan instrumentation, also requested by CI.
`halt_on_error=1` makes UBSan findings fail the process; without it, a diagnostic
can appear while unittest still reports success.

Test the real HA interface without a board, with rootless Podman:

```sh
.venv/bin/python tools/ha_lab.py up
.venv/bin/python tools/ha_lab.py test-engine
.venv/bin/python tools/ha_lab.py test
.venv/bin/python tools/ha_lab.py status
.venv/bin/python tools/ha_lab.py down
```

The lab UI is `http://127.0.0.1:18123`; synthetic credentials, logs and binaries
stay in private `.build/ha-lab/`. `up --fresh` archives previous lab data and
starts with new accounts. [Lab instructions and test boundaries](docs/ha-lab.md).

## Configure your device

```sh
cp -n examples/secrets.example.yaml examples/secrets.yaml
chmod 600 examples/secrets.yaml
```

Edit that file with your 2.4 GHz Wi-Fi credentials and a unique base64 32-byte API
key; the template contains the generation command. The same key protects native
API and encrypted OTA. No real credentials are committed.

| Example | Purpose |
| --- | --- |
| `examples/01_usb_probe.yaml` | Core USB enumeration only; no images or key decoding |
| `examples/02_keys_brightness.yaml` | All keys, brightness and diagnostics; blanks the displays |
| `examples/03_images_home_assistant.yaml` | Key 0 toggles `light.example_lamp`; actual HA feedback selects ON/OFF/? |
| `examples/04_hardware_test.yaml` | Standalone RGB/arrow patterns on keys 0/7/14; received presses show ON, releases restore the pattern; no HA actions |
| `examples/05_home_assistant_runtime.yaml` | Installed runtime: HA-controlled images/text/styles, v2 pages/input, status and replay; initial real text/input checks passed, artwork route pending |
| `examples/renderer_probe.yaml` | P2 local renderer: three font sizes, outlined text/artwork and truncation on keys 0/1/2/7/14; no runtime API or downloads; not hardware-tested |
| `examples/asset_loader_probe.yaml` | P3 PNG URL + label on key 0, then a label-only cache update; configure a real allowed origin/URL; HTTPS waits for HA time; not deployed/hardware-tested |

In example 04, the other keys intentionally start blank. Releasing any key sets
its desired image to the arrow pattern, so testing every key leaves all keys
with arrows. A deck-only reconnect redraws those saved desired images one key at
a time. An ESP restart instead reapplies the boot layout. Display updates are
change-driven, with a full redraw on attachment; periodic display polling is not
needed for this behaviour.

For runtime bindings and visuals use [example 05's HA setup guide](docs/home-assistant.md).
The [P6/P7 integration](docs/ha-integration.md) provides guided setup and a
[visual editor](docs/visual-editor.md) as an alternative to the manual P4 helpers;
its handoff stops
selected competing automations. Install its directory in HA's custom_components
and select the existing ESPHome deck. It runs with the browser closed.
The integration (or the independent P4 scripts) owns the layout and queries
revisions before each update; firmware
starts blank and preserves the last good tiles offline. Labels reuse cached
artwork. The sample HA automations bind press/release events and update key 0
from actual lamp state. Rebinding or changing supported visuals within the
configured asset origins requires no OTA. Runtime display/input and HA restart
tests on the device remain pending.

For the older static example 03, change `light_entity` to your entity. Add the ESPHome integration
at `streamdeck-original.local`, port 6053, with your API key, and allow the device
to perform HA actions in the integration options. A logging API client alone
does not establish valid lamp state. Do not add a second toggle automation on the
same key. [Protocol and HA behavior](docs/protocol.md) documents synchronization,
outages, requested brightness and the intentionally conservative freshness policy.

```sh
.venv/bin/esphome config examples/03_images_home_assistant.yaml
.venv/bin/python tools/check_firmware.py --compile --example 03_images_home_assistant --deploy
```

All examples use the same device name and represent alternative firmware. The
probe's stock `usb_host` claimant must not coexist with the external driver.
GPIO19/20 belong to native USB. UART0 is used for runtime logging; PSRAM is set
to octal 80 MHz and must be confirmed at boot. Flash is 16 MB using DIO mode.

## Flash, OTA and recovery when hardware is available

With the deck attached to a Linux PC, collect descriptors without changing its
images or brightness:

```sh
.venv/bin/python tools/probe_desktop.py
# Optional: press/release keys while recording complete interrupt reports.
.venv/bin/python tools/probe_desktop.py --seconds 30
```

The probe selects exactly one `0FD9:0060`, omits serial numbers, keeps the kernel
driver attached, and reports permission/query failures explicitly. See the
[desktop observations](docs/hardware.md#desktop-observations-2026-10-10) for the
captured configurations; the later S3 session established 17-byte key input.

First use the probe after the [unpowered wiring checks](docs/hardware.md).
Before plugging the XIAO USB-C into a computer, **physically disconnect the
power-inlet feed and remove the Stream Deck adapter**. The PC must be the only
power/data source in this flashing configuration.

Replace `/dev/ttyACM0` below with the actual board's serial path (prefer its stable
`/dev/serial/by-id/` path). The ROM upload path below succeeded on 2026-10-10;
the full original flash was backed up and verified before writing.

```sh
.venv/bin/esptool --port /dev/ttyACM0 flash-id
# Optional first-flash backup: use a new filename; firmware contains credentials.
umask 077
mkdir -p .build/backups
.venv/bin/esptool --chip esp32s3 --port /dev/ttyACM0 --no-stub read-flash 0 0x1000000 .build/backups/original-flash.bin
.venv/bin/python tools/check_firmware.py --compile --example 01_usb_probe --deploy
.venv/bin/esptool --chip esp32s3 --port /dev/ttyACM0 --no-stub --after no-reset write-flash --no-progress 0 .build/deploy/01_usb_probe/build/firmware.factory.bin
```

Remove the PC cable before returning to host wiring. Then connect the deck via
the passive C-male/A-female adapter and power the inlet from the qualified single
5 V source. The command above leaves the ESP in the ROM bootloader until that
power cycle; Wi-Fi starts when it boots from flash. Look for
`streamdeck-original` in the router's DHCP leases, or resolve
`streamdeck-original.local` on the same LAN. Native API logs use TCP 6053 and the
local encryption key. The enumeration probe
includes OTA so the next driver can be installed over the network.

Use UART0 through a separate **3.3 V logic** adapter for bench logs:
adapter RX to XIAO D6/GPIO43/TX and GND to GND; leave its power pin disconnected.
Optional adapter TX goes to D7/GPIO44/RX. Native USB runtime logging is unavailable
while that controller is hosting the Stream Deck.

After Wi-Fi works, OTA and logs use the network:

```sh
.venv/bin/python tools/check_firmware.py --compile --example 02_keys_brightness --deploy
.venv/bin/esphome upload examples/02_keys_brightness.yaml --device streamdeck-original.local --file .build/deploy/02_keys_brightness/build/firmware.ota.bin
.venv/bin/esphome logs examples/02_keys_brightness.yaml --device streamdeck-original.local
# Standalone visual/input diagnosis before enabling HA actions.
.venv/bin/python tools/check_firmware.py --compile --example 04_hardware_test --deploy
.venv/bin/esphome upload examples/04_hardware_test.yaml --device streamdeck-original.local --file .build/deploy/04_hardware_test/build/firmware.ota.bin
# Move to the HA example after qualifying the full large-report path.
.venv/bin/python tools/check_firmware.py --compile --example 03_images_home_assistant --deploy
.venv/bin/esphome upload examples/03_images_home_assistant.yaml --device streamdeck-original.local --file .build/deploy/03_images_home_assistant/build/firmware.ota.bin
```

If native USB recovery is needed, return to the PC-only flashing configuration,
hold BOOT, press/release RESET, release BOOT, and retry upload. Never burn eFuses
for a logging conflict. USB/CPU/OTA resets do not remove the deck's external VBUS;
a persistent fault may require physically unplugging the peripheral. Wi-Fi/API
absence does not cause periodic reboots, and an absent deck does not block OTA.

## Add artwork

```sh
.venv/bin/python tools/convert_assets.py my-icon.png assets/native/my-icon.bmp --background '#101820' --fit contain
.venv/bin/python tools/generate_reference_fixtures.py --check
```

Conversion flattens alpha onto the explicit background, preserves aspect ratio,
and centers the result in 72×72 pixels. `contain` letterboxes; `crop` fills and
crops centrally. The pinned upstream helper applies both flips and BMP encoding.
Each conversion writes the native BMP plus a SHA-256/length manifest. Declare it
under the hub's `images` list as in example 03; code generation embeds the bytes
in flash. Do not use an arbitrary BMP as a native image or flip it again at runtime.

See the [transport decision](docs/decisions/usb-transport.md) for the 8191-byte
report implementation, internal DMA buffers and cancellation lifetime rules.
