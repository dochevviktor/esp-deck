# Visual editor and artwork library (P7)

P8 update: compatible v2 firmware enables bounded label positioning, named
pages, sparse overlays and navigation/modifier bindings. Library settings now
offer Verify & provision address, also available under Configure → Artwork
address. Existing v1 devices retain basic editing with compiled origins.
See [the v2 guide](runtime-v2.md) for limits, inheritance/clear behavior, input
gating and the normal HA page select entity. The P7 baseline below is retained.

ESP Deck 0.7 bundles an administrator-only **ESP Deck** sidebar panel and links it
from integration settings. Install the integration directory, including its
`frontend/` subdirectory; no dashboard resource or frontend CDN is needed.
Configure retains HA's preset/repair options and links to the editor. The panel
does not replace that options control with a custom-panel redirect.
The [P6 backend](ha-integration.md) remains the sole layout writer and action
executor. The panel can close without stopping bindings or state feedback.
The optional dashboard card was evaluated and omitted: the panel covers editing,
and the existing synchronization entity covers dashboard status without adding
another configuration surface.

## Editing a deck

Select a key in the front-view 5-column × 3-row grid. The editor labels the keys
1–15; the underlying advanced automation indices remain 0–14. Selecting a key,
choosing a preview state, editing or applying a preset never executes its action.

- **Binding:** choose a light, switch, input boolean, script or scene preset.
  Alternatively select press/release actions and target entities. JSON action data
  is optional; complex logic belongs in an HA script. Automation mode exposes
  the existing `esp_deck_key` event and disables managed bindings for that key.
- **Appearance:** upload PNG/JPEG artwork, choose contain/crop, zoom and horizontal/
  vertical offset, then update the crop preview. Set the dynamic label, font
  12/16/20, text/outline/background colors. Text position stays at v1's fixed
  bottom alignment; positioning and pages/layers are P8.
- **State rules:** select an actual HA entity and override the on/off/unavailable
  appearance. Unspecified fields inherit the base tile. A state can inherit,
  clear or select library artwork independently of its label.

Drag keys to swap, or choose a destination and use Move/Swap/Copy. Move inserts
the selected key at the destination and shifts the intervening keys. Clear and
all local layout edits have a 30-step undo history. Arrow keys navigate the grid;
buttons and selectors provide keyboard and touch alternatives to dragging.

Save draft persists without activating. Apply saves local edits and activates
the saved draft. Revisions stay internal. A stale concurrent edit is rejected
without losing the browser's edits; export or reload before trying again.
Reload saved deliberately replaces local edits. Retry synchronization retries
failed tiles. Repair links open HA integration settings. “Rendered” remains
pixels reaching the scheduler, not USB completion or physical display readback.

Export/import and restoring the previous applied layout are in Library settings.
Exports contain portable entity names and artwork hashes, not download
credentials or original image bytes. Importing artwork references requires those
hashes in that deck's library. An HA installation backup must retain both
`.storage/esp_deck*` records and `esp_deck_artwork/`; a layout JSON export alone
is not an artwork backup. Treat action data and labels in exports as private.

## Conversion and storage limits

HA uses the Pillow **12.3.0 supplied by the pinned HA 2026.10.1 image**. It does
not install a different Pillow into HA or modify firmware fixture dependencies.
Image parsing, EXIF/color conversion and all file I/O run in an executor.

| Resource | Bound |
| --- | --- |
| Uploaded formats | Still PNG or JPEG, checked by content |
| Encoded source | 10 MiB, including chunked request bodies |
| Source dimensions | 4096 on either axis; 16,777,216 pixels |
| Concurrent conversion | One; at most three reserved requests including receiving/waiting |
| Upload body deadline | 30 seconds |
| Canonical output | 72×72 RGBA8, non-interlaced PNG, at most 32 KiB |
| Source library | 64 source files across the integration |
| Normalized variants | 256 across the integration |
| Total source + variant bytes | 64 MiB across the integration |
| Deck libraries | 16 |
| Retiring-reference/download grace | 120 seconds |

PNG chunk bounds/CRCs and animation markers are checked before Pillow decoding.
Truncated/malformed inputs, unsupported content, invalid EXIF and invalid color
profiles are rejected. EXIF orientation is applied before transforms; valid ICC
profiles convert to sRGB. Metadata is stripped from outputs. Bicubic transforms
operate on premultiplied alpha into the bounded output, avoiding a large zoomed
intermediate. The ESP performs alpha/background composition and dynamic text.
HA does not flip images into native orientation or rasterize changing labels.

