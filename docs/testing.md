# Validation and remaining hardware gates

## P9 local installation and lifecycle qualification, 2026-10-11

Implemented: version 0.9.0's deterministic allowlisted HA ZIP, `hacs.json`, bundled
editor/English translations/licences/local brand assets, private archive staging,
an owned-lab upgrade installer, pinned upstream distribution validators and CI
checks. See [installation and release instructions](release.md). The archive has
no firmware, local credentials or build trees. The installer retains old code and
HA data; fresh lab setup archives the previous lab. The normal lab remains bound
only to loopback. Nothing was published or committed by this session.

Hassfest exposed an invalid repair translation combining `description` and
`fix_flow`, and a missing config-entry-only schema. Both are fixed. Repair flows
now receive their bounded error placeholder. Deleting a disabled config entry
before component setup now loads the persisted artwork metadata so its token
and artwork are also revoked/removed. Incompatible example-04 bench firmware gets
concrete example-05/private-build/OTA/reload guidance. The editor accurately says
when its existing address-verification operation completed a device fetch.

Compiled: all **seven** supported ESP32 configurations with temporary synthetic
secrets, unchanged ESPHome 2026.9.0 / ESP-IDF 5.5.5 and USB configuration. Example
05 reports 115,011 B static RAM and 1,093,983 B flash; these are linker estimates,
not measured runtime memory. The fresh encrypted host virtual deck compiled,
and the updated editor bundle reproduces. No synthetic binary was uploaded.

Unit-tested: **65 Python unittest cases**, with ASan/UBSan on the nine native
executables and `UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1`. The final lab/
packaging follow-ups were rechecked with their eleven targeted host cases.
**Five frontend tests** pass, including twenty pixel-exact renderer fixtures.
All pinned upstream/font/render/PNG fixture checks pass. New host cases cover
determinism, standalone extraction, complete archive contents, exclusion of local
secrets/builds/caches, symlinks, duplicate/traversal/missing/oversized entries and
rejection before destination creation. The lab executes archived integration bytes.

HA-engine-tested: **62 pytest cases** pass on real HA 2026.10.1, with mocked native
actions. Four new cases cover bench upgrade guidance, rejection below the HA
minimum, repair placeholders and deleting a disabled entry before setup. The
upstream HA HTTP application's existing deprecation warning remains. No skips.

HA-container/browser-tested: **28 scenarios** pass in a fresh HA 2026.10.1 /
frontend 20260930.3 installation with the encrypted virtual deck. The declared
minimum and current stable HA release are the same version as checked on this
date; no earlier HA compatibility is claimed. Existing reload/restart/cache/
state-feedback/input-fence/page tests remain passing. P9 adds archive identity/
frontend serving, the editor's prefilled-address probe/upload/binding workflow,
actual P8 code installation and upgrade to the ZIP, cold configuration backup/
restore, entry removal and legacy layout-store migration through real restarts.
Saved artwork, layouts, pages, overlays and bindings survive upgrade/restore;
entry removal revokes old artwork access and preserves the ESPHome association.
The final P9-only recheck also exercises direct code uninstallation and restart.

Distribution validation: **not passed yet**. The pinned Hassfest run now reports
only the manifest's missing documentation URL. The actual upstream HACS manifest
schemas also require documentation/issue-tracker URLs; the checkout has no Git
remote or provided repository identity, and no URLs/maintainers were invented.
Local packaging tests do not waive this. Full online HACS repository validation,
GitHub-authorized HACS custom-repository install/update, publication and default
store submission are separate pending gates. The CI job is provided but no remote
CI run is claimed.

Hardware-verified: **none newly for P9**. No ESP was contacted or flashed; example
04 remains installed. Real ESP fetching/TLS/NVS, physical labels/artwork/input
timing, first-click, electrical, repeated recovery and soak tests remain pending.
Lab HTTP and simulated USB completion are not physical acceptance. No native USB,
UART0, transfer framing, dependency pin or unswitched-VBUS rule changed.

Commands run:

