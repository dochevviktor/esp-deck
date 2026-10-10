# ESP Deck

ESPHome firmware for the **original 15-key Elgato Stream Deck (0FD9:0060)** on a
**Seeed XIAO ESP32-S3 Plus**. The external component reads keys, controls brightness
and sends firmware-resident BMP images over native USB. Home Assistant uses the
encrypted ESPHome API; encrypted OTA is configured.

Implemented: protocol, asynchronous USB transport, reconnect/recovery, all 15 key
entities, brightness, diagnostics, images and a state-driven HA lamp example.
Compiled: all three examples on ESPHome 2026.9.0 / ESP-IDF 5.5.5.
Unit-tested: upstream byte fixtures, scheduler/input behavior, simulated USB
transfers, schema validation and captured desktop descriptors.
Hardware-verified: desktop descriptors, ESP chip/flash identity, 8 MB PSRAM
initialization, Wi-Fi, encrypted API and encrypted OTA. The S3 enumerates the
deck at full speed. A targeted host-side correction handles its incorrect
512-byte endpoint descriptors; the driver now initializes and completes all 32
startup reports with zero reported USB errors. Physical key/visual image checks,
electrical qualification and HA acceptance remain pending. See
[validation and remaining gates](docs/testing.md).

The original [handover](STREAM_DECK_ESPHOME_CODEX_HANDOVER.md) is preserved.
Start with the [hardware checklist](docs/hardware.md) before connecting anything.

## Develop and test without a board

From this repository, with Python 3.14, Git and a C++17 compiler:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/check_firmware.py
.venv/bin/python tools/check_firmware.py --compile
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
[versions](docs/versions.md). On systems with the sanitizer runtime installed,
prefix the test command with `SANITIZE=1` to enable ASan/UBSan. CI does this.

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

For the HA example change `light_entity` to your entity. Add the ESPHome integration
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
captured full-speed configuration and unresolved input-report length.

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
