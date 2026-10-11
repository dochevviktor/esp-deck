"""P8 acceptance over real encrypted native actions and simulated USB completion."""
from copy import deepcopy
import time

import pytest
from playwright.sync_api import sync_playwright, expect

from tools import ha_lab as lab
from test_backend import backend, command, ready, apply_layout
from test_live import call, control, settled, snapshot, state, PREFIX
from test_editor import login, command as browser_command, ready as browser_ready


def layout():
    main = [{"visual": {"text": str(key)}} for key in range(15)]
    other = deepcopy(main)
    target = {"entity_id": "light.example_lamp"}
    main[0].update(press={"action": "light.turn_on", "target": target},
                   release={"action": "light.turn_off", "target": target})
    other[0].update(press={"action": "light.turn_off", "target": target},
                    release={"action": "light.turn_on", "target": target})
    main[1]["navigation"] = {"kind": "page", "target": "second"}
    other[1]["navigation"] = {"kind": "page", "target": "main"}
    main[2]["navigation"] = {"kind": "momentary", "target": "shift"}
    return {"version": 2, "default_page": "main",
        "pages": [{"id": "main", "name": "Main", "keys": main}, {"id": "second", "name": "Second", "keys": other}],
        "overlays": [{"id": "shift", "name": "Shift", "keys": {"2": None, "3": {"visual": {"text": "Shift"}}}}]}


def test_capabilities_provision_fetch_and_failure_retains_allowlist(backend):
    caps = call(PREFIX + "get_deck_capabilities", response=True)
    assert (caps["protocol_version"], caps["keys"], caps["width"], caps["height"]) == (2, 15, 72, 72)
    assert caps["input_correlation"] == "pull_context_v2" and not caps["display_readback"]
    result = command(backend, "artwork_configure", origin="http://ha:8123")
    assert result["origin"] == "http://ha:8123"
    caps = call(PREFIX + "get_deck_capabilities", response=True)
    assert caps["origin_probe"] == "verified" and caps["origins"] == ["http://ha:8123"]
    with pytest.raises(AssertionError):
        command(backend, "artwork_configure", origin="http://ha:8124")
    assert command(backend, "artwork_list")["origin"] == "http://ha:8123"
    assert call(PREFIX + "get_deck_capabilities", response=True)["origins"] == ["http://ha:8123"]
    result = call(PREFIX + "provision_asset_origins", {"session": caps["session"],
        "origins": "http://ha:8123\nhttps://ha:8443", "test_url": "http://ha:8123/local/streamdeck/light_on.png"}, response=True)
    assert result["accepted"]
    lab.wait_for(lambda: call(PREFIX + "get_deck_capabilities", response=True)["origin_probe"] == "verified")
    old_session = snapshot()["session"]
    lab.podman("restart", "--time", "10", lab.PREFIX + "-deck")
    lab.wait_for(lambda: snapshot()["session"] != old_session)
    ready(backend)
    assert call(PREFIX + "get_deck_capabilities", response=True)["origins"] == ["http://ha:8123", "https://ha:8443"]
    command(backend, "artwork_configure", origin="http://ha:8123")


def test_same_pixels_new_binding_and_captured_release_across_page(backend):
    apply_layout(backend, layout())
    before = settled()
    control(masks=[1])
    lab.wait_for(lambda: state("light.example_lamp")["state"] == "on")
    command(backend, "select_page", page="second"); ready(backend)
    after = settled()
    assert after["tiles"][0]["uploads"] == before["tiles"][0]["uploads"]
    assert after["tiles"][0]["context"] != before["tiles"][0]["context"]
    control(masks=[0])
    lab.wait_for(lambda: state("light.example_lamp")["state"] == "off")
    # Navigation is driven through the correlated channel, never a debug action.
    control(masks=[2, 0])
    lab.wait_for(lambda: command(backend, "status")["active_page"] == "main")
    ready(backend)
    count = command(backend, "status")["binding_count"]
    control(masks=[3, 0])  # A managed press and navigation share one native batch.
    lab.wait_for(lambda: command(backend, "status")["active_page"] == "second")
    lab.wait_for(lambda: command(backend, "status")["binding_count"] == count + 2)
    assert state("light.example_lamp")["state"] == "off"
    command(backend, "select_page", page="main"); ready(backend)


