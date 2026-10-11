# Runtime v2: capabilities, origins and safe pages

P8 extends example 05 with four new encrypted native actions. The four v1
signatures, manual helper scripts and edge entities remain compatible. The
installed example 04 bench firmware has neither runtime version; a requested
firmware update is still required before using these features on the physical
deck. Software tests do not qualify actual USB timing or the power path.

## Capability discovery and positioning

`get_deck_capabilities()` returns the boot session, protocol version 2, model
`0FD9:0060`, 15 keys at 72×72, fonts 12/16/20, glyph policy, field mask, limits,
configured exact origins, provisioning status and input/status semantics.
HA checks discovery signatures and this record. A v1 device keeps the basic
editor; positioning, provisioning and navigation controls require their
capabilities. The backend also rejects unsupported layouts, including imports.

`set_key_visual_v2` preserves the v1 fields and adds `binding_context` and six
integer position arguments. Field bit 128 selects the whole text box/alignment;
all v2 arguments are always present. HA supplies a fresh opaque 32-character
context for each key's binding/page/overlay context. Firmware permits bounded
alphanumeric contexts up to 32 bytes. v1 has no context argument and rejects
bit 128. Mixing writers remains unsupported and is detected.

| Field | Default | Bounds/meaning |
| --- | --- | --- |
| `text_x`, `text_y` | 3, 3 | Box's top-left coordinate; x 0–48, y 0–71 |
| `text_width`, `text_height` | 66, 66 | Width 24–72, height 1–72; entire box must fit in 72×72 |
| `text_align` | 1 | 0 left, 1 center, 2 right |
| `text_valign` | 2 | 0 top, 1 middle, 2 bottom |

The existing two-line word/glyph wrap and final ellipsis use the box width.
Alignment applies to the complete two-line block. Ink clips to the box, so a
short box can clip lines; the one-pixel outline expands the clipped ink and
clips at the key boundary. Fonts, replacement glyphs, colors and native
orientation remain unchanged. Default pixels match all eleven v1 fixtures;
nine additional fixtures cover every horizontal/vertical alignment combination
with clipping. The browser uses the same glyph coverage and matches every
fixture exactly. Position/label changes reuse cached backgrounds without a GET.

## Explicit origin provisioning

The editor's Library settings and Configure → Artwork address accept the HA
origin reachable from the device. A browser URL or loopback/container address
does not establish ESP reachability. With v2, HA asks the device to fetch a tiny
72×72 PNG at a revocable probe path before committing the HA address.

`provision_asset_origins(session, origins, test_url)` accepts 1–4 newline-separated
exact HTTP(S) origins, at most 1088 bytes total, and a test URL within the proposed
allowlist. The GUI deliberately replaces the list with the selected HA origin;
the native operation supports advanced finite lists. ESPHome 2026.9.0 cannot
compile response actions with its noncopyable array arguments, so the new
operation uses a bounded string rather than changing dependency pins.

Admission requires the existing loader to be idle. During testing, provisioning
owns that same worker and a 32 KiB buffer; it does not start a second HTTP worker.
The production PNG decoder verifies the fetched body. Existing origin rules,
zero redirects/retries, timeouts, clock, certificate and hostname verification
apply. TLS is never disabled. Private CA configuration remains an advanced
firmware setting. Failure retains the previous allowlist and HA address.
Cancellation retains worker-owned memory until drained.

Only a successful explicit provisioning transaction saves a versioned finite
origin record through ESPHome preferences and synchronizes it to flash. Boot
validates the saved record before replacing compiled defaults. Layouts, page
selection, input and visual changes never write ESP flash. Capabilities expose
`origin_probe` (`idle`, `testing`, `verified`, or a bounded error code); the
provisioning action's acceptance means testing started, not that it succeeded.
The native probe tests the ESP fetch only when run on an ESP; the lab fetcher
proves the HA route and contract, not IDF TLS behavior.

## HA pages, overlays and migration

Existing version-1 layouts remain readable, exportable and editable. Enabling
pages in the editor explicitly converts a draft to version 2:

```json
{"version":2,"default_page":"main",
 "pages":[{"id":"main","name":"Main","keys":["15 full key configurations"]}],
 "overlays":[{"id":"shift","name":"Shift","keys":{"0":null}}]}
```

The example abbreviates the 15-element key array. IDs are 1–32 lowercase ASCII
letters/digits/underscores; names are 1–48 characters. Limits are eight full
pages and four overlays, within the existing 128 KiB layout limit. An overlay
omits a key to inherit it, uses `null` to clear it, or supplies a complete key
configuration to replace it. Overlay resolution replaces a whole tile and its
binding; it does not partially merge arbitrary action data. Only one overlay
can be active. Artwork reference/backup/GC traversal includes inactive pages
and overlays, while the ESP only receives the resolved current 15 tiles.

