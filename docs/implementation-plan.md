# Home Assistant runtime control implementation plan

Approved direction as of 2026-10-10: make ESP Deck a generic input and display
device. Home Assistant owns key bindings, automations and visual configuration;
the ESP32 composes images and text locally and handles USB. Once this capability
is installed, changing a binding, image or supported text/style must not require
another firmware build or upload.

Status, 2026-10-11: P0/P1 implemented and unit-tested (28 Python cases including
native C++ suites); all four existing examples compile with synthetic secrets.
The [runtime contract](runtime-visuals.md) fixes payload/presence rules, limits,
revisions, status and lifecycle. Owned images now survive replacement and delayed
USB cancellation. P2–P5 remain pending: runtime rendering, downloads and HA API
actions are not yet exposed. No new firmware was deployed or hardware-verified;
the existing static-image bench firmware remains installed.

## Resume in a fresh chat

1. Read [AGENTS.md](../AGENTS.md), this plan, the original
   [handover](../STREAM_DECK_ESPHOME_CODEX_HANDOVER.md), the
   [USB decision](decisions/usb-transport.md), and current
   [hardware evidence](hardware.md) and [test status](testing.md).
2. Inspect the worktree and current sources; preserve local edits and secrets.
3. Continue with P2 and [the finalized contract](runtime-visuals.md): add the
   bounded canvas/font/native-BMP renderer and deterministic fixtures. Use
   `ImageRef` and `visual::Store` from P0/P1 at the scheduler boundary. Add the
   PSRAM allocator adapter; do not attach a downloader until rendering is tested.
4. Keep example 04 as the known-working bench configuration. Add a separate
   generic HA example; do not begin by choosing a light entity to hardcode into
   the ESP firmware or repeating USB packet-size experiments.

This plan supersedes the original handover's deferral of runtime text rendering
and network-loaded artwork for this next stage. The fixed model/board, ESPHome
native API, protocol independence, power rules and hardware gates still apply.
The original handover stays intact as the historical specification.

## Working baseline to preserve

The repository baseline when this plan was written is `866bff7`; the implemented
USB startup/decoder changes are in `181c54a`. Version pins are in
[versions.md](versions.md): ESPHome 2026.9.0, ESP-IDF 5.5.5, Python Stream Deck
0.10.0 at `43666bb454186d1d7adeba9402f689449705d0b9`, and Pillow 12.3.0.

| Evidence category | Starting baseline (before P0/P1) |
| --- | --- |
| Implemented | Original-device codec, scheduler, 15 key entities, brightness, static artwork, diagnostics, reconnect handling and encrypted API/OTA |
| Compiled | All four existing examples with synthetic secrets |
| Unit-tested | 23 Python cases, including native C++ protocol/scheduler and production-transport simulations |
| Hardware-verified | Image feedback, press/release coverage for all 15 key indices, one peripheral reconnect with full redraw and resumed input, Wi-Fi/API/OTA and 8 MB PSRAM initialization |

The installed firmware is `04_hardware_test`, compiled
`2026-10-10 21:59:20 +0200`. Its OTA image is 846,240 bytes with SHA-256
`69854221b91d08647a7f64e0fb6d35535896a085dfdf0aa763ca9c286e88ad12`.
The owner reconfirmed `192.168.10.238` on 2026-10-11 and two ICMP probes succeeded;
confirm API identity again before a later deployment. The ESP and deck use the
externally powered host topology, not PC USB flashing wiring.

Preserve these established transport details:

- Target only Original `0FD9:0060` on XIAO ESP32-S3 Plus. Native USB is the host;
  runtime logs use UART0. External VBUS is unswitched; no invented power GPIO.
- Keep the source-pinned, build-local IDF descriptor hook, IN MPS 64 / OUT MPS 512,
  periodic-OUT FIFO allocation and standard HID SET_IDLE startup. Whether OUT 64
  would work with the corrected startup has not been isolated and is not this task.
- Key reports are observed as ID 1, 15 binary states and one zero trailing byte,
  17 bytes total. Preserve the captured fixture and non-key-ID rejection.
- The native image is a 15,606-byte 72 × 72 RGB24 BMP. Each image uses two complete
  8191-byte output reports. Keep the existing framing, key mapping and tests.
- USB transfer allocations remain in DMA-compatible internal memory. PSRAM is
  for runtime graphics/cache data, copied through the existing USB buffers.
