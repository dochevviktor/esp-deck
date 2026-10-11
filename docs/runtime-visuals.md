# Runtime visual contract v1

P0 defines and host-tests this contract; P1 implements owned native images and
the scheduler boundary. P2 adds the [bounded local renderer](rendering.md),
bundled fonts and PSRAM adapters, exercised by `renderer_probe`. P3 connects
[bounded URL loading and caching](asset-loading.md). P4 exposes the native actions
through `examples/05_home_assistant_runtime.yaml`, with [HA helpers, key events
and layout replay](home-assistant.md). Examples 01–04 keep their earlier behavior.
P4 is compiled and host-tested, not deployed: the installed bench firmware cannot
run these runtime actions.

The portable implementation is `components/stream_deck/visual_state.*`. It has
no ESPHome, USB, HTTP, JSON or font dependency. `Store` accepts validated patches,
coalesces one desired visual per key, hands a snapshot to one render worker, and
commits only a complete successful native image to `Scheduler`.

## HA interface and presence

The HA-facing helper is
[`examples/home_assistant/visual_patch.yaml`](../examples/home_assistant/visual_patch.yaml).
It accepts `session`, `key`, `revision` and a `patch` dictionary and returns the
native response. Normal HA writers use `script.stream_deck_apply` from
`runtime_scripts.yaml`, which serializes calls and queries the current revision.
Install the helpers with example 05; adjust the ESPHome action prefix and entity
IDs if they differ in your HA registry.

```yaml
action: script.stream_deck_visual_patch
data:
  session: "0123456789abcdef"  # Read the actual Visual session diagnostic.
  key: 0
  revision: 41
  patch:
    image_url: "http://homeassistant.local:8123/local/streamdeck/desk.png"
    image_revision: "desk-v1"
    text: "Desk"
    text_color: "#FFFFFF"
    outline_color: "#000000"
response_variable: visual_result
```

Omission preserves the latest **accepted desired** value, including changes still
queued or a target whose last render failed. Every patch is validated completely
before it changes that state. Fetch/decode/render failure leaves the previously
rendered tile intact; a later patch can correct the failed desired target.

| Intent | `patch` (other arguments as above, increasing revision) |
| --- | --- |
| Change artwork, preserving any label | `{image_url: "http://ha.local/icon.png", image_revision: "v2"}` |
| Change label, preserving artwork | `{text: "On"}` |
| Text only, explicitly removing old artwork | `{image_url: "", text: "Ready"}` |
| Image only, explicitly removing old label | `{image_url: "http://ha.local/icon.png", image_revision: "v2", text: ""}` |
| Clear artwork and label, preserving style | `{image_url: "", text: ""}` |
| Clear just the label | `{text: ""}` |
| Set a solid background | `{background_color: "#102030"}` |

Empty URL means clear and requires an empty/omitted `image_revision`. A nonempty
URL requires a nonempty `image_revision` in the same patch; revision alone is
invalid. Empty `text` means clear. Empty colours/fit, `null`, unknown fields,
unsupported font sizes and an empty patch are invalid. Style resets are explicit
assignments of the defaults below, not empty strings. The helper rejects unknown
fields and standalone `image_revision`; the native validator checks values.

The pinned ESPHome API uses a **fixed argument list**, so optional HA dictionary
fields become a presence bit mask on the wire. P0 schema tests run this signature
against installed ESPHome 2026.9.0. Its identifier validator reserves `text`;
the wire argument is therefore `label_text`, while HA's patch retains `text`.

Native action: `esphome.streamdeck_original_set_key_visual`.

| Argument | Native type | Meaning |
| --- | --- | --- |
| `session` | string | Current ESP visual boot session, exactly 16 hexadecimal digits |
| `key` | int | Logical front-view key 0..14 |
| `revision` | int | Per-key increasing integer 1..2,147,483,647, within this boot session |
| `fields` | int | Nonzero sum of the selected field bits below; unknown bits rejected |
| `image_url`, `image_revision` | string, string | Bit 1; both supplied, even for clear |
| `label_text` | string | Bit 2 |
| `font` | int | Bit 4; size 12, 16 or 20 |
| `text_color` | string | Bit 8; `#RRGGBB` |
| `outline_color` | string | Bit 16; `#RRGGBB` |
| `background_color` | string | Bit 32; `#RRGGBB` |
| `fit` | string | Bit 64; `contain` or `crop` |

All arguments are supplied on every call. Unselected strings use `""`; unselected
font uses 16. They are ignored except for byte-length limits. API adapters map
`label_text` to `Command::text`. Commands borrow their argument views only during
`submit`; accepted state owns fixed-size copies. No JSON parser or arbitrary
image upload is part of this action.

## Revisions, status and atomicity

