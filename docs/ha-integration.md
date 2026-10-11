# ESP Deck Home Assistant integration

P9 packages version 0.9.0 as an installable ZIP with the editor, translations,
brand images and licences. See [installation, upgrades and qualification](release.md).
It fixes repair translation validation and removal of disabled entries after
restart; saved layout/artwork formats and the v1/v2 contracts are unchanged.

Version 0.8 negotiates [runtime v2 capabilities](runtime-v2.md), verifies and
provisions the HA artwork address, supports positioned text and resolves bounded
pages/overlays in HA. A normal HA select entity chooses the active page. The
backend uses the correlated native input channel on v2 and retains the original
v1 event workflow for older runtime firmware. Setup and all operations reuse
HA's existing ESPHome connection; no second permanent client is created.

`custom_components/esp_deck/` is a locally installable integration for HA
**2026.10.1 or newer**, developed against 2026.10.1. Earlier HA versions are not
supported/tested. It owns saved layouts, entity feedback, press/release bindings
and synchronization while the browser is closed. P7's bundled
[visual editor and artwork library](visual-editor.md) provide everyday editing
without YAML or revision/URL plumbing. P8 supplies pages/layers. HACS online
repository/install/update validation remains a separate P9 gate; a GitHub account
is not needed for artifact installation or local tests.

The real device needs example 05's existing v1 runtime API. The installed
example 04 bench firmware is incompatible. P6 does not upload firmware, change
USB/power behavior, provision origins or claim physical display verification.

## Installation and guided setup

Copy `custom_components/esp_deck` into HA's `config/custom_components/esp_deck`
directory and restart HA. First add the device using HA's normal ESPHome
integration with its encrypted native API. Then add **ESP Deck** from Settings →
Devices & services and select that existing device.

Setup checks all four native action names, exact argument names/types, required
responses, the boot-session sensor, and 15 distinct press/release event entities.
It probes status without changing a tile. v1 has no explicit model/capability
response: compatibility is the known 15-key API contract, not hardware identity
readback. Capability discovery is P8.

The handoff form explicitly confirms exclusive visual ownership and lets you
select existing automations to disable. It also stops any running instances of
the three shipped P4 helper scripts. It preserves their YAML. Optionally choose
a light, switch, input boolean, script or scene for key 0. Toggle presets use
actual on/off/unavailable state for background feedback. Script/scene presets
invoke `turn_on`. No HA entity ID is compiled into the ESP.

Open **ESP Deck** in the sidebar for the 5×3 editor, or use Configure →
**Set an entity preset** to replace any key in the saved draft,
with an option to apply the draft. A preset
replaces that key's binding, appearance and state rule; Apply activates the
whole draft. Saving configuration or previewing a preset never executes its
bound action.

The lab stages this same integration directly. After changing its source:

```sh
.venv/bin/python tools/ha_lab.py down
.venv/bin/python tools/ha_lab.py up
.venv/bin/python tools/ha_lab.py test-engine
.venv/bin/python tools/ha_lab.py test
```

The existing synthetic account in private `.build/ha-lab/credentials.json` is
retained. `test` runs the manual P4 scenarios with the managed entry disabled,
then enables/exercises P6 and leaves a managed demonstration layout installed.
It operates only on the isolated lab. `--fresh` is optional and archives existing
lab data. No production account, hardware or HACS login is used.

## Layouts and bindings

Layout version 1 contains exactly 15 front-view keys, left to right in rows of
five. Each key contains `visual`, `mode`, `press`, `release` and `state`.
Omitted visual fields get the v1 defaults; omitted bindings/rules are empty.
State rules apply a visual patch over the base appearance, so labels can change
without changing artwork identity.

One key, before normalization, can look like this:

```json
{
  "visual": {
    "text": "Desk",
    "image_url": "http://ha:8123/local/streamdeck/light_off.png",
    "image_revision": "v1"
  },
  "mode": "managed",
  "press": {
    "action": "light.toggle",
    "target": {"entity_id": "light.example_lamp"}
  },
  "release": null,
  "state": {
    "entity": "light.example_lamp",
    "on": {"text": "Desk ON", "background_color": "#176B32"},
    "off": {"text": "Desk OFF"},
    "unavailable": {"text": "Unavailable", "background_color": "#5C2525"}
  }
}
```

