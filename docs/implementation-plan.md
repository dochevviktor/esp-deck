# Home Assistant runtime control implementation plan

Direction update, 2026-10-12: the owner requested direct HA-to-ESP API artwork
uploads. The [bounded upload path](artwork-upload.md) is implemented and becomes
the default for library images on capability-compatible firmware. This explicitly
supersedes the earlier deferral of direct/chunked uploads. It reuses encrypted
native API actions, source hashes, PNG decoding, local rendering and existing
input/USB fences. HTTP remains for older firmware and external URLs. Hardware
rules and pending device/electrical gates are unchanged; no deployment occurred.

USB startup follow-up, 2026-10-11: the owner confirmed the 23:05:52 image still
showed only the logo, unknown keys and no brightness response. Restoring example
04's full startup on runtime firmware returned real key reports, all 15 key
states and four HA light actions. The driver now runs that sequence regardless
of diagnostics; logging no longer changes initialization. The fixed quiet
23:50:23 build is deployed; 72 sanitizer host tests and all seven synthetic
builds pass. Real key reports and brightness USB completions also arrive on that
quiet build; visual confirmation and cold/repeated recovery remain open. The
owner's concurrent HA edits are preserved; newly added artwork hits the known
`origin_not_allowed`/device-reachable-address gate. See the
[current physical record](hardware-lab.md); no flash erase or USB packet-size
experiment was used.

Latest recovery, 2026-10-11: the owner moved HA 18123 to the real ESP and confirmed
working brightness, labels, light control and page shifting before the reported
freeze. Its stale ESP Deck association is repaired and the extra 18124 HA is
stopped. A reproduced Redraw bug left applied revisions permanently zero; the
scheduler now separates image identity from USB work, with regression tests.
Corrected firmware compiled `23:05:52 +0200` is deployed. All seven synthetic
configurations compile; 72 host tests pass with sanitizers. Real Redraw and editor
Apply now return all 15 tiles to USB-applied/ready. Physical confirmation remains
requested. Original image pages are preserved alongside separate Hardware pages.
Use [the current physical guide](hardware-lab.md); automated virtual-lab tests now
refuse the retargeted instance, and artwork networking remains pending.

Physical P9 follow-up, 2026-10-11: the owner supplied the GitHub repository and
authorized the real-device update. Example 05 with the HTTP probe-buffer fix is
now deployed and paired to a separate HA 2026.10.1 hardware lab. All 15 text/page
tiles reach USB-applied status and 12 real light-binding actions were observed.
See [the physical lab evidence](hardware-lab.md). The 32 KiB origin probe exposed
and fixed a production-fetcher 128 KiB-only assumption; 70 host tests pass with
sanitizers and all seven synthetic firmware configurations compile. Local HACS
schemas/Hassfest now pass with real repository metadata. A reachable ESP-to-HA
artwork route, visual confirmation, fuller physical acceptance and online HACS
validation remain pending. Example 04 is retained as a private rollback artifact.

Earlier P9 packaging checkpoint, 2026-10-11: local version 0.9.0 packaging, archive installation and
lifecycle qualification are implemented. All seven synthetic firmware builds,
65 host tests (ASan/UBSan), five frontend tests, 62 HA-engine cases and the
28-scenario real HA/native-API/browser run pass. The four P9 lifecycle cases also
pass their final recheck with complete code removal/restart. See [the release guide](release.md).
Hassfest's repair-translation/schema errors are fixed; final HACS/Hassfest metadata
validation is blocked on the actual GitHub documentation/issue URLs and maintainer.
This checkout has no remote configured. HACS online install/update, physical
deployment/runtime acceptance and the existing electrical/soak gates remain open.
No ESP was contacted or flashed; example 04 remains the hardware baseline.

Approved direction as of 2026-10-10: make ESP Deck a generic input and display
device. Home Assistant owns key bindings, automations and visual configuration;
the ESP32 composes images and text locally and handles USB. Once this capability
is installed, changing a binding, image or supported text/style must not require
another firmware build or upload.