```sh
SANITIZE=1 UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/check_firmware.py --compile
.venv/bin/python tools/generate_reference_fixtures.py --check
.venv/bin/python tools/generate_render_fonts.py --check
.venv/bin/python tools/generate_render_fixtures.py --check
.venv/bin/python tools/generate_png_fixtures.py --check
npm run build --prefix frontend
npm run check --prefix frontend
npm test --prefix frontend
.venv/bin/python tools/package_release.py --check
.venv/bin/python tools/package_release.py
.venv/bin/python tools/ha_lab.py up --fresh --artifact .build/release/0.9.0/esp_deck.zip
.venv/bin/python tools/ha_release.py .build/release/0.9.0/esp_deck.zip
.venv/bin/python tools/ha_lab.py test
.venv/bin/python tools/ha_lab.py test-release
.venv/bin/python tools/check_distribution.py
git diff --check
```

The [sanitized P9 acceptance record](../tests/ha_lab/acceptance-p9-2026-10-11.json)
records the tested archive/source/image identities, counts and pending gates.
The 28-case full run and final four-case P9 recheck passed with no skips.
The distribution command fails for the metadata gate described above. Private
logs, JUnit, cold backups, screenshots and binaries remain in ignored `.build/`.
The installer's first development attempt exposed expired-token polling and
SELinux labels on moved files; it now refreshes authentication after unauthenticated
readiness and recreates only its stopped owned HA container to relabel its private
mount. Subsequent archive installation and lifecycle runs use that corrected path.

## Runtime capabilities, positioning and safe pages, 2026-10-11 (P8)

Implemented: runtime v2 capabilities and separate fixed-signature actions;
bounded text boxes/alignment with unchanged default pixels/cache identities;
explicit origin provisioning through the existing encrypted API and HTTP worker;
and a persisted, validated finite origin record. HA 0.8 stores up to eight pages
and four sparse overlays, resolves only the current 15 keys, and exposes a normal
page select plus editor navigation/modifier controls. v1 remains compatible.
See [the contract, input ordering audit and usage](runtime-v2.md).

Input safety uses applied request revisions, USB generations and capture epochs,
with captured press/release binding contexts. A bounded native action-response
channel polls at approximately 100 ms, resynchronizing on disconnect, overflow,
lost acknowledgements or one-second lease/response expiry. It does not infer
display completion from `rendered` or order legacy event entities against status.
Already accepted actions retain their context across simultaneous navigation;
transitions/failures reject new presses on affected keys. Whole-deck atomicity
and physical display readback are not claimed.

Compiled: all seven supported firmware examples using temporary synthetic secrets
on unchanged ESPHome 2026.9.0 / ESP-IDF 5.5.5 pins. The final example 05 validation
reports 115,011 bytes static RAM and 1,093,983 bytes flash; these compiler figures
are not runtime heap/PSRAM measurements. The final test-only host deck and bundled
frontend also compile. The installed lab integration matches the source tree.
No validation image was uploaded.

Unit-tested: 60 Python unittest cases, including nine native executables; five
frontend tests with twenty exact renderer/preview fixtures; all pinned upstream,
font, rendering and PNG fixture checks. New tests cover applied versus rendered,
same-image context changes, stale IN epochs/output generations, retained release
pairs, failed tiles, lost acknowledgements/lease expiry, overflow, bounded origins,
decode/clock failures, cancellation drain and position limits. Position-only
updates reuse retained artwork without another fetch. The initial ASan/UBSan
attempt failed at link time because `/usr/lib64/libasan.so.8.0.0` was missing.

Sanitizer follow-up, 2026-10-11: both `libasan` and `libubsan` are now installed
at `16.2.1-2.fc44.x86_64`, with GCC 16.1.1. Enabling the checks exposed an empty
vector's null source passed to a zero-length `memcpy` in the P8 fake fetcher.
An empty-buffer guard now skips that copy. All 60 host tests pass without
sanitizer diagnostics, including nine native executables compiled and run with
ASan/UBSan. `UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1` made any UBSan
finding fatal, avoiding the default recoverable diagnostic's misleading unittest
success. This follow-up changes only the test helper and documentation;
firmware builds, HA/browser results and hardware status retain their earlier
evidence below. No firmware rebuild, deployment, hardware test or remote CI run
was performed for this guard.

HA-engine-tested: 58 pytest cases against real HA 2026.10.1 with mocked native
actions. New cases cover page/overlay bounds, inherit/clear precedence, inactive
artwork references, storage/export/import, v1 capability rejection, captured
release bindings, rapid changes, momentary ownership and simultaneous accepted
press/navigation delivery. Existing authorization, migration, storage failure,
coalescing, registry rename and unload coverage remains passing.

