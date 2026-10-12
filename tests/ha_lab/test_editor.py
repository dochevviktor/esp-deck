"""P7 acceptance in Chromium, real HA, and the encrypted virtual deck."""
import json
import time
import secrets
import struct
import zlib
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pytest
from playwright.sync_api import sync_playwright, expect

from tools import ha_lab as lab
from test_backend import backend, command as backend_command, ready as backend_ready, apply_layout
from test_live import call, control, settled, snapshot, state, ws


def command(*args, **kwargs):
    # Playwright sync owns an event loop; run the independent WS client elsewhere.
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(backend_command, *args, **kwargs).result()


def ready(*args):
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(backend_ready, *args).result()


def fresh_png():
    # A new content identity on reruns, while the browser filename stays identical.
    color = secrets.token_bytes(3) + b"\xff"
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 72, 72, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress((b"\0" + color * 72) * 72)) + chunk(b"IEND", b""))


def login(page):
    creds = lab.credentials()
    page.goto(lab.URL, wait_until="domcontentloaded")
    page.get_by_label("Username", exact=True).fill(creds["username"])
    page.get_by_label("Password", exact=True).fill(creds["password"])
    page.get_by_role("button", name="Log in", exact=True).click()
    page.locator("home-assistant").wait_for(timeout=30000)
    page.goto(lab.URL + "/esp-deck", wait_until="domcontentloaded")
    page.locator("esp-deck-panel #apply").wait_for(timeout=30000)


