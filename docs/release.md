# Installation and release qualification (P9)

ESP Deck 0.9.0 packages the HA integration and its bundled editor as `esp_deck.zip`.
It does not contain ESP firmware, Wi-Fi/API credentials, lab data or test tools.
The supported HA minimum is **2026.10.1**, also the current stable release checked
on 2026-10-11. One version therefore covers both minimum and current in this run;
earlier HA releases are rejected before registering the integration.
[HA release record](https://github.com/home-assistant/core/releases/tag/2026.10.1).

Physical runtime acceptance remains separate. Example 04 is still the installed
bench firmware. The integration explains that it needs
`examples/05_home_assistant_runtime.yaml` and points to private-build/encrypted-OTA
instructions when an incompatible device is selected. Installing the HA ZIP does
not upload firmware. The [hardware](hardware.md) and [testing](testing.md) gates
still apply.

## Build and direct installation

```sh
npm ci --prefix frontend --ignore-scripts --no-audit --no-fund
npm run check --prefix frontend
.venv/bin/python tools/package_release.py --check
.venv/bin/python tools/package_release.py
.venv/bin/python tools/check_distribution.py
```

Outputs are ignored under `.build/release/0.9.0/`: `esp_deck.zip`, `SHA256SUMS`
and a per-file `release.json`. The archive is deterministic for identical inputs.
Its explicit allowlist contains only the integration modules, manifest, services,
English translations, compiled editor, font/project licences, notice and local
brand images. Filesystem symlinks and unexpected Python modules fail the build.
Archive installation validates the complete member set, duplicate/path/symlink
hazards and compressed/expanded size before creating a destination.

The ZIP root contains `manifest.json`, `__init__.py`, `frontend/`, etc. For direct
installation, extract its contents **inside** HA's
`config/custom_components/esp_deck/`, then restart HA. Do not extract it into the
config root. For an update, stop HA and preserve the old `esp_deck` code directory
outside `custom_components`, then install into a new directory of that name.
Keep `.storage/esp_deck*` and `esp_deck_artwork/` in place. Do not merge arbitrary
old Python files into the new package.

HA's ESPHome integration first pairs the encrypted device. Add ESP Deck, choose
that device, hand over visual/binding ownership and optionally select an entity
preset. Open ESP Deck from the sidebar. Under **Library settings & backup**, the
address comes from HA's configured internal URL: click **Verify & provision
address** to verify a real device-side PNG fetch on v2. The normal flow requires
no URL typing, YAML, revision counters or manual frontend resource registration.
Upload/crop an image, edit the label/binding and Apply. The backend keeps working
after the browser closes. An inaccessible HA address needs correction in HA's
network settings or the advanced artwork address control; a browser's successful
connection does not prove that the ESP can reach it.

## HACS boundary

`hacs.json` selects a ZIP release named `esp_deck.zip`, with HA minimum 2026.10.1.
All integration files, including `brand/icon.png`, live under
`custom_components/esp_deck`. A released ZIP must use the same version as
`manifest.json`. The repository also retains the bundled files for branch-based
installation. This follows [HACS integration requirements](https://www.hacs.xyz/docs/publish/integration/)
and [ZIP/minimum-version settings](https://www.hacs.xyz/docs/publish/start/).

Repository identity is not configured in this checkout yet. The manifest still
needs the actual documentation/issue URLs and maintainer identity before its
distribution checks can pass. Do not substitute fabricated project URLs or
interpret the local archive's existence as HACS readiness.

`check_distribution.py` runs the actual upstream Hassfest image and imports the
actual HACS manifest schemas from its action image. Both images are pinned by
digest in that tool; only a private staged copy is mounted/relabelled. It records
logs/results under `.build/distribution/`. This checks local code/metadata without
an account. The full HACS action reads a published GitHub repository instead:

```sh
# After publishing the repository, with an existing token supplied privately:
.venv/bin/python tools/check_distribution.py --online OWNER/REPOSITORY
```

That optional command requires `GITHUB_TOKEN`, passes it through the container
environment and disables PR comments. It does not publish a repository/release.
HACS custom-repository installation/update additionally requires HACS onboarding
and GitHub device authorization; it has not been exercised here. Once published,
add the actual repository URL in HACS → Custom repositories, category Integration,
install ESP Deck and restart HA. Default-store inclusion is a separate publishing
step, not implied by supporting a custom repository.

## Repeat the artifact and lifecycle tests

```sh
.venv/bin/python tools/ha_lab.py up --fresh --artifact .build/release/0.9.0/esp_deck.zip
.venv/bin/python tools/ha_lab.py test
```

`--fresh` moves the previous private lab into an archive; it does not erase it.
The lab installs the ZIP's bytes in both real HA and the engine-test mount.
It continues to bind only `127.0.0.1:18123`. No production HA, physical ESP,
host USB device or GitHub account participates.

To update an already running owned lab without rebuilding the virtual deck:

```sh
.venv/bin/python tools/ha_release.py .build/release/0.9.0/esp_deck.zip
.venv/bin/python tools/ha_lab.py test
.venv/bin/python tools/ha_lab.py test-release  # Only the four P9 lifecycle cases
```

The installer stops only its ownership-checked HA container and preserves the
previous code under the private lab's `installations/` directory. It recreates
that stopped container so SELinux `:Z` applies to the new private files; neither
the repository nor unrelated containers are relabelled. Expired lab access
tokens are refreshed before authenticated checks.

P9 adds four real-container/browser scenarios to the P4–P8 regression:

- Exact archive bytes are installed and its frontend is served. The editor
  verifies the prefilled artwork address, binds an entity, uploads and applies
  artwork, then continues with the browser closed.
- Actual P8 version 0.8.0 code from commit
  `279e58bce7303ea4e7c2cb07cf85cd4c2c9394e6` is installed and exercised before the
  0.9.0 ZIP update. Saved drafts/applied/backup layouts, pages, overlays, artwork
  and bindings must survive. The history commit must exist locally for this test.
- A stopped-HA copy of the entire private lab configuration is backed up.
  Removing ESP Deck must revoke its artwork and delete its layout/artwork while
  preserving the ESPHome device. Removing its code and restarting must also remove
  its services/frontend. Restoring that cold backup must restore the
  layout, artwork and functioning binding. This is a configuration backup/restore
  test, not a claim about Supervisor/cloud-backup providers.
- A version-0 layout store is migrated through an actual HA restart, then saved
  as version 1 and verified after another restart.

The engine suite separately tests incompatible bench guidance, the HA minimum,
repair translations and removal of disabled entries before component setup.
Source-tree lab installs retain their original regression command; archive-only
scenarios run only with a recorded artifact installation and are reported separately.

## Physical continuation

Before an explicitly requested example-05 upload: verify the encrypted API
identity, retain the working example-04 artifacts, choose the HA instance and
device-reachable LAN address, and compile with `--deploy` and local secrets.
Synthetic `.build/firmware/` images are never deployable. The lab's `ha:8123`
container alias and loopback port are not physical-ESP addresses. Expose only the
chosen interface/port for a supervised device session and verify its actual fetch.
The runtime, first-click, input/display timing, repeated recovery, soak and
electrical measurements remain pending. Controller resets never remove external,
unswitched VBUS.