P8 checkpoint, 2026-10-11: P0–P8 software implemented and tested (60 Python unittest cases,
including nine native C++ executables; five frontend tests including twenty
pixel-exact rendering fixtures; 58 real-HA engine tests with mocked native
actions; 24 real-container/native-API/browser scenarios).
All seven firmware configurations compile with
synthetic secrets. The [asset loader](asset-loading.md) adds bounded asynchronous
HTTP(S), strict PNG decoding and retained background caching to the
[runtime contract](runtime-visuals.md) and [renderer](rendering.md).
P4 adds [native API controls, key events and HA layout replay](home-assistant.md).
P5 adds the [isolated HA lab](ha-lab.md), an encrypted ESPHome host virtual deck,
and a replay fix found by real HA testing. P3's live ESP asset-reachability check
and physical HA/device acceptance remain pending.
P6 adds the [HA integration backend](ha-integration.md): guided setup/presets,
atomic draft/applied layouts, bindings, admin APIs, repair and synchronization.
P7 adds the bundled [visual editor and artwork library](visual-editor.md):
5×3 editing, bounded PNG/JPEG crop/normalization, hash references, restricted
revocable device reads and firmware-matched previews.
P8 adds [runtime v2](runtime-v2.md): explicit capabilities, verified persistent
origins, positioned labels, bounded HA pages/overlays and input correlated with
USB-applied revisions. The local sanitizer blocker is resolved: `libasan` and
`libubsan` are installed, and all 60 host tests pass with ASan/UBSan on the nine
native executables after adding an empty-buffer guard to the P8 test fetcher.
UBSan was configured to halt on errors; see [the follow-up evidence](testing.md).
No firmware was deployed or newly hardware-verified; example 04 remains the
installed bench baseline.

Planning update, 2026-10-11: develop a HACS-distributed HA integration with a
bundled visual editor, image uploads and later pages/layers. P5 now establishes
an independent Podman HA lab; P6–P8 deliver the product experience; P9 retains
the real-device and release gates from the original P5. The owner's production
HA is not a prerequisite for software development/testing. This planning update
was research/documentation at the time. P5 has since implemented and exercised
the HA lab; P6's integration backend and P7's editor/uploads are locally
installed/tested. P8's advanced firmware/backend/editor is now software-tested;
HACS distribution and physical qualification remain P9 work.
Read [the research and architecture decision](decisions/home-assistant-ux.md).

## Resume in a fresh chat

1. Read [AGENTS.md](../AGENTS.md), this plan, the original
   [handover](../STREAM_DECK_ESPHOME_CODEX_HANDOVER.md), the
   [USB decision](decisions/usb-transport.md), and current
   [hardware evidence](hardware.md) and [test status](testing.md).
