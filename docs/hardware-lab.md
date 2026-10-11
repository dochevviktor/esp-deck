# Physical runtime lab (P9)

The owner's real ESP at `192.168.10.238` now runs example 05, compiled
`2026-10-11 22:23:49 +0200`, with the P9 HTTP probe-buffer fix. Its encrypted OTA
image is **1,094,096 bytes**, SHA-256
`ff080cfce4abc4f932d8a127dbb169245c95b9926618108efbc850973cda0d0c`.
The image was built with local secrets, not synthetic validation credentials.
The original working example-04 OTA/factory images and ELF are preserved privately
in `.build/backups/pre-runtime-ZSSlrBm3/`. Its OTA hash still matches the recorded
`69854221b91d08647a7f64e0fb6d35535896a085dfdf0aa763ca9c286e88ad12` baseline.
The [sanitized session record](../tests/fixtures/s3_0060/runtime_acceptance_2026-10-11.json)
keeps artifact identities, observations and open gates without device credentials
or MAC/serial values.

## Isolation and current network boundary

`tools/ha_bench.py` manages a **separate** HA 2026.10.1 instance with fresh lab
credentials under ignored, private `.build/ha-bench/`. The automated virtual-deck
lab remains on `127.0.0.1:18123`. They must not share an ESPHome entry: both real
and virtual nodes are named `streamdeck-original` and would collide on native
action names. The hardware instance contains only synthetic light/scene entities,
the real encrypted ESPHome connection and the managed ESP Deck integration.
It has no P4 manual replay/key automations and no injected physical input.

The hardware UI is available inside the VM at `http://127.0.0.1:18124/esp-deck`
or `http://192.168.122.72:18124/esp-deck`. Username/password are in private
`.build/ha-bench/credentials.json`. Only loopback and the selected VM interface
are published; there is no wildcard bind or Internet exposure. Container mounts,
network and teardown are separately named and ownership-checked. The ESP key is
read only for pairing and stored by HA in that private instance.

**Artwork is not verified yet.** This VM is behind gateway `192.168.122.1`, while
the ESP is on `192.168.10.0/24`. HA can initiate its encrypted connection to the
ESP, so text, pages and bindings work. The ESP's probe fetch of
`http://192.168.122.72:18124` fails. A LAN-accessible host port forward to the VM's
port 18124, or suitable bridging/routing, is needed before claiming artwork
acceptance. The chosen LAN address must replace HA's internal artwork URL and be
verified from the ESP. The failed probe preserved the compiled origin allowlist;
neither TLS verification nor origin filtering was disabled. HTTP here is for
non-sensitive test artwork; actual HTTPS/clock/certificate behavior is unqualified.

The owner explicitly requested the firmware update. Text/input testing proceeded
over the working native API while the independent ESP-to-HA artwork route remains
pending. No successful live PNG fetch, origin persistence or image-cache claim is
inferred from that partial network readiness.

## Commands

To create/reuse the current hardware instance:

```sh
.venv/bin/python tools/ha_bench.py up --bind 192.168.122.72 \
  --asset-origin http://192.168.122.72:18124 --device 192.168.10.238
.venv/bin/python tools/ha_bench.py pair
.venv/bin/python tools/ha_bench_controls.py setup
.venv/bin/python tools/ha_bench_controls.py status
.venv/bin/python tools/device_probe.py --host 192.168.10.238 --seconds 30
```

`setup` deliberately replaces the hardware lab's saved layout with the test layout
below. It selects the single paired compatible device through the real setup flow;
all action bindings target synthetic entities. `status` and `device_probe` are
read-only. Raw capture logs stay private; probe output omits MAC/serial values,
credentials and artwork URLs. A SHA-256 device fingerprint is used for OTA identity
checks, without publishing the underlying identifier.

