# Bounded URL loading and caching (P3)

P8 adds [explicit, verified origin provisioning](runtime-v2.md#explicit-origin-provisioning)
over the encrypted API. A valid persisted v2 origin record replaces compiled
defaults at boot. The decoder, fetch/TLS limits, retained caches and v1 compiled
origin configuration described below remain in effect.

P9's first physical session found that production HTTP admission incorrectly
required the full 128 KiB artwork buffer even for the 32 KiB origin probe. Both
admission paths now accept a nonzero caller capacity up to the existing ceiling;
declared and streamed bodies are bounded by that actual capacity. The native HTTP
test now runs the real worker as well as the transfer implementation. The fix is
deployed; [live artwork/network acceptance](hardware-lab.md) is still pending.

P3 connects validated visual requests to HTTP(S), a bounded PNG decoder, the P2
renderer, and the immutable-image scheduler. It is opt-in with `asset_loading`.
The four numbered examples and `renderer_probe` retain their existing behavior.
`asset_loader_probe` exercises the new path with a configurable asset URL; no
firmware has been uploaded for this work. P4 adds HA-facing actions in example 05;
see [HA runtime controls](home-assistant.md).

## Configuration and reachable assets

```yaml
stream_deck:
  asset_loading:
    allowed_origins:
      - http://homeassistant.local:8123
      - https://assets.example.net
    # Optional public CA PEM for a private HTTPS server:
    # ca_certificate: ../assets/ha-ca.pem
```

There must be 1..4 HTTP/HTTPS origins, each consisting only of scheme, host and
optional port. Hostname case and default ports are normalized; scheme and port
remain significant. Requests must match an allowed origin exactly. Credentials,
queries, fragments, IPv6 literals and malformed URLs are rejected. There are no
Authorization headers, cookies, HA administrator tokens or automatic redirects.
The optional CA file is bounded to 16 KiB and cannot contain a private key.

Use a PNG reachable **from the ESP's network**, for example a non-sensitive file
under HA's `config/www/streamdeck/desk.png`, served as
`http://<HA-host>:8123/local/streamdeck/desk.png`. `/local/` is unsuitable for
sensitive artwork. Authenticated media/signed URLs are not supported in v1.
Set both `asset_origin` and `asset_url` in `examples/asset_loader_probe.yaml`.
The supplied `homeassistant.local` value is a configurable placeholder, not a
confirmed server on the owner's network. The pinned build enables mDNS DNS
queries, but actual DNS/routing/server access still requires a device check.

HTTPS uses the pinned IDF CA bundle or the supplied CA, with hostname and
certificate-date checks enabled. No insecure fallback is exposed. The probe uses
Home Assistant time and waits for a valid clock before an HTTPS request; plain
HTTP does not require HA time. Another ESPHome time source can be used in a real
configuration. Date validation is an SDK setting and therefore also applies to
other TLS users in a firmware with asset loading enabled.
Typed HTTPS calls made before the clock reaches 2021 return `clock_not_ready`
without opening a connection. The time source must still supply correct current
time; the epoch guard alone is not a clock-synchronization proof.

After an explicitly requested deployment with a real URL, the probe requests
`Desk` plus the downloaded image on key 0, then changes the label to `Cached`.
Diagnostics should show one download and a cache hit for that label change.
Press/release logs remain active during the operation. The probe's boot request
is local diagnostic code, not an HA binding or runtime API action. Failed boot
requests are not retried automatically. Live URL/TLS reachability, display
appearance and latency remain unverified until that hardware test.

## Pipeline, threads and cancellation

The portable pipeline has one job at a time:
`fetch → validate PNG → inflate → reconstruct rows → render → commit`.
Fifteen desired visual slots coalesce pending updates in `visual::Store`.
Only a fully decoded/rendered BMP can become scheduler desired state.

`HttpFetcher` owns one persistent 8 KiB-stack FreeRTOS worker. It copies the
bounded URL, performs a single GET into a caller-owned PSRAM buffer, cleans up
the HTTP/transport handles, then publishes a token-tagged result using atomic
release/acquire synchronization. It never touches ESPHome entities, Store,
cache references or `ImageRef` counters. Those remain on the main loop.

Cancellation requests do not delete the worker, close its handle from another
task, or free its destination. The pipeline retains that buffer until a matching
completion retires the request. Old completion tokens cannot finish newer work.
On the logical deadline the current request reports failure; a still-retiring
worker prevents a new fetch, while input/API/OTA continue. The synchronous IDF
DNS resolver may take longer than the socket timeout to return; in that case the
buffer remains retained during drain. No forceful task deletion or MCU reboot
is used as a timeout mechanism. The runtime service has boot lifetime, like the
USB host; shutdown cancels and retains pending resources until retirement/reboot.

PNG validation scans at most 1,024 payload bytes per step. Inflate receives at
most 1,024 input and output bytes per step, and reconstruction processes one
bounded scanline per step. The P2 renderer processes one row per step. ESPHome
is asked to run successive loop iterations during decode/render only; every
iteration services USB and input first. HTTP waiting does not busy-spin the main
loop. Actual step durations and heap trends still need S3 measurement; there is
no animation-rate or latency guarantee.

## Fetch policy and limits

The pinned ESPHome HTTP wrapper performs blocking connection/header/read work.
P3 uses the same pinned IDF HTTP/TLS facilities behind the worker and a bounded
custom transport, rather than invoking that wrapper on the main loop.

| Resource or behavior | Limit/policy |
| --- | --- |
| Requests in flight | One; pending visuals coalesce per key |
| URL | 512 bytes, allowed origin required |
| Accepted status | 200 only; redirects/401/retries do not trigger another request |
| Content type | `image/png` if supplied; signature/format validation always follows |
| Content encoding | Missing or `identity`; gzip/other coding rejected |
| Encoded body | 128 KiB, counted even with chunked/unknown Content-Length |
| Response headers/trailers | 8 KiB parser cap; initial transport header reads also capped |
| Wire bytes including framing | 192 KiB, so excessive chunk overhead is rejected |
| Connect timeout | 5 s socket/connect bound (DNS drain caveat above) |
| Read/write/poll wait | At most 500 ms per underlying I/O call |
| Request acceptance deadline | 15 s; late/cancelled results cannot publish pixels |
| Automatic redirects/retries | Zero |

Requests send `Accept: image/png`, `Accept-Encoding: identity`, and
`Cache-Control: no-cache` for deliberate content revisions. Content-Length is
checked before reading the body when known; an extra-byte probe detects overflow
at the exact capacity for unknown-length responses. HTTP completion must be
confirmed by IDF, not inferred from a short read. Header callbacks are not used
to abort requests (the pinned IDF ignores their return errors); the transport
checks the recorded policy error before further I/O.

Asset-enabled builds set the shared IDF HTTP parser's `HTTP_MAX_HEADER_SIZE` to
8192, including chunked trailers. Other IDF HTTP users in that firmware must fit
this limit too. The checker verifies the actual parser compilation flag, HTTPS,
custom transport, CA bundle and certificate date validation settings. The
`HTTP_CLIENT` log tag is silenced because its verbose messages include raw
paths/headers. Our diagnostics report only counts, HTTP status, request/revision
IDs and fixed error names, never URL/header/body values.

## PNG support and provenance

Supported: **non-interlaced PNG**, standard color types 0/2/3/4/6 and their legal
bit depths (1/2/4/8/16 as applicable), PLTE/tRNS transparency, and all five row
filters. Sixteen-bit samples are normalized to RGB8/alpha8 with integer rounding.
Source width and height must each be 1..256, with at most 65,536 pixels and 256
chunks. Interlaced PNG, APNG and unknown critical chunks are rejected. Re-export
such artwork as an ordinary non-interlaced PNG. JPEG is not implemented.

The validator checks signature, chunk bounds/names/order, all CRCs, palette and
transparency rules, consecutive IDATs, and a final empty IEND with no trailing
data. Only then are decoder buffers allocated. The inflater must reach verified
zlib end with its Adler checksum, consume exactly the IDAT stream and produce
exactly the dimensions' expected filtered bytes. An extra output byte detects a
dimension-mismatched expansion bomb before it can grow memory. Invalid filters,
palette indices and incomplete pixels also fail. Ancillary metadata is bounded
and CRC-checked but color profiles/gamma are not applied, matching the P2 encoded-
RGB composition policy.

The inflate/CRC engine is miniz 1.15 from pngle 1.1.0 at
`b1c68193f1d3f8642b3e0e095d457a828038e6fb`, the PNG dependency selected by the
pinned ESPHome runtime-image component. The source and Unlicense are vendored
under `components/stream_deck/third_party/`, with original/local SHA-256 pins.
The only source patch selects bytewise loads for portable sanitizer tests; line
endings are normalized. Tests reverse that patch and reproduce the upstream
hash. The C bridge disables heap allocation and prefixes symbols to avoid IDF
ROM collisions. Existing ESPHome/IDF/Pillow dependency versions are unchanged.

The stock PNG/runtime-image wrapper does not expose the allocation control,
exact inflated-size check, format-completion guarantee or small output slices
required here. P3 therefore supplies a strict PNG frontend around that pinned
inflater. It does not port Pillow or adopt another display/USB framework. PNG
fixtures use Pillow plus hand-built PNG/zlib cases independently checked against
Pillow; documented 16-bit normalization has explicit expected values.

## Cache, memory and failed updates

Cache identity is exact URL + explicit `image_revision` + fit + background
color. The cache stores scaled/composited 72×72 RGB backgrounds, without labels.
Text/font/fill/outline-only changes reuse them; fit/background changes can need
a fresh fetch. Replacing a file at the same URL needs a new image revision and
a higher request revision. No persistent browser cache hit can override that
explicit local identity.

There are sixteen cache slots: fifteen current key backgrounds plus one staging
slot. Current keys pin their backgrounds; only unpinned slots can be evicted,
oldest first. Identical backgrounds can be shared across keys. Keys transfer
their pin only after a successful full-tile commit. A failed fetch/decode/render
leaves the old BMP and pin intact. A label changed during the initial download
lets that download finish and caches its background, discards the old label's
result and renders the newest label without another GET. A changed asset instead
requests cancellation and drains the old worker before reuse.

All graphics allocations, including runtime service metadata, charge one 2 MiB
PSRAM root allocator. Native images have a nested 512 KiB cap including ownership
metadata; backgrounds and cache entries have a 256 KiB cap. The remaining budget
covers the 128 KiB encoded buffer, bounded inflate state, filtered source data
(at most 524,545 bytes including the overflow sentinel for RGBA16), decoded RGBA
(at most 262,144 bytes) and the 36,342-byte render workspace. Intermediates are
released as their users retire. Allocations have no internal-RAM fallback.

The worker stack and IDF network/TLS allocations are additional internal/SDK
overhead, not charged as graphics. Existing internal free/minimum heap diagnostics
remain available. USB DMA uses its existing dedicated internal buffers. These
software caps are not measurements of network/USB coexistence or physical PSRAM
reliability; P9 must collect those observations.

`StreamDeck::submit_visual`, `visual_session`, and `visual_status` provide the
typed bridge used by the probe and P4's native API adapter. New error
names include `origin_not_allowed`, `fetch_timeout`, `http_status`,
`unsupported_encoding`, `unsupported_png`, and `clock_not_ready`; malformed PNG uses `decode_failed`.
Status retains the last rendered revision on failure. `rendered` still means
queued immutable desired pixels, not USB completion or display readback.
Duplicate failed requests do not retry; a higher request revision does.

## Verification and remaining hardware work

Run the normal host suite and synthetic firmware checker. Additional fixture
verification is `.venv/bin/python tools/generate_png_fixtures.py --check`.
The tests cover PNG color/filter/transparency cases, malformed/truncated/oversized
inputs and compressed expansion attacks; cache reuse/revisions/eviction; delayed
cancellation and stale tokens; previous-tile preservation; and production HTTP
transaction guards with fake IDF transports. TLS tests verify configuration and
failure handling, not a real TLS handshake or the FreeRTOS task's physical timing.

The loader probe is included in build validation and CI. Synthetic firmware is
never for upload. Before a requested device test, establish the owner's actual
asset origin/PNG, CA/time source if HTTPS, and local deployment credentials.
Then verify successful download and cache relabel, invalid URLs/certificates,
network loss, rapid updates, key input/API/OTA responsiveness, deck reconnect,
heap trends and timing. Hardware/electrical release gates remain unchanged.

Primary references: [pinned IDF HTTP client API](https://docs.espressif.com/projects/esp-idf/en/v5.5.5/esp32s3/api-reference/protocols/esp_http_client.html),
[pngle source pin](https://github.com/kikuchan/pngle/tree/b1c68193f1d3f8642b3e0e095d457a828038e6fb),
and [PNG specification](https://www.w3.org/TR/png-3/). Exact adapter behavior was
checked against the locally installed ESPHome 2026.9.0 / IDF 5.5.5 source.
