# Stream Deck Original → ESPHome → Home Assistant
## Codex project handover — XIAO ESP32-S3 Plus

Prepared: 2026-09-26  
Updated: 2026-09-26 — revision 2, clarified power-only input and USB-C host connection  
Target device: Elgato Stream Deck Original, USB `0FD9:0060`  
Target board: Seeed Studio XIAO ESP32-S3 **Plus**  
Status: researched implementation specification; no ESP32 firmware has been built or hardware-tested as part of this handover.

## Revision 2: hardware clarification that supersedes the earlier wiring proposal

The owner clarified that the four-pad USB breakout is **only a power inlet**. Its VBUS/GND feed the XIAO's 5V/GND pins; its D+/D− are not connected. The Stream Deck connects separately to the XIAO's onboard USB-C connector through a **USB-C male to USB-A female data-capable adapter**, receiving both power and data through that connection.

Use this as the baseline topology. The previous recommendation to break out the USB-C data pair and split the peripheral power into a separate branch is **not a prerequisite**. A single source feeding two loads does not, by itself, create a conflict between two power supplies. The remaining hardware gates are source capacity/authorization, input protection, voltage drop and board-path loading, adapter compatibility, and preventing accidental second-source attachment. The firmware must assume **unswitched, externally supplied VBUS**, not a GPIO-controlled peripheral power rail.

This revision changes the hardware specification and related acceptance tests. It does not change the original-device protocol, large-report transport requirement, project scope or minimum software deliverables. No new hardware test or firmware build is claimed.

## 1. Assignment and starting point

Build a maintainable ESPHome external component that makes an original 15-key Stream Deck a standalone Wi-Fi control surface for Home Assistant. Use ESPHome's native API, not a separate desktop bridge or MQTT broker. The microcontroller must both read the physical keys and update their images and the device brightness.

The owner has already supplied this identification:

```text
Bus 009 Device 004: ID 0fd9:0060 Elgato Systems GmbH Stream Deck
```

The owner also reports that `abcminiuser/python-elgato-streamdeck` works with this unit on a computer. Treat that as the desktop baseline; do not claim that any ESP32 implementation has been validated. The power/data topology is now specified in Section 2. The exact Python revision, device firmware, complete USB descriptors, actual board revision, source rating, protection parts, and specific cables/breakout/adapter have not yet been supplied.

The board originally considered was an ESP32-C6. That is no longer the target. Implement for the available XIAO ESP32-S3 Plus, using its native USB host hardware and the ESP-IDF framework.

### First instruction to the coding agent

> Read this document before creating code. Use the clarified power-only inlet and onboard USB-C host topology in Section 2; do not redesign it around a separate USB data breakout by default. Start with repository scaffolding, pinned dependencies, a hardware checklist, a transport architecture decision and native protocol tests. Then implement incrementally through the milestones below. Resolve the original model's 8,191-byte output-report transport before investing in Home Assistant UI features. Treat proposed component configuration as an API to implement, not as an existing ESPHome platform. Proceed with hardware-independent work while requesting only the measurements or descriptors needed for the next hardware gate. Separate “implemented,” “compiled,” “unit-tested” and “hardware-verified” in every progress report.

### Minimum deliverable

Support all 15 press/release states, an HA-controllable 0–100% brightness setting, firmware-resident key images, one example where actual HA entity state selects an icon, USB disconnect/reconnect recovery, and OTA updates. Include reproducible tests and wiring documentation.

Defer other Stream Deck models, hubs, animations, dynamic font rendering, arbitrary network image uploads, LVGL, battery operation and elaborate page systems. A small page selector can follow the first working release. Do not replace ESPHome with a permanent Linux/Python service.

## 2. Hardware: power-only inlet and onboard USB-C host connection

### 2.1 Owner's intended topology

There are two physically distinct connections:

| Connection | Purpose and wiring |
|---|---|
| USB power-input breakout | Source VBUS goes to XIAO `5V` through the selected input protection; source GND goes to XIAO `GND`. Breakout D+/D− remain unconnected and insulated. |
| XIAO onboard USB-C + C-male/A-female adapter | Carries USB VBUS, GND, D+ and D− to the Stream Deck's USB-A plug. This is the only USB data connection during host operation. |

Conceptual power/data routing (protection parts and load limits still need validation):

```text
ONE regulated 5 V source
        |
        | USB power-input breakout: VBUS + GND only
        | D+ / D- not connected to the XIAO or the Stream Deck bus
        v
Selected input protection (see 2.3)
        |
        v
XIAO 5V / GND
        |
        +-- onboard power circuit --> ESP32-S3 board load
        |
        +-- shared USB VBUS / GND --> onboard USB-C
                                           |
                              passive C-male / A-female adapter
                                           |
                                      Stream Deck

USB DATA, separate from the power-input connection:
ESP32-S3 USB host <--> onboard USB-C <--> same adapter <--> Stream Deck
```

This is electrically plausible: the published Plus V1.1 schematic places the header `5V` pin and USB-C VBUS on the same net. Thus, feeding that rail can supply the board and pass power out through USB-C. The Stream Deck's load does **not** pass through the board's 3.3 V regulator. This is a schematic-based inference, not a measured current rating for the header-to-connector path. [S1, S2]