def test_transitions_failed_tiles_rapid_pages_and_reconnect(backend):
    config = layout()
    config["pages"][1]["keys"][0]["visual"]["text"] = "Different"
    apply_layout(backend, config)
    control(delay_ms=200)
    count = command(backend, "status")["binding_count"]
    command(backend, "select_page", page="second")
    control(masks=[1, 0])
    ready(backend)
    assert command(backend, "status")["binding_count"] == count
    for page in ("main", "second", "main", "second"):
        command(backend, "select_page", page=page)
    ready(backend)
    assert command(backend, "status")["active_page"] == "second"
    # Cancel an in-flight page and reject callbacks from its retired generation.
    command(backend, "select_page", page="main")
    control(attached=False)
    time.sleep(0.2)
    control(attached=True, masks=[0], delay_ms=0)
    ready(backend)
    assert all(t["applied_revision"] == t["revision"] for t in command(backend, "status")["tiles"])
    config["pages"][1]["keys"][0]["visual"].update(image_url="http://ha:8123/local/streamdeck/invalid.png", image_revision="bad")
    apply_layout(backend, config)
    command(backend, "select_page", page="second")
    lab.wait_for(lambda: command(backend, "status")["tiles"][0].get("phase") == "failed")
    count = command(backend, "status")["binding_count"]
    control(masks=[1, 0]); time.sleep(0.4)
    assert command(backend, "status")["binding_count"] == count
    command(backend, "select_page", page="main"); ready(backend)


def test_modifier_release_overflow_and_usb_restart_reset(backend):
    apply_layout(backend, layout())
    control(masks=[4])
    lab.wait_for(lambda: command(backend, "status")["active_overlay"] == "shift")
    ready(backend)
    assert snapshot()["tiles"][2]["text"] == "" and snapshot()["tiles"][3]["text"] == "Shift"
    control(masks=[0])
    lab.wait_for(lambda: command(backend, "status")["active_overlay"] is None)
    ready(backend)
    control(masks=[4])
    lab.wait_for(lambda: command(backend, "status")["active_overlay"] == "shift")
    control(masks=[4] * 34)  # Production input-report FIFO overflow, silent resync.
    lab.wait_for(lambda: command(backend, "status")["active_overlay"] is None)
    ready(backend); control(masks=[0])
    control(masks=[4])
    lab.wait_for(lambda: command(backend, "status")["active_overlay"] == "shift")
    control(attached=False); time.sleep(0.2)
    control(attached=True, masks=[4, 0])
    lab.wait_for(lambda: command(backend, "status")["active_overlay"] is None)
    ready(backend)


def test_positioning_pages_and_navigation_in_editor(backend):
    apply_layout(backend, {"version": 1, "keys": [{} for _ in range(15)]})
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        errors = []; page.on("pageerror", lambda error: errors.append(str(error)))
        login(page)
        page.get_by_role("button", name="Enable pages & overlays", exact=True).click()
        page.get_by_role("button", name="Add page", exact=True).click()
        expect(page.locator("#edit-page")).to_have_value("page_1")
        page.locator("#page-name").fill("Music"); page.locator("#page-name").press("Tab")
        page.get_by_role("tab", name="Appearance", exact=True).click()
        page.locator("#v-text").fill("Music"); page.locator("#v-text").press("Tab")
        page.locator("#v-text_align").select_option("0"); page.locator("#v-text_valign").select_option("0")
        page.get_by_role("button", name="Add overlay", exact=True).click()
        page.get_by_role("button", name="Clear selected key", exact=True).click()
        page.get_by_role("button", name="Inherit selected key", exact=True).click()
        page.locator("#edit-overlay").select_option("")
        page.locator("#edit-page").select_option("main")
        page.get_by_role("tab", name="Binding", exact=True).click()
        page.locator("#navigation").select_option("page:page_1")
        page.get_by_role("button", name="Apply", exact=True).click()
        expect(page.locator("#draft-status")).to_have_text("Applied layout", timeout=15000)
        browser_ready(backend)
        saved = browser_command(backend, "get_layout")["applied"]
        assert saved["version"] == 2 and saved["pages"][1]["name"] == "Music"
        assert saved["pages"][1]["keys"][0]["visual"]["text_align"] == 0
        assert saved["overlays"][0]["keys"] == {}
        page.screenshot(path=str(lab.LAB / "p8-editor.png"), full_page=True)
        assert not errors, errors
        browser.close()
    control(masks=[1, 0])
    lab.wait_for(lambda: command(backend, "status")["active_page"] == "page_1")
    ready(backend)
