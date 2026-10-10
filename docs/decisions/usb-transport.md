# USB transport decision

Status: implemented and exercised without hardware. Real full-report transfers
remain an acceptance gate. The attached handover is preserved unchanged at
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
The transport therefore submits contiguous batches of at most `32 * MPS`, with
the only short packet at the end. At MPS 64 the lengths are 2048, 2048, 2048,
2047. The application still hands over one complete report. Continuations add
no report ID, HID header, padding or ZLP and cannot interleave another report.
The host packetizes each batch. Fake-IDF tests concatenate the submissions and
compare all 8191 bytes with the upstream fixture. Whether this branch is used on
the owner's unit is unknown until its descriptors are captured.

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

On failed submission, STALL, short output, deadline or detach, invalidate the
session. Use `usb_host_lib_set_root_port_power(false)` to disconnect the controller
logically. This IDF's public halt/flush endpoint API cannot address EP0; the root
disconnect drives cancellation through the stack's device-gone path. Halt/flush
claimed nonzero endpoints as needed, keep pumping client callbacks, and release
interfaces/close/free buffers only after every submitted transfer has retired.
Re-enable the controller after a five-second recovery delay and discover again.

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
