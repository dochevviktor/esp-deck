# USB transport decision

Status: implemented, unit-tested, compiled and initially functional on the S3.
With IN-64 / OUT-512, HID SET_IDLE startup and the captured 17-byte input format,
the owner confirms visible RGB/arrow images, press/release image feedback, all
15 key indices and one peripheral reconnect with full redraw and resumed input.
Each edge completes both 8191-byte image pages. Earlier
packet-size-only attempts did not work; their host completions were insufficient
evidence. Detailed mapping/visual checks, brightness, repeated recovery and release
qualification remain open.
The handover is preserved at
`STREAM_DECK_ESPHOME_CODEX_HANDOVER.md`.

Use ESP-IDF 5.5.5's asynchronous USB host API directly. `stream_deck` installs the
host exactly once and claims one Original 0FD9:0060 HID interface. The final driver
configuration excludes stock `usb_host`; that component is used only by the probe.
The stock ESPHome 2026.9.0 wrapper restricts buffers to at most 1024 bytes, so it
cannot carry an 8191-byte report through its public transfer methods.

## Transfers and memory

The client allocates one input buffer using the discovered endpoint MPS and one
8199-byte output/control buffer using `usb_host_transfer_alloc`. The allocator
supplies DMA-compatible memory. On S3 these buffers use internal memory, not
arbitrary PSRAM. Immutable native BMP assets stay in flash, including the default
blank image; there is no 15-key framebuffer.

P1 adds `ImageRef` ownership for future runtime images. Static assets still avoid
allocation; owned native BMPs use an injected bounded allocator (P2 supplies the
PSRAM-only adapter). Desired/applied slots and scheduler/transport jobs retain references.
The transport releases its image only when completion is taken or cancellation
has fully drained. This changes image lifetime, not USB DMA allocation or report
framing; see the [runtime contract](../runtime-visuals.md).

Feature writes always use EP0 `SET_REPORT(Feature)`. Output uses interrupt OUT if
the discovered HID interface has that endpoint, otherwise EP0
`SET_REPORT(Output)`, matching HIDAPI. Neither interface 0 nor endpoint 0x81 is
hardcoded. Ambiguous interfaces, unsupported endpoint types, other VID/PIDs,
non-full-speed devices, and malformed descriptor layouts are rejected.

For EP0 the complete transfer is 8 setup bytes plus 8191 report bytes. `wLength`
is 8191 and `num_bytes` is 8199. A completed control transfer's `actual_num_bytes`
includes the setup bytes in this IDF release; the driver checks the exact total.
The nonzero report ID remains in both `wValue` and data byte zero.

Audit correction to the handover's conservative cap assumption: in IDF 5.5.5,
`CONFIG_USB_HOST_CONTROL_TRANSFER_MAX_SIZE` sizes internal enumeration/configuration
**data-stage** buffers; it is not a universal client-buffer length check. Set it
to 8192 and independently allocate 8199 bytes for the client's complete transfer.
The build checker inspects the generated SDK setting, not just the YAML.