HA-container/browser-tested: 24 scenarios against real HA 2026.10.1 and the
encrypted virtual deck. Five P8 scenarios verify capability discovery, actual
device-side probe-route fetching and failed-address retention, finite origin
persistence across virtual reboot, same-pixel/different-binding changes without
new USB image uploads, captured releases, concurrent navigation, failed and
transitioning keys, rapid pages, reconnect during output, held modifier release,
FIFO overflow and overlay reset. Chromium exercises page creation/naming,
positioning, inherit/clear, navigation, Apply and operation after closing the
editor. The v1 regression starts from an explicit one-page layout so the complete
suite is repeatable after P8 has left a multi-page demo in the private lab.

Hardware-verified: none newly for P8. The ESP was not flashed or contacted;
example 04 remains the bench baseline. ESP-side fetch/TLS/NVS, physical text and
display/input timing, electrical, first-click, repeated-recovery and soak gates
remain pending in [hardware.md](hardware.md). The lab's native renderer and
simulated USB completion do not waive them. P9 is next; HACS/Hassfest/distribution
remain separate unfinished work.

Commands run:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/check_firmware.py --compile
.venv/bin/python tools/check_firmware.py --compile --example 05_home_assistant_runtime
npm run build --prefix frontend
npm run check --prefix frontend
npm test --prefix frontend
.venv/bin/python tools/generate_reference_fixtures.py --check
.venv/bin/python tools/generate_render_fonts.py --check
.venv/bin/python tools/generate_render_fixtures.py --check
.venv/bin/python tools/generate_png_fixtures.py --check
.venv/bin/python tools/ha_lab.py up --fresh
.venv/bin/python tools/ha_lab.py down
.venv/bin/python tools/ha_lab.py up
.venv/bin/python tools/ha_lab.py test
SANITIZE=1 UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 .venv/bin/python -m unittest discover -s tests -v
git diff --check
```

The sanitizer command passed after the follow-up above. The full host suite,
HA-engine and 24 live scenarios passed with no skips in their respective runs.
Raw logs, JUnit, credentials, screenshots and binaries remain private/ignored;
[sanitized P8 acceptance metadata](../tests/ha_lab/acceptance-p8-2026-10-11.json)
records artifact/version identities and results. The lab remains running with a
synthetic page-navigation example. Earlier acceptance records below are historical.

## Visual editor and artwork library, 2026-10-11 (P7)

Implemented: ESP Deck 0.7.0's bundled admin panel, 5×3 select/move/swap/copy/clear
and undo, entity/action presets, appearance/state rules, draft/apply/conflict
feedback, touch/keyboard controls and retry/repair navigation. Bounded PNG/JPEG
uploads normalize off HA's event loop to immutable 72×72 RGBA PNGs. Stored hashes
resolve to revocable per-deck device paths; editing/preview routes remain admin
authenticated. Private source/variant quotas, atomic writes, cancellation drain,
reference/backup retention, garbage collection and log redaction are implemented.
[Usage, limits and architecture](visual-editor.md).

Compiled: **seven ESP32 firmware configurations** using temporary synthetic
secrets, the test-only ESPHome host deck, and the bundled frontend with Node
24.13.0 / esbuild 0.25.12. The production firmware/protocol/USB code and dependency
pins did not change. The virtual fetcher adds sanitized byte counters only.
`npm run check --prefix frontend` verifies the shipped bundle is reproducible.

Unit-tested: **59 Python unittest cases**, including **eight native C++
executables**, plus **four frontend tests**. Ten normalized alpha, EXIF, palette,
greyscale, large-photo and crop outputs match the production PNG decoder's RGBA
bytes. Invalid/animated/truncated images, malformed EXIF, metadata stripping,
limits and unchanged filenames are covered. Browser preview code matches all
**eleven native renderer BMP fixtures pixel for pixel**; its PNG reader preserves
RGBA without browser premultiplication. All existing upstream/font/render/PNG
fixture checks pass. No new sanitizer result is claimed for this session.

HA-engine-tested: **50 pytest cases** using HA 2026.10.1 with mocked native
actions. Seven added cases cover authentication/authorization, references versus
unsaved uploads, cross-deck access, traversal/query rejection, capability
revocation/redaction/rate limits, source refresh/deduplication, quota/storage
failure, cancellation, concurrent edits, reference/backup GC and in-flight bytes.
Removing an entry also removes its empty owned artwork directory.

HA-container/browser-tested: **19 scenarios**, against real HA 2026.10.1 /
frontend 20260930.3 and the encrypted virtual deck. A fresh synthetic lab was
created with `up --fresh`; the earlier private lab was archived, not erased.
The full P4/P6 regression suite passes. Three P7 scenarios exercise the editor
from the UI: light/scene binding, upload/crop/apply, relabel, replacement at the
same source filename, moving keys, keyboard/touch/clear/undo, conflicting drafts,
unauthenticated/bad/oversized uploads and operation after the browser closes.
The virtual deck fetches at most 32 KiB for each normalized artwork image;
label-only changes add **zero downloads and zero downloaded bytes**. A background
color change can fetch again under v1's existing composed-background cache rule.

The full regression caught HA's custom configuration-panel association hiding
the existing options/repair control. The integration keeps the normal Configure
menu, adds a link to the sidebar editor there, and browser-tests both paths.
No manual frontend resource registration is used. Desktop/mobile screenshots,
raw logs, tokens, layouts and binaries stay private under `.build/ha-lab/`.
Sanitized [P7 acceptance metadata](../tests/ha_lab/acceptance-p7-2026-10-11.json)
records the versions, source/artifact identities and test counts.

Hardware-verified: **none newly for P7**. No device was flashed or contacted;
example 04 remains the installed bench baseline. Actual ESP fetch/TLS, physical
display/input timing, electrical, first-click, repeated-recovery and soak gates
remain pending. Origin provisioning/positioning/pages are P8; HACS/Hassfest,
distribution and physical qualification remain P9. No remote CI run is claimed.

Commands run:

```sh
npm ci --prefix frontend --ignore-scripts --no-audit --no-fund
npm run build --prefix frontend
npm run check --prefix frontend
npm test --prefix frontend
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/check_firmware.py --compile
.venv/bin/python tools/ha_lab.py up --fresh
.venv/bin/python tools/ha_lab.py down
.venv/bin/python tools/ha_lab.py up
.venv/bin/python tools/ha_lab.py test
git diff --check
```

## Home Assistant integration backend, 2026-10-11 (P6)

Implemented: `custom_components/esp_deck/` version 0.6.0 with config/options and
repair flows, exact v1 signature discovery, stable registry associations, a
coalescing backend writer, actual-state entity presets, press/release actions,
exclusive advanced automation events, and admin-only services/WebSocket APIs.
Versioned draft/applied layouts use private atomic storage, optimistic revisions,
a retained previous applied layout, migration and portable export/import.
Storage errors/corruption do not activate new layouts. The adapter uses HA's
existing ESPHome connection through services, with no credential access, extra
native client or duplicate physical device. [Usage and migration](ha-integration.md).

Compiled: all **seven firmware configurations** with temporary synthetic secrets,
plus the unchanged test-only ESPHome host target. Firmware/protocol/USB code and
dependency pins were not changed. No validation image was uploaded.

Unit-tested: **54 Python unittest cases**, including **seven native C++
executables** and all pinned protocol/font/render/PNG fixture checks. The lab
staging/lifecycle tests also pass with integration staging enabled.

HA-engine-tested: **43 pytest cases** in the pinned HA image with mocked native
transport (41 P6 cases plus the two P4 cases). Coverage includes bounded layouts,
explicit clears, presets, storage migrations/future rejection, actual atomic-write
failures, corruption preservation, concurrent edit conflicts, backup/import,
registry renames/missing/disabled identities, setup/handoff, source re-enabling,
coalescing/no-op sync, current-state feedback, restart/session revisions,
failed-job retries, competing writers, counter exhaustion, release pairing,
contexts, stale native completions, unload during I/O, transaction draining,
binding overflow, malformed native responses, redacted diagnostics and every
admin service/WS permission boundary. HA's upstream HTTP application deprecation
warning remains; no project test is skipped.

HA-container/browser-tested: **16 scenarios** using HA 2026.10.1/frontend
20260930.3 and the real encrypted virtual-deck API. Nine retain P4 regression
coverage; seven add direct custom-integration installation/setup, light/preset
bindings with no browser, draft/apply/export/import, label-cache reuse, no-op
sync, session/target renames, actionable asset failures retaining pixels,
unload/reload and layout persistence, HA restart/outage input suppression,
virtual reboot/replay, the real options API, and opening the configuration menu
in Chromium. P4 and P6 are explicitly handed control for their own tests; they
are not allowed to run competing replay/binding paths.

Real-source review/testing found two integration details worth retaining: HA
`Store` logs some write failures rather than raising them, so the storage adapter
detects failure before acknowledging an edit; HA HTTP startup precedes config-entry
loading, so restart tests wait for the entry. The browser test clicks the custom
button host to include HA's slotted icon in pointer hit-testing.

The [sanitized P6 acceptance record](../tests/ha_lab/acceptance-p6-2026-10-11.json)
records image/test identities. Raw logs, JUnit, screenshots, tokens and host
executables stay under ignored `.build/ha-lab/`. Existing lab credentials/data
were retained. The lab is left running with the managed integration enabled and
synthetic light/scene presets. A pinned HA engine CI job was added; it has not
been run on remote CI. HACS installation, Hassfest, release branding/metadata,
the P7 visual editor and P8 pages/origin provisioning remain later gates.

Hardware-verified: **none for P6**. No physical flash, OTA, USB or ESP asset fetch
was performed. Example 04 remains installed. `rendered` still means scheduler
desired pixels, not physical readback. Electrical, first-click, repeated-recovery,
soak and P3/P9 physical-runtime gates remain pending.

Commands run:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/check_firmware.py --compile
.venv/bin/python tools/ha_lab.py down
.venv/bin/python tools/ha_lab.py up
.venv/bin/python tools/ha_lab.py test-engine
.venv/bin/python tools/ha_lab.py test
git diff --check
```