def test_editor_upload_crop_relabel_move_touch_and_closed_browser(backend):
    apply_layout(backend, {"version": 1, "keys": [{} for _ in range(15)]})
    ready(backend)
    call("light.turn_off", {"entity_id": "light.example_lamp"})
    initial_actions = command(backend, "status")["binding_count"]
    initial_downloads = settled()["downloads"]
    assert command(backend, "status")["capabilities"]["artwork_upload"] == "png_chunks_v1"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 1000}, has_touch=True)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        login(page)
        page.locator("#preset-entity").select_option("light.example_lamp")
        page.get_by_role("button", name="Use preset", exact=True).click()
        expect(page.locator("#draft-status")).to_have_text("Unsaved edits")
        page.get_by_role("tab", name="Appearance", exact=True).click()
        page.locator("#upload").set_input_files(str(lab.ROOT / "assets/source/transport_test.png"))
        page.locator("#crop-fit").wait_for(timeout=15000)
        page.locator("#crop-fit").select_option("crop")
        page.locator("#crop-zoom").fill("1.5")
        page.locator("#crop-x").fill("0.5")
        page.get_by_role("button", name="Update crop preview", exact=True).click()
        expect(page.locator("#crop-update")).to_be_enabled(timeout=15000)
        page.locator("#v-text").fill("My lamp")
        page.locator("#v-text").press("Tab")
        page.locator("#v-font").select_option("12")
        page.get_by_role("button", name="Apply", exact=True).click()
        expect(page.locator("#draft-status")).to_have_text("Applied layout", timeout=15000)
        ready(backend); first = settled(0)
        assert first["tiles"][0]["text"] == "My lamp"
        assert len(first["tiles"][0]["image_revision"]) == 64
        assert first["downloads"] == initial_downloads
        page.locator("#v-text").fill("Relabeled")
        page.locator("#v-text").press("Tab")
        page.get_by_role("button", name="Apply", exact=True).click()
        expect(page.locator("#draft-status")).to_have_text("Applied layout", timeout=15000)
        ready(backend); second = settled(0)
        assert second["tiles"][0]["text"] == "Relabeled"
        assert second["downloads"] == first["downloads"] and second["download_bytes"] == first["download_bytes"]
        assert second["tiles"][0]["image_revision"] == first["tiles"][0]["image_revision"]
        page.locator("#upload").set_input_files({"name": "transport_test.png", "mimeType": "image/png",
            "buffer": fresh_png()})
        expect(page.locator("#apply")).to_be_enabled(timeout=15000)
        page.get_by_role("button", name="Apply", exact=True).click()
        expect(page.locator("#draft-status")).to_have_text("Applied layout", timeout=15000)
        ready(backend); replaced = settled(0)
        assert replaced["tiles"][0]["image_revision"] != second["tiles"][0]["image_revision"]
        assert replaced["downloads"] == second["downloads"]
        assert replaced["tiles"][0]["hash"] != second["tiles"][0]["hash"]
        page.locator("#destination").select_option("4")
        page.get_by_role("button", name="Move", exact=True).click()
        page.get_by_role("button", name="Apply", exact=True).click()
        expect(page.locator("#draft-status")).to_have_text("Applied layout", timeout=15000)
        ready(backend); moved = settled(4)
        assert moved["tiles"][4]["text"] == "Relabeled"
        assert command(backend, "status")["binding_count"] == initial_actions
        page.screenshot(path=str(lab.LAB / "p7-editor.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        page.get_by_role("button", name="Key 5", exact=True).tap()
        page.get_by_role("button", name="Clear key", exact=True).tap()
        page.get_by_role("button", name="Undo", exact=True).tap()
        expect(page.locator("#v-text")).to_have_value("Relabeled")
        assert page.evaluate("document.querySelector('home-assistant').getBoundingClientRect().width") <= 390
        page.screenshot(path=str(lab.LAB / "p7-editor-mobile.png"), full_page=True)
        assert not errors, errors
        browser.close()
    call("light.turn_off", {"entity_id": "light.example_lamp"})
    control(masks=[1 << 4, 0])
    lab.wait_for(lambda: state("light.example_lamp")["state"] == "on")
    ready(backend)
    assert command(backend, "status")["binding_count"] == initial_actions + 1
    # v1 caches a composed background; a changed background color may fetch once.
    # The strict zero-GET guarantee above is for label-only edits.
    assert settled(4)["tiles"][4]["rendered_revision"] > moved["tiles"][4]["rendered_revision"]


def test_editor_concurrent_drafts_keyboard_and_scene_preset(backend):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        first = context.new_page(); login(first)
        second = context.new_page()
        second.goto(lab.URL + "/esp-deck")
        second.locator("#apply").wait_for(timeout=30000)
        for page in (first, second):
            page.get_by_role("button", name="Key 1", exact=True).click()
            page.get_by_role("tab", name="Appearance", exact=True).click()
        first.locator("#v-text").fill("First draft"); first.locator("#v-text").press("Tab")
        first.get_by_role("button", name="Save draft", exact=True).click()
        expect(first.locator("#draft-status")).to_have_text("Saved draft · not applied", timeout=15000)
        second.locator("#v-text").fill("Stale draft"); second.locator("#v-text").press("Tab")
        second.get_by_role("button", name="Save draft", exact=True).click()
        expect(second.locator("#notice")).to_contain_text("another window", timeout=15000)
        expect(second.locator("#v-text")).to_have_value("Stale draft")
        assert command(backend, "get_layout")["draft"]["keys"][0]["visual"]["text"] == "First draft"
        first.get_by_role("button", name="Key 1", exact=True).focus()
        first.get_by_role("button", name="Key 1", exact=True).press("ArrowRight")
        expect(first.get_by_role("button", name="Key 2", exact=True)).to_be_focused()
        first.get_by_role("tab", name="Binding", exact=True).click()
        first.locator("#preset-entity").select_option("scene.lab_on")
        first.get_by_role("button", name="Use preset", exact=True).click()
        first.get_by_role("button", name="Apply", exact=True).click()
        expect(first.locator("#draft-status")).to_have_text("Applied layout", timeout=15000)
        ready(backend)
        browser.close()
    call("light.turn_off", {"entity_id": "light.example_lamp"})
    control(masks=[1 << 1, 0])
    lab.wait_for(lambda: state("light.example_lamp")["state"] == "on")


def test_real_upload_requires_auth_and_rejects_malformed_and_oversized(backend):
    url = lab.URL + "/api/esp_deck/upload/" + backend
    for payload, auth, expected in ((b"bad", False, 401), (b"bad", True, 400), (b"x" * (10 * 1024 * 1024 + 1), True, 400)):
        headers = {"Content-Type": "image/png"}
        if auth:
            headers["Authorization"] = "Bearer " + lab.credentials()["access_token"]
        request = urllib.request.Request(url, payload, headers)
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(request, timeout=30)
        assert err.value.code == expected
    document = command(backend, "export_layout")
    assert "/api/esp_deck/artwork/" not in json.dumps(document)