Original encoded sources are private, bounded files used for later recropping;
they may retain source metadata and are never device-downloadable. Filenames are
not identities or paths. Source bytes and normalized bytes use separate SHA-256
identities. Identical normalized bytes deduplicate; their crop/source provenance
tracks the latest normalization. Replacing the same browser filename with new
content produces a new image revision when the normalized pixels change.

Variants are immutable files. Atomic private metadata commits follow successful
file writes. Failures remove newly created uncommitted files; startup reconciles
crash leftovers. Cancellation drains accepted executor work before releasing
its conversion slot/transaction. A quota failure leaves saved layouts intact.
Explicit removal/collection retains draft, applied and previous-applied backup
references, recent uploads and retiring fetches. Collection also removes sources
with no remaining variant. Entry removal revokes its token then deletes its exact
owned artwork. Unloading preserves saved artwork.

## Device access and the v1 origin limit

Stored visuals can contain `asset_id`, a 64-character lowercase SHA-256. The backend
resolves it to a URL and uses the same hash as native `image_revision`. Empty
`asset_id` plus empty URL/revision clears artwork. Library references cannot be
combined with an external URL. Existing advanced external PNG URLs remain valid;
the browser does not fetch arbitrary external URLs for previews.

Editing, uploading, listing, previewing and deleting require an authenticated
administrator. Device GETs use a 256-bit random, per-deck capability in the path:

```text
/api/esp_deck/artwork/<private capability>/<content hash>.png
```

This read-only route serves only that deck's referenced normalized files, with a
bounded grace for previously referenced in-flight work. An unsaved upload alone
does not grant device access. Sources, directory traversal, cross-deck references,
query strings and unknown hashes are rejected. Invalid requests have a global
120-per-minute threshold; valid capabilities remain usable during that limit.
Response bytes are owned before sending, so garbage collection cannot truncate
an in-flight response. Responses are not HTTP-cacheable.

Revoke download links persists a new token and resynchronizes the deck. New reads
using the old token fail immediately; already accepted responses can finish.
Capabilities never appear in editor APIs, layout export or diagnostics. The HA
log filter redacts these paths in normal log/access handlers. A reverse proxy's
own access logs are outside HA: exclude or redact this route there too. A path
credential does not encrypt LAN HTTP traffic; use non-sensitive artwork or
verified HTTPS. No HA user/admin token is sent to the ESP.

The address defaults to HA's configured internal URL. Library settings can
change it, but **v1 firmware must already allow that exact origin**. P7 does not
provision firmware origins. An origin or fetch error stays visible with a retry/
repair route. P8 owns the device-side provisioning and reachability wizard.
The lab uses its configured `http://ha:8123`; a physical ESP needs a reachable
LAN address matching its compiled allowlist. No production HA is required.

The firmware's existing cache identity includes URL, content revision, image fit
and background color. Text/font/text-color/outline-only edits reuse the background
with **zero additional device GETs**. Fit/background changes can require another
fetch. Normalization reduces network and decoder work; it does not change the
15,606-byte native BMP or two 8191-byte USB reports.

## Preview and reproducible validation

`frontend/` contains plain custom-element source and an esbuild **0.25.12** lock.
The tested build uses Node **24.13.0**, npm **11.6.2**. The build extracts the
firmware's DejaVu Sans 2.37 glyph coverage/metrics and ships its license beside
the module. Runtime code has no external dependencies or font downloads.

```sh
npm ci --prefix frontend --ignore-scripts --no-audit --no-fund
npm run build --prefix frontend
npm run check --prefix frontend
npm test --prefix frontend
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/ha_lab.py down
.venv/bin/python tools/ha_lab.py up
.venv/bin/python tools/ha_lab.py test
.venv/bin/python tools/check_firmware.py --compile
```

Preview uses the bundled 4-bit glyphs and the firmware's layout, interpolation,
outline and rounding rules, not browser font rendering. All eleven native BMP
fixtures match pixel for pixel in the JS tests. A bounded RGBA PNG reader avoids
browser canvas premultiplication/color-conversion differences. The host suite
normalizes ten large-photo/alpha/palette/greyscale/EXIF/crop cases and compares
every resulting PNG's RGBA bytes with the **production C++ PNG decoder**.

The HA-engine tests cover atomic failures, quotas, cancellation drain, concurrent
drafts, permissions, token redaction/revocation, cross-device and traversal
rejection, backup/reference GC and in-flight retention. Real-container browser
tests exercise upload/crop/apply/relabel/move, unchanged download counts for
labels, replacement at the same filename, keyboard/touch controls, conflicting
drafts, and closed-browser actions. See [test evidence](testing.md) for the
executed counts and remaining hardware gates. HACS distribution validation is P9.
