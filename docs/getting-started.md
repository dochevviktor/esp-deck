# Firmware setup and recovery

Use the original 15-key Stream Deck (`0FD9:0060`) with the Seeed
XIAO ESP32-S3 Plus. Other Stream Deck models and boards are outside this project's
scope. The supported runtime is
[`05_home_assistant_runtime.yaml`](../examples/05_home_assistant_runtime.yaml);
Home Assistant owns its bindings and visuals.

## Prepare the environment

Use Python 3.14 and the pinned dependencies:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
cp -n examples/secrets.example.yaml examples/secrets.yaml
chmod 600 examples/secrets.yaml
```

Edit `examples/secrets.yaml` with your 2.4 GHz Wi-Fi credentials and a unique
base64 32-byte API key. The template includes the key-generation command; the key
protects both the native API and encrypted OTA. Keep this file and build artifacts
private. Existing secrets must be preserved.

[Example 05](../examples/05_home_assistant_runtime.yaml) supports direct delivery
of library artwork over the encrypted API. That path needs no HA artwork address.
External image URLs still need a reachable, permitted origin; see
[artwork delivery](artwork-upload.md) and [URL loading](asset-loading.md).

## Choose a configuration

All examples use the same device name and are alternative firmware images.

| Example | Purpose |
| --- | --- |
| `01_usb_probe` | USB enumeration only |
| `02_keys_brightness` | All 15 key entities, brightness and diagnostics; blank displays |
| `03_images_home_assistant` | Static artwork demo bound to `light.example_lamp` |
| `04_hardware_test` | Standalone RGB/arrow patterns and local press/release feedback |
| `05_home_assistant_runtime` | HA-managed artwork, labels, bindings, pages and replay |
| `renderer_probe` | Local text/artwork renderer checks |
| `asset_loader_probe` | PNG URL loading and cached label updates |

Examples live in [`examples/`](../examples/). The two rendering/loading probes
have software validation; their separate physical acceptance remains pending.
The probe's stock `usb_host` claimant must not coexist with the external driver.

Example 04 initially draws on keys 0, 7 and 14. Presses show a lightbulb; releases
restore arrows. A deck-only reconnect restores the saved desired images, while
an ESP restart reapplies the boot layout.

For example 03, replace `light_entity` with your entity and allow the ESPHome
device to perform HA actions. Avoid a second toggle automation on the same key.
Example 05 instead uses HA-owned bindings through the
[ESP Deck integration](ha-integration.md).

## Build for your device

First review the [hardware checklist](hardware.md). Native USB belongs to the
host, runtime logs use UART0, and the external 5 V rail is unswitched. Software
resets do not remove peripheral power.

To prepare runtime firmware with your local secrets:

```sh
.venv/bin/python tools/check_firmware.py --compile --example 05_home_assistant_runtime --deploy
```

This builds privately under `.build/deploy/05_home_assistant_runtime/`; it does
not flash the device. The directory is mode 0700 and contains credentials in
artifacts and potentially compiler logs. Never commit it.

Builds made without `--deploy` use synthetic secrets under `.build/firmware/`.
**Never upload those validation images.** See [development](development.md) for
hardware-independent checks.

## First USB flash

Before connecting the XIAO to a computer, **physically disconnect the external
power-inlet feed and remove the Stream Deck adapter**. The PC must be the only
power/data source during USB flashing.

Replace `/dev/ttyACM0` with the actual board's serial path, preferably its stable
`/dev/serial/by-id/` path. Check the board and optionally back up its existing
16 MB flash to a new private directory:

```sh
.venv/bin/esptool --port /dev/ttyACM0 flash-id
umask 077
mkdir -p .build/backups
deck_backup_dir=$(mktemp -d .build/backups/first-flash-XXXXXX)
.venv/bin/esptool --chip esp32s3 --port /dev/ttyACM0 --no-stub read-flash 0 0x1000000 "$deck_backup_dir/flash.bin"
```

Backups may contain credentials. Keep them private and verify a successful read
before relying on them. The ROM path (`--no-stub`) was used successfully for this
board; [the first upload record](hardware.md#first-firmware-upload-2026-10-10)
contains the bench details.

For initial enumeration, build and flash the probe:

```sh
.venv/bin/python tools/check_firmware.py --compile --example 01_usb_probe --deploy
.venv/bin/esptool --chip esp32s3 --port /dev/ttyACM0 --no-stub --after no-reset write-flash --no-progress 0 .build/deploy/01_usb_probe/build/firmware.factory.bin
```

The command leaves the ESP in its ROM bootloader. Remove the PC cable, connect the
deck through a passive data-capable USB-C male to USB-A female adapter, and power
the inlet from the qualified single 5 V source. Confirm enumeration before
progressing to runtime firmware. Look for `streamdeck-original` in DHCP leases
or resolve `streamdeck-original.local`.

## OTA, logs and recovery

Once Wi-Fi works, build the chosen example privately and upload its OTA image:

```sh
.venv/bin/python tools/check_firmware.py --compile --example 05_home_assistant_runtime --deploy
.venv/bin/esphome upload examples/05_home_assistant_runtime.yaml --device streamdeck-original.local --file .build/deploy/05_home_assistant_runtime/build/firmware.ota.bin
.venv/bin/esphome logs examples/05_home_assistant_runtime.yaml --device streamdeck-original.local
```

Confirm that the address resolves to your intended ESP before uploading. The
[physical lab guide](hardware-lab.md) also documents the identity/hash-checked
encrypted uploader used for the existing bench device.

For UART0 logs, use a separate **3.3 V logic-level** adapter: its RX connects to
XIAO D6/GPIO43/TX, with common GND. Optional adapter TX connects to
D7/GPIO44/RX. Leave the adapter's power pin disconnected. GPIO19/20 are reserved
for native USB. Examples configure 16 MB flash in DIO mode and 8 MB octal PSRAM
at 80 MHz; confirm memory initialization at boot.

For USB recovery, return to the PC-only flashing configuration, hold BOOT,
press/release RESET, release BOOT, and retry. Never burn eFuses to resolve a
logging conflict. An ESP reset, OTA reboot or USB controller reset does not
switch VBUS; a persistent peripheral fault may require physically unplugging it.

After runtime firmware is installed, follow the
[Home Assistant integration setup](ha-integration.md#installation-and-guided-setup).
The firmware starts blank, retains the last good tiles while offline, and
receives the saved layout from HA after reconnecting.

## Static artwork and desktop diagnostics

For firmware-resident images in example 03:

```sh
.venv/bin/python tools/convert_assets.py my-icon.png assets/native/my-icon.bmp --background '#101820' --fit contain
.venv/bin/python tools/generate_reference_fixtures.py --check
```

Conversion composites transparency, preserves aspect ratio and produces the
72×72 native BMP. `contain` letterboxes; `crop` fills and centrally crops.
Declare the generated image under the hub's `images` list. Do not flip it again
or substitute an arbitrary BMP. Everyday runtime artwork uses the
[HA editor](visual-editor.md) instead.

With the deck attached directly to a Linux PC, the read-only probe captures its
descriptors without changing artwork or brightness:

```sh
.venv/bin/python tools/probe_desktop.py
.venv/bin/python tools/probe_desktop.py --seconds 30
```

The optional timed capture records press/release reports. The probe requires
exactly one `0FD9:0060`, omits serial numbers and keeps the kernel driver attached.