2. Inspect the worktree and current sources; preserve local edits and secrets.
3. Continue the remaining P9 gates in [the release guide](release.md), against
   [runtime v2](runtime-v2.md), the [integration backend](ha-integration.md),
   [P7 editor/artwork pipeline](visual-editor.md), isolated HA lab and test-only
   virtual deck, using
   [the architecture decision](decisions/home-assistant-ux.md),
   [the runtime contract](runtime-visuals.md), [P3's loader](asset-loading.md)
   and [P4's HA guide](home-assistant.md). Podman 5.8.4/rootless is available on
   this Fedora 44 host; HA 2026.10.1 and the encrypted virtual deck now pass the
   [lab scenarios](ha-lab.md). Use fresh
   lab configuration and synthetic devices, not the owner's HA data or credentials.
4. Example 05 is now installed on the real ESP; example 04's private images/ELF
   remain the known-working rollback artifacts. Continue from [the hardware lab](hardware-lab.md).
   Resolve its ESP-to-HA asset route and finish the supervised tests. Do not hardcode
   HA entities into firmware, reset visual state on API logger connections, or
   repeat USB packet-size experiments for this stage.
5. Preserve v1 compatibility, hash-only saved artwork references and
   zero-download label/position updates. P8's capabilities, provisioning and
   safe page/layer switching are implemented; retain their input fences. Before a
   requested real-device upload in P9, verify device identity, preserve the bench
   artifacts and establish the chosen HA asset address and deployment readiness.

This plan supersedes the original handover's deferral of runtime text rendering
and network-loaded artwork. The owner's P5 extension also brings a guided HA
editor, upload normalization and bounded pages/layers into planned scope. The
fixed model/board, ESPHome native API, protocol independence, power rules and
hardware gates still apply.
The original handover stays intact as the historical specification.

## Working baseline to preserve

The repository baseline when this plan was written is `866bff7`; P4 is now in
`f862f54`. The USB startup/decoder changes are in `181c54a`. Version pins are in
[versions.md](versions.md): ESPHome 2026.9.0, ESP-IDF 5.5.5, Python Stream Deck
0.10.0 at `43666bb454186d1d7adeba9402f689449705d0b9`, and Pillow 12.3.0.

| Evidence category | Starting baseline (before P0/P1) |
| --- | --- |
| Implemented | Original-device codec, scheduler, 15 key entities, brightness, static artwork, diagnostics, reconnect handling and encrypted API/OTA |
| Compiled | All four existing examples with synthetic secrets |
| Unit-tested | 23 Python cases, including native C++ protocol/scheduler and production-transport simulations |
| Hardware-verified | Image feedback, press/release coverage for all 15 key indices, one peripheral reconnect with full redraw and resumed input, Wi-Fi/API/OTA and 8 MB PSRAM initialization |

The preserved pre-runtime baseline is `04_hardware_test`, compiled
`2026-10-10 21:59:20 +0200`. Its OTA image is 846,240 bytes with SHA-256
`69854221b91d08647a7f64e0fb6d35535896a085dfdf0aa763ca9c286e88ad12`.
The owner reconfirmed `192.168.10.238` on 2026-10-11 and two ICMP probes succeeded;
the current installed image and identity checks are in [the physical lab guide](hardware-lab.md).
Verify identity before another upload. The ESP and deck use the
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
| Image upload, 72×72 artwork preparation, labels and supported style values | Bounded fetching/decoding, final alpha composition and outlined text |
| Visual updates based on actual entity state | Native BMP encoding, serialized USB output and desired-image restoration |
| Authoritative layouts, bindings, active page/layer and replay after restart | Bounded current-key caches and last successfully rendered tiles |

The existing key entities in `examples/packages/deck.yaml` already support
HA-side automation bindings. P4's event entities publish real edges without an
API subscription snapshot; prefer those for new bindings. A Home Assistant
`button` entity is an outbound command, not a
physical-key input. The new configuration must not also run the firmware-side
`light.toggle` from example 03. Retain that example as a static demo, not the
recommended rebinding workflow.

The first runtime version includes URL-loaded artwork with caching, optional
runtime labels with black outlines, image-only/text-only/combined tiles, and
generic encrypted native API actions. Start with PNG for icons; add JPEG in this
stage only with explicit decoder limits and tests. Bundle a small licensed font
set with defined sizes and glyph coverage. Label changes use those fonts at
runtime; arbitrary font uploads or unlimited character coverage are not promised.

A guided editor, upload/crop/fit pipeline, key rearrangement and bounded pages/
modifier layers are now planned in P6–P8. HA stores them; only the active 15 tiles
need to reside on the ESP. Keep the P4 YAML interface for advanced use/testing,
but routine setup must not require hand-editing it. Chunked image uploads to the
ESP were subsequently authorized on 2026-10-12; see [the upload contract](artwork-upload.md).
Flash-persisted layouts, animations, unlimited graphical layers/fonts, other
models, a second host stack, MQTT and a permanent desktop bridge remain out of
scope. A test-only virtual deck does not become a deployment dependency.

## Intended user experience and implementation order

After initial compatible firmware/Wi-Fi setup: install one HACS integration,
select the ESPHome deck, open a 5×3 editor, choose a key's HA binding and appearance,
upload/crop an image, and Apply. Provide presets for common entity states and an
advanced route to HA scripts/automations. Revisions, key-index plumbing, asset
URLs and replay are backend responsibilities. The editor works without adding
a dashboard card; an optional card shares the same saved configuration.

| Stage | Outcome | Needs the owner's HA/deck? |
| --- | --- | --- |
| P5 | Reproducible real HA lab, virtual deck and automated integration tests | No |
| P6 | HA backend with discovery/setup, persisted layouts, bindings and synchronization | No |
| P7 | Usable 5×3 editor and bounded upload → 72×72 PNG pipeline | No |
| P8 | Capability-aware label position, origin setup and safe pages/modifier layers | No for software; device acceptance later |
| P9 | Packaging/upgrade tests, then physical runtime and release qualification | Physical deck for hardware gates; lab HA can be used |

HACS distributes the custom integration; this is not a Supervisor app/add-on.
Use a bundled custom panel and a backend that runs with the browser closed.
The [architecture decision](decisions/home-assistant-ux.md) records the primary
sources, existing HA API constraints, upload access design and test boundaries.

## Runtime contract

P0 selected a fixed native API signature with presence flags and an HA patch
helper. The [complete contract](runtime-visuals.md) is authoritative. The following
shows the helper payload shape exposed by example 05 (not the installed bench):

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

- [x] Compose a 72 × 72 RGB canvas with an explicit background and alpha handling.
  Preserve aspect ratio with documented contain/crop behaviour; do not assume a
  fixed-size decoder automatically matches the reference helper's scaling.
- [x] Render runtime labels using bundled glyphs, a black outline and configurable
  fill. Define alignment, wrapping/truncation, size choices, UTF-8 handling and
  unsupported-character behaviour. Pin font assets and preserve their licences.
- [x] Convert the composed canvas into the exact native BMP layout, applying
  orientation once. Do not flip already-native assets again.
- [x] Reuse the pinned ESPHome runtime-image/font facilities where suitable; do
  not port desktop Pillow or introduce LVGL merely to draw these small tiles.

Acceptance: fixtures cover transparency, asymmetric colours/orientation, outlined
text, long/empty/unsupported labels and invalid images. Native BMP headers and
page encoding still match the pinned upstream contract. Embedded font/scaling
pixels need their own deterministic fixtures; do not claim pixel-identical
Pillow rendering without testing it.

Implemented in `renderer.*`, `render_font.*`, `render_memory.*` and
`render_esphome.h`. The font generator calls the pinned ESPHome rasterizer;
the image adapter accepts completed Image/RuntimeImage pixels. P3 now supplies
PNG decoding. Eleven native-renderer snapshots and independent upstream/analytical
checks cover P2. The separate `renderer_probe` compiles the complete local path
and is in the build/CI matrix. A clean-build USB dependency omission discovered
by this probe is corrected in the build-local IDF recipe; it does not change
USB framing or the installed firmware.

### P3 Add URL loading and caching

Primary files: a bounded asset-loader adapter around the pinned runtime-image /
HTTP facilities, component configuration and loader tests.

- [x] Fetch asynchronously or in bounded work slices. Keep input, Wi-Fi, native
  API and OTA responsive while loading and rendering.
- [x] Cache reusable decoded backgrounds independently from rendered labels.
  Unchanged asset revisions hit the cache; changing only text never re-downloads.
- [x] Bound compressed data and decoded source dimensions, not just the 72 × 72
  destination. Reject malformed/truncated/oversized images and release all resources.
- [x] Limit redirects/timeouts/retries, validate TLS where used, and define the
  allowed HTTP/HTTPS sources. Redact credentials or signed query strings in logs.
  Do not embed a long-lived HA administrator token in firmware.
- [ ] Ensure the ESP can reach the selected URL. HA `/local/` files are appropriate
  only for non-sensitive assets; authenticated media URLs need deliberate support.
  The configurable probe and origin/TLS/time rules are documented, but the owner's
  actual PNG URL and live device test are still pending; no P3 firmware was flashed.

Acceptance: fake-loader tests cover cache hits, replacement revisions, failed
fetches, out-of-order completion, cancellation and bounded memory. Failures keep
the previous tile and expose an actionable status without reboot loops.

P3 software acceptance is covered by native PNG/pipeline tests, production HTTP
transaction tests with fake IDF, schema tests, and `asset_loader_probe` compilation.
The loader uses one HTTP worker and bounded main-loop decode/render steps. Its
sixteen background slots retain all current key backgrounds; labels reuse them
without a fetch. Graphics allocations share a 2 MiB PSRAM root budget. PNG
CRC/order/zlib completion/decoded size are checked before pixels can commit.
The existing ESPHome wrapper was unsuitable for these strict limits, so a bounded
frontend uses its pinned pngle dependency's allocation-free miniz engine. HTTPS
enforces trust/hostname/dates and requires a valid clock; no redirects or retries.
See [asset-loading.md](asset-loading.md) for exact limits, source provenance,
DNS cancellation-drain behavior and remaining device checks.

Fifteen plain RGB24 canvases occupy 233,280 bytes, about 228 KiB. This is only a
base estimate: decoded backgrounds, completed BMPs, active versions, decoder and
TLS workspaces need additional budget. Use the board's verified 8 MB PSRAM with
explicit caps, and measure internal heap; do not consume USB DMA reserves.

### P4 Expose generic Home Assistant controls and resynchronization

Primary files: `components/stream_deck/__init__.py`, `stream_deck.*`, API actions,
new `examples/05_home_assistant_runtime.yaml`, HA automation/script examples,
`tools/check_firmware.py` and schema/integration tests.

- [x] Expose generic visual, clear, refresh/invalidate and status operations over
  the encrypted native API. Add useful field descriptions and error responses.
- [x] Publish stable key inputs without fixed HA entity IDs or firmware-side
  service calls. Remove the bench's automatic bulb/arrow substitutions from this
  new example; HA controls the desired artwork from actual state.
- [x] Provide HA examples for press/release automations, state-driven visuals and
  changing a key binding/image/label entirely from HA. Avoid duplicate local and
  HA action paths, startup-triggered actions and replay of presses after outages.
- [x] Make HA replay the latest layout on HA startup and ESP restart/reconnection,
  using an explicit boot/session identity and idempotent revisions as needed.
  A deck-only reconnect restores cached desired tiles without downloading again.
- [x] Define a safe offline/default display until synchronization. Cache in RAM
  initially; do not write flash on every label or state change.
- [x] Add the new example to the build checker and update the public contract and
  README without making the unchanged diagnostic example harder to use.

Acceptance: HA-side rebinding requires no OTA. Image, label and supported style
changes require no compilation. Routine logger connections do not invalidate
HA-owned state. Repeated synchronization is safe and does not resend unchanged
images unnecessarily. No custom HA frontend is required for these basic controls.

Software acceptance: `visual_api.*` wraps the existing Store/Pipeline and returns
bounded revision/status/error records through the pinned `api.respond` interface.
The runtime package requires encryption/PSRAM/asset loading and enforces Store's
visual ownership. Fifteen native edge-event entities preserve the binary sensors
while avoiding subscription-state replay as actions. Production publication tests
cover baselines, held keys, overflow, stale generations and detach cleanup.
HA helper tests cover full 15-key replay, current-state visuals, session/revision
recovery, scalar string preservation and action-registration timing. Native API
tests prove unchanged replay creates no download or new scheduled image.
These are host/synthetic-build results. P5 adds real HA lab sessions; P9 retains
physical runtime/rendering/reconnection acceptance.

### P5 Establish an independent HA integration lab

Implemented files: `tools/ha_lab.py`, `tests/ha/`, `tests/ha_lab/`, a test-only ESPHome
host adapter/configuration, and version/image locks separate from firmware pins.

- [x] Record the P4 baseline: 48 Python cases, seven native executables, all
  fixture checks and seven synthetic firmware builds passed.
- [x] Check local prerequisites without mutation: Fedora 44, Podman 5.8.4,
  rootless/Netavark, SELinux enforcing; no HA image/container or 8123/18123 listener
  at research time. This is not a container startup test.
- [x] Add repeatable lab up/status/test/down commands. Pin a released HA image
  by tag and digest; start by evaluating source-reviewed HA 2026.10.1. Record
  Python/test-tool versions and later HACS/frontend versions. Keep these locks
  separate from the ESPHome/IDF/Pillow fixture pins.
- [x] Create fresh private `.build/ha-lab/` config/data with synthetic accounts,
  keys, a demo light, scenes and test scripts. Use a named rootless network and
  `127.0.0.1:18123` for the UI. Handle SELinux on lab-owned mounts; no privileged
  mode, USB passthrough or production HA config is needed. Scope teardown to
  lab resources and preserve unrelated containers.
- [x] Prove pinned ESPHome `host` + encrypted native API in a small spike, then
  add a test-only adapter for the portable Store/renderer/scheduler. Reuse the
  P4 action signature and event behavior; simulate USB completions and physical
  inputs. Add host HTTP fetching for asset-route tests without claiming coverage
  of the IDF worker. Do not reimplement the encrypted wire protocol by hand.
- [x] Pair the virtual deck with HA's real ESPHome integration by explicit host/
  port. Verify action-response support, entity/action discovery and registry
  rename behavior before choosing the minimum supported HA version.
- [x] Execute the actual P4 helper scripts in HA, covering all 15 keys, numeric
  labels/sessions, revision conflicts, unchanged replay, state feedback, outages,
  HA restart, virtual ESP reboot and logger connections. Keep the existing
  native tests as the independent renderer/USB oracle.
- [x] Add HA pytest tests and browser/API smoke tests with a clear distinction
  between mocked clients, real container/native-API sessions and hardware. Inject
  presses only through the virtual deck; avoid a production debug action.

Acceptance: a repeatable command starts a clean HA lab, connects the virtual deck
and runs the P4 integration scenarios without the owner's HA, ESP or GitHub
account. Store sanitized logs/results and image/version identities. No electrical,
USB, physical-display or actual ESP HTTP/OTA claim comes from this gate.

Software acceptance passed on 2026-10-11 using `up --fresh` followed by `test`:
two HA-engine tests and nine real HA/native-API/browser scenarios. Both images
are pinned by tag/digest independently of firmware dependencies. Initial minimum
HA baseline: 2026.10.1; earlier versions are untested. The real server exposed
the invalid P4 `has_service()` template; replay now listens for native action
registration events. Registry IDs survive renames, while manual helper entity
references need updating. `down` preserves private data and unrelated containers;
`--fresh` archives the previous lab. See [the lab guide](ha-lab.md) and
[test evidence](testing.md). No physical firmware was deployed.

### P6 Build the HACS integration backend and guided setup

Implemented files: `custom_components/esp_deck/` with manifest, config/options flow,
storage, ESPHome adapter, binding/sync controllers, actions, diagnostics and
translations; tests under `tests/ha/`.

- [x] Package one integration in the existing repository. Use HA config entries
  to choose an existing ESPHome deck, verify the runtime signature and associate
  stable device/entity registry references. Resolve names automatically; provide
  a repair flow for missing, disabled, renamed or incompatible entities/actions.
- [x] Reuse HA's ESPHome connection and credentials through a narrow tested
  adapter. Follow current helper/device-registry ownership rules. Do not create
  duplicate physical devices or a second permanent native API client.
- [x] Persist a versioned HA layout model with draft/applied revisions, atomic
  saves, migrations, backup/export/import and bounded asset references. Distinguish
  this layout version from the ESP boot session and per-key request revisions.
- [x] Provide entity presets and explicit press/release bindings to HA actions,
  scripts/scenes, plus key events for advanced automation. Execute bindings in
  HA with context and error reporting; do not write entity IDs into ESP firmware
  or rewrite the user's automations.yaml. Avoid duplicate managed/automation paths.
- [x] Move the P4 queued writer/replay logic into one backend controller per deck:
  query current session/revisions, coalesce latest desired state, skip unchanged
  visuals, subscribe to actual entity state and replay after HA/ESP reconnect.
  Stop/unsubscribe cleanly on unload; discard stale tasks after configuration changes.
- [x] Explain migration from manual P4 scripts and disable competing replay/
  binding paths deliberately. Preserve their ability to be used independently.
- [x] Expose save/sync/status operations and authenticated configuration APIs
  with backend permission checks. Hiding the editor from non-admin users is not
  itself authorization. Surface actionable failures and connectivity separately.

Acceptance: adding the integration, selecting a virtual deck and binding a
synthetic light works through HA; state changes, restarts and configuration
reloads synchronize correctly with the browser closed. Export/import and unload
tests pass. Direct local installation is sufficient; HACS login is not required
for development. Use existing allowed-origin URLs until P7/P8 provide the wizard.

Software acceptance: [the backend guide](ha-integration.md) documents the saved
model, admin services/WebSocket API, guided presets and deliberate P4 handoff.
HA registry UUIDs preserve associations across renames. The source-tested adapter
uses existing ESPHome discovery metadata and HA services, without reading its
credentials, claiming its physical device or creating another permanent client.
Atomic storage failures/corruption fail closed; optimistic edits, backup/import,
migrations, stale tasks, bounded binding queues, unload and permissions have
real-engine tests. Seven added live scenarios cover setup/presets, actual light
feedback, cache reuse, renames, failure reporting, HA/ESP restart, unload/reload
and the integration/options UI. The combined suites have 43 engine tests and
16 real-container/native-API/browser scenarios. All seven synthetic firmware
configurations compile; none was deployed. Distribution metadata/HACS/Hassfest
remain P9 gates. The visual editor was subsequently implemented in P7 below.

### P7 Deliver the visual editor and efficient artwork library

Implemented files: `frontend/` source/esbuild lock, a compiled module under
`custom_components/esp_deck/frontend/`, `artwork.py`, `panel.py`, model/API
extensions and browser/image tests. See [the editor guide](visual-editor.md).

- [x] Register a bundled sidebar/configuration panel. Show the actual 5×3 key
  arrangement with select/move/swap/copy/clear, undo and keyboard/touch alternatives.
  Separate binding, appearance and state rules; common actions need no YAML.
- [x] Support the current font sizes, colors, outline, image fit and on/off/
  unavailable presets. Keep optional advanced HA scripts/automations discoverable.
  Show draft versus applied state, save/apply progress and retry/repair. Selecting
  a tile or previewing it must not fire the bound action.
- [x] Accept authenticated PNG/JPEG uploads into HA. Enforce encoded-byte and
  decoded-pixel limits before expensive processing; reject malformed/animated/
  unsupported content. Process EXIF/crop/zoom/offset, strip metadata and normalize
  off the HA event loop into non-interlaced 72×72 PNGs, initially capped at 32 KiB.
- [x] Keep source/library disk usage and conversion concurrency bounded. Store
  immutable variants by content hash and use that hash as `image_revision`.
  Preserve alpha and keep dynamic labels in the ESP renderer. Label-only changes
  must not generate/download another raster, and native orientation is applied once.
- [x] Implement the restricted, revocable asset-path capability described in
  the architecture decision, compatible with the current no-header/no-query URL
  contract. Authenticate editing/uploads; restrict device reads to referenced
  normalized files. Cover credential redaction, path traversal, cross-device
  access, revocation, in-flight retention and reference-aware garbage collection.
- [x] Verify every normalized fixture with the production PNG decoder. Reuse
  bundled glyph metrics/render fixtures for previews; don't equate browser font
  rendering with ESP pixels without comparison tests. Test large photos, alpha,
  bad EXIF, limits, concurrent edits and refresh at the same source filename.
- [x] Evaluate a thin optional dashboard card only if it improves normal use;
  it must share backend configuration and work without owning synchronization.
  No card was needed: the bundled panel and existing HA status entity cover this
  stage without another configuration surface.

Acceptance: from a fresh lab UI, pick a key, bind a light/script, upload and crop
an image, change its label, move the key and apply, with no URL/counter editing.
Only bounded 72×72 artwork is fetched by the virtual deck; relabeling performs
zero additional asset GETs. State-driven operation continues after the editor
closes. A normalized source reduces network/decoder work, not fixed USB report size.

Software acceptance: desktop/mobile Chromium exercises preset binding,
upload/crop/apply/relabel, same-filename content replacement, moving keys,
keyboard/touch/undo, concurrent edit rejection and closed-browser operation in
the isolated HA/virtual-deck lab. Label-only edits cause zero device GETs.
Ten normalized image cases decode through the production C++ PNG decoder;
all eleven native renderer fixtures match the browser preview algorithm exactly.
The full suite now has 59 host, four frontend, 50 HA-engine and 19 live scenarios.
All seven synthetic firmware configurations compile. No device deployment or
new hardware verification occurred. v1 origin setup remains explicit; P8 owns
provisioning/capabilities/positioning/pages, and P9 owns distribution/hardware gates.

### P8 Add capabilities, positioning and safe pages/layers

Implemented files: `runtime_v2.h`, `origin_provisioning.h`, the separate v2 action
package, renderer/Store/scheduler extensions, HA `advanced.py` and page select,
editor controls, simulator and ordering tests. See [the v2 guide](runtime-v2.md).

- [x] Add explicit capability reporting: protocol version, 15-key/72×72 model,
  supported visual fields/fonts/limits, configured origins and status semantics.
  Keep v1 working; hide advanced controls when a device lacks their capability.
- [x] Add a bounded encrypted-API origin-provisioning operation so setup can
  select the HA address reachable from the ESP without rebuilding for each move.
  Persist only explicit provisioning changes. Keep exact allowlists, verified
  TLS and finite origins; validate a test fetch from the device. Private-CA
  provisioning stays advanced. The current compiled origin is a documented v1 limit.
- [x] Version the visual action to support bounded text position/alignment within
  72×72, with defined wrapping/clipping/outline behavior. Keep the current defaults
  and label-cache reuse. Image transforms can stay in HA's normalized raster.
  Do not silently add arguments to v1's fixed signature or rasterize every text
  update into a network image as a shortcut.
- [x] Store named 15-key pages and sparse logical overlays in HA, initially
  capped at 8 pages/4 overlays with one active overlay. Define inherit/clear and
  precedence; expose page selection as a normal HA control. Resolve only the
  active tiles to the ESP, not an unbounded page framebuffer/cache.
- [x] Specify and implement a tested input/display correlation mechanism before
  enabling page/layer bindings. P4's `rendered` precedes two-page USB completion.
  Track applied revisions and USB generation, gate transitioning keys, and reject
  delayed edges from a previous binding context. Audit the actual native API
  ordering/channel rather than relying on a fixed delay or a HA-side flag alone.
- [x] Capture binding context for an accepted press/release pair. Define navigation
  keys and momentary modifiers, reset transient layers/holds on disconnect/restart/
  overflow, and never replay input after an outage. Retain a safe unavailable/
  retry state if a page cannot finish; do not promise an atomic whole-deck swap.
- [x] Exercise rapid page changes, failed tiles, concurrent presses, old callbacks,
  held modifiers, same-image/different-binding keys and reconnect during output
  in portable/simulator tests; add these cases to physical P9 acceptance.

Acceptance: capabilities prevent unsupported settings; positioning renders within
bounds; page/layer resolution is deterministic and stale/transition inputs cannot
execute the wrong binding. Software tests pass without new hardware. This stage
does require a compatible firmware update before those new features work on a
real deck; later per-key/page edits do not require further builds.

Software acceptance: all seven synthetic firmware configurations compile. The
60 host, five frontend, 58 HA-engine and 24 real HA/native-API/browser scenarios
pass. Twenty renderer fixtures match the browser exactly. The lab verifies
origin fetch/failure/persistence across virtual reboot, same-image rebinding,
captured release pairs, concurrent navigation, failed/transitioning tiles,
rapid pages, held modifiers/overflow/reconnect and the page editor. The source
audit uses connection-scoped native action responses with a bounded input
reader/ack protocol; it does not assume ordering between legacy event entities
and rendered status. Full [evidence and remaining gates](testing.md) are separate
from hardware: no deployment or new physical verification occurred.

### P9 Qualify installation, physical behavior and distribution

This retains the original P5 physical checks and adds product/release validation.
Software installation tests can proceed before any device deployment.

- [x] Run HA pytest, real-container/native-API and browser suites, plus the full
  host fixtures and synthetic builds for every supported firmware example.
  Exercise the declared minimum/current HA versions and upgrade/reload/restart,
  data migration, backup/restore and removal. Record actual versions and results.
- [x] Build local installation packaging with `hacs.json`, translations,
  brand/licence assets and the bundled frontend. Verify direct installation from
  the artifact and actual P8-to-P9 code upgrade, preserving saved data.
- [x] Complete the manifest's real repository/maintainer metadata and pass the
  upstream HACS local schemas and Hassfest. Both now pass locally.
- [ ] Run full online HACS repository validation and separately smoke-test
  HACS custom-repository install/update when the repository
  is published and GitHub device authorization is available.
  Public release/default-store submission is a later publishing step, not a
  prerequisite for local tests or custom-repository support.
- [x] Verify the guided flow with no manual YAML, URLs, revision counters or
  frontend-resource registration after initial device setup. Detect incompatible
  bench firmware with a clear upgrade path instead of unexplained missing controls.
- [ ] Before a requested physical upload, confirm device identity, chosen HA
  instance/version, reachable asset address/access and readiness to replace the
  bench firmware. Back up private working artifacts; use local-secret deployment
  builds only. The isolated lab HA may be used; production HA remains optional.
  Identity, private backups/builds, actual encrypted OTA and physical HA pairing
  are now recorded. The owner-authorized text/input session proceeded while the
  independent asset return route remains pending, so this combined gate stays open.
- [ ] For device tests expose only the needed lab HA address/port on the LAN;
  distinguish it from loopback/container names and match the configured origin.
  Verify a real ESP fetch including clock/certificate behavior where applicable.
- [ ] Test image-only, text-only, outlined/positioned text and combined tiles on
  real keys; change visuals and bindings from HA independently of physical presses.
  Verify crop/color/orientation and the upload/label-cache path end to end.
- [ ] Exercise rapid replacements, pages/layers, all keys during rendering,
  invalid assets, network loss, HA/ESP restart, logger clients and deck reconnect.
  Verify API/OTA responsiveness, input ordering, stale-binding protection, queue/
  error counters, timing and internal/PSRAM memory trends.
- [ ] Record download/render/redraw timing and measured memory. Complete or retain
  explicit pending status for the first-click, repeated-recovery, soak and
  electrical gates in [hardware.md](hardware.md) and [testing.md](testing.md).

Acceptance: installation and the core per-key editing flow are demonstrated in
the lab; an actual ESP/deck session separately demonstrates the advertised runtime
features. Report implemented, compiled, unit-tested, HA-container/browser-tested
and hardware-verified evidence distinctly. Publication readiness does not waive
physical/electrical qualification or imply default HACS inclusion.

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
presence semantics in [the contract](runtime-visuals.md). P2 bundles DejaVu Sans
2.37 with its license and deterministic glyph assets. P5 establishes the local HA
test baseline independently of the owner. P7 adds JPEG import on HA while the ESP
continues to receive PNG. P8 resolves input/display ordering and origin
provisioning in [the v2 contract](runtime-v2.md); physical timing/fetch validation
remains pending. Additional ESP codecs,
arbitrary fonts and unlimited graphical composition remain follow-on work.
Direct/chunked uploads are now implemented as the default for library artwork.
Physical HTTP tests still need a reachable chosen HA endpoint; direct artwork
transfers use the existing native API connection.

## Validation and deployment commands

Hardware-independent validation uses synthetic secrets:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/generate_reference_fixtures.py --check
.venv/bin/python tools/generate_render_fonts.py --check
.venv/bin/python tools/generate_render_fixtures.py --check
.venv/bin/python tools/generate_png_fixtures.py --check
.venv/bin/python tools/check_firmware.py --compile
git diff --check
```

Do not upload `.build/firmware/` validation images. Only when a later device
deployment is requested, build example 05 privately with:

```sh
.venv/bin/python tools/check_firmware.py --compile --example 05_home_assistant_runtime --deploy
```

Use the resulting `.build/deploy/05_home_assistant_runtime/build/firmware.ota.bin`
for an encrypted OTA upload to the verified device. Keep local `secrets.yaml`,
compiler logs, backup images and binaries private and ignored. Do not change
dependency pins, flash partitions or the physical power arrangement implicitly.

## Reference material

- [HA/HACS research and architecture decision](decisions/home-assistant-ux.md):
  primary sources, rootless lab findings, backend/editor split, upload/access
  design and the limits of software simulation.
  P5 lab commands are in [the lab guide](ha-lab.md); integration/editor commands
  remain P6–P7 deliverables.

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