`session` is the controller's boot identity, not an API connection ID or USB
generation. The component generates a fresh 64-bit identity at ESP startup,
exposes it through the Visual session diagnostic, and requires it on commands.
The portable `Store` receives
that identity at construction. Commands for a previous boot fail with
`wrong_session`; reconnecting an API logger cannot create a new visual session.

HA owns monotonic per-key request revisions and should serialize updates through
the helper. Preserve counters across HA restarts, or query current status and
continue above the accepted revision. Do not wrap the signed 32-bit range.
Identical retries use the same revision and the same selected fields. Equivalent
colour hex case is normalized. A duplicate returns its current status without
another render/retry. Reusing a revision with different fields/values produces
`revision_conflict`; lower revisions produce `stale_revision`. Rejected requests
do not replace the current status or advance the accepted revision.

Accepted requests report `queued`, then `rendering`, then `rendered` or `failed`.
`idle` means no runtime request has been accepted for that key. Status retains
the latest accepted revision and last successfully rendered revision. The
action response and `get_key_visual_status(session, key)` expose these
bounded per-key records, for example:

```json
{"session":"0123456789abcdef","key":0,"request_revision":41,"accepted":true,
 "revision":41,"rendered_revision":40,"phase":"queued","error":"none"}
```

All native actions require response data (`supports_response: only`). HA uses
`response_variable` to capture the record. `accepted` describes the visual
operation, independently of API transport success; even rejected requests return
a record. Status queries set `request_revision` to 0 and can return
`accepted: true` with a retained worker error. `clear_key_visual` clears image
and label, preserving style; `refresh_key_image` changes the current desired
URL's content revision, preserving other fields. Both use the same session/key/
request-revision rules. Exact arguments and HA examples are in
[the integration guide](home-assistant.md#native-operations-and-error-handling).

`rendered` means a whole immutable native BMP has reached the USB scheduler's
desired slot. It does not mean either USB page has completed or that the deck's
display was read back. USB report completions remain a separate diagnostic.
Validation errors use the enum names in `error_name`; worker failures use
`fetch_failed`, `decode_failed`, `render_failed` or `out_of_memory`. Error messages
must not echo a URL, API key or arbitrary payload. Duplicate failed requests
return the retained failure; a higher revision explicitly retries.

At most one worker runs. New patches coalesce in 15 fixed slots. When the active
request is superseded, its worker still retires safely, but its completion cannot
publish a tile or overwrite newer status. A mismatched old completion cannot
release another active job. The next worker receives the latest full desired
state; round-robin selection prevents one busy key from starving the others.
There is no unbounded history/event queue. Querying a newer revision's status
also establishes that an older pending revision has been superseded.

A higher revision whose complete visual equals the last rendered visual updates
status without rendering or scheduling another image. A combined image/text
change has a single commit point. Scheduling then holds that immutable version
through both pages; later requests cannot mix old page 1 with new page 2.

## Rendering and asset policy for P2/P3

Defaults: black background, white label, black one-pixel outline, font size 16,
aspect-preserving centered `contain`. `crop` fills and crops centrally. Rendering
composites alpha over the configured opaque background, then draws the label.
The renderer uses bundled DejaVu Sans 2.37 in sizes 12/16/20 with ASCII
U+0020..007E and Latin-1 U+00A0..00FF glyphs, at 4-bit coverage. Source, license
and rasterizer pins are in `assets/fonts/manifest.json`; see [rendering](rendering.md)
for the exact scaling, alpha, layout and outline rules.

Labels use valid UTF-8, at most 96 bytes and 48 Unicode scalar values. LF is the
only permitted control character. Unsupported scalars become `?` during P2
rendering; malformed UTF-8, overlong encodings, surrogates, NUL and other controls
are rejected. Labels are centered horizontally at the bottom with a
two-pixel inset, wrap at spaces into at most two lines, and use `...` to indicate
truncation on the final line (split long words at glyph boundaries). P2 fixtures
record these pixels; no Pillow-identical font/scaling claim is made.

The decoder supports bounded non-interlaced PNG; JPEG/APNG/interlaced PNG are
not included in v1. HTTP and HTTPS sources use an explicit configured origin
allowlist in the P3 adapter. HTTP is for
non-sensitive local assets. HTTPS must verify certificates; no insecure fallback.
The current syntax validator permits ASCII DNS/IPv4 hosts and optional ports
1..65535, and rejects userinfo, query strings, fragments, malformed percent
escapes, whitespace, backslashes and IPv6 literals. P3 enforces origin, byte,
dimension, chunk, decode and network limits; HTTPS checks trust/hostname/dates
and refuses an unset clock. See [asset-loading.md](asset-loading.md).
HA `/local/` files are suitable only for non-sensitive assets. Authenticated
media and signed URLs require a later deliberate extension.

The asset identity includes exact URL and `image_revision` (1..64 ASCII letters,
digits or `._:-`). Replacing a file at the same URL requires a different asset
revision and a higher request revision. Clear operations do not globally evict
shared assets. Labels reuse the key's retained decoded background, independent
of label/style rendering. P3 includes fit/background parameters in the cache
identity when caching a scaled/composited background. Current key backgrounds
are pinned; only unpinned entries can be evicted, between jobs. An asset revision
change is the explicit refresh/invalidate
operation, so URL reuse never forces an accidental permanent cache hit.

In the HA runtime configuration, `Store` is the sole visual writer after boot.
The `runtime_visuals` option rejects local hub key automations/static artwork and
direct `set_image` calls cannot alter the scheduler. The separate bench
configuration remains the place for local bulb/arrow actions. Explicit redraw
preserves desired pixels and remains available.

| Resource | v1 ceiling |
| --- | --- |
| URL | 512 bytes |
| Encoded PNG | 128 KiB, including streamed bodies without Content-Length |
| Source dimensions / pixels | At most 256 on each axis and 65,536 pixels |
| Label | 96 UTF-8 bytes / 48 scalar values |
| Pending work | 15 coalescing keys; one active fetch/decode/render worker |
| Cached decoded backgrounds | 256 KiB; retain current 72×72 RGB backgrounds for label reuse |
| Owned native BMPs | 512 KiB including ownership metadata, charged to a bounded pool and the P3 root |
| Total graphics allocation | 2 MiB PSRAM root covering service/cache/image/decoder/workspace allocations |
| Fetch timing | 5-second socket/connect bound, 500 ms I/O waits, 15-second acceptance deadline; DNS drain can take longer |
| Automatic redirects / retries | 0 / 0; a new request revision is an explicit retry |

The renderer processes one row per `step()` and the caller yields between
steps (initial target: at most 2 ms of local CPU work before yielding, still to
be measured). Decoder source/workspace allocations
are bounded before allocation. RGB canvas/BMP/cache data belongs in PSRAM;
DMA USB transfers keep their existing internal allocations. Network/TLS/internal
heap overhead is additional and must be measured in P9. P3 enforces these graphics
caps; network/decode/render coexistence still needs device measurement.

## Image ownership

`runtime_image.*` provides `ImageRef`. Firmware-lifetime static `NativeImage`
objects use `from_static` without allocation. Runtime native bytes use `copy`,
which validates the BMP, makes one owned allocation containing metadata and
pixels, and returns an empty handle if allocation fails. The renderer chooses
a nonzero version; each successful copy has a distinct immutable identity even
when supplied pixels/version values match. Scheduler change detection compares
retained identities and explicit redraw revisions, not mutable byte pointers.

The allocator is injected, accounts for metadata and pixels, and must outlive
all its handles. P2 supplies the PSRAM adapter without internal-heap fallback. Host tests inject allocation
failure and bounded storage. Reference operations belong to the main loop;
the counter is deliberately not atomic. A future worker on another task must
transfer ownership/results to that loop explicitly.

Desired slots, applied slots, active scheduler job and transport job each retain
references. Replacing desired state or evicting a cache entry cannot affect an
active upload. Page 1 completion retains the scheduler job for page 2. Successful
page 2 replaces the applied reference. Detach releases scheduler active/applied
references while the transport retains its job until every pending callback has
retired; a delayed cancellation therefore cannot free its image early. Desired
references survive for redraw. Completed transport jobs transfer their reference
to the caller and release their internal copy. No image allocation/free happens
in the USB completion callbacks.

## Restart and offline rules

| Event | Required behaviour |
| --- | --- |
| ESP boot/reboot | Fresh visual session; blank default until HA replays authoritative state; RAM cache starts empty |
| Deck-only disconnect/reconnect | Keep visual session, revisions and desired tiles; scheduler resets/brightness/redraws without downloads |
| HA/API/Wi-Fi absent | Preserve last good desired tiles; USB input/display and OTA remain independent; do not replay key edges later |
| HA restart/reconnect | Read session/status; replay authoritative full state with safe revisions; unchanged state does not resend images |
| API logger connection/disconnection | No visual lifecycle event; no clearing or inferred HA availability |

Revisions/layout are not written to flash. HA-side binding changes require no
firmware changes with example 05. Its native key event entities publish only
real edges and do not replay state on API subscription. Physical inputs remain guarded against startup
transitions; the existing first-report baseline limitation is unchanged. The
USB/power rules and pending hardware gates in `docs/hardware.md` still apply.

Sources for the adapter shape: the locally installed pinned
`esphome/components/api/user_services.h` enforces argument count, and
`api/__init__.py` validates names/types; the regression test uses those files.
The public [ESPHome action documentation](https://esphome.io/components/api/#user-defined-actions)
and [HA script syntax](https://www.home-assistant.io/docs/scripts/) describe the
integration points. The original HA helper unit tests execute templates locally;
P5 additionally runs the [real HA engine and encrypted virtual-deck sessions](ha-lab.md).
Neither establishes physical ESP/deck acceptance.
