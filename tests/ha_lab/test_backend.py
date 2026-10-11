"""Real installed P6 integration + real encrypted native API, without hardware."""

from copy import deepcopy
import time
import urllib.error

import pytest

from tools import ha_lab as lab
from test_live import call, control, settled, snapshot, state, ws

MANUAL = ["automation.stream_deck_replay_authoritative_layout", "automation.stream_deck_key_0_press_binding",
          "automation.stream_deck_key_0_release_binding"]


def command(entry_id, operation, **parameters):
    return ws({"type": "esp_deck/command", "entry_id": entry_id, "operation": operation, "parameters": parameters})


def ready(entry_id):
    def check():
        # HTTP starts before config-entry setup/WS registration after HA restart.
        if not any(entry["entry_id"] == entry_id and entry["state"] == "loaded"
                   for entry in lab.request("/api/config/config_entries/entry")):
            return None
        result = command(entry_id, "status")
        return result if result["state"] == "ready" else None
    return lab.wait_for(check, timeout=40, description="managed backend synchronization")


@pytest.fixture(scope="module")
def backend():
    lab.refresh_token()
    control(attached=True, masks=[0], delay_ms=0, fail_page=0)
    entries = lab.request("/api/config/config_entries/entry")
    existing = next((entry for entry in entries if entry["domain"] == "esp_deck"), None)
    devices = ws({"type": "config/device_registry/list"})
    source = next(entry for entry in entries if entry["domain"] == "esphome")
    device = next(item for item in devices if item["config_entry_id"] == source["entry_id"])
    # The config flow explicitly chooses which existing automations to stop.
    manual = [item["entity_id"] for item in lab.request("/api/states")
              if item["entity_id"].startswith("automation.") and item["attributes"].get("id") in (
                  "stream_deck_replay_layout", "stream_deck_key_0_press", "stream_deck_key_0_release")]
    if existing is None:
        flow = lab.request("/api/config/config_entries/flow", {"handler": "esp_deck", "show_advanced_options": False})
        assert flow["step_id"] == "user", flow
        flow = lab.request("/api/config/config_entries/flow/" + flow["flow_id"], {"device_id": device["id"]})
        assert flow["step_id"] == "handoff" and not flow.get("errors"), flow
        flow = lab.request("/api/config/config_entries/flow/" + flow["flow_id"], {
            "exclusive_control": True, "disable_automations": manual,
            "preset_entity": "light.example_lamp", "label": "Lab lamp"})
        assert flow["type"] == "create_entry", flow
        entry_id = flow["result"]["entry_id"]
    else:
        entry_id = existing["entry_id"]
        call("automation.turn_off", {"entity_id": manual, "stop_actions": True})
        ws({"type": "config_entries/disable", "entry_id": entry_id, "disabled_by": None})
    ready(entry_id)
    assert all(state(entity)["state"] == "off" for entity in manual)
    yield entry_id
    # Leave a working managed layout for the owner's lab inspection.
    ready(entry_id)


def apply_layout(entry_id, layout):
    current = command(entry_id, "get_layout")
    saved = command(entry_id, "save_layout", layout=layout, expected_revision=current["draft_revision"])
    command(entry_id, "apply_layout", expected_revision=saved["draft_revision"])
    ready(entry_id)
    return settled()


def test_real_guided_setup_reuses_esphome_and_closed_browser_binding(backend):
    entries = lab.request("/api/config/config_entries/entry")
    assert len([entry for entry in entries if entry["domain"] == "esphome"]) == 1
    devices = ws({"type": "config/device_registry/list"})
    source_id = next(entry["entry_id"] for entry in entries if entry["domain"] == "esphome")
    assert len([device for device in devices if device["config_entry_id"] == source_id]) == 1
    assert not any(device["config_entry_id"] == backend for device in devices)
    # This basic-flow scenario must also be repeatable after the P8 editor has
    # left a multi-page layout in the private lab.
    layout = {"version": 1, "keys": [{} for _ in range(15)]}
    layout["keys"][0] = command(backend, "preset", entity_id="light.example_lamp", label="Lab lamp")["key"]
    apply_layout(backend, layout)
    call("light.turn_off", {"entity_id": "light.example_lamp"})
    ready(backend)
    before = command(backend, "status")["binding_count"]
    control(masks=[1, 0])
    lab.wait_for(lambda: state("light.example_lamp")["state"] == "on")
    lab.wait_for(lambda: command(backend, "status")["binding_count"] == before + 1)
    assert settled(0)["tiles"][0]["text"] == "Lab lamp"
    call("light.turn_off", {"entity_id": "light.example_lamp"})
    ready(backend)
    assert command(backend, "status")["connected"]