## Independent HA lab, 2026-10-11 (P5)

Implemented: reproducible `up/status/test/down` tooling, private synthetic HA
configuration/accounts/artwork, ownership-scoped rootless resources, separate
image/test locks, encrypted ESPHome host virtual deck, bounded host fetching,
simulated input/output/recovery, HA engine tests and a browser smoke test.
`up --fresh` archives the previous lab and initializes fresh accounts/storage.
No owner's HA data, device secrets, hardware or GitHub account is required.
See [the lab guide](ha-lab.md).

Compiled: the ESPHome 2026.9.0 host executable inside its pinned image, and all
seven ESP32 firmware configurations with temporary synthetic secrets using
`tools/check_firmware.py --compile`. Firmware estimates remain those below;
no firmware code, USB transport/scheduling or dependency pin changed in P5.

Unit-tested: **54 Python unittest cases**, including the same **seven native C++
executables**. Six new cases cover resource ownership/inspection failures,
private staging with byte-identical production sources/API definitions, scoped
teardown, and host HTTP byte/type/redirect limits. Upstream protocol, font,
rendering and PNG fixture checks run in this suite and pass. No new sanitizer
or remote CI result is claimed.

HA-engine-tested: **two pytest cases** run inside the pinned HA image with real
script/template/automation engines and mocked native actions. They verify full
layout replay, revision queries, numeric text/session preservation, actual state
feedback, and late service registration with no subsequent sensor change.

