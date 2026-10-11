# Independent Home Assistant lab (P5)

The lab runs real HA and a test-only ESPHome `host` deck in rootless Podman.
It uses fresh synthetic credentials and does not need the owner's HA, ESP,
Stream Deck or GitHub account. It is a development dependency only. P6's custom
integration and P7's editor are not installed or implemented by this stage.

## Commands and isolation

Use the existing repository `.venv` and rootless Podman on Linux x86_64:

```sh
.venv/bin/python tools/ha_lab.py up
.venv/bin/python tools/ha_lab.py status
.venv/bin/python tools/ha_lab.py test
.venv/bin/python tools/ha_lab.py down
```

`up` pulls digest-pinned images, compiles the host executable, starts HA, completes
synthetic onboarding and pairs `deck:6053` through HA's real ESPHome config flow.
The UI is [http://127.0.0.1:18123](http://127.0.0.1:18123). Username/password and
generated API/auth keys are in private `.build/ha-lab/credentials.json`; they are
never printed. HA can fetch synthetic artwork at `http://ha:8123/local/streamdeck`.
That container address is for the lab, not an origin to put in physical firmware.

The only published port is `127.0.0.1:18123`. HA and the deck have a dedicated
rootless network, with no host networking, USB devices, privileged mode or D-Bus
mount. Capabilities are dropped and no-new-privileges is enabled. SELinux `:Z`
labels apply only to staged lab directories, never the workspace. Run `down`
before rebuilding; a running executable/config is not rewritten or relabeled.
Routine `up` reuses a running lab. CLI mutations take an exclusive local lock.

`down` checks repository-specific ownership labels and removes only the two lab
containers and their network. It retains config, keys, builds and test results.
It never prunes containers/images/volumes. For new accounts, storage and builds:

```sh
.venv/bin/python tools/ha_lab.py up --fresh
.venv/bin/python tools/ha_lab.py test
```

`--fresh` first tears down owned resources, then **moves** the previous private
directory to `.build/ha-lab-archive-<timestamp>-<suffix>` before creating a new one.
Archived credentials and binaries stay private and ignored. Source changes to
the staged configuration/adapter require `down` followed by `up`; the test runner
copies current HA engine tests before running them.

First use needs internet access to download the pinned OCI images, PlatformIO
native platform/libraries, test packages and Chromium headless browser. The lab
runner has its own virtual environment, so firmware fixture pins stay untouched.
Playwright's Linux browser needs the usual Chromium system libraries; the tested
Fedora host already supplied them. No global package installation is automated.

## Version and compatibility boundary

Images and direct versions are pinned in
[`tests/ha_lab/versions.json`](../tests/ha_lab/versions.json); the runner's full
Python resolution is in
[`requirements-lock.txt`](../tests/ha_lab/requirements-lock.txt). HA engine tests
use the pinned HA image's Python and packages plus the small pinned
[`tests/ha/requirements.txt`](../tests/ha/requirements.txt) set. Firmware pins are
unchanged in the repository root.

| Component | Lab baseline |
| --- | --- |
| HA / frontend | 2026.10.1 / 20260930.3 |
| HA Python / aioesphomeapi | 3.14.6 / 46.6.0 |
| ESPHome host / Python / compiler | 2026.9.0 / 3.14.6 / GCC 14.2.0 |
| PlatformIO native | 1.2.1 |
| Host runner Python / pytest / pytest-asyncio | 3.14.7 / 8.4.2 / 1.2.0 |
| Playwright / Chromium headless | 1.56.0 / 141.0.7390.37 (build 1194) |
| Container host | Fedora 44, Podman 5.8.4, rootless Netavark, SELinux enforcing |
| HACS | Not installed; packaging/install flow is a later gate |

Use HA **2026.10.1 as the initial minimum supported/tested baseline** for P6.
This does not establish compatibility with earlier versions. Action responses
are available through HA's ESPHome service registry with required response data.
Discovery produces 15 binary sensors, 15 edge events, one session sensor and the
four unchanged P4 actions. Wrong-key and unencrypted clients are rejected.

Entity registry renames retain the registry entry ID. A device UI-name change
does not rename actions: their prefix still follows the ESP node name. Renaming
the session entity breaks the manually configured P4 helper reference until it
is updated/restored. P6 should persist registry references and resolve current
names. HA can return HTTP 200 and an **empty result** when a script stops with
an error; require an explicit `accepted: true`, not just transport success.

The lab exposed an unsupported P4 `has_service()` template call. The shipped
replay automation now listens for the two required `service_registered` events
and waits for a valid session. ESPHome registers its action batch synchronously;
a brief coalescing delay precedes replay. A later registration schedules another
attempt even when no sensor changes. A real-HA engine test covers this case.

## What runs in the virtual deck

`tests/ha_lab/components/virtual_deck` is host-only and cannot compile for an ESP.
Staging copies the production portable protocol, immutable images, Store, visual
API, PNG decoder, renderer/font and scheduler sources byte-for-byte. The four API
action definitions/lambdas also come directly from the production P4 package.
The ESP32 component/IDF HTTP worker/USB transport are not compiled into the host.

The genuine ESPHome API supplies encryption, discovery, entities and responses;
there is no hand-written Noise/protobuf server. Host graphics allocations use
the existing bounded allocators with malloc rather than PSRAM. A cancellable
Python subprocess fetches PNGs through bounded host HTTP while the ESPHome loop
keeps running. The same production pipeline validates/decodes/composes them.
This verifies HA routes/cache behavior, not IDF HTTP/TLS timing or memory use.

The scheduler emits real reset/brightness/two-page report bytes; the adapter
simulates completion, delay, failure and peripheral reconnect. Private one-shot
file commands inject masks through the production input queue and edge tracker.
The initial all-up report is explicit simulated input, not a new driver policy.
No production debug action, firmware binding, power GPIO or second USB host is
introduced. A snapshot distinguishes rendered revisions from simulated completed
output and stores hashes/counts without asset URLs. Neither is display readback.

## Test layers and artifacts

`test` executes three distinct layers:

1. HA pytest tests execute the actual shipped scripts and late-registration
   replay in HA's script/template/automation engine, with mocked native actions.
2. Real-container tests use REST/WebSocket calls through HA's actual ESPHome
   connection. They cover all 15 keys, action responses, revisions/duplicate/
   conflict/stale requests, numeric text and sessions, unchanged replay, PNG
   fetching/cache/refresh/failures, state feedback, registry renames, logger
   clients, HA outage/restart, virtual ESP reboot and simulated USB recovery.
3. A Chromium smoke test logs in, opens the virtual deck in HA's device UI and
   checks its session diagnostic. HA bindings/state feedback continue after
   the browser closes. This is not a test of the future custom editor.

The ordinary unittest suite separately covers ownership-safe lifecycle commands,
private source/API staging, HTTP limits and redirect rejection. Its existing
native executables remain the independent byte/renderer/USB oracle. The lab
does not replace pinned reference fixtures with self-derived expectations.

Private artifacts include `ha-engine.log`, `pytest/ha-engine.xml`,
`live-tests.log`, `live.xml`, `ha-browser.png`, `versions.json` and `results.json`.
The last two contain sanitized version/result metadata; raw HA/deck/build logs
and credentials remain in the ignored private directory. Browser/API tests
exercise only the synthetic lab and include no production entity IDs or accounts.
See [current acceptance evidence](testing.md) for results and counts.

The sanitized [P5 acceptance record](../tests/ha_lab/acceptance-2026-10-11.json)
retains image identities, the tested host-executable hash and test counts without
credentials, raw logs or binaries.

No electrical, USB/DMA, physical display, actual ESP HTTP/TLS or OTA acceptance
comes from P5. Example 04 remains the installed bench firmware. The P3 live
asset-reachability check and P9 hardware gates remain pending.