- Physical detach must not repeat root-port power-off after DEV_GONE; that caused
  the prior IDF abort. Retire callbacks before releasing transfer-owned resources.

## Ownership and scope

| Home Assistant owns | ESP32 owns |
| --- | --- |
| Key bindings, conditions, scripts, scenes and complex triggering | Physical key state and real press/release publication |
| Image selection, label text and supported style values | Fetching/decoding, scaling, alpha composition and outlined text |
| Visual updates based on actual entity state | Native BMP encoding, serialized USB output and desired-image restoration |
| Authoritative layout and replay after restart | Bounded local caches and last successfully rendered tiles |

The existing key entities in `examples/packages/deck.yaml` already support
HA-side automation bindings. Use binary-sensor transitions or deliberately added
event entities; a Home Assistant `button` entity is an outbound command, not a
physical-key input. The new configuration must not also run the firmware-side
`light.toggle` from example 03. Retain that example as a static demo, not the
recommended rebinding workflow.

The first runtime version includes URL-loaded artwork with caching, optional
runtime labels with black outlines, image-only/text-only/combined tiles, and
generic encrypted native API actions. Start with PNG for icons; add JPEG in this
stage only with explicit decoder limits and tests. Bundle a small licensed font
set with defined sizes and glyph coverage. Label changes use those fonts at
runtime; arbitrary font uploads or unlimited character coverage are not promised.

A drag-and-drop HA layout editor, direct file-upload UI, chunked image uploads,
flash-persisted layouts, pages and animations are follow-on work. Other Stream
Deck models, another host stack, MQTT and a permanent desktop bridge remain out
of scope. A normal HA automation/script interface is sufficient for this stage.

## Runtime contract

P0 selected a fixed native API signature with presence flags and an HA patch
helper. The [complete contract](runtime-visuals.md) is authoritative. The following
shows the helper payload shape; it is not a currently available firmware action:

```yaml
key: 0
session: "0123456789abcdef"
revision: 1
patch:
  image_url: "http://homeassistant.local:8123/local/streamdeck/desk.png"
  image_revision: "desk-v1"
  text: "Desk"
  text_color: "#FFFFFF"
  outline_color: "#000000"
```

Required semantics:

- Key is always bounded to 0..14. Optional fields preserve their previous values;
  selected empty URL/text values explicitly clear artwork/text. Omitted fields
  preserve their values; empty style values are rejected.
- A text-only tile uses a configured solid background. A label-only update on an
  existing image reuses its cached background and does not fetch it again.
- A combined image/text change becomes visible only after the entire new tile
  is ready. Keep the previous valid tile if validation, fetch or rendering fails.
- Cache identities include an explicit content revision or equivalent invalidation
  mechanism. Reusing a URL must not prevent deliberate replacement of that file.
- Expose accepted/queued, rendered and failed states with request/revision IDs.
  USB completion is not physical display readback.
- Protect newer requests from older asynchronous download/render completions.
  Coalesce pending changes per key without modifying an active two-page image.

The pinned native API action implementation expects a fixed argument list.
Presence flags now distinguish preserve from explicit clear; the helper supplies
every argument and maps `text` to wire argument `label_text` because `text` is
reserved by the pinned schema. Schema/template/native tests cover this choice.
Keep uploaded asset transport separate so a future chunked-upload path can reuse
the renderer.

## Implementation stages

### P0 Finalize the API and lifecycle contract

- [x] Define typed per-key visual state, explicit clear/preserve rules, font/style
  defaults, request revisions, status/error responses and cache invalidation.
- [x] Set finite limits for URLs, encoded bytes, source pixel count, labels,
  queued jobs, cache memory, timeouts and retries before accepting network input.
- [x] Choose and test the native API representation and HA script/helper interface.
- [x] Define boot, deck-only reconnect, HA restart and offline behaviour. A logging
  client connecting/disconnecting must not clear images or masquerade as HA state.

Acceptance: concrete payload examples and validation tests cover image-only,
text-only, combined, clear, invalid and stale requests. No entity-specific
function is part of the firmware contract.

### P1 Add owned runtime images and a safe scheduler boundary

Primary files: `components/stream_deck/protocol.*`, `scheduler.*`, a new runtime
image/visual-state module, and `tests/native/`.

- [x] Replace or extend the static-pointer-only lifetime model with immutable,
  owned image versions and explicit retention for desired, applied and active jobs.
  Keep flash-resident assets compatible with existing examples.
