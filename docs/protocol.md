# Original-device protocol and component contract

Only VID 0x0FD9 / PID 0x0060 is accepted. The reference is
[`StreamDeckOriginal.py` at 43666bb4](https://github.com/abcminiuser/python-elgato-streamdeck/blob/43666bb454186d1d7adeba9402f689449705d0b9/src/StreamDeck/Devices/StreamDeckOriginal.py),
with its `StreamDeck` base class and `PILHelper`. This is the original BMP
protocol, not the newer Classic/JPEG protocol.

Logical keys viewed from the front:

```text
 0  1  2  3  4
 5  6  7  8  9
10 11 12 13 14
```

Wire indices reverse each row: `[4,3,2,1,0,9,8,7,6,5,14,13,12,11,10]`.
Input is exactly 16 bytes, with each key at `1 + wire_index`. Only zero/one state
bytes are accepted. Malformed input preserves previous state and increments the
error counter. The default ignores byte zero, matching the reference; it logs
the first observed header. An optional `input_report_id` enforces a byte after
the owner's descriptor/capture establishes it. We do not assign an unobserved ID.
Extra/padded report lengths are rejected until supported with evidence.

The first [desktop capture](hardware.md#desktop-observations-2026-10-10) declares
input IDs `0x01`, `0xa0`, `0xa1` with 17 bytes including ID. This differs from the
pinned library's 16-byte read limit. Capture actual interrupt reports before
deciding whether to accept an additional byte or filter non-key IDs; no input
contract change is claimed from the descriptor alone.

The first valid report of each connection establishes a baseline without user
actions. A key already held then also has its eventual release suppressed; its
next press/release pair behaves normally. Duplicate reports have no edges;
multiple held keys are supported. Disconnect makes key sensors unavailable and
does not synthesize release actions. Queue overflow follows the same silent
baseline policy. If the device sends only on change and sends no initial report,
the first change establishes the baseline; test this explicitly on hardware
before relying on first-click behavior.

| Operation | Complete report (including ID) |
| --- | --- |
| Brightness | 17 bytes: `05 55 AA D1 01 PP`, then 11 zero bytes |
| Device reset, codec only | 17 bytes: `0B 63`, then 15 zero bytes |
| Stream initialization/reset | 8191 bytes: `02`, then zeros |
| Image page 1 | `02 01 01 00 00 KEY` + 10 zeros + 7803 BMP bytes + 372 zeros |
| Image page 2 | `02 01 02 00 01 KEY` + 10 zeros + 7803 BMP bytes + 372 zeros |

`KEY = wire_index + 1`. Both image reports are always 8191 bytes. BMPs are exactly
15,606 bytes: a 54-byte header and 72×72×3 uncompressed BGR pixel data. Only the
upstream baseline header layout is accepted. Horizontal and vertical flips occur
offline via `PILHelper`; runtime never flips the bytes again.

Brightness always means percent, including floating-point inputs. Finite values
are rounded to the nearest integer and clamped to 0–100. NaN/Infinity are rejected.
The number entity reports the desired value, not measured brightness. Desired
state survives USB reconnects; an MCU reboot uses YAML's `initial_brightness`
(default 30), because NVS brightness restoration is not implemented.

## Configuration and actions

The numbered examples are validated configurations. The hub supports:

- `id`, `initial_brightness`, optional `input_report_id`.
- `images`: list of `{id, file}` native BMPs, embedded into flash during code generation.
- Optional `on_key_press` / `on_key_release` automations with zero-based `key` argument.
- `connected`: binary sensor that becomes true after successful full stream reset
  and brightness initialization. It does not mean every image has finished redrawing.
- Optional diagnostic sensors: `errors` (transport + malformed inputs),
  `input_overflows`, `input_queue_high_water`, `internal_free_heap`,
  `internal_minimum_free_heap`, updated every ten seconds.

`binary_sensor: platform: stream_deck` accepts `key` 0–14 and `stream_deck_id`.
One binding per key is allowed. `number: platform: stream_deck` creates the single
0–100, step-1 brightness control. Normal names/action mappings belong in YAML.
Delayed binary sensor filters and initial-state triggers are rejected because they
would invalidate reconnect synchronization. `on_state_change` observes availability
changes by design; use hub key triggers or guarded press/release automations for actions.

`stream_deck.set_image` accepts `id`, `key` (constant or template), and `image` ID.
`stream_deck.redraw` requeues desired images. Typed C++ methods `set_image(key,
const NativeImage*)`, `set_brightness(percent)` and `redraw()` are also available.
Native image objects and their data must be immutable and live for the firmware's
entire lifetime. Invalid runtime keys/images return false without queuing work.

Every key defaults to a flash-resident blank BMP. After connection the driver
redraws all 15 desired images, clearing displays retained from a previous run.
Only changed desired assets are sent during normal operation. No network image
uploads, fonts, animation engine, pages, device serial storage or firmware queries.

## Home Assistant example

Example 03 toggles `${light_entity}` on physical key 0 and selects ON/OFF/? artwork
from that entity's **reported** state. Unknown/unavailable states use ?. Neither
the press nor a successful service send changes the icon optimistically. Initial
and reconnect synchronization never call `light.toggle`.

Use the ESPHome integration's option allowing the device to perform Home Assistant
actions. API encryption and encrypted OTA share the unique local API key. No HA
token or broker is required. A logging connection alone is insufficient: the
example also requires a state-subscribing API connection and fresh actual entity
feedback before acting. Commands during an outage are discarded, not replayed.

Any API client disconnect invalidates feedback conservatively until another actual
HA state callback arrives; even a logging-client disconnect can temporarily show ?.
Raw-state callbacks handle unchanged state resent after HA reconnect. This sample
detects connection loss, not a frozen HA process that keeps its TCP connection
alive; a guaranteed wall-clock freshness limit would require an HA heartbeat.

Avoid a second HA automation on key 0 that also toggles the lamp. If using external
HA binary-sensor automations, guard startup/unavailable-to-on transitions. All
examples start with `api.batch_delay: 0ms`; real rapid-transition delivery still
needs testing with the owner's HA version.
