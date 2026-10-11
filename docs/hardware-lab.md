# Physical runtime lab (P9)

## USB startup recovery — current firmware

The owner reported that the 23:05:52 runtime image still left the deck on its
logo, with unknown keys and no visible brightness response. Read-only checks
confirmed zero captured input, all 15 binary key states missing, and 124 host
report completions despite USB ready. The earlier Redraw correction fixed
applied-revision bookkeeping, **not this physical failure**. Runtime images/text
are RAM-only; no flash/NVS erase was performed.

The next controlled build changed only example 05's `usb_diagnostics` to true,
matching example 04's startup. Compiled `2026-10-11 23:43:04 +0200`, its
1,094,160-byte OTA image has SHA-256
`3bebf78a49a4cacdc1363c9cb3ed934a7f41d1cd3c242b4f2a4cdd01bfeedc35`.
Encrypted, identity-checked OTA completed in 65.07 seconds. GET_CONFIGURATION,
the 267-byte HID report descriptor and firmware feature 4 all returned exact
lengths and byte-for-byte matches to the preserved bench replies; SET_IDLE
completed with its expected eight setup bytes. A real 17-byte key report arrived,
all 15 HA binary key states became known, and HA subsequently counted four
physical light-binding actions. USB errors and input overflows remained zero in
the captures. These establish live input/control communication; they are not
display or brightness readback.

The driver previously ran only SET_IDLE when diagnostics were disabled. The fix
makes the **whole four-request bench startup unconditional on every attachment**;
`usb_diagnostics` now controls reply logging only. It preserves request order,
8191-byte report framing, IN-64/OUT-512, UART0, external unswitched VBUS, and all
HA/runtime behavior. Which individual query or timing difference mattered has
not been isolated; the full working sequence is deliberately retained.

The fixed example 05 is installed with verbose diagnostics **off**:

- Compiled `2026-10-11 23:50:23 +0200`; OTA **1,094,144 bytes**.
- SHA-256 `1fc89983e9a496e7340ac5022a19417dd2e6f476af0e9fa44e41146791d6d1c7`.
- Encrypted OTA with identity/hash checks and connection-local MSS 536 completed
  in **58.99 seconds**. No synthetic image, bootloader or partition changes.
- All seven synthetic firmware configurations compile; **72 host tests pass
  with ASan/UBSan**. The expanded production-transport regression failed against
  the previous driver and passes after the fix, including diagnostics on/off,
  both output routes, and short/STALL/timeout/detach at every startup step.
- HA reconnected and all 15 text tiles initially reported USB-applied. The quiet
  build then captured three key-4 down observations and releases, with all 15
  key states known, zero USB errors/overflows and queue high-water one. Six
  brightness reports completed during the owner's slider tests (last requested
  value 36%). Physical display/brightness confirmation remains requested; host
  completions are not readback. No cold-start, repeated-recovery or soak pass is
  inferred from this one OTA/warm-start sample.

The owner made concurrent editor changes during testing. The agent's proposed
temporary-label edit was refused **before writing** when it detected the changed
label. The final upload preserved the latest draft/applied layout at revision 16
exactly. The agent's earlier unchanged-layout Apply was a no-op, not a fresh
image-transfer test. The prior runtime and diagnostic OTA/ELF artifacts and layout
snapshots are private under `.build/backups/usb-startup-VvGnBbrQ/`; the original
example-04 rollback artifact remains unchanged. HA 18123 remains the sole
physical controller; there is no new HA instance or layout replacement.

The owner subsequently applied revision 18 with artwork on the fifth key. That
tile reports `origin_not_allowed`, while the other 14 text tiles are rendered and
USB-applied. The saved library address `http://ha:8123` is container-only, not a
reachable/provisioned ESP artwork origin. The old fifth-key tile is retained;
this failed image replacement must not be counted as an applied new image just
because its previous revision still has matching applied/rendered counters.
No artwork was removed and origin/TLS checks were not bypassed.

At handoff the owner's subsequent revision 23 reports **ready**, all 15 current
tiles are accepted/rendered/USB-applied without error, and all 15 binary key states
remain known. HA's binding count reached six: two additional physical light
actions after the final diagnostics-off upload. The revision-18 artwork error
above is historical, not the latest status; live artwork delivery remains a
separate qualification gate.

[Sanitized startup comparison and final-build capture](../tests/fixtures/s3_0060/startup_recovery_2026-10-11.json).

