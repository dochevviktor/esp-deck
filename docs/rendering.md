# Bounded local renderer (P2)

`components/stream_deck/renderer.*` composes one 72×72 tile from decoded pixels
and the visual contract's style/text. It produces an immutable `ImageRef` for
the existing two-page scheduler. It does not fetch URLs or decode PNGs; those
are P3 work. No Home Assistant runtime action is exposed yet.

## Rendering and ownership

`Renderer::begin(state, source)` validates the source, style and UTF-8 and lays
out the label. `step()` performs one row of background scaling, one row of the
text mask, or one row of composition/BMP encoding. There are 216 row steps per
tile. The caller yields between steps; elapsed time per step and end-to-end
latency still need measurement on the ESP. `begin` refuses to replace a busy
render; `cancel` stops it without publishing partial output.

`copy_image(version, allocator)` returns an owned native BMP only after DONE.
It returns an empty handle before completion or on allocation failure. The
caller passes the result to `visual::Store::finish`, or records an explicit
worker failure. The store rejects superseded results and the scheduler retains
an active image through both USB pages. The renderer never writes into an image
already given to the scheduler.

A `PixelView` borrows immutable top-to-bottom RGB, RGBA, BGR or BGRA bytes. It
is not an encoded PNG/BMP or a `NativeImage`. Its owner must keep the pixels
alive until rendering finishes/cancels. Sources cannot overlap the workspace.
Dimensions are 1..256 on each axis, with at most 65,536 pixels. Stride must fit
the row and be at most 1,024 bytes; total supplied storage is at most 256 KiB.
Truncated buffers, unknown formats, invalid dimensions and overflow-sized
lengths/strides are rejected before reading pixels. An empty view requests a
solid background. File/content validation belongs to the decoder before this
boundary.

`render_esphome.h` adapts a completed ESPHome `image::Image` (including
`RuntimeImage`) without copying. The pinned RGB storage order is BGR/BGRA; the
adapter checks dimensions, bpp, data and transparency. RGB565, binary, grayscale
and chroma-key images are refused. Tests exercise the boundary with a fake
image object; `renderer_probe` compiles it against the real pinned Image API.

## Pixels and text

Contain scales the long edge to 72, rounds the short edge to the nearest pixel
(minimum one), and centers the result over the solid background. Crop scales
the short edge to 72 and removes the excess centrally. An odd spare pixel goes
to the bottom/right letterbox or crop. This preserves the aspect ratio up to
integer pixel rounding; it does not stretch the source to a square.

Sampling is bilinear at pixel centers, with source coordinates quantized to
1/256 pixel. RGB is weighted by alpha before interpolation, then composited over
the configured background with integer rounding. Fully transparent source
colours cannot bleed into visible neighbours. Composition operates in encoded
RGB, without gamma correction. This is a documented embedded filter, not the
offline Pillow LANCZOS conversion or a pixel-identical replacement for it.

Labels use DejaVu Sans 2.37, generated at 12/16/20 pixels with 4-bit coverage.
Each font includes 191 glyphs: ASCII U+0020..007E and Latin-1 U+00A0..00FF. The
shared strict UTF-8 decoder enforces 96 bytes and 48 Unicode scalar values;
unsupported valid scalars become `?`. Invalid UTF-8/control characters fail.

Labels occupy at most two bottom-centered lines. The layout accounts for glyph
bearings and advances, wraps at ASCII spaces, splits long words at glyph
boundaries, and honors LF. Leading/trailing spaces at line breaks are discarded;
trailing whitespace/newlines alone do not cause an ellipsis. Excess content on
the second line is replaced by `...`, fitting complete glyphs. There is no
kerning, shaping or bidirectional layout. The line heights are 15, 19 and 24
pixels respectively. The layout reserves two outer pixels plus one pixel for
the outline; actual visible strokes depend on each glyph's metrics.

One coverage mask represents the complete label. A 3×3 maximum filter supplies
the one-pixel outline (black by default), composited before the configured fill.
This preserves outlines where adjacent glyphs overlap and supports labels over
varying image pixels. `background()` exposes the completed scaled RGB background
without text, so P3 can cache it independently of the label. Its view belongs to
the workspace and must be copied/retained separately before workspace reuse.

The 54-byte BMP header comes from the validated blank native image. For
front-view pixel `(x, y)`, BGR bytes go to `54 + 3*(72*y + 71-x)`: the reference's
vertical flip cancels BMP's bottom-up row storage, while horizontal orientation
is reversed once. Native static assets continue directly through `set_image`;
they never enter this pixel renderer. The asymmetric upstream native BMP and
both 8191-byte reports match byte-for-byte.