HA-container/browser-tested: **nine scenarios**, all passing after a clean
`up --fresh`, against **HA 2026.10.1 / frontend 20260930.3** and the compiled
encrypted virtual deck. They verify real ESPHome config-flow pairing, required
action responses, rejection of unencrypted/wrong-key clients, 31 entities/four
actions, all 15 key pairs, state-driven on/off/unavailable feedback, duplicate/
conflicting/stale revisions, unchanged replay with no fetch/output, relabel cache
reuse, deliberate refresh, 404/bad PNG/origin failures, registry renames, API
logger clients, simulated output failure/delay/reconnect, HA outage/restart with
no press replay, and a virtual reboot with a digit-only session. Chromium logs
into HA and opens the virtual device UI; bindings work after the browser closes.
The initial minimum supported/tested HA baseline is 2026.10.1, not a claim that
earlier releases are incompatible. HACS/custom editor tests remain future work.

Live testing found P4's unsupported `has_service()` HA template. Its replay now
listens to `service_registered` events and waits for a valid visual session.
Entity registry IDs survive renames; the manual helper's entity-name reference
needs updating after a rename. A script error can return HTTP 200 with an empty
response, so clients must check explicit acceptance. These behaviors are tested
and guide P6's registry adapter and synchronization controller.

Sanitized locks and [acceptance metadata](../tests/ha_lab/acceptance-2026-10-11.json)
are under `tests/ha_lab/`. Raw build/HA/
deck logs, JUnit reports, browser screenshot and per-run versions/results remain
private in ignored `.build/ha-lab/`. Scoped teardown and restart were exercised;
unrelated existing containers were preserved. SELinux stayed enforcing.