def test_draft_apply_export_import_cache_and_noop_sync(backend):
    layout = command(backend, "get_layout")["applied"]
    layout["keys"][3]["visual"].update(image_url="http://ha:8123/local/streamdeck/light_on.png",
                                       image_revision="p6-v1", text="Artwork")
    apply_layout(backend, layout)
    before = settled()
    layout["keys"][3]["visual"]["text"] = "Relabeled"
    current = command(backend, "get_layout")
    saved = command(backend, "save_layout", layout=layout, expected_revision=current["draft_revision"])
    assert snapshot()["tiles"][3]["text"] == "Artwork"
    exported = command(backend, "export_layout")
    assert "registry_id" not in str(exported)
    imported = command(backend, "import_layout", document=exported, expected_revision=saved["draft_revision"])
    command(backend, "apply_layout", expected_revision=imported["draft_revision"])
    ready(backend)
    after = settled(3, "Relabeled")
    assert after["downloads"] == before["downloads"]
    assert command(backend, "export_layout", which="backup")["layout"]["keys"][3]["visual"]["text"] == "Artwork"
    revisions = [tile["revision"] for tile in after["tiles"]]
    command(backend, "sync")
    time.sleep(1)
    assert [tile["revision"] for tile in snapshot()["tiles"]] == revisions
    assert snapshot()["reports"] == after["reports"]
    with pytest.raises(urllib.error.HTTPError) as error:
        lab.request("/api/services/esp_deck/status?return_response", {"entry_id": backend}, auth=False)
    assert error.value.code == 401


def test_renamed_session_and_target_follow_stable_registry_ids(backend):
    session = "sensor.stream_deck_original_visual_session"
    lamp = "light.example_lamp"
    try:
        ws({"type": "config/entity_registry/update", "entity_id": session, "new_entity_id": "sensor.p6_session"})
        ws({"type": "config/entity_registry/update", "entity_id": lamp, "new_entity_id": "light.p6_lamp"})
        ready(backend)
        call("light.turn_off", {"entity_id": "light.p6_lamp"})
        control(masks=[1, 0])
        lab.wait_for(lambda: state("light.p6_lamp")["state"] == "on")
        exported = command(backend, "export_layout", which="applied")
        assert exported["layout"]["keys"][0]["state"]["entity"]["entity_id"] == "light.p6_lamp"
    finally:
        ws({"type": "config/entity_registry/update", "entity_id": "sensor.p6_session", "new_entity_id": session})
        ws({"type": "config/entity_registry/update", "entity_id": "light.p6_lamp", "new_entity_id": lamp})
    ready(backend)


def test_actionable_asset_failure_keeps_pixels_and_explicit_correction(backend):
    original = command(backend, "get_layout")["applied"]
    layout = deepcopy(original)
    before = settled()
    layout["keys"][3]["visual"].update(image_url="http://ha:8123/local/streamdeck/missing.png", image_revision="missing")
    current = command(backend, "get_layout")
    saved = command(backend, "save_layout", layout=layout, expected_revision=current["draft_revision"])
    command(backend, "apply_layout", expected_revision=saved["draft_revision"])
    failed = lab.wait_for(lambda: (result if (result := command(backend, "status"))["tiles"][3].get("phase") == "failed" else None))
    assert failed["connected"] and failed["tiles"][3]["error"] == "http_status"
    assert snapshot()["tiles"][3]["hash"] == before["tiles"][3]["hash"]
    downloads = snapshot()["downloads"]
    time.sleep(1)
    assert snapshot()["downloads"] == downloads
    apply_layout(backend, original)