The HA page select entity and `esp_deck.select_page` select a saved page.
Navigation keys use `navigation: {kind: page|overlay|momentary, target: id}`;
these are exclusive with managed press/release actions and automation mode.
`page` selects a page and clears overlays; `overlay` toggles an overlay;
`momentary` activates one until its accepted press is released. The first held
momentary modifier wins. A release belongs to its captured modifier even if
the overlay replaces/clears that key. An explicit page/toggle selection ends
that modifier's ownership. Restarts start on the default page with no overlay.
Disconnect, stream reset/overflow or configuration replacement clear transient
holds/overlays without synthesizing release actions.

## Input/display correlation and the audited native channel

`rendered_revision` still means a complete tile reached the scheduler.
`applied_revision` is nonzero only when the latest rendered state also matches
the scheduler's completed two-report image in the current `usb_generation`.
It becomes zero during rendering/failure/disconnect. It is **USB completion,
not physical display readback**. A same-pixel update may advance the applied
request revision without uploading the same bytes again; its context still
changes independently.

The USB IN completion callback snapshots the scheduler's input epoch. Accepted
visual changes, two-page completion and attach/detach advance that epoch.
The main loop drains captured input before applying a pending output completion.
The portable v2 channel admits a press only with matching capture/current epoch,
USB generation, applied visual revision and nonempty binding context. This
conservatively rejects an IN observation crossing a display/context boundary.
It records the context/revision at press and retains them for its release.
The guarantee is at USB observation/completion boundaries; precise contact-to-
display timing and the existing first-input baseline policy remain hardware gates.

HA polls `read_deck_inputs(session, reader, ack)` on its existing encrypted
ESPHome connection, approximately every 100 ms. One response contains at most
32 captured edges, each with key, edge, context, applied revision, generation
and sequence, plus a stream reset counter. There is no entity-state replay,
second native client, device-originated HA service permission or input history.
A new random reader, wrong acknowledgement, missing/slow response, one-second
reader lease expiry, USB generation change or queue overflow clears unreliable
input and held state. The first/reset response is synchronization only. HA
rejects responses taking one second or longer and never retries their edges.
This delivery lease bounds outage handling; it is not a display-transition delay.

Audit of the installed ESPHome **2026.9.0** and aioesphomeapi **46.6.0**:

- `api_connection.cpp::on_execute_service_request` and
  `api_server.cpp::register_active_action_call` map a client call ID to its
  connection and a server-generated action ID. Calls are removed when that
  connection disconnects.
- `user_services.h::APIRespondAction` constructs an immediate, owned JSON
  response. `send_action_response` routes it to that connection;
  `send_execute_service_response` sends a message, without the entity batching
  and deduplication path. Failure can drop a response, which the reader/ack
  protocol handles by resynchronizing, not by replaying input.
- `aioesphomeapi/client.py::execute_service` subscribes to its specific response
  call ID before sending and unsubscribes in `finally`. HA's existing ESPHome
  service handler awaits this response. The integration never subscribes to
  a separate socket or assumes ordering between an event entity and status.

The v1 event entities remain available for independent manual installations.
When v2 is negotiated, the managed controller ignores them for bindings.
Before dispatching a press, HA compares the packet context to the active resolved
key, capturing that configuration for the matching release. It invalidates
old press contexts immediately on page selection, including same-image changes.
The native applied gate handles the later per-tile USB transition. A delayed
old press cannot select the new binding, and a release cannot invoke an unrelated
new release action. Already executed HA actions cannot be undone by a later
disconnect. Failed keys retain previous valid pixels and stay gated; the editor
reports failures/retry. Whole-deck swaps are not atomic.

## Validation and remaining limits

Portable tests cover two-page fences, same-image rebinding, stale IN epochs and
output generations, captured releases, failed rendering, overflow, leases/lost
acks, bounded provisioning/decoder failures and alignment bounds. HA tests cover
page precedence, storage/exports, capability enforcement and modifier ownership.
Real lab scenarios cover provisioning, page transitions, rapid changes, failures,
held modifiers, reconnect and editor operation; see [testing.md](testing.md).

The USB report formats, descriptor hook, UART0 logging and unswitched external
VBUS topology are unchanged. New functionality requires one compatible firmware
update; later supported page/key edits require no rebuild. Electrical, actual
ESP fetching, first-click, input latency, repeated recovery and soak qualification
remain pending in [hardware.md](hardware.md). No device deployment is part of P8.
