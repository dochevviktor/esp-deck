# Home Assistant runtime controls (P4)

[`05_home_assistant_runtime.yaml`](../examples/05_home_assistant_runtime.yaml)
is the generic firmware configuration. HA owns bindings and the authoritative
layout; the ESP fetches allowed PNGs, renders labels and sends native images.
Changes within the supported styles and configured asset origins need no build
or OTA. Example 04 remains the installed bench baseline: P4 has been compiled
and host-tested, but has not been deployed or tested with a live HA server.

## Install the example after the deployment gate

Before a device upload, establish the owner's HA version, actual reachable asset
origin/PNG, and readiness to replace the bench firmware, as required by P5.
The HA installation must support ESPHome user-defined action responses and HA
script `response_variable`; the actual installed HA version is still unknown.
The firmware adapter compiles against pinned ESPHome 2026.9.0. See
[ESPHome's action-response interface](https://esphome.io/components/api/#calling-from-home-assistant).

1. Set `asset_origin` in example 05 to the HA origin reachable from the ESP, such
   as `http://homeassistant.local:8123`. Only non-sensitive PNGs belong under HA's
   `config/www/streamdeck/`, served as `/local/streamdeck/`. The demo files are
   `assets/source/light_on.png`, `light_off.png` and `unknown.png`. A different
   allowed origin is a firmware configuration change; changing paths/content
   inside that origin is an HA-only change. HTTPS also needs valid time and a
   trusted server certificate; see [asset loading](asset-loading.md).
2. Build synthetic validation firmware with
   `.venv/bin/python tools/check_firmware.py --compile --example 05_home_assistant_runtime`.
   Never upload it. For a later explicitly requested upload, build privately
   with `--deploy`, using local `examples/secrets.yaml`, and upload only the
   resulting `.build/deploy/05_home_assistant_runtime/build/firmware.ota.bin`.
   The existing [OTA and wiring instructions](../README.md#flash-ota-and-recovery-when-hardware-is-available)
   still apply; native USB is the host, UART0 is for logs, and VBUS is unswitched.
3. Connect through the encrypted ESPHome integration. This example has no
   firmware-originated HA service calls. Its native event entities do not require
   enabling the integration's “Allow the device to perform Home Assistant
   actions” option. Keep bindings in HA; don't also bind its binary key sensors
   to the same actions.
4. Merge [`visual_patch.yaml`](../examples/home_assistant/visual_patch.yaml) and
   [`runtime_scripts.yaml`](../examples/home_assistant/runtime_scripts.yaml)
   into HA's `scripts.yaml` (the files are script mappings). Merge
   [`runtime_automations.yaml`](../examples/home_assistant/runtime_automations.yaml)
   into `automations.yaml` (a list). Preserve your existing entries. Alternatively,
   use separate directories with HA's `!include_dir_merge_named` for scripts and
   `!include_dir_merge_list` for automations.
5. Check the actual entity IDs in HA Developer Tools. The examples assume
   `sensor.stream_deck_original_visual_session` and
   `event.stream_deck_original_key_0_edge`. Registry renames can differ. The
   default device action prefix is `esphome.streamdeck_original_`.
6. Replace `light.example_lamp` in both HA files, and set `artwork_base` to match
   the configured origin. Reload scripts and automations. Run
   `script.stream_deck_sync_layout` once to test synchronization; inspect its
   trace and the status action before expecting physical output.

The reusable ESPHome package is
[`packages/runtime_api.yaml`](../examples/packages/runtime_api.yaml), using hub
ID `deck` from `packages/deck.yaml`. Its `runtime_visuals` configuration requires
PSRAM, asset loading and API encryption. The schema rejects static artwork/local
hub key automations in this mode, and the direct `set_image` methods reject
changes so the visual store remains authoritative. Explicit redraw and brightness
remain available. The package creates no additional loader or renderer.

## Change a binding, image or label in HA

The press automation toggles the example lamp. The release automation writes a
logbook entry to demonstrate a separate release binding. Change their HA
`actions`/`target` fields to rebind a key, or copy them using another key's event
entity. All 15 binary sensors and `Key N edge` event entities remain stable.

`stream_deck_sync_layout` is the authoritative example layout: key 0 displays
the actual lamp's on/off/unknown image and label; key 1 is text-only; keys 2..14
are blank. Every replay supplies all visual fields for all 15 keys, so removing
an entry cannot leave an old icon behind. Add more HA state triggers when adding
state-dependent keys. Update this layout for changes that should survive a replay.

For an immediate partial change from HA Developer Tools or another HA script:

```yaml
action: script.stream_deck_apply
data:
  key: 0
  patch:
    text: "Desk"
    font: 20
    text_color: "#FFFF00"
    outline_color: "#000000"
response_variable: visual_result
```

Omitting an image preserves the desired artwork and reuses its decoded cache.
`patch: {text: ""}` clears just text; `{image_url: "", text: ""}` clears image and
text while preserving style/background. A full black reset also supplies
`background_color: "#000000"`. Image-only uses a URL/content revision and empty
text; text-only uses empty URL and the desired text. Unknown fields, nulls and
invalid styles are rejected. See [the complete contract](runtime-visuals.md).

To replace artwork at the same URL, change its content revision as well:

```yaml
action: script.stream_deck_apply
data:
  key: 0
  patch:
    image_url: "http://homeassistant.local:8123/local/streamdeck/desk.png"
    image_revision: "desk-v2"
response_variable: visual_result
```

Use the queued `stream_deck_apply` helper for all normal writers. It reads the
current session and accepted per-key revision before submitting the next revision,
so HA needs no persistent counter. It fails explicitly at revision 2,147,483,647;
there is no wraparound. The low-level `stream_deck_visual_patch` helper instead
requires explicit session/key/revision and supports an identical retry after an
uncertain response. Don't race direct native calls against the queued helper.
Dictionary templates preserve string values such as `"123"` and digit-only boot
sessions instead of allowing HA to coerce individual fields into numbers.

## Native operations and error handling

All four actions return data and must be called with `response_variable` in HA.
The field descriptions appear through ESPHome action metadata.

| Action suffix | Arguments | Effect |
| --- | --- | --- |
| `set_key_visual` | Fixed presence-mask signature in the contract | Patch selected desired fields atomically |
| `clear_key_visual` | `session`, `key`, `revision` | Clear image and label; preserve style |
| `refresh_key_image` | `session`, `key`, `revision`, `image_revision` | Use a new asset version for the current desired URL; preserve label/style |
| `get_key_visual_status` | `session`, `key` | Read a bounded per-key record without mutation |

For direct clear/refresh calls, first query status and use `revision + 1` with
the same session. Refresh requires existing desired artwork and a nonempty
content revision. A new token deliberately fetches again; reusing a cached token
can reuse that asset. Repeat the same command and revision for an identical retry.
For normal scripted clear/refresh, the queued patch helper provides the same
semantics with automatic revision management.

```yaml
action: esphome.streamdeck_original_get_key_visual_status
data:
  session: "0123456789abcdef"  # Replace with the actual Visual session value.
  key: 0
response_variable: visual_status
```

Every response contains `session`, `key`, `request_revision`, `accepted`,
`revision`, `rendered_revision`, `phase` and `error`. Status queries use
`request_revision: 0`. Responses carry only bounded identifiers/error names,
never the submitted URL or label. API transport success means the call returned
a record; check `accepted` for command/query validity. A rejected command returns
the previous status with its rejection error and cannot advance the revision.

An accepted request progresses through `queued`, `rendering`, then `rendered`
or `failed`. Query again for asynchronous completion. `accepted: true` on a
status query means the query was valid, even if the record reports a failed
render. `rendered` means a complete BMP reached the scheduler, not physical
display readback or even USB completion. Failed fetches/decodes/renders leave
the previous good tile intact. Error codes are defined by `visual::error_name`,
including `wrong_session`, `revision_conflict`, `origin_not_allowed`,
`clock_not_ready`, `http_status`, `decode_failed` and `out_of_memory`.
An identical failed request retains the failure; a higher revision explicitly
retries. No automatic image retry loop is installed.

## Reconnection, input and defaults

ESP boot creates a new session and a blank desired layout. HA replays on startup,
visual-session changes/reavailability, automation reload, and the configured
entity's state changes. Replay waits up to 60 seconds for the session and native
actions, rechecking registration even when no sensor state changes. A pending
replay reads fresh HA state when it executes. Same-session replays advance
revisions safely; an unchanged rendered tile creates no new download or image
upload. A deck-only reconnect keeps the session/revisions/cache and redraws the
desired tiles through the existing scheduler.

HA/Wi-Fi/API loss preserves the last good tiles in RAM. An API logger joining or
leaving has no lifecycle effect. There is no layout persistence or per-label
flash write. An ESP reboot discards that RAM state until HA synchronizes again.

Only real `KeyTracker` edges emit native `press`/`release` events. The pinned
ESPHome subscription iterator does not replay events; its connection queue keeps
separate event occurrences. Baseline reports, held-at-attach release suppression,
overflow resynchronization and disconnect cleanup do not emit events. HA's
example also guards restore, availability and attribute-only state transitions.
No application queue saves presses for a future HA connection. Delivery during
network interruptions is not guaranteed, and the existing first-report baseline
can still consume the first physical click after USB attachment. That limitation
is unchanged and must be qualified in P5.

Host tests execute the shipped HA templates/sequence logic with a fake API, test
the production API/pipeline with fake HTTP, and drive production key publication
with fake ESPHome entities. Firmware compiles the actual ESPHome action and event
interfaces. These do not constitute a live HA integration or physical acceptance
test. The [P5 checklist](implementation-plan.md#p5-verify-end-to-end-and-hand-off)
and [hardware gates](hardware.md) remain open.

Sources: pinned local ESPHome `api/user_services.h`, `api/subscribe_state.cpp`
and `api/api_connection.h`; [HA event behavior](https://www.home-assistant.io/integrations/event/)
and [HA's ESPHome event adapter at 2026.10.1](https://github.com/home-assistant/core/blob/2026.10.1/homeassistant/components/esphome/event.py).
The template string-coercion guard follows
[HA's native-result parser at 2026.10.1](https://github.com/home-assistant/core/blob/2026.10.1/homeassistant/helpers/template/__init__.py).
Those source checks do not establish the owner's HA version or a live test result.