Assume one input source at a time, no battery and no powered hub for the initial build. A PC used **only as that one power source through the breakout** is not a second source and has no data connection to the host bus. Do not describe this operating state as two USB power supplies fighting each other. Source adequacy is a separate issue; see 2.4.

### 2.2 Native USB data and adapter selection

The S3 native USB signals are **GPIO19 = D−** and **GPIO20 = D+**, already routed to the onboard USB-C connector. No separate GPIO data wires, USB-C solder taps or USB-C breakout are required for the intended adapter arrangement. The board label **D19 means GPIO11**, not GPIO19; do not connect the power breakout's data pads there. Reserve GPIO19/20 for USB. [S1, S2, S3]

Start with a simple **passive, USB 2.0 data-capable USB-C male to USB-A female adapter** with verified VBUS/GND and data continuity. Do not substitute a charge-only adapter, hub, PD charging dock, Y cable or device that requires active role/power negotiation. Document the exact adapter and test both USB-C plug orientations. If it fails, inspect routing and enumeration before assuming a firmware protocol failure.

The Plus schematic shows fixed **5.1 kΩ CC pull-downs**, not a managed Type-C source port. Type-C source/sink attachment uses the CC mechanism, which is distinct from configuring the S3's USB controller as a host. Therefore this externally energized, passive-adapter arrangement is a **fixed-purpose prototype**, not a standards-compliant general-purpose USB-C source implementation. The practical expectation that a suitable passive adapter can pass power/data here must be verified on the actual hardware. [S2, S22]

Configure the S3 explicitly for host operation using the pinned ESP-IDF stack. Do not rely on the adapter to select the MCU's USB role or generate 5 V. Do not require CC resistor modifications or add a PD controller as part of the baseline firmware assignment. Broader Type-C compatibility would be a separate hardware redesign.

### 2.3 Protection, current path and voltage budget

The `5V` pin is a shared VBUS rail, not a GPIO or an independently regulated/current-limited host output. Seeed specifies a series diode when using it as an external power input. Its orientation is **anode toward the input source, cathode toward XIAO 5V**. The onboard power-path diode does not isolate the header 5V pin from USB-C VBUS. [S1, S2]

In this clarified arrangement, an external input diode carries the **combined board + Stream Deck current**, unlike the board-only branch in the superseded diagram. Select a suitably rated low-forward-drop part and include its drop and dissipation in the power budget. A properly designed reverse-current-blocking/ideal-diode circuit is an alternative when its behavior is verified. Do not choose an arbitrary signal diode or treat reverse-current blocking as overcurrent protection. [S1, S23; circuit implications of the topology]

Include suitable input fault-current protection, or document the source's current limiting and why it adequately protects the actual wiring/board path. A high-current supply does not force that current into normal loads, but its rating alone does not protect thin wires or PCB tracks from a fault. [S21, S23]

For qualification, record source voltage and current rating, input cable/wire size and length, protection parts, adapter identity, total operating/peak current, and voltage at both XIAO 5V and the Stream Deck-facing USB-A VBUS. The common input path carries both loads; the board-to-USB-C branch carries the Stream Deck load. The cited board documents do not establish a guaranteed external-peripheral current rating for that branch, and the board's 3.3 V regulator rating is not that rating. Confirm the actual PCB revision and inspect/check the path under load. [S1, S2; qualification requirements]

Use these engineering checks:

```text
Required source capability >= maximum combined input demand + design margin

VBUS at Stream Deck = source voltage
                    - input protection drop
                    - wire/connector/PCB-path drops
```

Measure startup/hot-plug behavior and operation with Wi-Fi active and brightness at 100%; use a scope for short dips when available. Confirm stable USB operation, no brownouts, and no abnormal heating. Do not infer peak or inrush current solely from USB `bMaxPower`, a source label or the board's typical-current table. Do not raise the supply above the permitted 5 V operating range to conceal excessive voltage loss. [S21; test requirements]

If load-path qualification fails, revisit a separately supplied peripheral branch or host-power carrier as a **fallback**, not a prerequisite imposed by the old interpretation. Any fallback needs a complete revised wiring diagram so that parallel VBUS paths do not bypass its protection.

### 2.4 Dedicated 5 V supply versus PC USB power

Prefer a regulated 5 V source explicitly capable of the measured combined load without relying on a data handshake at this inlet. Do not assume every USB charger exposes its label's highest power through bare VBUS/GND; verify the actual 5 V output mode and source requirements. Never use a high-voltage PD/QC trigger to feed this rail.

A **standard PC USB data port is not an interchangeable, guaranteed high-current supply** for this power-only inlet. With the inlet D+/D− disconnected, neither the XIAO nor the Stream Deck enumerates with that PC. The conventional USB 2.0 power model permits one 100 mA unit load before configuration; up to 500 mA needs the appropriate host configuration. The S3 enumerating the Stream Deck on its separate downstream bus does not obtain a larger budget from the upstream PC. [S21, S23]

Some ports provide more in practice, but that is not proof of an authorized or protected power arrangement. Treat PC power as an optional, source-specific test only after establishing that the particular port supports the required power-only load and verifying startup, current and voltage behavior. Do not connect the inlet data pads to the S3 host pair to try to fix power negotiation. [S23; project constraint]

### 2.5 Single-source invariant and programming