`http://ha:8123` is the **lab container address**, not an address for physical
firmware. Existing URLs must use the device's compiled allowed origins and meet
the [v1 PNG/URL limits](asset-loading.md). An origin mismatch is reported by the
native API; this backend does not change the allowlist or perform the ESP fetch.
The origin-provisioning wizard remains P8. P7's restricted artwork route works
with an already allowed HA origin and defaults to HA's configured internal URL.

The layout is `{"version":1,"keys":[...15 key objects...]}`. Visual fields are
those in the [runtime contract](runtime-visuals.md): image URL/revision, text,
font 12/16/20, three `#RRGGBB` colors and `contain`/`crop`. Label bounds are
96 UTF-8 bytes/48 scalars. URLs are at most 512 ASCII bytes, without credentials,
query or fragment. Empty image/text explicitly clears it. An image change in a
state patch must include both URL and revision. Unknown fields are rejected.
P7 also accepts a hash-only `asset_id` for normalized library artwork. It is
resolved to the private device URL/revision only by the backend, never exposed in
exports. Image patches clear the alternative URL or library reference explicitly;
labels/styles still preserve the image. See [artwork access](visual-editor.md).

Action bindings use a literal `action`, optional JSON `data`, and optional
`target.entity_id` (one entity or at most 16). Put entity targets in `target`,
not `data.entity_id`, so they can follow renames. Action data is capped at 4 KiB;
layouts at 128 KiB with finite nesting/node counts. Action templates, broad
device/area targets, arbitrary condition trees and pages are not this model.
Use an HA script for complex actions. Recursive `esp_deck.*` bindings are rejected.

Entity references are pinned to registry UUIDs where available. HA renames of
session, key events, targets and state sources are followed automatically.
Missing pinned UUIDs never fall back to an unrelated entity reusing an old name.
Unregistered entities can still be used by their entity ID, without that rename
guarantee. Export resolves current names and removes installation-specific UUIDs;
import resolves/pins them in the receiving HA instance.

`mode: "automation"` requires empty press/release bindings and emits
`esp_deck_key` events with `entry_id`, `key` and `edge`. This is the advanced
automation path. Managed keys execute their configured actions and do not emit
that additional event. ESPHome's original event entities remain accessible;
the integration cannot detect every external automation using them. Keep exactly
one action path per edge. HA action contexts link to the input event; failures
surface as `binding_action_failed`, without echoing payloads.

Press/release pairing rejects orphan releases, repeated presses, availability
restores and attribute-only event updates. Disconnect, config changes and unload
discard held state and queued actions. The binding queue is capped at 32; overflow
discards the backlog and suspends bindings until explicit Sync, a configuration
change or reconnection. It reports an error. Cancellation cannot undo an action
already executed by another integration. This guards HA-observed work; v1 does
not correlate a physical input with completed USB pixels. Page/layer switching
and that stronger ordering guarantee remain P8 work.

## Storage and authenticated API

HA `.storage/esp_deck.<config-entry-id>` holds a versioned private record:
draft/applied layouts and edit revisions, plus the previous applied layout as a
one-level backup. Saves use atomic replacement. Disk failures are returned before
the in-memory draft or active configuration is changed. Corrupt/future records
fail setup instead of activating a blank layout; HA preserves corrupt files for
repair. Storage version 0's explicit single-layout format migrates to version 1;
unknown future formats are rejected. HA backups include this storage. Removing
the config entry removes its layout store; disabling/unloading retains it.

Draft revisions are optimistic edit counters, distinct from the layout schema,
ESP boot session and per-key request revisions. Save/import/apply require the
current `expected_revision`; a concurrent stale edit returns `draft_conflict`.
Import saves a new draft, then Apply activates it. Export can select `draft`,
`applied` or `backup`. Treat exports as private: existing artwork paths and
user-supplied action data may be sensitive. Diagnostics omit all layout text,
URLs, action payloads and connection credentials.

All configuration/status operations require an administrator at the HA service
or WebSocket boundary. Non-admin users cannot bypass this by calling the backend
directly. HA internal automations may call the admin services in HA's usual
system context. Services require response data:

| Action | Parameters in addition to `entry_id` |
| --- | --- |
| `esp_deck.get_layout` | None; returns draft/applied records and revisions |
| `esp_deck.save_layout` | `layout`, `expected_revision` |
| `esp_deck.apply_layout` | `expected_revision` |
| `esp_deck.export_layout` | Optional `which`: draft/applied/backup |
| `esp_deck.import_layout` | `document`, `expected_revision` |
| `esp_deck.preset` | `entity_id`, `label`; returns a key, without saving/firing |
| `esp_deck.sync` | None; explicit reconciliation/retry of failed tiles |
| `esp_deck.status` | None; connection/render/binding state |
| `esp_deck.artwork_list` | None; private library metadata and origin |
| `esp_deck.artwork_variant` | `source_id`, `transform` (fit, zoom, x, y) |
| `esp_deck.artwork_configure` | `origin`; does not provision firmware |
| `esp_deck.artwork_revoke` | None; rotate capability and resynchronize |
| `esp_deck.artwork_collect` | None; remove unreferenced, unretained files |
| `esp_deck.artwork_delete` | `asset_id`; refuse referenced/retained files |

The authenticated WebSocket equivalent is:

```json
{"id":1,"type":"esp_deck/command","entry_id":"YOUR_ENTRY_ID",
 "operation":"status","parameters":{}}
```

Use the same operation names/parameters as the table, without the `esp_deck.`
prefix. The HA config-entry selector supplies `entry_id` in Developer Tools.
Neither interface exposes or stores ESPHome credentials.
The admin-only `esp_deck/entries` WebSocket command lists editor decks.
Authenticated admin HTTP upload/preview and restricted device GET routes are
documented in [the P7 guide](visual-editor.md).

## Synchronization, status and repair

One controller per entry queries current session/revisions, coalesces current
HA state and writes a complete desired visual only when it changed. Unchanged
successful syncs skip native writes. A restart queries the ESP and reasserts
HA state with fresh per-key revisions; the firmware skips rendering/downloading
when its complete visual is already identical. Logger clients do not alter this
lifecycle. Label-only updates retain the background cache identity.

Queued/rendering work is polled at 500 ms, bounded to 30 seconds; a 30-second
reconciliation checks connectivity and revisions without rewriting unchanged
tiles. Failed fetch/render jobs remain failed until edited or explicitly retried.
Unexpected external revision changes report `competing_writer`. Stop the other
writer, then synchronize. Signed native revision exhaustion requires a fresh
device boot session; counters never wrap.

The helper synchronization sensor and status API separate `connected` from
`ready`, `syncing`, `failed`, `offline` and `repair_required`. Per-key records
include accepted/rendered revisions, phase and a bounded error code.
**Rendered means pixels reached the scheduler, not USB completion or physical
display readback.** Previously valid pixels remain on failed asset/render jobs.

Missing/disabled/incompatible device entities/actions create a repair issue.
Enable entities in ESPHome, use Configure → Repair entity mapping to select
the session and ordered key events, or Reconfigure for a replacement device.
Incompatible bench firmware needs example 05. Reconnect/registration events and
the periodic check retry connectivity; this is distinct from retrying bad artwork.
The integration does not own/duplicate the physical ESPHome device or create a
second permanent native client. Its status entity belongs to the helper entry.

The narrow adapter is source-tested against HA 2026.10.1's ESPHome
`runtime_data.info/services/device_info`, `build_service_name`, and registry IDs.
All network execution goes through HA services. The storage write-error guard
is likewise pinned/tested against HA's `Store` behavior. These compatibility
surfaces need retesting for later HA versions. The design follows HA's
[helper device guidance](https://developers.home-assistant.io/blog/2025/07/18/updated-pattern-for-helpers-linking-to-devices/)
and [single-owner device registry](https://developers.home-assistant.io/blog/2026/07/21/device-registry-single-config-entry/).

## Migrating from P4 YAML

Export/back up your manual layout and decide which keys should remain advanced
automation keys. Stop `stream_deck_replay_layout` and every manual key binding
that overlaps a managed binding. Select the relevant automations in the handoff
form, and confirm other/custom writers have been stopped. The integration never
rewrites `automations.yaml` or infers permission to disable arbitrary automations.

Recreate bindings using entity presets or import/save a v1 layout; script actions
can target your existing HA scripts. Do not point bindings at the P4 visual writer
scripts. Disabled manual paths are not automatically re-enabled on unload. To go
back to P4, disable/remove the ESP Deck entry first, then deliberately re-enable
the desired manual replay/bindings. P4 remains independently usable and tested.