- [x] Hold the active image through both pages and completion/cancellation. Never
  free or overwrite it when a new HA request, disconnect or cache eviction arrives.
- [x] Give each update a distinct identity/revision. Mutating pixels behind the
  same `NativeImage *` is insufficient; runtime copies now have retained identities.
- [x] Keep ownership/scheduling logic independent of ESPHome and inject allocation
  where needed so host tests can exercise allocation failure and resource lifetime.

Acceptance: native tests cover rapid replacement during either page, stale
generations, delayed cancellation, eviction of referenced assets, allocation
failure, no use-after-free and unchanged static golden output.

### P2 Implement bounded local rendering

Primary files: new renderer/canvas modules, ESPHome font/decoder adapters,
`tools/`, rendering fixtures and attribution records.

- [ ] Compose a 72 × 72 RGB canvas with an explicit background and alpha handling.
  Preserve aspect ratio with documented contain/crop behaviour; do not assume a
  fixed-size decoder automatically matches the reference helper's scaling.
- [ ] Render runtime labels using bundled glyphs, a black outline and configurable
  fill. Define alignment, wrapping/truncation, size choices, UTF-8 handling and
  unsupported-character behaviour. Pin font assets and preserve their licences.
- [ ] Convert the composed canvas into the exact native BMP layout, applying
  orientation once. Do not flip already-native assets again.
- [ ] Reuse the pinned ESPHome runtime-image/font facilities where suitable; do
  not port desktop Pillow or introduce LVGL merely to draw these small tiles.

Acceptance: fixtures cover transparency, asymmetric colours/orientation, outlined
text, long/empty/unsupported labels and invalid images. Native BMP headers and
page encoding still match the pinned upstream contract. Embedded font/scaling
pixels need their own deterministic fixtures; do not claim pixel-identical
Pillow rendering without testing it.

### P3 Add URL loading and caching

Primary files: a bounded asset-loader adapter around the pinned runtime-image /
HTTP facilities, component configuration and loader tests.

- [ ] Fetch asynchronously or in bounded work slices. Keep input, Wi-Fi, native
  API and OTA responsive while loading and rendering.
- [ ] Cache reusable decoded backgrounds independently from rendered labels.
  Unchanged asset revisions hit the cache; changing only text never re-downloads.
- [ ] Bound compressed data and decoded source dimensions, not just the 72 × 72
  destination. Reject malformed/truncated/oversized images and release all resources.
- [ ] Limit redirects/timeouts/retries, validate TLS where used, and define the
  allowed HTTP/HTTPS sources. Redact credentials or signed query strings in logs.
  Do not embed a long-lived HA administrator token in firmware.
- [ ] Ensure the ESP can reach the selected URL. HA `/local/` files are appropriate
  only for non-sensitive assets; authenticated media URLs need deliberate support.

Acceptance: fake-loader tests cover cache hits, replacement revisions, failed
fetches, out-of-order completion, cancellation and bounded memory. Failures keep
the previous tile and expose an actionable status without reboot loops.

Fifteen plain RGB24 canvases occupy 233,280 bytes, about 228 KiB. This is only a
base estimate: decoded backgrounds, completed BMPs, active versions, decoder and
TLS workspaces need additional budget. Use the board's verified 8 MB PSRAM with
explicit caps, and measure internal heap; do not consume USB DMA reserves.

### P4 Expose generic Home Assistant controls and resynchronization

Primary files: `components/stream_deck/__init__.py`, `stream_deck.*`, API actions,
new `examples/05_home_assistant_runtime.yaml`, HA automation/script examples,
`tools/check_firmware.py` and schema/integration tests.

- [ ] Expose generic visual, clear, refresh/invalidate and status operations over
  the encrypted native API. Add useful field descriptions and error responses.
- [ ] Publish stable key inputs without fixed HA entity IDs or firmware-side
  service calls. Remove the bench's automatic bulb/arrow substitutions from this
  new example; HA controls the desired artwork from actual state.
- [ ] Provide HA examples for press/release automations, state-driven visuals and
  changing a key binding/image/label entirely from HA. Avoid duplicate local and
  HA action paths, startup-triggered actions and replay of presses after outages.
- [ ] Make HA replay the latest layout on HA startup and ESP restart/reconnection,
  using an explicit boot/session identity and idempotent revisions as needed.
  A deck-only reconnect restores cached desired tiles without downloading again.
- [ ] Define a safe offline/default display until synchronization. Cache in RAM
  initially; do not write flash on every label or state change.