During host operation, the native USB-C connector is dedicated to the Stream Deck adapter. The input breakout may connect to either the selected supply or a qualified PC power port, **not both**. Keep its data pads open; they are not an upstream USB link.

**Before connecting a PC to the XIAO's native USB-C connector for flashing, physically disconnect the breakout's power feed from the board/source and remove the Stream Deck adapter.** Unplugging the feed is preferable to merely assuming an attached source is off. Native USB flashing is a separate operating configuration with the PC as the only power/data source.

The single-source topology avoids the earlier source-conflict concern, but accidental second-source attachment still matters because header 5V and USB-C VBUS are tied. An input-branch diode alone does not isolate an externally energized board from a PC attached directly to USB-C. [S2, S23]

Use a power-inlet connector/cable arrangement that cannot readily be confused with the Stream Deck host output. Do not introduce a USB-A male-to-male power cable between host-style sockets. Label the inlet and host connection; insulate exposed pads and provide strain relief.

Configure runtime logging on **UART0**, not USB Serial/JTAG. A separate **3.3 V logic-level** USB-UART adapter can receive logs from XIAO **D6/GPIO43/TX**; connect its RX there and share GND. For bidirectional UART, connect adapter TX to **D7/GPIO44/RX**. Leave the adapter's power pin disconnected when the board is separately powered. Document BOOT/reset recovery and establish OTA early. Do not burn eFuses to solve a USB logging conflict. [S1, S3, S12]

### 2.6 Firmware assumptions and hardware gate

**VBUS is externally supplied and unswitched in the baseline.** Do not invent a `vbus_enable_pin`, assign a GPIO to generate 5 V, or claim software power-cycle recovery. A real external load switch would be a hardware change. A CPU reset, OTA reboot or USB bus reset does not remove peripheral power from this shared rail. Consequently, test startup both with a newly powered Stream Deck and with a Stream Deck that stayed powered while the ESP restarted. [S2; circuit inference and implementation requirement]

Before first connecting the Stream Deck, confirm: actual board revision; source and protection ratings; VBUS polarity/common ground/no shorts; input D+/D− isolation; adapter data routing and unloaded VBUS; and the absence of any second source. Then perform supervised loaded voltage/current/temperature and enumeration tests. Keep battery power disconnected initially.

Treat these as hardware acceptance gates, not a reason to delay repository scaffolding, protocol fixtures or native tests. Record the distinction between a plausible topology, a reviewed parts-level implementation and a hardware-tested setup.

## 3. Toolchain and provenance

Use a normal external component: Python configuration/code-generation files plus C++ runtime code under `components/stream_deck/`. Do not use the removed legacy `custom_component` mechanism or execute the desktop Python library on the ESP32. [S11]

At project start, select and pin a released ESPHome version and its supported ESP-IDF/toolchain combination. Record the resolved IDF version, USB component version where applicable, build image/environment, and tested Home Assistant version. Do not independently upgrade IDF underneath ESPHome without a documented reason and a successful build.

Pin the Python Stream Deck reference revision and Pillow version used for fixtures. Record the owner's working revision when available. Retain upstream MIT attribution for adapted code. Do not commit credentials, logs containing secrets, or unnecessary device serial numbers. [S4, S7]

**Source-date caveat:** the online ESPHome `dev` files inspected for this handover are moving references. Recheck their equivalents in the selected release. Pin source SHAs in the project's technical notes rather than relying permanently on `dev`, `master` or `latest` URLs.

The Plus is specified with **16 MB flash and 8 MB PSRAM**. Start with explicit `variant: esp32s3`, `flash_size: 16MB` and ESP-IDF. Verify detected memory at boot. Octal PSRAM at 80 MHz is a candidate configuration to validate, not a reason to enable octal flash. Avoid inventing a board identifier for the Plus; ESPHome supports explicit variant configuration. [S1, S13, S14]

## 4. Resolve the large-report USB transport before committing the architecture

ESPHome's stock `usb_host` component is useful for enumeration, but the reviewed implementation is **not a drop-in transport for this model's image reports**. [S8–S10]

At review time:

| Layer | Observed limitation |
|---|---|
| `usb_host` YAML | `max_packet_size` accepts only 64, 128, 256, 512 or 1024 |
| `USBClient::setup()` | Allocates transfer slots using the configured packet-buffer size |
| `USBClient::transfer_out()` | Rejects output longer than the allocated transfer buffer |
| `USBClient::control_transfer()` | Rejects payloads larger than the buffer minus the 8-byte setup packet |
| `usb_host` code generation | Sets `CONFIG_USB_HOST_CONTROL_TRANSFER_MAX_SIZE` to 1024 |

The original Stream Deck sends **8,191-byte output reports**. Setting `max_packet_size: 8192` is not a supported solution. A USB endpoint's maximum packet size is also not the same thing as a complete HID report or USB transfer length. [S4, S8–S10]

### Recommended decision path

Prefer the **ESP-IDF asynchronous USB host APIs with dedicated transfer allocations**, behind a small transport interface. Either let the external component own the host stack, or integrate with an already installed host bus using a clearly supported client lifecycle. There must be **exactly one host-stack installer** and no duplicate claimant for the device interface. [S15]

