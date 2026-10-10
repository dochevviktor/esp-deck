# USB transport decision

Status: implemented, unit-tested, compiled and exercised on the S3, but not
functionally qualified. A narrowly scoped descriptor correction enabled
interface claiming and 32 host-reported startup completions, including full
8191-byte outputs. The IN-64 / OUT-64 attempt still left the logo displayed and
produced no input after physical presses. An IN-64 / OUT-512 experiment is now
deployed and also failed the owner's display/input test after reconnects and a
whole-system power cycle. Functional transport and release qualification remain open.
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
limit. Host completion is observed, but device processing is unverified. See the
[S3 observations](../hardware.md#network-and-s3-usb-session-2026-10-10).

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
visual feedback without HA. The owner confirmed no patterns or key events even
after reconnects and a whole-system power cycle. Both the single-transfer 512-byte path and the four-batch 64-byte
path are covered by native tests.

The optional `usb_diagnostics: true` bench setting makes three read-only EP0
queries before scheduler initialization: GET_CONFIGURATION, GET_DESCRIPTOR for
the discovered HID report-descriptor length (bounded to 320 bytes), and
GET_REPORT(Feature 4) for firmware. Every driver now sends SET_IDLE(0, all report
IDs); in the diagnostic sequence it precedes fetching the HID descriptor, matching
the initialization in
[Linux usbhid v6.12](https://github.com/torvalds/linux/blob/v6.12/drivers/hid/usbhid/hid-core.c).
This standard request selects report-on-change behaviour; it is not a device
reset. Key packets were first captured after this startup change; physical input
actions and rendering still need confirmation. No serial feature is read. Buffers
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