Hardware-verified: **none for P5**. No physical flash, OTA, USB transaction or ESP
asset fetch occurred. Example 04 remains installed. Host malloc/HTTP/process
timing and simulated output cannot qualify PSRAM, IDF networking/DMA, panel pixels,
electrical power, first-click behavior, repeated recovery or physical P9 gates.

Commands run:

```sh
.venv/bin/python tools/ha_lab.py up --fresh
.venv/bin/python tools/ha_lab.py test
.venv/bin/python tools/ha_lab.py status
.venv/bin/python tools/ha_lab.py down
.venv/bin/python tools/ha_lab.py up
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/check_firmware.py --compile
git diff --check
```

## Home Assistant runtime controls, 2026-10-11 (P4)

Implemented: generic native set/clear/refresh/status actions with descriptions
and bounded responses, a visual-session diagnostic, 15 physical press/release
event entities, exclusive runtime visual ownership, and HA scripts for serialized
patches and authoritative layout replay. Example 05 has no fixed HA entity IDs
or local bulb/arrow actions. Example 04 and USB framing, descriptor correction,
DMA allocation and external VBUS behavior are unchanged. See [the HA integration
guide](home-assistant.md) and [contract](runtime-visuals.md).

Unit-tested: **48 Python cases**, including **seven native C++ executables**.
Production visual API tests cover queued/rendering/rendered/failed responses,
rejections retaining accepted/rendered revisions, duplicate/conflicting/stale
requests, sessions, clear/refresh, failed fetches preserving pixels, label cache
reuse, deck restoration without fetch, and unchanged replay without a new
scheduled image. Response snapshots own their session strings. Production key
publication tests cover all 15 keys, repeated reports, simultaneous edges, stale
generations, initial/held baselines, overflow synchronization, disconnect without
fabricated release, reattachment and rejection of direct runtime image changes.

HA tests execute the actual helper/replay templates and sequence logic against
a fake API: current entity state, all fields for 15 keys, HA-only layout edits,
revision queries after HA restart, new ESP sessions, explicit failures, integer
exhaustion, and event restore/availability guards. Dictionary templates preserve
numeric-looking labels and digit-only sessions as strings. Replay rechecks late
action registration with a bounded wait. Schema tests enforce encryption/PSRAM/
loader/ownership requirements and unique bounded event keys. Pinned reference,
font, rendering and PNG fixture checks all pass.

Compiled: all **seven** configurations with synthetic secrets, including example
05, on ESPHome 2026.9.0 / ESP-IDF 5.5.5. The checker verifies existing USB console/
descriptor/FIFO constraints and the new example's HTTP/TLS settings; CI includes
example 05. Remote CI was not executed here.

Hardware-verified: **none for P4**. No upload, live HA server test or device asset
request occurred. Example 04 remains installed. The extended plan assigns the
HA lab/integration/editor to P5–P8 and physical acceptance to P9. Before device
tests, establish HA version/response support, a reachable PNG origin and deployment
readiness. First-click, electrical, heap/timing and repeated recovery gates
remain open. Native assertions and warnings-as-errors were used;
no local ASan/UBSan run is claimed.