def test_unload_reload_persistence_and_no_offline_press_replay(backend):
    call("light.turn_off", {"entity_id": "light.example_lamp"})
    ready(backend)
    before = settled()
    document = command(backend, "get_layout")
    assert not ws({"type": "config_entries/disable", "entry_id": backend, "disabled_by": "user"})["require_restart"]
    control(masks=[1, 0])
    time.sleep(.5)
    assert state("light.example_lamp")["state"] == "off"
    assert snapshot()["reports"] == before["reports"]
    ws({"type": "config_entries/disable", "entry_id": backend, "disabled_by": None})
    ready(backend)
    assert command(backend, "get_layout") == document
    assert snapshot()["downloads"] == before["downloads"]
    assert snapshot()["reports"] == before["reports"]
    assert state("light.example_lamp")["state"] == "off"


def test_ha_restart_and_virtual_reboot_replay_without_browser(backend):
    call("light.turn_off", {"entity_id": "light.example_lamp"})
    ready(backend)
    before = settled()
    document = command(backend, "get_layout")
    lab.podman("stop", "--time", "10", lab.PREFIX + "-ha")
    try:
        control(masks=[1, 0])
    finally:
        lab.podman("start", lab.PREFIX + "-ha")
    lab.wait_for(lambda: lab.request("/api/")["message"] == "API running.")
    lab.refresh_token()
    ready(backend)
    assert state("light.example_lamp")["state"] == "off"
    assert command(backend, "get_layout") == document
    assert settled()["reports"] == before["reports"]
    lab.private_write(lab.LAB / "deck/next-session", "2345678901234567")
    lab.podman("restart", "--time", "10", lab.PREFIX + "-deck")
    lab.wait_for(lambda: state("sensor.stream_deck_original_visual_session")["state"] == "2345678901234567")
    ready(backend)
    assert settled(3, "Relabeled")["session"] == "2345678901234567"
    assert command(backend, "get_layout") == document


def test_browser_integration_and_options_preset(backend):
    # Exercise the actual HA options flow without a frontend owning synchronization.
    flow = lab.request("/api/config/config_entries/options/flow", {"handler": backend, "show_advanced_options": False})
    flow = lab.request("/api/config/config_entries/options/flow/" + flow["flow_id"], {"next_step_id": "binding"})
    assert flow["step_id"] == "binding"
    flow = lab.request("/api/config/config_entries/options/flow/" + flow["flow_id"], {
        "key": "2", "entity_id": "scene.lab_on", "label": "Scene", "apply": True})
    assert flow["type"] == "create_entry", flow
    ready(backend)
    from playwright.sync_api import sync_playwright
    creds = lab.credentials()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(lab.URL, wait_until="domcontentloaded")
        page.get_by_label("Username", exact=True).fill(creds["username"])
        page.get_by_label("Password", exact=True).fill(creds["password"])
        page.get_by_role("button", name="Log in", exact=True).click()
        page.locator("home-assistant").wait_for(timeout=30000)
        page.goto(lab.URL + "/config/integrations/integration/esp_deck", wait_until="domcontentloaded")
        page.get_by_text("ESP Deck", exact=True).first.wait_for(timeout=30000)
        # Click HA's button host: its slotted icon is outside the shadow button
        # and correctly receives pointer events at the center of the control.
        page.locator("ha-button").filter(has=page.get_by_role("button", name="Configure", exact=True)).click(timeout=30000)
        page.get_by_text("Set an entity preset", exact=True).wait_for(timeout=30000)
        page.get_by_role("link", name="Open the visual editor", exact=True).wait_for(timeout=10000)
        page.screenshot(path=str(lab.LAB / "p6-browser.png"), full_page=True)
        browser.close()
    call("light.turn_off", {"entity_id": "light.example_lamp"})
    control(masks=[1 << 2, 0])
    lab.wait_for(lambda: state("light.example_lamp")["state"] == "on")