For the initial implementation, owning the stack inside the external component is a reasonable default because the project targets one device and needs custom large transfers. Do not also enable stock `usb_host` in that final configuration. If reusing the stock installer, audit installation order, client event processing, teardown and generated SDK options before selecting it.

A narrowly scoped, tested extension to ESPHome's USB wrapper is an alternative, not a requirement. Avoid private-buffer manipulation, blindly expanding every transfer slot, or loading two unrelated host stacks. A generic HID driver is also optional; audit its output/control length limits before depending on it.

For a direct control transfer, an 8,191-byte data stage needs **8,199 bytes including the 8-byte setup packet**, plus any allocator/alignment allowance required by the pinned stack. A nominal 8,192-byte total buffer is insufficient. Use the USB host allocation APIs for DMA-suitable buffers; do not assume arbitrary PSRAM pointers are valid USB DMA buffers. Audit the selected stack's control-transfer maximum and the final generated `sdkconfig`, including whether the configured cap includes setup overhead. [S15]

An early transport test must prove a complete 8,191-byte report. Do not claim image support after testing only a 17-byte brightness request.

## 5. Original-device protocol contract

### 5.1 Scope and source of truth

Support **VID `0x0FD9`, PID `0x0060` only** initially. Elgato's newer “Stream Deck Classic” protocol explicitly excludes this original model. Use `StreamDeckOriginal.py`, its base class, the image helper and the working desktop implementation as references. Do not substitute a newer JPEG protocol. [S4–S6, S18]

All report lengths below include the report ID at byte zero. Golden fixtures and an optional desktop USB capture must validate the actual transport conventions; do not strip or duplicate that byte accidentally.

### 5.2 Key mapping and input

Expose logical zero-based keys as viewed from the front:

```text
 0  1  2  3  4
 5  6  7  8  9
10 11 12 13 14
```

The reference reverses each row's column order:

```text
wire_index(k) = (k / 5) * 5 + (4 - (k % 5))     # integer division
```

The mapping is `[4,3,2,1,0, 9,8,7,6,5, 14,13,12,11,10]`. Image headers use `wire_index(k) + 1`. The reference reads 16 input bytes and uses `report[1 + wire_index(k)]` as the state for logical key `k`. [S4]

Reject keys outside `0..14`; do not copy the reference's permissive upper-bound check. Validate input length before accessing states. The reference discards, rather than validates, the first input byte: determine the actual input report ID and allowed report lengths from descriptors/captures, not from a newer model. A short, malformed or failed read must not become “all keys released.”

Track edges from full state reports; support multiple held keys. Duplicate reports must not repeat actions. Keep initial/reconnection state synchronization distinct from a new user press.

### 5.3 Feature and initialization reports

| Operation | Reference report bytes |
|---|---|
| Brightness | 17 bytes: `05 55 AA D1 01 PP`, then 11 zero bytes; `PP` is integer 0–100 |
| Device reset | 17 bytes: `0B 63`, then 15 zero bytes |
| Image-stream reset | 8,191 bytes: `02`, then 8,190 zero bytes |
| Serial read, optional | Feature report ID `03`, requested length 17; reference extracts text from offset 5 |
| Firmware read, optional | Feature report ID `04`, requested length 17; reference extracts text from offset 5 |

The base class calls image-stream reset when opening the device. Port that initialization behavior and test it after reconnecting or aborting an image upload. Device reset and image-stream reset are different operations. Do not repeatedly reset the whole device as a substitute for error handling. [S4, S5]

Define firmware brightness in percent throughout. ESPHome number values may arrive as floating-point percentages; do not copy the Python library's “float means normalized 0–1” convention and accidentally turn 50.0 into 5,000%.

### 5.4 Image bytes and two-page framing

The normal asset is an uncompressed 24-bit **72 × 72 BMP**. The reference image helper flips horizontally and vertically before BMP encoding. Generate native bytes offline using that helper, or match it byte-for-byte; do not apply those flips again at runtime. [S4, S6]

For the baseline BMP format:

```text
Pixel data                       72 × 72 × 3 = 15,552 bytes
BMP header                                        54 bytes
Complete native BMP                           15,606 bytes
Reference split                               7,803 + 7,803 bytes
Output report length                           8,191 bytes
Per-report header                                 16 bytes
Per-report zero padding             8,191 - 16 - 7,803 = 372 bytes
```

**Split the BMP in half as the reference does. Do not fill the first report with 8,175 image bytes merely because that much space is available.**

Each report's 16-byte header is:

```text
02 01 PAGE 00 LAST KEY 00 00 00 00 00 00 00 00 00 00
```

`PAGE` is 1 then 2; `LAST` is 0 then 1; `KEY` is the one-based remapped key. Append that page's 7,803 BMP bytes and 372 zero bytes. Send the entire 8,191-byte report. [S4]

For example, logical key 0 has `KEY = 05`:

```text
Page 1: 02 01 01 00 00 05 00 00 00 00 00 00 00 00 00 00
Page 2: 02 01 02 00 01 05 00 00 00 00 00 00 00 00 00 00
```

Initially reject unsupported BMP dimensions, bit depth, compression, header layout or length. Use RGB test patches, text, a top-left marker and an asymmetric arrow to reveal orientation/channel-order mistakes. Do not treat an arbitrary `.bmp` file as an already valid native asset.