- [ ] Add the new example to the build checker and update the public contract and
  README without making the unchanged diagnostic example harder to use.

Acceptance: HA-side rebinding requires no OTA. Image, label and supported style
changes require no compilation. Routine logger connections do not invalidate
HA-owned state. Repeated synchronization is safe and does not resend unchanged
images unnecessarily. No custom HA frontend is required for these basic controls.

### P5 Verify end to end and hand off

- [ ] Run the full host suite, fixture checks and synthetic compilation of all
  existing examples plus the new runtime example. Record actual results/counts.
- [ ] Before hardware deployment, confirm the HA version, reachable asset URL and
  access method, and the owner's readiness to replace the bench firmware.
  Preserve a private copy of the working deployment artifacts when appropriate.
- [ ] Test image-only, text-only, outlined text and combined tiles on real keys;
  verify changes initiated in HA independently of button presses.
- [ ] Exercise rapid replacements during output, all keys during rendering,
  invalid URLs/images, network loss, HA restart, ESP restart and deck reconnect.
  Check API/OTA availability, input ordering, queue/errors and heap trends.
- [ ] Record download/render/redraw timing and memory measurements rather than
  promising animation rates or latency. Update implemented, compiled, unit-tested
  and hardware-verified status separately.

Acceptance: the owner can rebind controls and change images/text from HA without
firmware changes, with reliable resynchronization and no regression in the tested
USB path. Mark the remaining release/electrical gates independently.

## Known limitations and deferred decisions

The first valid input report after attachment is currently a silent baseline;
an already-held key's release is also suppressed. The observed first key-0 click
after reconnect can therefore be consumed. Do not fix this by assuming all keys
are released or inventing a press during synchronization. Investigate a validated
initial-state read or another explicit policy separately, with held-key tests,
before claiming first-click or lossless HA automation acceptance.

Only one successful post-fix peripheral reconnect is recorded. Brightness levels,
exact position/colour/orientation checks, simultaneous holds, mid-upload detach,
repeated cold/warm starts, overnight soak and electrical measurements remain in
[hardware.md](hardware.md) and [testing.md](testing.md). Runtime graphics do not
waive those gates. A source label or successful image transfer is not power-path
qualification.

P0 settled glyph coverage/size choices, byte/dimension limits and native API
presence semantics in [the contract](runtime-visuals.md). P2 still needs the
actual licensed/pinned font assets. Before hardware integration, establish HA
server/version and allowed asset origin/access. These do not block rendering
development. Additional codecs, fonts, upload transports and an HA editor remain
follow-on work.

## Validation and deployment commands

Hardware-independent validation uses synthetic secrets:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/generate_reference_fixtures.py --check
.venv/bin/python tools/check_firmware.py --compile
git diff --check
```

Do not upload `.build/firmware/` validation images. Only when a later device
deployment is requested, and after example 05 exists, build it privately with:

```sh
.venv/bin/python tools/check_firmware.py --compile --example 05_home_assistant_runtime --deploy
```

Use the resulting `.build/deploy/05_home_assistant_runtime/build/firmware.ota.bin`
for an encrypted OTA upload to the verified device. Keep local `secrets.yaml`,
compiler logs, backup images and binaries private and ignored. Do not change
dependency pins, flash partitions or the physical power arrangement implicitly.

## Reference material

- [Python basic example](https://python-elgato-streamdeck.readthedocs.io/en/stable/examples/basic.html):
  scale an icon, draw a label, convert to native format. Black outlining is a new
  requirement, not behaviour claimed by that example.
- [Pinned PILHelper](https://github.com/abcminiuser/python-elgato-streamdeck/blob/43666bb454186d1d7adeba9402f689449705d0b9/src/StreamDeck/ImageHelpers/PILHelper.py):
  aspect-preserving scaling, alpha composition and final native orientation.
- [ESPHome native API actions](https://esphome.io/components/api/#user-defined-actions)
  and [online images](https://esphome.io/components/image/online_image/).
  Use the locally installed 2026.9.0 source to resolve exact APIs rather than
  upgrading to match moving documentation.
- Local reusable components: `.venv/lib/python3.14/site-packages/esphome/components/`
  `runtime_image/`, `online_image/`, `font/`, `display/` and `api/`.
  The pinned ESP32 API message cap is 32 KiB; future arbitrary asset uploads must
  be bounded/chunked rather than one unbounded base64 action.