Commands run successfully:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/generate_reference_fixtures.py --check
.venv/bin/python tools/generate_render_fonts.py --check
.venv/bin/python tools/generate_render_fixtures.py --check
.venv/bin/python tools/generate_png_fixtures.py --check
.venv/bin/python tools/check_firmware.py --compile
git diff --check
```

## URL loading and caching, 2026-10-11 (P3)

Implemented: opt-in HTTP(S) asset loading on one persistent worker, exact origin
restrictions, validated TLS including certificate dates/clock readiness, strict
bounded PNG decoding, retained per-key/shared backgrounds, and the typed visual
bridge to `Store`/renderer/scheduler. Graphics share a 2 MiB PSRAM root with
separate native-image and cache caps. No input/USB framing or power behavior
changed. The [loader contract](asset-loading.md) records limits, supported PNG
formats, timeout/drain behavior, and the pinned inflater's provenance.

Unit-tested: **37 Python cases**, including six native C++ executables. New tests
cover PNG CRC/chunk order, standard colour types and legal depths, all row
filters, palette/transparency, exact zlib completion, truncated/malformed data,
dimension/byte caps and an expansion bomb. The largest RGBA16 input exercises
the filtered-source allocation bound. Fixtures reproduce and the vendored
inflater's documented patch reverses to its pinned upstream SHA-256.

Pipeline simulations exercise shared cache hits, explicit content revisions,
label changes during/after download without refetching, fifteen retained key
backgrounds plus staging/eviction, allocation failures, old-tile preservation,
stale tokens, delayed cancellation, and USB reconnect without a new download.
Production HTTP transaction code runs against fake IDF transports to check
status/redirect/auth policy, configured TLS trust/hostname settings, unset-clock
rejection, body/header limits, stalled I/O and clock wrap, cancellation and
cleanup. These are not a live TLS/HTTP server test or a FreeRTOS timing test.

Compiled: all six examples with synthetic secrets, including the new
`asset_loader_probe`. The checker inspects the actual generated SDK and compiler
configuration for custom HTTP transport, HTTPS, CA bundle, certificate-date
validation, the 8 KiB HTTP header/trailer limit, and the existing USB rules.
The loader probe is also in CI's build matrix; remote CI has not run here.

Hardware-verified: **none for P3**. No upload or physical asset request was made.
The actual asset origin/PNG and device reachability check remain pending; the
probe uses a configurable placeholder. Example 04 remains the last recorded
hardware baseline. Internal heap/TLS coexistence, step/download/render timings,
key/API/OTA responsiveness and network/reconnect tests still need a device run.
At P3 validation time, the local ASan/UBSan libraries were unavailable; no
sanitizer pass was claimed for that run. See the later P8 follow-up above.

Commands run successfully:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/generate_png_fixtures.py --check
.venv/bin/python tools/generate_reference_fixtures.py --check
.venv/bin/python tools/generate_render_fonts.py --check
.venv/bin/python tools/generate_render_fixtures.py --check
.venv/bin/python tools/check_firmware.py --compile
git diff --check
```

## Local rendering, 2026-10-11 (P2)

Implemented: bounded RGB(A)/BGR(A) source views, aspect-preserving contain/crop,
premultiplied-alpha bilinear sampling, outlined runtime text with licensed/pinned
DejaVu Sans 2.37 at 12/16/20 px, exact native BMP encoding, and PSRAM-only
workspace/image allocation. `render_esphome.h` bridges completed ESPHome images;
PNG decoding and fetching/cache were added in P3 above; P4 adds HA controls. See
[rendering](rendering.md) for the precise pixel, lifetime and memory rules.

Unit-tested: **31 Python cases**, including four native C++ executables. The
renderer suite checks source bounds and invalid styles/UTF-8, partial-work
cancellation, source/workspace lifetime, PSRAM allocation failure/capability
flags/budget reclamation, stale render rejection, alpha correctness, aspect
scaling, font coverage, outlined text, wrapping/truncation and unsupported glyphs.
The resulting asymmetric BMP and both key-0 image pages match the existing
upstream fixtures exactly. Eleven additional native-renderer regression snapshots
have been visually inspected through `.build/render-preview.png`; these are not
independent Pillow font/scaling fixtures. Font generation reproduces using the
bundled source and pinned ESPHome/FreeType versions.

Compiled: the four numbered examples plus the new `renderer_probe`, with
synthetic secrets. A second renderer-probe build in a fresh temporary build
directory also passed. That clean build matters: the initial probe exposed
ESPHome's omission of the build-local USB override from discovered built-ins.
The override now explicitly links its public IDF USB target into the application
after target creation. The checker verifies the application receives USB's
include path as well as compiling the pinned patched source. No installed SDK
file, packet framing or USB startup sequence changed. CI now includes both
example 04 and the renderer probe; remote CI itself has not run in this session.

Hardware-verified: **none for P2**. No firmware was uploaded. Example 04 remains
the last recorded hardware baseline; new fonts, PSRAM rendering load, step
timings and display appearance await device testing. At P2 validation time,
local ASan/UBSan runtimes were unavailable, so that run's native assertions and
counting allocators established only the exercised paths, not a sanitizer pass.
See the later P8 follow-up above.