### 5.5 USB transfer routing: inspect, do not guess

The provided `lsusb` line does not identify interfaces or endpoints. Enumerate the active configuration, find the relevant HID interface and interrupt IN endpoint, record its address and packet size, and determine whether there is an interrupt OUT endpoint. Do not hardcode interface 0 or endpoint `0x81` without evidence.

HIDAPI's libusb transport sends normal output via interrupt OUT when available, otherwise via HID `SET_REPORT(Output)` on endpoint zero. Feature writes use `SET_REPORT(Feature)`. Mirror the verified route for this device. [S17]

For the control route, verify these against the pinned HIDAPI implementation/capture:

| Request | bmRequestType | bRequest | wValue | wIndex | wLength |
|---|---:|---:|---:|---|---:|
| Brightness feature | `0x21` | `0x09` | `0x0305` | HID interface number | 17 |
| Device-reset feature | `0x21` | `0x09` | `0x030B` | HID interface number | 17 |
| Image output, only if using EP0 | `0x21` | `0x09` | `0x0202` | HID interface number | 8191 |

These numbered reports include their nonzero report ID in both `wValue` and the first data byte; that is not accidental duplication. USB setup fields are little-endian on the wire. Let the host stack packetize transfers; never turn one image report into independent 64-byte HID reports. [S17]

## 6. Runtime architecture and safety properties

Separate three layers:

**Protocol codec:** hardware-independent C++, with fixed bounds and native tests. It maps keys, validates/decodes input, builds feature requests and produces either page of a native BMP upload. No ESPHome or FreeRTOS dependency in this layer.

**USB transport:** owns descriptors, interface claiming, async transfers, task/event processing, timeouts/recovery and resource lifetime. Pass complete reports to this layer, not display abstractions. The exact API must match the pinned IDF; do not invent host functions from memory. [S15]

**ESPHome component:** owns entities, automations, desired images/brightness and main-loop publication. Keep HA entity names and application behavior in YAML rather than the USB driver.

Suggested lifecycle:

```text
DETACHED -> DISCOVERING -> CLAIMED -> INITIALIZING -> READY
    ^                                                   |
    +------------- disconnect / recovery --------------+
```

Normal absence at boot must not permanently fail the component or prevent networking/OTA. Validate VID/PID and descriptors before sending commands. Publish a diagnostic connection state separately from API connectivity.

### Concurrency and queues

Use the USB library/client event-processing model required by the selected stack. A transfer completion callback must remain short: copy necessary data into owned storage, schedule subsequent USB work where permitted, and return. Publish ESPHome entity states and run automations on the main loop, not from arbitrary USB/FreeRTOS callbacks. [S9, S15]

Maintain **an ordered input-edge/report queue** separate from **a coalescing image queue**. Collapsing all input into the latest boolean state can lose a complete short click; collapsing pending image requests to the latest desired image per key is useful.

Keep one key's two-page upload serialized. Coalesce only pending work, not the bytes of an active upload. If an image changes during transmission, finish or cleanly abort the active image before sending the newest one. Bound queue sizes; expose overflow/error counters and define a resynchronization policy. Do not silently drop events and still claim lossless delivery.

Use session/generation IDs so callbacks from an old USB connection cannot modify a new connection's state. Never reuse/free a submitted transfer buffer before completion/cancellation is resolved. Log submission failures, STALLs, short transfers and disconnects with bounded rate. Implement software deadlines and recovery using APIs that actually exist; do not assume a timeout field is enforced by every IDF host version.

On disconnect, clear or invalidate held-key state without treating cleanup as a real release automation. On reconnect, synchronize input without inventing a press for an already-held key, restore desired brightness and redraw the desired images. Document how an eventual physical release of a key held across reconnect is handled.

The baseline has always-powered VBUS. Reinitialize after an ESP-only reset/OTA reboot even when the Stream Deck has retained power and display state. Exercise USB/protocol recovery without assuming that restarting the MCU or host stack physically power-cycles the peripheral. If a fault ultimately needs removal of power, report that requirement explicitly and document manual unplug/replug; do not implement a fictitious power-switch GPIO.

### Memory and scheduling

Keep native assets in flash initially. Use PSRAM for optional caches only after validation; reserve DMA-compatible internal memory for USB buffers. One 15,606-byte native image plus a reusable output-transfer buffer is enough to avoid a full 15-key framebuffer. Do not allocate every image dynamically inside transfer callbacks.

Yield during multi-key redraws; keep input reception and Wi-Fi responsive. Change-only updates are the baseline. Record internal free heap, minimum free heap, queue high-water marks and transfer errors during stress tests. Do not promise animation performance or input latency before measuring it.

## 7. ESPHome and Home Assistant interface to implement

Component domain: **`stream_deck`**. This is a proposed new external component, not an assertion that stock ESPHome already provides it.

| Proposed interface | Required behavior |
|---|---|
| Hub ID | Represents one original Stream Deck and its desired display state |
| `binary_sensor` platform | A key index `0..14`; publishes physical pressed state |
| Hub press/release triggers | Optional in addition to sensors; actual user edges only |
| Brightness `number` | 0–100%, step 1; tracks desired setting and reapplies after reconnect |
| Connected diagnostic sensor | Actual USB device/driver readiness, not merely Wi-Fi or API status |
| Set-image action or typed C++ method | Selects a firmware-resident native asset for a logical key |
| Restore/redraw operation | Reapplies current desired images without changing HA entities |