There is another limit below the public API: `hcd_dwc.c` defines an interrupt
descriptor list of **32 packets**. An 8191-byte report at MPS 64 requires 128
packets, and submitting it in one interrupt transfer would exceed that list.
The transport submits contiguous batches of at most `32 * MPS`, with
the only short packet at the end. At MPS 64 the lengths are 2048, 2048, 2048,
2047. The application still hands over one complete report. Continuations add
no report ID, HID header, padding or ZLP and cannot interleave another report.
The host packetizes each batch. Fake-IDF tests concatenate the submissions and
compare all 8191 bytes with the upstream fixture. The owner's desktop capture
shows interrupt OUT at both speeds, with MPS 64 in the advertised other-speed
configuration. Actual S3 enumeration at full speed returned the **512-byte**
configuration instead, including after the owner removed deck power for over
20 seconds. With the current 512-byte OUT endpoint, an 8191-byte report fits in
one transfer: 15 full packets and a final 511-byte packet, within the 32-packet
limit. Host completion and actual RGB/arrow rendering are now observed with the
combined startup/decoder changes. See the
[functional confirmation](../hardware.md#first-confirmed-images-and-local-key-actions-2026-10-10).

## Original full-speed descriptor compatibility

A parser-only relaxation cannot correct this: IDF's `usb_host_interface_claim`
allocates every endpoint from its cached configuration, and `hcd_dwc.c` separately
checks packet sizes against controller FIFO limits. Linux's USB core
[clamps oversized full-speed interrupt descriptors to 64 bytes](https://github.com/torvalds/linux/blob/v6.12/drivers/usb/core/config.c),
but the pinned IDF public interface-claim API has no descriptor-override argument.

`components/stream_deck/idf_usb/` provides an IDF project-component override named
`usb`, copied into the individual firmware build by ESPHome's extra-build-file
API. [IDF gives project components precedence over built-ins](https://docs.espressif.com/projects/esp-idf/en/v5.5.5/esp32s3/api-guides/build-system.html#multiple-components-with-the-same-name).
It compiles the installed 5.5.5 USB sources with a generated copy of `usbh.c`.
The generator checks SHA-256 pins for `usbh.c`, `usb_host.c`, `Kconfig` and the
upstream CMake recipe, and rejects unexpected versions or patch locations.
The SDK installation is never written. The firmware checker also requires the
generated `usbh_stream_deck.c` to appear in the actual compiler commands.

The P2 renderer probe exposed a clean-build dependency issue: ESPHome's built-in
discovery includes only components below the installed SDK, so this project-local
`usb` override was omitted from the application's generated requirements.
`link_application.cmake` now adds an explicit public `idf::usb` dependency to
ESPHome's application target after all targets exist, using the pinned CMake
DEFER facility. This works without an old discovery cache and changes no USB
source/framing. The checker verifies the USB include directory on the application's
actual transport compile command. A fresh isolated renderer-probe build passed.

The hook runs inside `usbh_dev_set_config_desc` after allocation/copy and before
the descriptor is published. It changes **only the IN endpoint** MPS from 512
to 64 for full speed, VID/PID `0FD9:0060`, and a byte-for-byte match with the
captured 41-byte layout. OUT stays at the advertised 512. This is a nonstandard
full-speed interrupt endpoint experiment, not a general USB compatibility fix.
The 400 mA declaration and HID report sizes remain
unchanged. Already-correct, high-speed, other-device and unrecognized layouts
are not altered. There is no const cast on a descriptor borrowed by the class
driver and no extra host installer. The parser accepts IN MPS 16..64 and OUT
MPS 1..64 or exactly 512; other oversized packet sizes remain rejected.

The previous correction forced both endpoints to 64. IDF reported successful
transfers with exact lengths and no USB errors, but the owner saw only the logo
and pressing keys produced no first-input snapshot. Thus that result did **not**
pass the functional large-report gate. The current experiment tests whether
64-byte short packets prematurely terminate reports in the deck firmware by
preserving the advertised 512-byte OUT framing. This is a hypothesis, not an
established cause. Key input is polled with a 64-byte buffer. After adding HID
SET_IDLE startup, a real 17-byte ID-1 key report arrived; the decoder now accepts
that captured layout (15 binary key states plus a zero trailer) as well as the
reference's truncated 16-byte form. Other IDs/lengths are not newly accepted.

`CONFIG_USB_HOST_HW_BUFFER_BIAS_PERIODIC_OUT=y` is required to allocate sufficient
periodic-OUT FIFO space for that endpoint. The IN and balanced biases are
disabled. The firmware checker verifies the generated setting for every driver
build. The IDF HCD accepts this layout; its acceptance does not make an oversized
full-speed interrupt endpoint USB-compliant or prove the peripheral's behaviour.

Native tests cover the exact correction, every single-byte layout mutation,
wrong IDs/speed, idempotence, and a complete golden stream reset through the
production transport with the corrected layout. Build-hook tests verify source
pins, unpublished-copy placement and refusal to write inside the SDK source tree.
On hardware, example 04 reports interface 0/0, IN `0x81` MPS 64 / OUT `0x02`
MPS 512, initialization complete and 32 host completions. It requests asymmetric
RGB/TL/arrow patterns on keys 0, 7 and 14; press/release automations provide local
visual feedback without HA. The packet-size-only build produced no patterns or
key events even after reconnects and a whole-system power cycle. After the HID
startup and decoder changes, the owner confirmed visible patterns and supplied
press/release logs with complete two-page image transfers. Both the single-transfer
512-byte path and the four-batch 64-byte path are covered by native tests; the
64-byte path has not been hardware-retested with the new HID initialization.

Every attachment now performs the complete bench-proven EP0 sequence before
scheduler initialization: GET_CONFIGURATION, SET_IDLE(0, all report IDs),
GET_DESCRIPTOR for the discovered HID report-descriptor length (bounded to 320
bytes), and GET_REPORT(Feature 4) for firmware. The optional
`usb_diagnostics: true` setting controls verbose reply logging only; it must not
change device initialization. SET_IDLE precedes fetching the descriptor, matching
the initialization in
[Linux usbhid v6.12](https://github.com/torvalds/linux/blob/v6.12/drivers/hid/usbhid/hid-core.c).
This standard request selects report-on-change behaviour; it is not a device
reset. Key packets were first captured after this startup change; physical input
actions and basic rendering were subsequently confirmed after fixing the decoder.
The 2026-10-11 runtime investigation found a functional difference hidden behind
that logging option: runtime builds previously sent only SET_IDLE, while the
working bench sent all four requests. Enabling the bench sequence on the otherwise
unchanged runtime firmware restored captured 17-byte key input and populated all
15 HA key states. The three read replies matched the earlier bench fixtures.
The fix preserves the whole known-working sequence in both modes; the individual
query or timing responsible has not been isolated. See [current physical
evidence](../hardware-lab.md). Native regression coverage requires identical
requests with diagnostics on/off, both output routes, and safe handling of
STALL/short replies, timeout and physical detach at each startup step.

No serial feature is read. Buffers
round up IN capacity to EP0 MPS without changing wLength. Replies/status/actual
lengths are retained for late API configuration dumps and never counted as
output report completions or decoded as key input. A completed STALL/short reply
is recorded and the next query proceeds; a pending timeout uses normal recovery.

## Tasks, ordering and lifetime

A 4096-byte FreeRTOS task services library events. All client operations and
callbacks are serviced by `usb_host_client_handle_events(..., 0)` on the ESPHome
loop task. Callbacks only record completion flags; they never publish entities,
allocate images, free transfers, or run user automations. The loop handles
descriptors, encoding, exact-length checks and subsequent submissions.

Full input reports go through a bounded 32-entry FIFO and edge tracker. A queue
overflow increments a visible counter, discards the unreliable backlog and uses
the newest report as a silent baseline. It does not claim lossless input during
overflow. Images use 15 desired-state slots; only pending images coalesce. An
active key's two pages use the same immutable image, even if a newer request
arrives. Scheduling rotates through keys, and brightness can run between images.

Connection generations and per-job sequence numbers reject obsolete work. On
reconnect, send the full stream reset, desired brightness, then all desired images.
This applies equally when the deck stayed powered during an ESP reboot.
Desired images remain in RAM across a deck-only disconnect; an ESP restart
recreates the configured boot state instead. Updates are change-driven, with
full restoration on attachment, not a periodic full-display refresh. One physical
deck reconnect has now confirmed sequential desired-image restoration and resumed
key events. ESP-only restart and repeated recovery tests remain open.

## Deadlines and recovery

Do not rely on `usb_transfer_t.timeout_ms`: it is documented as unsupported in the
pinned stack. Output has a 3-second software deadline for the whole report,
including interrupt continuations. An interrupt IN request can legitimately NAK
while nothing changes, so idle input is not treated as a timeout.

On failed submission, STALL, short output or deadline, invalidate the session.
If the device has not already gone, use `usb_host_lib_set_root_port_power(false)`
to disconnect the controller logically. This IDF's public halt/flush endpoint API cannot address EP0; the root
disconnect drives cancellation through the stack's device-gone path. Halt/flush
claimed nonzero endpoints as needed, keep pumping client callbacks, and release
interfaces/close/free buffers only after every submitted transfer has retired.
Re-enable the controller after a five-second recovery delay and discover again.
For `DEV_GONE`/NO_DEVICE, let IDF's existing physical-disconnect path cancel and
recycle the port instead. Requesting power-off after a physical detach overwrites
its RECOVERY state and caused an observed `root_port_recycle` abort on 5.5.5.
Regression tests forbid that extra call and retain buffers until callbacks retire.

The API's word "power" does **not** mean the XIAO switches peripheral VBUS. This
board has an externally energized, unswitched 5 V rail. The Stream Deck can retain
power throughout recovery. If cancellation never completes, retain the buffers,
log a bounded diagnostic, and keep networking/OTA alive; manual unplug or reboot
may be needed. No fabricated GPIO power switch and no repeated device-reset
feature writes are used. A real device/driver deadlock remains a hardware test.

## Console ownership

Use UART0 for logging. ESPHome 2026.9.0's logger also requests the USB Serial/JTAG
secondary console for S3 even with UART0 selected. The component disables that
secondary console after core defaults; the probe's base YAML explicitly does the
same. Generated SDK configuration is checked after every build. No eFuses change.

## Audited sources

- [ESPHome USB wrapper at the pinned release](https://github.com/esphome/esphome/tree/c6e4c87e525dd343e470d8dea368957a002f6505/esphome/components/usb_host).
- [IDF USB host implementation](https://github.com/espressif/esp-idf/blob/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/usb/usb_host.c),
  [HCD packet limits and completion counts](https://github.com/espressif/esp-idf/blob/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/usb/hcd_dwc.c),
  [USBH endpoint/control validation](https://github.com/espressif/esp-idf/blob/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/usb/usbh.c),
  [host API documentation](https://docs.espressif.com/projects/esp-idf/en/v5.5.5/esp32s3/api-reference/peripherals/usb_host.html).
- [HIDAPI 0.15.0 routing](https://github.com/libusb/hidapi/blob/d6b2a974608dec3b76fb1e36c189f22b9cf3650c/libusb/hid.c).
