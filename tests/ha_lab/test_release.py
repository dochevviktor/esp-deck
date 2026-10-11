"""P9 archive install, actual P8 upgrade, migration, backup/restore and removal."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import time
import urllib.error
import urllib.request

import pytest
from playwright.sync_api import sync_playwright, expect

from tools import ha_lab as lab, ha_release, package_release
from test_backend import backend, command, ready, apply_layout
from test_live import call, control, settled, state, ws
from test_editor import login, command as browser_command, ready as browser_ready


def artifact():
    path = lab.LAB / "installed-release.zip"
    assert path.is_file(), "P9 requires up --artifact or tools/ha_release.py before testing"
    payload = path.read_bytes()
    package_release.inspect_archive(payload)
    return payload


def restart_ha():
    lab.start_ha(recreate=True)
    lab.wait_for_ha()


def test_installed_archive_brand_and_guided_default_address(backend):
    files = package_release.inspect_archive(artifact())
    installed = lab.LAB / "config/custom_components/esp_deck"
    for name, data in files.items():
        assert (installed / name).read_bytes() == data, name
    assert lab.request("/api/config")["version"] == "2026.10.1"
    # All runtime resources must be served by the installed directory.
    with urllib.request.urlopen(lab.URL + "/esp_deck_static/esp-deck.js") as response:
        assert response.read() == files["frontend/esp-deck.js"]
    assert files["brand/icon.png"].startswith(b"\x89PNG\r\n\x1a\n")
    apply_layout(backend, {"version": 1, "keys": [{} for _ in range(15)]})
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        login(page)
        page.get_by_text("Library settings & backup", exact=True).click()
        # HA's own configured internal address is already filled in; no URL,
        # revision counter, YAML or Lovelace resource is entered by the user.
        expect(page.locator("#origin")).to_have_value("http://ha:8123")
        page.get_by_role("button", name="Verify & provision address", exact=True).click()
        expect(page.locator("#set-origin")).to_be_enabled(timeout=30000)
        assert browser_command(backend, "status")["capabilities"]["origin_probe"] == "verified"
        page.locator("#preset-entity").select_option("light.example_lamp")
        page.get_by_role("button", name="Use preset", exact=True).click()
        page.get_by_role("tab", name="Appearance", exact=True).click()
        page.locator("#upload").set_input_files(str(lab.ROOT / "assets/source/transport_test.png"))
        page.locator("#crop-fit").wait_for(timeout=15000)
        page.locator("#v-text").fill("Release artwork")
        page.locator("#v-text").press("Tab")
        page.get_by_role("button", name="Apply", exact=True).click()
        expect(page.locator("#draft-status")).to_have_text("Applied layout", timeout=15000)
        browser_ready(backend)
        page.screenshot(path=str(lab.LAB / "p9-artifact-editor.png"), full_page=True)
        browser.close()
    call("light.turn_off", {"entity_id": "light.example_lamp"})
    ready(backend)
    control(masks=[1, 0])
    lab.wait_for(lambda: state("light.example_lamp")["state"] == "on")


def test_upgrade_actual_p8_code_to_release_preserves_pages_and_artwork(backend):
    payload = artifact()
    before = command(backend, "get_layout")
    original = deepcopy(before["applied"])
    # Include normalized artwork, an inactive page and a sparse overlay.
    main = deepcopy(original["keys"])
    main[1]["navigation"] = {"kind": "page", "target": "other"}
    layout = {"version": 2, "default_page": "main", "pages": [
        {"id": "main", "name": "Main", "keys": main},
        {"id": "other", "name": "Other", "keys": deepcopy(original["keys"])}],
        "overlays": [{"id": "shift", "name": "Shift", "keys": {"2": None}}]}
    apply_layout(backend, layout)
    saved = command(backend, "get_layout")
    library = command(backend, "artwork_list")
    assert any(key["visual"].get("asset_id") for key in main)
    try:
        ha_release.install(ha_release.baseline_files(), baseline=True)
        ready(backend)
        assert command(backend, "get_layout") == saved
        assert command(backend, "artwork_list") == library
        # Exercise the old integration, not merely a rewritten manifest.
        command(backend, "select_page", page="other")
        ready(backend)
    finally:
        ha_release.install(package_release.inspect_archive(payload), artifact=payload)
    ready(backend)
    assert command(backend, "get_layout") == saved
    assert command(backend, "artwork_list") == library
    assert command(backend, "status")["active_page"] == "main"
    assert settled(0)["tiles"][0]["image_revision"] == main[0]["visual"]["asset_id"]
    lab.private_write(lab.LAB / "upgrade-result.json", json.dumps({
        "from_commit": ha_release.UPGRADE_BASELINE, "from_version": "0.8.0", "to_version": "0.9.0",
        "release_sha256": hashlib.sha256(payload).hexdigest(), "result": "passed",
        "preserved": ["draft", "applied", "backup", "pages", "overlays", "artwork", "bindings"],
    }, indent=2) + "\n")


def test_cold_backup_restore_and_removal_revoke_artwork_preserve_esphome(backend):
    ready(backend)
    saved = command(backend, "get_layout")
    library = command(backend, "artwork_list")
    config = lab.LAB / "config"
    snapshot = lab.LAB / "release-backups" / secrets.token_hex(8)
    snapshot.mkdir(parents=True, mode=0o700)
    source_id = next(e["entry_id"] for e in lab.request("/api/config/config_entries/entry") if e["domain"] == "esphome")
    asset_id = saved["applied"]["pages"][0]["keys"][0]["visual"]["asset_id"]
    # Private capability is used only for a revocation check, never logged.
    artwork_record = json.loads((config / ".storage/esp_deck.artwork").read_text())["data"]
    token = artwork_record["decks"][backend]["token"]
    path = f"/api/esp_deck/artwork/{token}/{asset_id}.png"
    with urllib.request.urlopen(lab.URL + path) as response:
        original_png = response.read()
    lab.podman("stop", "--time", "10", lab.PREFIX + "-ha")
    try:
        shutil.copytree(config, snapshot / "config")
    finally:
        restart_ha()
    ready(backend)
    try:
        result = lab.request("/api/config/config_entries/entry/" + backend, method="DELETE")
        assert result.get("require_restart") is False
        assert not (config / f".storage/esp_deck.{backend}").exists()
        assert not (config / "esp_deck_artwork" / backend).exists()
        assert any(e["entry_id"] == source_id for e in lab.request("/api/config/config_entries/entry"))
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(lab.URL + path)
        assert error.value.code == 404
        devices = ws({"type": "config/device_registry/list"})
        assert any(device["config_entry_id"] == source_id for device in devices)
        # Complete direct uninstallation: stop HA, preserve/remove only its
        # integration code, then check that ESPHome still works after restart.
        lab.podman("stop", "--time", "10", lab.PREFIX + "-ha")
        (config / "custom_components/esp_deck").rename(snapshot / "removed-code")
        restart_ha()
        assert not any(group["domain"] == "esp_deck" for group in lab.request("/api/services"))
        with pytest.raises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(lab.URL + "/esp_deck_static/esp-deck.js")
        assert missing.value.code == 404
    finally:
        lab.podman("stop", "--time", "10", lab.PREFIX + "-ha")
        config.rename(snapshot / "after-removal")
        shutil.copytree(snapshot / "config", config)
        restart_ha()
    ready(backend)
    assert command(backend, "get_layout") == saved
    assert command(backend, "artwork_list") == library
    with urllib.request.urlopen(lab.URL + path) as response:
        assert response.read() == original_png
    call("light.turn_off", {"entity_id": "light.example_lamp"})
    ready(backend)
    control(masks=[1, 0])
    lab.wait_for(lambda: state("light.example_lamp")["state"] == "on")


def test_legacy_store_migration_survives_real_restart(backend):
    before = command(backend, "get_layout")
    config = lab.LAB / "config"
    path = config / f".storage/esp_deck.{backend}"
    baseline = deepcopy(before["applied"])
    lab.podman("stop", "--time", "10", lab.PREFIX + "-ha")
    lab.private_write(path, json.dumps({"version": 0, "minor_version": 1, "key": f"esp_deck.{backend}",
                                      "data": {"layout": baseline}}))
    restart_ha()
    ready(backend)
    migrated = command(backend, "get_layout")
    assert migrated["draft_revision"] == migrated["applied_revision"] == 1
    assert migrated["draft"] == migrated["applied"] == baseline
    assert migrated["backup"] is None
    # The migrated envelope is persisted on the next successful edit.
    result = command(backend, "save_layout", layout=baseline, expected_revision=1)
    command(backend, "apply_layout", expected_revision=result["draft_revision"])
    ready(backend)
    lab.podman("stop", "--time", "10", lab.PREFIX + "-ha")
    restart_ha()
    ready(backend)
    assert command(backend, "get_layout")["applied"] == baseline
    assert json.loads(path.read_text())["version"] == 1