Use proper code-generation registration and validation for all exposed platforms/actions. Reject duplicate key bindings where ambiguous, invalid keys, unsupported platforms and incompatible USB ownership. Brightness is a requested/applied setting, not a claimed measured display value unless readback is implemented.

Provide one HA example: logical key 0 requests `light.toggle` for a replaceable example entity, and the entity's **actual reported state** selects on/off/unknown icons. Use a Home Assistant text sensor when distinguishing `unknown`/`unavailable` from `off` is important. Keep the action mapping in YAML and document the permission required for ESPHome-originated HA actions. [S16, S19]

Do not assume any native-API connection proves HA is online; a logging client can also connect. Do not replay old action requests after an outage. Mark unavailable/stale state explicitly and restore icons from fresh HA state after reconnection.

For binary-sensor-driven HA automations, configure `api.batch_delay: 0ms` initially to preserve rapid transitions, then test actual delivery. Guard automations against startup/unavailable-to-on transitions. Avoid triggering the same HA action through both a local press automation and an HA sensor automation. ESPHome documents immediate sending mode and HA action permissions. [S16]

Implement state-driven icons before adding arbitrary custom API image uploads. For normal commands prefer existing ESPHome automation/native-API facilities instead of hardcoded HTTP requests or storing a long-lived HA token on the board.

## 8. Initial core-only enumeration configuration

Create `examples/01_usb_probe.yaml` from the following starting point and validate it against the pinned ESPHome version. It is **an enumeration probe only**, not a Stream Deck driver or a hardware-tested configuration. Sources for the core options: [S8, S12–S14, S16, S20].

```yaml
esphome:
  name: streamdeck-original
  friendly_name: Stream Deck Original

esp32:
  variant: esp32s3
  flash_size: 16MB
  framework:
    type: esp-idf

psram:
  mode: octal
  speed: 80MHz

logger:
  hardware_uart: UART0
  baud_rate: 115200
  level: VERBOSE  # Enumeration bench only; reduce for normal operation.

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password

api:
  encryption:
    key: !secret api_encryption_key
  batch_delay: 0ms
  reboot_timeout: 0s  # Development: do not reboot just because HA is absent.

ota:
  - platform: esphome
    password: !secret ota_password

usb_host:
  # VBUS comes from the power-only inlet via the board rail; no GPIO power switch.
  devices:
    - id: deck_probe
      vid: 0x0FD9
      pid: 0x0060
```

Place a real, untracked `secrets.yaml` alongside the example, with a valid API encryption key. Ship only `secrets.example.yaml`; use synthetic CI secrets for validation. Add a secrets-generation/setup instruction, not working credentials shared across installations.

Remove this debug-device claimant when switching to the real driver. If the external component owns host installation, remove the entire stock `usb_host` block in subsequent examples. The probe's successful enumeration does not prove HID access or large-report support.

In the finished examples load local code through `external_components`, for example a source path `../components` relative to the example directory. Generate and compile the final `stream_deck` schema before documenting runnable examples. Do not fill the README with invented YAML that has never passed validation. [S11]

## 9. Asset conversion and independent tests

Create an offline conversion tool accepting a source image, compositing transparency onto an explicit background, converting to RGB and producing the exact 72×72 native BMP expected by the reference helper. Also emit a C++ asset or build-time inclusion format, byte length and SHA-256 manifest. Specify scaling/cropping behavior explicitly. Native conversion and image-page encoding are separate steps. [S6]

Generate golden fixtures using the **pinned upstream Python encoder with a recording/mock transport**, not a second copy of the new algorithm. Capture brightness, both reset operations and both image reports for logical keys 0, 4, 5, 10 and 14. Preserve expected output bytes as test fixtures with provenance. No physical USB device should be needed for these fixture tests.

Native C++ tests must compare output byte-for-byte with those fixtures, including report IDs, padding and page order. Test mapping for every key, malformed/short input, simultaneous presses, duplicate reports, invalid key IDs, brightness boundaries, malformed BMPs and image-length validation. Hardware-independent scheduler tests should cover reconnect generations and two-page upload interruption.

A mock proves the codec against the reference; it does not prove the ESP32 transport, USB power or display orientation. Keep those acceptance categories separate.

## 10. Repository deliverables

Use approximately this structure; small implementation-driven changes are acceptable:

```text
README.md
AGENTS.md
HANDOVER.md                         # Preserve this specification.
LICENSE
THIRD_PARTY_NOTICES.md
docs/
  hardware.md                      # Actual reviewed wiring and power diagram.
  protocol.md
  testing.md
  versions.md
  decisions/usb-transport.md
components/stream_deck/
  __init__.py                      # Schema and hub code generation.
  binary_sensor.py
  number.py
  automation.h                     # Only if custom actions/triggers are used.
  stream_deck.h
  stream_deck.cpp
  protocol.h
  protocol.cpp
  usb_transport.h
  usb_transport.cpp
examples/
  01_usb_probe.yaml
  02_keys_brightness.yaml
  03_images_home_assistant.yaml
  secrets.example.yaml
assets/
tools/
  convert_assets.py
  generate_reference_fixtures.py
tests/
  fixtures/
  native/
  test_config.py
requirements-dev.txt               # Pinned, or equivalent lockfile.
.github/workflows/ci.yaml
.gitignore
```

