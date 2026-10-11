"""Real HA container + encrypted ESPHome host API. No mocks or physical device.

Only file-based virtual-deck controls inject input. Production actions remain
identical to P4, and production PNG/render/store/scheduler code executes in C++.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import time
import urllib.error

import aiohttp
import pytest

from tools import ha_lab as lab

SESSION = "sensor.stream_deck_original_visual_session"
REPLAY = "automation.stream_deck_replay_authoritative_layout"
PREFIX = "esphome.streamdeck_original_"


def snapshot():
    return json.loads((lab.LAB / "deck/status.json").read_text())


def control(**values):
    seq = snapshot()["sequence"] + 1
    temporary = lab.LAB / "deck/control.tmp"
    lab.private_write(temporary, json.dumps({"sequence": seq, **values}))
    temporary.replace(lab.LAB / "deck/control.json")
    lab.wait_for(lambda: snapshot()["sequence"] == seq, timeout=5, description="virtual input acknowledgement")


def state(entity):
    return lab.request("/api/states/" + entity)


def call(action, data=None, *, response=False):
    domain, service = action.split(".", 1)
    result = lab.request(f"/api/services/{domain}/{service}" + ("?return_response" if response else ""), data or {})
    return result["service_response"] if response else result


def patch(key, values):
    return call("script.stream_deck_apply", {"key": key, "patch": values}, response=True)


def settled(key=None, text=None):
    previous = None
    stable_since = time.monotonic()
    def ready():
        nonlocal previous, stable_since
        data = snapshot()
        tiles = data["tiles"] if key is None else [data["tiles"][key]]
        signature = (data["session"], data["reports"], data["active_page"],
                     [(tile["revision"], tile["phase"], tile["uploads"]) for tile in data["tiles"]])
        if signature != previous:
            previous, stable_since = signature, time.monotonic()
        if (data["active_page"] == 0 and all(tile["phase"] == "rendered" for tile in tiles)
                and (text is None or tiles[0]["text"] == text)
                and time.monotonic() - stable_since >= 0.35):
            return data
        return None
    # Observe stable report counters as well: rendered precedes simulated output.
    return lab.wait_for(ready, timeout=30, description="completed simulated tile output")


async def websocket_command(message):
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(lab.URL + "/api/websocket") as ws:
            assert (await ws.receive_json())["type"] == "auth_required"
            await ws.send_json({"type": "auth", "access_token": lab.credentials()["access_token"]})
            assert (await ws.receive_json())["type"] == "auth_ok"
            await ws.send_json({"id": 1, **message})
            while True:
                result = await ws.receive_json(timeout=20)
                if result.get("id") == 1:
                    assert result["success"], result
                    return result["result"]


def ws(message):
    return asyncio.run(websocket_command(message))


@pytest.fixture(autouse=True)
def stable_lab():
    for suffix in ("ha", "deck"):
        item = lab.inspect_owned("container", lab.PREFIX + "-" + suffix)
        assert item and item["State"]["Running"], "Start the owned lab with tools/ha_lab.py up"
    lab.refresh_token()
    # P4 and the managed backend are alternative owners. Preserve its saved
    # layouts while pausing it for the manual-helper regression suite.
    for entry in lab.request("/api/config/config_entries/entry"):
        if entry["domain"] == "esp_deck" and entry.get("disabled_by") is None:
            ws({"type": "config_entries/disable", "entry_id": entry["entry_id"], "disabled_by": "user"})
    lab.pair()
    manual_bindings = [item["entity_id"] for item in lab.request("/api/states")
                       if item["entity_id"].startswith("automation.") and item["attributes"].get("id")
                       in ("stream_deck_key_0_press", "stream_deck_key_0_release")]
    call("automation.turn_on", {"entity_id": manual_bindings})
    call("automation.turn_off", {"entity_id": REPLAY, "stop_actions": True})
    control(attached=True, masks=[0], delay_ms=0, fail_page=0)
    call("light.turn_off", {"entity_id": "light.example_lamp"})
    call("script.stream_deck_sync_layout")
    settled()
    yield
    call("automation.turn_on", {"entity_id": REPLAY})


def test_encrypted_pairing_discovery_and_action_response():
    result = lab.podman("exec", lab.PREFIX + "-deck", "python", "/lab/native_probe.py", "encryption")
    probe = json.loads(result.stdout.strip().splitlines()[-1])
    assert probe["version"] == "2026.9.0"
    assert probe["entities"] == 31
    assert probe["actions"] == ["clear_key_visual", "get_key_visual_status", "refresh_key_image", "set_key_visual"]
    entities = ws({"type": "config/entity_registry/list"})
    deck_entities = [entry for entry in entities if entry["platform"] == "esphome"]
    assert len([entry for entry in deck_entities if entry["entity_id"].startswith("event.")]) == 15
    assert len([entry for entry in deck_entities if entry["entity_id"].startswith("binary_sensor.")]) == 15
    services = next(group["services"] for group in lab.request("/api/services") if group["domain"] == "esphome")
    assert len(services["streamdeck_original_set_key_visual"]["fields"]) == 12
    assert services["streamdeck_original_set_key_visual"]["response"]["optional"] is False
    with pytest.raises(urllib.error.HTTPError):
        call(PREFIX + "get_key_visual_status", {"session": snapshot()["session"], "key": 0})
    result = call(PREFIX + "get_key_visual_status", {"session": snapshot()["session"], "key": 0}, response=True)
    assert result["accepted"] and result["phase"] == "rendered"


def test_actual_p4_helpers_all_keys_revisions_numeric_text_and_noop_replay():
    before = settled()
    assert [tile["key"] for tile in before["tiles"]] == list(range(15))
    call("script.stream_deck_sync_layout")
    after = settled()
    assert after["downloads"] == before["downloads"]
    assert after["reports"] == before["reports"]
    for old, new in zip(before["tiles"], after["tiles"], strict=True):
        assert new["revision"] == old["revision"] + 1
        assert new["hash"] == old["hash"]
    result = patch(4, {"text": "123"})
    assert result["accepted"]
    assert settled(4, "123")["tiles"][4]["text"] == "123"
    values = {"session": result["session"], "key": 4, "revision": result["revision"], "patch": {"text": "123"}}
    duplicate = call("script.stream_deck_visual_patch", values, response=True)
    assert duplicate["accepted"] and duplicate["revision"] == result["revision"]
    conflict = call("script.stream_deck_visual_patch", {**values, "patch": {"text": "456"}}, response=True)
    assert conflict["error"] == "revision_conflict" and not conflict["accepted"]
    stale = call("script.stream_deck_visual_patch", {**values, "revision": result["revision"] - 1}, response=True)
    assert stale["error"] == "stale_revision" and not stale["accepted"]
    wrong = call("script.stream_deck_visual_patch", {**values, "session": "0000000000000000"}, response=True)
    assert wrong["error"] == "wrong_session"


def test_real_asset_fetch_cache_revision_and_failures_preserve_tile():
    before = settled()
    patch(0, {"text": "Cached"})
    changed = settled(0, "Cached")
    assert changed["downloads"] == before["downloads"]
    assert changed["cache_hits"] > before["cache_hits"]
    result = call(PREFIX + "refresh_key_image", {"session": changed["session"], "key": 0,
        "revision": changed["tiles"][0]["revision"] + 1, "image_revision": "refresh-" + str(time.time_ns())}, response=True)
    assert result["accepted"]
    refreshed = settled(0)
    assert refreshed["downloads"] == before["downloads"] + 1
    assert refreshed["tiles"][0]["hash"] == changed["tiles"][0]["hash"]
    for path, error in (("missing.png", "http_status"), ("invalid.png", "decode_failed")):
        result = patch(0, {"image_url": "http://ha:8123/local/streamdeck/" + path, "image_revision": "bad-v1"})
        lab.wait_for(lambda: snapshot()["tiles"][0]["phase"] == "failed" and
                     snapshot()["tiles"][0]["revision"] == result["revision"], timeout=20)
        failed = snapshot()["tiles"][0]
        assert failed["error"] == error
        assert failed["hash"] == refreshed["tiles"][0]["hash"]
        assert failed["rendered_revision"] == refreshed["tiles"][0]["rendered_revision"]
    downloads = snapshot()["downloads"]
    rejected = call("script.stream_deck_visual_patch", {"session": snapshot()["session"], "key": 0,
        "revision": snapshot()["tiles"][0]["revision"] + 1,
        "patch": {"image_url": "http://example.invalid/icon.png", "image_revision": "v1"}}, response=True)
    assert rejected["error"] == "origin_not_allowed" and snapshot()["downloads"] == downloads
    cleared = call(PREFIX + "clear_key_visual", {"session": snapshot()["session"], "key": 0,
        "revision": snapshot()["tiles"][0]["revision"] + 1}, response=True)
    assert cleared["accepted"]
    assert settled(0, "")["tiles"][0]["image_revision"] == ""


def test_all_fifteen_real_events_and_state_driven_ha_binding():
    call("automation.turn_on", {"entity_id": REPLAY})
    edges_before = snapshot()["edges"]
    for key in range(15):
        entity = f"event.stream_deck_original_key_{key}_edge"
        previous = state(entity)["state"]
        control(masks=[1 << key])
        lab.wait_for(lambda: state(entity)["state"] != previous and
                     state(entity)["attributes"].get("event_type") == "press", timeout=10)
        pressed = state(entity)["state"]
        control(masks=[1 << key])  # Duplicate report cannot become another event.
        time.sleep(0.1)
        assert state(entity)["state"] == pressed
        control(masks=[0])
        lab.wait_for(lambda: state(entity)["state"] != pressed and
                     state(entity)["attributes"].get("event_type") == "release", timeout=10)
    assert state("light.example_lamp")["state"] == "on"
    assert snapshot()["edges"] == edges_before + 30
    settled(0, "Desk ON")
    call("scene.turn_on", {"entity_id": "scene.lab_off"})
    lab.wait_for(lambda: state("light.example_lamp")["state"] == "off")
    settled(0, "Desk OFF")
    # Direct HA state feedback, independent of any virtual physical press.
    call("light.turn_on", {"entity_id": "light.example_lamp"})
    settled(0, "Desk ON")
    # A synthetic entity can report unavailable independently of button input.
    lab.request("/api/states/light.example_lamp", {"state": "unavailable", "attributes": {}})
    settled(0, "Desk ?")


def test_registry_renames_preserve_ids_but_manual_helpers_need_entity_names():
    entries = ws({"type": "config/entity_registry/list"})
    entry = next(entry for entry in entries if entry["entity_id"] == SESSION)
    renamed = "sensor.lab_renamed_session"
    try:
        result = ws({"type": "config/entity_registry/update", "entity_id": SESSION, "new_entity_id": renamed})
        assert result["entity_entry"]["id"] == entry["id"]
        assert state(renamed)["state"] == snapshot()["session"]
        revision = snapshot()["tiles"][3]["revision"]
        # HA stop/error records the failed script trace but REST can still return
        # HTTP 200 with an empty response. Require accepted, not transport success.
        assert not patch(3, {"text": "requires HA helper reconfiguration"}).get("accepted")
        assert snapshot()["tiles"][3]["revision"] == revision
        # Native action prefix is the ESP node name, independent of registry UI names.
        assert call(PREFIX + "get_key_visual_status", {"session": snapshot()["session"], "key": 3}, response=True)["accepted"]
        ws({"type": "config/device_registry/update", "device_id": entry["device_id"], "name_by_user": "Renamed virtual deck"})
        assert call(PREFIX + "get_key_visual_status", {"session": snapshot()["session"], "key": 3}, response=True)["accepted"]
    finally:
        ws({"type": "config/entity_registry/update", "entity_id": renamed, "new_entity_id": SESSION})
        ws({"type": "config/device_registry/update", "device_id": entry["device_id"], "name_by_user": None})
    assert patch(3, {"text": "Registry restored"})["accepted"]


def test_logger_connections_do_not_reset_or_redraw_visuals():
    before = settled()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(lab.podman, "exec", lab.PREFIX + "-deck", "python", "/lab/native_probe.py", "logger")
        assert call(PREFIX + "get_key_visual_status", {"session": before["session"], "key": 0}, response=True)["accepted"]
        future.result(timeout=15)
    after = snapshot()
    assert after["session"] == before["session"]
    assert after["downloads"] == before["downloads"]
    assert after["reports"] == before["reports"]
    assert after["tiles"] == before["tiles"]


def test_delayed_failed_simulated_usb_and_deck_only_reconnect():
    before = settled()
    control(masks=[1 << 9])  # Recovery invalidates a held state without a release event.
    control(delay_ms=350, fail_page=2)
    patch(7, {"text": "First"})
    lab.wait_for(lambda: snapshot()["active_page"] == 1)
    patch(7, {"text": "Latest"})
    lab.wait_for(lambda: snapshot()["failed_reports"] > before["failed_reports"])
    control(delay_ms=0, masks=[0])
    final = settled(7, "Latest")
    assert final["edges"] == before["edges"] + 1
    control(attached=False)
    detached = snapshot()
    control(attached=True, masks=[1 << 8, 0])  # Held-at-attach release stays silent.
    lab.wait_for(lambda: snapshot()["reports"] >= detached["reports"] + 32)
    after = snapshot()
    assert after["session"] == before["session"]
    assert after["downloads"] == final["downloads"]
    assert after["edges"] == detached["edges"]
    assert [tile["hash"] for tile in after["tiles"]] == [tile["hash"] for tile in final["tiles"]]


def test_ha_outage_restart_no_input_replay_and_virtual_reboot_numeric_session():
    call("automation.turn_on", {"entity_id": REPLAY})
    before = settled()
    lab.podman("stop", "--time", "10", lab.PREFIX + "-ha")
    try:
        control(masks=[1, 0])
        offline = snapshot()
        assert offline["session"] == before["session"]
        assert offline["tiles"] == before["tiles"]
    finally:
        lab.podman("start", lab.PREFIX + "-ha")
    lab.wait_for(lambda: lab.request("/api/")["message"] == "API running.", description="HA restart")
    lab.refresh_token()
    lab.pair()
    lab.wait_for(lambda: snapshot()["tiles"][14]["revision"] > before["tiles"][14]["revision"])
    after = settled()
    assert after["session"] == before["session"]
    assert after["downloads"] == before["downloads"]
    assert after["reports"] == before["reports"]
    assert state("light.example_lamp")["state"] == "off"  # Outage press was never replayed.
    numeric_session = "1234567890123456"
    lab.private_write(lab.LAB / "deck/next-session", numeric_session)
    lab.podman("restart", "--time", "10", lab.PREFIX + "-deck")
    lab.wait_for(lambda: state(SESSION)["state"] == numeric_session, description="new virtual boot identity")
    lab.wait_for(lambda: snapshot()["tiles"][14]["phase"] == "rendered", description="automatic reboot replay")
    assert patch(4, {"text": "123"})["session"] == numeric_session
    assert settled(4, "123")["downloads"] == 1


def test_browser_authenticated_ha_ui_smoke():
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
        page.goto(lab.URL + "/config/devices/dashboard", wait_until="domcontentloaded")
        page.get_by_text("Stream Deck Original", exact=True).first.click(timeout=30000)
        page.get_by_text("Visual session", exact=True).first.wait_for(timeout=30000)
        page.screenshot(path=str(lab.LAB / "ha-browser.png"), full_page=True)
        assert "onboarding" not in page.url
        browser.close()
    # The P4 automations continue after the browser has closed.
    call("automation.turn_on", {"entity_id": REPLAY})
    control(masks=[1])
    control(masks=[0])
    lab.wait_for(lambda: state("light.example_lamp")["state"] == "on")
    settled(0, "Desk ON")