Commands run successfully:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/generate_reference_fixtures.py --check
.venv/bin/python tools/generate_render_fonts.py --check
.venv/bin/python tools/generate_render_fixtures.py --check
.venv/bin/python tools/check_firmware.py --compile
git diff --check
```

## Runtime foundations, 2026-10-11

P0/P1 are implemented: the [runtime contract](runtime-visuals.md), bounded owned
visual state, request/session validation, coalescing and atomic render commit,
plus immutable native-image ownership through the scheduler and transport.
At that checkpoint the host suite passed **28 Python cases**, including three
native C++ executables. All four numbered examples compiled with
synthetic secrets. P2–P4 were completed subsequently as recorded above; examples
01–04 continue to expose no URL fetching, font rendering or runtime API action.

New tests exercise image/text/combined/clear patches; strict UTF-8, URL, colour,
font and size validation; stale/conflicting/duplicate revisions; session mismatch;
out-of-order completion; unchanged visual suppression; failed rendering and
allocation preserving the old tile; all 15 coalescing slots and USB reconnect.
Ownership tests replace images during either page, evict cache references, check
allocation limits/reclamation, read retained bytes against the unchanged upstream
fixtures, and hold stale jobs across generations. Production-transport simulations
delay cancellation during page 1 or 2 on both EP0 and interrupt OUT and check that
owned pixels remain allocated until callbacks retire. The HA helper's templates
are tested locally, and its fixed argument signature validates against pinned
ESPHome; this is not a live HA integration test.

Commands run for this stage:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/generate_reference_fixtures.py --check
.venv/bin/python tools/check_firmware.py --compile
git diff --check
```

GCC warnings are errors and assertions remain enabled. Local sanitizer runtimes
were absent during this stage; no ASan/UBSan pass was claimed then. Counting/poisoning test
allocators cover the exercised ownership paths, not every possible execution.
The owner reconfirmed `192.168.10.238`; two ICMP requests received replies. This
is reachability only, not a new firmware/USB/HA qualification. No firmware upload
was made, and the installed example 04 remains the recorded hardware baseline.

## Earlier hardware sessions, 2026-10-10

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
| Implemented | Codec, scheduler, USB transport/entities/images/recovery, diagnostics, desktop probe, private builds, source-pinned IDF descriptor hook, P0/P1 visual contract/owned images, P2 renderer/fonts/PSRAM, P3 HTTP(S)/PNG/cache, P4 native API responses/key events/HA replay |
| Unit-tested | 54 Python cases including seven native C++ suites, PNG/pipeline/HTTP guards, renderer/font fixtures, runtime ownership/visual API, production key publication, HA helper/replay templates, captured descriptors, production USB simulations, build/lab ownership guards and private staging |
| HA engine / real sessions | Two HA engine cases with mocked native actions; nine real HA 2026.10.1/native-API/browser scenarios against the test-only virtual deck |
| Compiled | Examples 01–05 plus renderer_probe and asset_loader_probe with synthetic credentials, plus P5's ESPHome host virtual deck. Earlier private deployments used examples 01, 02 and 04; ESP-IDF 5.5.5 / ESPHome 2026.9.0 |
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
machine lacked `/usr/lib64/libasan.so.8.0.0`. Those local C++ tests ran with warnings as
errors and assertions enabled, without sanitizers. `SANITIZE=1` enables ASan/UBSan
on a machine with those runtimes; the CI workflow requests them. No sanitizer
pass was claimed for that earlier run. The P8 follow-up above records the later
successful local check with both `libasan` and `libubsan` installed.

Latest synthetic builds, 2026-10-11, including P0–P4 and the IN-64 / OUT-512 path:

| Example | Static RAM estimate | Application flash estimate |
| --- | ---: | ---: |
| 01 USB probe | 108,371 B / 341,760 B | 783,987 B / 8,126,464 B |
| 02 keys/brightness | 110,835 B / 341,760 B | 815,119 B / 8,126,464 B |
| 03 images/HA | 111,307 B / 341,760 B | 870,879 B / 8,126,464 B |
| 04 standalone hardware test | 110,995 B / 341,760 B | 847,051 B / 8,126,464 B |
| 05 HA runtime | 114,515 B / 341,760 B | 1,075,407 B / 8,126,464 B |
| Renderer probe | 111,675 B / 341,760 B | 882,023 B / 8,126,464 B |
| Asset loader probe | 113,635 B / 341,760 B | 1,055,271 B / 8,126,464 B |

These linker estimates exclude runtime USB/task/network allocation and are not
free-heap measurements. The renderer probe links the rendering path and defers
its pixel allocations until after PSRAM initialization. The loader probe includes
the visual store and fetch/decode/render pipeline; service/graphics and worker/TLS
allocations occur at runtime. Example 05 additionally links the real native API
responses and event entities. None of these estimates measures peak heap.
The checker also verifies the actual generated control
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