## Font provenance and regeneration

The bundled TTF and unmodified release license are in `assets/fonts/`.
`manifest.json` pins the release archive, TTF, license, generated source,
bitmap hashes and generation versions. `tools/generate_render_fonts.py` calls
the installed ESPHome 2026.9.0 `font.glyph_to_glyphinfo`, with freetype-py 2.5.1
and its bundled FreeType 2.13.2. It checks those versions and source hashes.
No dependency version was upgraded. The three packed bitmaps total 29,457 bytes
plus glyph metrics; the 757,076-byte TTF is not included in firmware.

Using ESPHome's rasterizer retains its glyph packing/metrics. A small portable
consumer provides wrapping and outlined composition: the stock font printer
blends against one supplied background colour, whereas this renderer must blend
against each image pixel. No FreeType, Pillow or LVGL runs on the ESP.

```sh
.venv/bin/python tools/generate_render_fonts.py --check
.venv/bin/python tools/generate_render_fixtures.py --check
```

Omit `--check` only when deliberately updating assets. Font regeneration needs
the pinned local TTF; it does not download a moving font URL. Rendering snapshot
generation runs the native invariant tests and writes eleven BMP cases plus a
manifest. It also produces `.build/render-preview.png` for visual review.
These BMPs are **native-renderer regression snapshots**, not an independent
Pillow oracle. Separate analytical alpha/scaling checks and the upstream BMP/page
fixtures establish independent behavior. The snapshots cover transparent contain
and crop, asymmetric input, empty tiles, all font sizes, two lines, truncation,
unsupported characters and combined artwork/outlined text.

## PSRAM and validation probe

`PsramWorkspace` allocates one 36,342-byte workspace after PSRAM initialization:
15,552 RGB background bytes, 5,184 mask bytes, and 15,606 BMP bytes. It is reused
across jobs. `PsramImageAllocator` enforces a separate 512 KiB ceiling including
image ownership metadata. Both use `MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT` with no
internal-heap fallback. Allocation failure is recoverable. Allocator and workspace
owners must outlive their images/renderers. The small renderer object/font tables
are separate from these pixel allocations; USB DMA allocation is unchanged.

P2 uses at most 560,630 bytes for one workspace plus a full native-image pool.
Decoder/source/cache/TLS memory is not included in that figure; P3 must enforce
the total graphics budget and retain backgrounds within its cache cap. Tests
inject allocation failure and verify exact allocation capabilities, capacity
reclamation and no early free; these are not physical PSRAM stress tests.

`examples/renderer_probe.yaml` links and exercises the complete local path. It
requests text-only `Café` at sizes 12/16/20 on keys 0/1/2, a combined RGB/arrow +
yellow outlined `Desk` on key 7, and a truncated two-line label on key 14. It
processes one row per 5 ms interval and logs physical key events. It has no HA
actions or key-triggered artwork substitutions. Its source PNG is converted to
pixels at build time; this does not test runtime PNG decoding. The four numbered
examples, especially installed example 04, keep their existing behavior.

The build checker includes this probe using temporary synthetic secrets. Do not
upload those images. No P2 hardware upload or display/timing/memory verification
has been performed; the separate electrical and USB release gates remain open.

## P3 adapter audit to carry forward

The pinned `RuntimeImage` provides `set_external_buffer`, which can avoid its
own pixel allocation. Decode at the bounded source dimensions before invoking
this renderer: its fixed-width/height path scales X and Y independently.
Its current PNG decoder inherits byte-count completion from `ImageDecoder`, and
`RuntimeImage::end_decode()` finalizes an active session without independently
checking PNG IEND/truncation. P3 must establish format completion, byte/dimension
limits and cancellation before publishing a view. The default `RAMAllocator`
also permits fallback to internal memory; decoder/workspace allocation needs
explicit accounting so it cannot consume the USB reserve. These observations
come from the locally installed pinned source, not claims about other releases.

Sources: [DejaVu 2.37 release](https://github.com/dejavu-fonts/dejavu-fonts/releases/tag/version_2_37),
[pinned ESPHome font generator](https://github.com/esphome/esphome/blob/c6e4c87e525dd343e470d8dea368957a002f6505/esphome/components/font/__init__.py),
and [pinned runtime-image sources](https://github.com/esphome/esphome/tree/c6e4c87e525dd343e470d8dea368957a002f6505/esphome/components/runtime_image).