## Earlier Apply/redraw recovery — current HA setup

The owner confirmed that physical keys, brightness, rendered labels, the light
toggle and page switching worked before Apply. They had retargeted the original
HA on **port 18123** from the virtual deck to `192.168.10.238`. That ESPHome
connection worked, but ESP Deck still referenced the removed virtual device and
reported `device_missing`. The separate 18124 instance still controlled the real
deck. It is now stopped, with its private config/artifacts retained. **18123 is
the sole physical controller**; its ESP Deck association was repaired using the
supported Reconfigure flow.

A second, reproduced firmware bug was triggered by the outgoing **Redraw keys**
button (recorded in HA at `2026-10-11T20:46:21Z`). Redraw advanced the scheduler's
USB work revision but not the Store's recorded image revision. USB reports could
complete while `applied_revision` stayed zero indefinitely, causing
`usb_apply_timeout` and intentionally gating v2 key actions. The regression test
failed before the fix. Desired-image identity and USB-work revisions are now
separate; redraw still gates input until a fresh complete two-report image, even
when another redraw arrives during either page. Reconnect and same-pixel rebinding
are covered too. USB packet sizes, startup and power handling are unchanged.

The earlier corrected private example-05 build was installed:

- Compiled `2026-10-11 23:05:52 +0200`.
- OTA size **1,094,160 bytes**, SHA-256
  `4f5ceb4a39b10674b10a2851af0877518cb3a840a13b3031d97ecb034334d8f9`.
- Encrypted OTA, with connection-local MSS 536, completed in **59.27 seconds**
  including identity verification. The preceding firmware and both HA instances'
  registries/layouts/artwork were backed up privately under
  `.build/backups/apply-recovery-GEsdqMkL/`.
- After reboot, all 15 tiles reached USB-applied status. Repeating the actual
  Redraw command on hardware returned all 15 to ready, without errors, in
  **3.632 seconds** including HA synchronization/polling. USB/overflow counters
  remained zero in the capture. Chromium then edited key 5 to **Apply OK** and
  clicked Apply through the real editor; all 15 tiles again reported applied.
  Physical appearance and renewed key action confirmation are still requested.

[Sanitized recovery record](../tests/fixtures/s3_0060/redraw_recovery_2026-10-11.json).

The user's `Main` and `Other` image pages are unchanged as JSON data, including
artwork and bindings. `Hardware Main` / `Hardware Second` and a hardware modifier
overlay were added separately; `Hardware Main` is the temporary default. The
image pages still depend on an ESP-reachable artwork address. The saved origin
`http://ha:8123` is a container alias, and 18123 is presently loopback-bound; these
are not usable physical-ESP asset addresses. The text pages allow operation while
that network setup remains unfinished.

Use the existing account at **http://127.0.0.1:18123/esp-deck**. Reload the editor
to see the repaired association and added pages. The fifth key should show the
browser-applied **Apply OK** label. The original first-click-after-boot limitation
remains; use two deliberate presses for the initial input check.

```sh
.venv/bin/python tools/ha_bench_controls.py --instance lab status
.venv/bin/python tools/device_probe.py --host 192.168.10.238 --seconds 15
```

The controls tool now requires an explicit `--instance lab` (18123) or `bench`
(18124). `setup` deliberately replaces a demo layout; status/probe are the
appropriate read-only commands for the preserved current setup. Synthetic lab
tests/rebuilds, including direct pytest and `up --fresh`, now refuse this
retargeted instance. Standalone host and mocked HA engine tests remain safe.
The 18124 launcher also refuses to create a second controller for the same ESP
while the original 18123 HA is running with it. This prevents future automated
tests or parallel lab setup from interfering with the real device.

The sections below record the earlier, separate-18124 session for provenance.

## First runtime deployment (historical)

The owner's real ESP at `192.168.10.238` first ran example 05, compiled
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
.venv/bin/python tools/ha_bench_controls.py --instance bench setup
.venv/bin/python tools/ha_bench_controls.py --instance bench status
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
.venv/bin/python tools/ha_bench_controls.py --instance bench provision --origin DEVICE_REACHABLE_HA_ORIGIN
.venv/bin/python tools/ha_bench_controls.py --instance bench artwork
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
the new boot and the saved layout restored. The owner subsequently reported
manual ESP/deck restarts and a full power cycle while trying to recover from
Apply. These recovery attempts are not qualified warm-restart or power tests.