Keep `AGENTS.md` short: fixed target, source-of-truth protocol, hardware gates, no secrets, no unverified success claims, and commands for tests/builds. Include exact setup, compile, flash, OTA and recovery commands in the README once validated.

CI must run native codec tests, configuration/schema tests and firmware compilation for supported examples. Pin dependencies and create temporary nonproduction secrets in CI. Do not leave hardware-dependent tests as automatically passing placeholders. Keep firmware build output and local credentials out of Git.

## 11. Implementation milestones and acceptance gates

### M0 — Reproducible foundation

Create the repository, version manifest, hardware checklist and transport decision note. Implement the independent codec and reference fixtures. Pin dependencies and compile a minimal ESPHome configuration. Report unavailable tools honestly; no fake build logs.

**Pass:** reproducible native tests, source provenance, baseline firmware build and an explicit plan for large reports. Hardware work may remain blocked on wiring confirmation.

### M1 — Hardware and enumeration

Use the owner's already clarified topology in Section 2. Request only the still-missing concrete details (board revision, source rating, protection parts, breakout connector/cable and exact C-to-A adapter) and these desktop outputs:

```sh
lsusb -v -d 0fd9:0060
lsusb -t
```

Record configuration/interface descriptors, endpoint directions/addresses, transfer types, packet sizes, bus speed and declared power. Retrieve the HID report descriptor where possible; explain any permissions needed rather than treating incomplete `lsusb` output as complete. Request an optional usbmon/Wireshark capture of the working Python test only when it resolves a concrete transport uncertainty; avoid capturing unrelated devices.

Verify the power-only inlet/data-isolation checklist and single-source invariant. Flash the core probe in the separate PC-only flashing configuration, then switch to the powered host configuration. Measure VBUS unloaded and under load, confirm memory and UART/OTA logs, and enumerate `0FD9:0060` repeatedly. Test both orientations of the selected USB-C adapter. Record actual wiring, board revision, source, protection, currents and voltage drops. A PC-source variant requires its own power-budget qualification, not just a successful boot.

**Pass:** reviewed single-source implementation with recorded electrical checks, stable boot, correct memory detection, working logs/OTA and repeatable USB enumeration. Adapter/source qualifications apply only to the tested parts. Enumeration alone is not completion of the driver.

### M2 — Input, features and the large-report gate

Implement the chosen async host client, read button states and send brightness reports. Then test image-stream reset as a complete 8,191-byte output, followed by one known-good two-page image. Capture transfer statuses and actual byte counts. Revisit the abstraction or SDK configuration before proceeding if large transfers are rejected or stalled.

**Pass:** all key indices are correct; brightness values 0, 1, 50 and 100 work; the complete large-report route works; a known asymmetric image displays on the intended key.

### M3 — Display service and recovery

Add firmware assets, change-only updates, serialized two-page uploads and desired-state restoration. Test all 15 key positions with numbered asymmetric images. Exercise input while repeatedly redrawing keys. Unplug during either upload page and while a key is held. Also reset the ESP without removing the shared 5 V supply, leaving the Stream Deck continuously powered, and verify reinitialization and desired-state restoration.

**Pass:** correct orientation/color/order across all keys, no page interleaving, no spurious user actions on reconnect, no stuck pressed state, no crash/leaked transfer on unplug, restored images and brightness after reconnect or an ESP-only reboot. Recovery makes no unsupported promise to switch peripheral power.

### M4 — ESPHome entities and HA behavior

Implement the documented component schema, all key entities, brightness control and connected diagnostics. Deliver one end-to-end HA lamp example using real entity feedback rather than optimistic icon toggles. Test API/Wi-Fi/HA outages, unavailable entities and actions initiated elsewhere.

**Pass:** a physical press causes exactly one intended action; changing the entity in HA updates the icon; unavailable state is distinguishable; reconnection does not replay commands; OTA remains usable.

### M5 — Release qualification

Targets for the first hardware-tested release: 10 cold starts, 10 ESP-only warm restarts with the Stream Deck continuously powered (including an OTA reboot), at least 20 peripheral unplug/replug cycles, 100 deliberate press/release pairs with no missing or duplicate actions under the documented test conditions, simultaneous held keys, disconnects during image output, and an overnight soak with periodic state changes. Include high-brightness/Wi-Fi load testing on the final power path. Record electrical measurements, heap/queue/error trends and any limitations. These are acceptance targets, not tests already performed.

**Pass:** documented results with firmware commit, dependency versions and wiring revision; no unexplained reset, persistent state corruption or growing resource leak. Measure responsiveness and full-page update time instead of inventing performance guarantees.

## 12. Reporting and unresolved information

At each handoff, provide the commit/files changed, commands actually run and their results, hardware observations versus mocked results, known issues and the next concrete test. End with the narrow question needed to unblock that test only when necessary.

Already established: the four-pad breakout is a power-only inlet, and the Stream Deck receives power/data through the onboard USB-C port and a C-male/A-female adapter. Do not ask the owner to explain that topology again or insist on an extra USB-C data breakout.