After establishing the LAN route, use `down` then `up` with the reachable address
as `--asset-origin` (and the VM's actual interface as `--bind`). Existing private
accounts, pairing, layouts and artwork are retained. Then:

```sh
.venv/bin/python tools/ha_bench_controls.py provision
.venv/bin/python tools/ha_bench_controls.py artwork
```

Provisioning must report success before the artwork command can be accepted as a
fetch test. `artwork` uploads the asymmetric test PNG to the HA library and applies
image-only and image-plus-label tiles to keys 4, 7 and 14. It stores only artwork
hashes in the layout. Use the editor to relabel later and compare physical loader
download/cache counters in the private probe logs.

Stop only this physical test HA with:

```sh
.venv/bin/python tools/ha_bench.py down
```

The private configuration and paired device are retained on disk; the ESP keeps
its last valid visuals. The synthetic regression lab is unaffected.

## OTA observation and repeatable upload

Two standard encrypted OTA attempts failed before a complete image transfer.
The ESP logged `Timeout reading 3 bytes`; Linux TCP counters showed repeated
retransmission of bulk data, with only handshake bytes acknowledged. The working
bench firmware stayed running with USB ready and no USB/input-overflow errors.
This is evidence of a network-transfer problem, not a proven root cause in the
USB driver or the power path. The precise VM/NAT/Wi-Fi cause remains unisolated.

Setting **TCP MSS 536 for the upload connection only** allowed the unchanged
first runtime image to upload successfully: ESPHome reported 57.85 seconds total.
The follow-up probe fix also uploaded successfully with that setting (58.64 seconds
including identity preflight). Encryption remained required, plaintext fallback
was disabled, and no dependency source, system route, USB packet size, bootloader,
flash partition, UART or VBUS control was changed.

Future explicitly requested uploads can use:

```sh
.venv/bin/python tools/check_firmware.py --compile --deploy --example 05_home_assistant_runtime
sha256sum .build/deploy/05_home_assistant_runtime/build/firmware.ota.bin
.venv/bin/python tools/device_probe.py --host 192.168.10.238 --seconds 5
# Supply the actual image hash and device fingerprint printed above:
.venv/bin/python tools/upload_firmware.py --host 192.168.10.238 \
  --example 05_home_assistant_runtime --sha256 IMAGE_SHA256 \
  --identity-sha256 DEVICE_FINGERPRINT --tcp-mss 536
```

The uploader accepts only named `.build/deploy/` application images, checks the
expected hash and encrypted API identity before sending, rejects symlinks, and
retains a private upload log. It cannot select a `.build/firmware/` validation
image or update the bootloader. Omit `--tcp-mss` on a network path that works with
normal segment sizes; this is a scoped workaround, not a firmware protocol change.

## What the first session establishes

- The physical identity matched the bench record before deployment. Both runtime
  uploads completed, and the latest compilation time was confirmed afterward.
- HA discovered **40 entities and eight native actions**, negotiated protocol v2,
  and restored all **15 USB-applied tiles** after the second OTA reboot.
- The first text/page layout reached applied status in **1.839 seconds**.
  Subsequent HA-driven switches to the second page and back completed at the
  status boundary in **0.307 / 0.306 seconds**. These include tool/API polling;
  they are not physical display readback or contact latency measurements.
- The real correlated input channel dispatched **12 light bindings** at the first
  checkpoint, later reaching **21**, in the synthetic HA instance. A 45-second
  native API capture also recorded two press/release pairs for key 1 (page
  navigation). No input was injected
  by a simulator or a production debug action. This is a short observed count,
  not the 100-pair or all-key reliability qualification.
- Sampled USB errors and input overflows remained **zero**; input high-water
  reached **1**. A post-test sample had **220,184 B internal free heap** and
  **181,032 B minimum internal heap**. The bounded graphics allocator reported
  **344,544 B used / 438,324 B peak** throughout the final 45-second capture.
  PSRAM was available.
  These are short observations, not a leak/soak qualification.

Test layout: key 0 toggles the lab light and displays actual ON/OFF state; key 1
switches page; key 2 holds a Shift overlay affecting key 3. The remaining keys
show numbers in three font sizes, with positioned text on key 3 and HA automation
events for unbound test keys. The first-input/first-click limitation remains;
an already-held initial key is not turned into a fabricated press.

The first physical provisioning request exposed a real integration gap:
`OriginProvisioner` uses a 32 KiB buffer but both production HTTP admission paths
required exactly 128 KiB. The fix accepts any nonzero capacity up to the existing
128 KiB ceiling and enforces the supplied capacity throughout the transfer.
Native tests now execute `HttpFetcher::start`, the actual worker and HTTP transfer
together with a deterministic FreeRTOS test double, covering task allocation,
reuse, cancellation, exact 32 KiB, overlong declared/streaming bodies and guard
bytes. On the corrected ESP the probe is admitted and completes with a fetch
failure for the VM endpoint, rather than being rejected before starting.

Owner confirmation of displayed text/appearance, successful real artwork fetching,
cache reuse, persisted origins, detailed press/page/modifier behavior, HTTPS,
repeated recovery, electrical measurements and soak remain open in
[hardware.md](hardware.md) and [testing.md](testing.md).

Later in the session, additional ESP boot-session changes and a temporary USB
disconnect were observed without an agent-issued restart or upload. The deck
subsequently returned to USB/backend ready, with zero USB/overflow counters in
the new boot and the saved layout restored. The owner has been asked whether
these were deliberate physical tests. Their cause is **not established**; do not
count them as qualified warm restarts or claim there were no unexplained resets.