Still to establish: actual Plus PCB revision; exact adapter, inlet connector and cables; supply rating/source behavior and protection parts; loaded-path measurements; complete descriptors; Python baseline revision/device firmware; and HA entity names for the example. These do not prevent scaffolding and native protocol work now.

Distinguish the corrected single-source topology from a qualified implementation. Do not claim the project is hardware-verified because the desktop library works, tests pass or firmware compiles. Success requires the real S3-to-Stream-Deck link, correct display output, reliable powered-peripheral reboot recovery and end-to-end HA behavior.

## 13. Primary sources

Accessed 2026-09-26. The moving source links below are research starting points; replace them with pinned revisions in the project where appropriate. Bracketed source groups elsewhere in this document refer to these entries.

**S1 — Seeed board specifications, Plus pin map and power guidance.**  
https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/

**S2 — Seeed XIAO ESP32-S3 Plus V1.1 schematic, 2026-01-15; circuit on PDF page 4.**  
https://files.seeedstudio.com/wiki/SeeedStudio-XIAO-ESP32S3/res/XIAO_ESP32S3_Plus_V1.1_SCH_260115.pdf

**S3 — Espressif S3 USB documentation; physical D−/D+ pins and console behavior.** The device-mode page is cited for pin routing only, not as the host implementation.  
https://docs.espressif.com/projects/esp-idf/en/v5.4.2/esp32s3/api-reference/peripherals/usb_device.html  
https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/usb-serial-jtag-console.html

**S4 — Original Stream Deck implementation; authoritative report framing for this project.**  
https://github.com/abcminiuser/python-elgato-streamdeck  
https://raw.githubusercontent.com/abcminiuser/python-elgato-streamdeck/master/src/StreamDeck/Devices/StreamDeckOriginal.py

**S5 — Stream Deck base class; open/reset-stream sequence.**  
https://raw.githubusercontent.com/abcminiuser/python-elgato-streamdeck/master/src/StreamDeck/Devices/StreamDeck.py

**S6 — Reference PIL image helper.**  
https://raw.githubusercontent.com/abcminiuser/python-elgato-streamdeck/master/src/StreamDeck/ImageHelpers/PILHelper.py

**S7 — Upstream license.**  
https://raw.githubusercontent.com/abcminiuser/python-elgato-streamdeck/master/LICENSE

**S8 — ESPHome USB-host configuration and enumeration probe.**  
https://esphome.io/components/usb_host/

**S9 — ESPHome USBClient implementation and transfer-size checks.**  
https://raw.githubusercontent.com/esphome/esphome/dev/esphome/components/usb_host/usb_host_client.cpp  
https://raw.githubusercontent.com/esphome/esphome/dev/esphome/components/usb_host/usb_host.h

**S10 — ESPHome USB-host schema and generated SDK configuration.**  
https://raw.githubusercontent.com/esphome/esphome/dev/esphome/components/usb_host/__init__.py

**S11 — ESPHome external component structure/loading.**  
https://esphome.io/components/external_components/

**S12 — ESPHome logger hardware UART selection.**  
https://esphome.io/components/logger/

**S13 — ESPHome ESP32 variant, flash and framework configuration.**  
https://esphome.io/components/esp32/

**S14 — ESPHome PSRAM configuration.**  
https://esphome.io/components/psram/

**S15 — Espressif USB host architecture, transfer APIs and configuration.** Use documentation matching the pinned framework.  
https://docs.espressif.com/projects/esp-usb/en/latest/esp32s3/usb_host.html  
https://docs.espressif.com/projects/esp-idf/en/v5.4.2/esp32s3/api-reference/peripherals/usb_host.html

**S16 — ESPHome native API, immediate state delivery and HA action permissions.**  
https://esphome.io/components/api/

**S17 — HIDAPI libusb implementation, `hid_write` and feature/control transfers.**  
https://raw.githubusercontent.com/libusb/hidapi/master/libusb/hid.c

**S18 — Elgato's Classic documentation explicitly excludes PID 0x0060.**  
https://docs.elgato.com/streamdeck/hid/stream-deck-classic/

**S19 — Importing HA states as ESPHome text sensors.**  
https://esphome.io/components/text_sensor/homeassistant/

**S20 — ESPHome OTA configuration.**  
https://esphome.io/components/ota/esphome/

**S21 — Texas Instruments, “Powering electronics from the USB port,” SLYT118, first article, PDF pages 1–2.** Historical USB 2.0 enumeration/current, inrush and power-path guidance; not a universal description of every modern charging port.  
https://www.ti.com/lit/pdf/slyt118

**S22 — Texas Instruments TPS25751 datasheet, section 8.3.4, PDF page 37.** Reference for Type-C CC source/sink attachment, distinct from USB data-host configuration. This controller is not fitted to the XIAO and is not a required component for the prototype.  
https://www.ti.com/lit/ds/symlink/tps25751.pdf

**S23 — Analog Devices, “USB Battery Charging Guide.”** USB 2.0 power-budget communication, reverse-current blocking and the distinction between actual port current availability and permitted/protected operation. Interpret its historical PC-port observations in context rather than as guarantees for current hardware.  
https://www.analog.com/en/resources/technical-articles/usb-battery-charging-guide.html
