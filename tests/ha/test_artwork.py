"""Artwork transactions and admin/capability boundaries in the real HA engine."""
import asyncio
from copy import deepcopy
from io import BytesIO
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aiohttp import web
from PIL import Image
import pytest
import pytest_asyncio

from custom_components.esp_deck import api
from custom_components.esp_deck.artwork import ArtworkLibrary, DATA_KEY, GRACE_SECONDS, MAX_UPLOAD
from custom_components.esp_deck.model import LayoutError, empty_layout
from custom_components.esp_deck.panel import CapabilityFilter, DeviceArtworkView, PreviewView, UploadView
from test_backend import engine, deck, start, wait_until


def png(color="red"):
    output = BytesIO()
    Image.new("RGBA", (90, 60), color).save(output, format="PNG")
    return output.getvalue()


@pytest_asyncio.fixture
async def library(deck):
    lib = deck.hass.data[DATA_KEY] = ArtworkLibrary(deck.hass)
    await lib.load()
    await lib.ensure(deck.entry.entry_id)
    await lib.ensure("other-deck")
    await lib.configure(deck.entry.entry_id, "http://ha:8123")
    return lib


async def save_asset(deck, asset_id):
    layout = empty_layout()
    layout["keys"][0]["visual"]["asset_id"] = asset_id
    await api.execute(deck.hass, "save_layout", {"entry_id": deck.entry.entry_id, "layout": layout,
                      "expected_revision": deck.repo.data["draft_revision"]})
    return layout


@pytest.mark.asyncio
async def test_capability_only_references_device_scope_revocation_and_secret_free_export(deck, library):
    await start(deck)
    entry = deck.entry.entry_id
    asset = await library.upload(entry, png())
    key = asset["asset_id"]
    token = library.data["decks"][entry]["token"]
    repos = {entry: deck.repo}
    with pytest.raises(LayoutError):  # An uploaded, unsaved file is not device-readable.
        library.authorize(token, key, repos)
    layout = await save_asset(deck, key)
    assert library.authorize(token, key, repos) == entry
    assert library.resolve(entry, layout["keys"][0]["visual"])["image_revision"] == key
    with pytest.raises(LayoutError):
        library.authorize(library.data["decks"]["other-deck"]["token"], key, repos)
    with pytest.raises(LayoutError):
        library.validate("other-deck", layout)
    for bad in ("../a", "/etc/passwd", key + "/..", "%2e%2e", "a" * 63):
        with pytest.raises(LayoutError):
            await library.read(entry, bad)
    document = await api.execute(deck.hass, "export_layout", {"entry_id": entry})
    assert token not in json.dumps(document)
    assert token not in json.dumps(await api.execute(deck.hass, "get_layout", {"entry_id": entry}))
    assert token not in json.dumps(library.listing(entry, deck.repo))
    await library.configure(entry, revoke=True)
    with pytest.raises(LayoutError):
        library.authorize(token, key, repos)
    assert library.authorize(library.data["decks"][entry]["token"], key, repos) == entry
    for _ in range(125):
        with pytest.raises(LayoutError):
            library.authorize("invalid", key, repos)
    with pytest.raises(LayoutError, match="rate_limited"):
        library.authorize("invalid", key, repos)
    # Invalid-request floods cannot block a valid known deck.
    assert library.authorize(library.data["decks"][entry]["token"], key, repos) == entry


@pytest.mark.asyncio
async def test_atomic_failures_quota_concurrency_and_source_refresh(deck, library):
    entry = deck.entry.entry_id
    initial = deepcopy(library.data)
    with patch.object(library.store, "async_save", side_effect=LayoutError("storage_write_failed")):
        with pytest.raises(LayoutError):
            await library.upload(entry, png())
    assert library.data == initial
    assert not list(library._directory(entry).iterdir())
    with patch("custom_components.esp_deck.artwork.MAX_LIBRARY_BYTES", 100):
        with pytest.raises(LayoutError, match="library_full"):
            await library.upload(entry, png())
    first, duplicate, refreshed = await asyncio.gather(library.upload(entry, png()),
        library.upload(entry, png()), library.upload(entry, png("blue")))
    assert first["asset_id"] == duplicate["asset_id"] != refreshed["asset_id"]
    assert len(library.data["decks"][entry]["variants"]) == 2
    async with library.slot(), library.slot(), library.slot():
        with pytest.raises(LayoutError, match="busy"):
            async with library.slot():
                pass
    assert library.pending == 0
    reopened = ArtworkLibrary(deck.hass)
    await reopened.load()
    assert reopened.data == library.data
    orphan = library._directory(entry) / ".upload-orphan"
    await deck.hass.async_add_executor_job(orphan.write_bytes, b"unfinished")
    await reopened.load()
    assert not await deck.hass.async_add_executor_job(orphan.exists)


@pytest.mark.asyncio
async def test_reference_gc_backup_and_inflight_read_retention(deck, library):
    await start(deck)
    entry = deck.entry.entry_id
    asset = await library.upload(entry, png())
    key = asset["asset_id"]
    await save_asset(deck, key)
    await api.execute(deck.hass, "apply_layout", {"entry_id": entry, "expected_revision": 1})
    await api.execute(deck.hass, "save_layout", {"entry_id": entry, "layout": empty_layout(), "expected_revision": 1})
    await api.execute(deck.hass, "apply_layout", {"entry_id": entry, "expected_revision": 2})
    library.leases.clear()
    with pytest.raises(LayoutError, match="in_use"):
        await library.collect(entry, deck.repo, asset_id=key)  # Previous applied backup.
    await api.execute(deck.hass, "save_layout", {"entry_id": entry, "layout": empty_layout(), "expected_revision": 2})
    await api.execute(deck.hass, "apply_layout", {"entry_id": entry, "expected_revision": 3})
    assert library.authorize(library.data["decks"][entry]["token"], key, {entry: deck.repo}) == entry
    response_bytes = await library.read(entry, key)
    assert (await library.collect(entry, deck.repo))["removed_files"] == 0  # Retiring fetch grace.
    library.leases.clear(); library.read_leases.clear()
    assert (await library.collect(entry, deck.repo))["removed_files"] == 2
    assert response_bytes.startswith(b"\x89PNG")  # A response owns its bytes through network drain.
    with pytest.raises(LayoutError):
        await library.read(entry, key)


@pytest.mark.asyncio
async def test_cancelled_conversion_drains_before_releasing_slot(deck, library):
    entered, release = asyncio.Event(), asyncio.Event()
    original = library._insert
    async def delayed(*args):
        entered.set()
        await release.wait()
        return await original(*args)
    async def work():
        async with library.slot():
            return await library.upload(deck.entry.entry_id, png())
    with patch.object(library, "_insert", delayed):
        task = asyncio.create_task(work())
        await entered.wait()
        task.cancel()
        await asyncio.sleep(.02)
        assert library.pending == 1 and library.conversion.locked() and not task.done()
        task.cancel()  # A disconnect followed by shutdown must not free the slot early.
        await asyncio.sleep(.02)
        assert library.pending == 1 and library.conversion.locked() and not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert library.pending == 0 and not library.conversion.locked()
    assert len(library.data["decks"][deck.entry.entry_id]["variants"]) == 1


class Request(dict):
    content_type = "image/png"
    query_string = ""
    def __init__(self, payload=b"", *, admin=True):
        super().__init__(hass_user=SimpleNamespace(is_admin=admin))
        self.payload = payload
        self.content_length = len(payload)
        self.content = self
    async def iter_chunked(self, _):
        for at in range(0, len(self.payload), 65536):
            yield self.payload[at:at + 65536]


@pytest.mark.asyncio
async def test_http_admin_upload_preview_bounds_and_capability_get(deck, library):
    await start(deck)
    entry = deck.entry.entry_id
    upload, preview, device = UploadView(deck.hass), PreviewView(deck.hass), DeviceArtworkView(deck.hass)
    with pytest.raises(web.HTTPForbidden):
        await upload.post(Request(png(), admin=False), entry)
    with pytest.raises(web.HTTPForbidden):
        await preview.get(Request(admin=False), entry, "a" * 64)
    oversized = Request(b"x" * (MAX_UPLOAD + 1)); oversized.content_length = None
    assert (await upload.post(oversized, entry)).status == 400  # Chunked requests are bounded too.
    response = await upload.post(Request(png()), entry)
    assert response.status == 200
    key = json.loads(response.body)["asset_id"]
    token = library.data["decks"][entry]["token"]
    with pytest.raises(web.HTTPNotFound):
        await device.get(Request(), token, key)
    await save_asset(deck, key)
    public = await device.get(Request(), token, key)
    private = await preview.get(Request(), entry, key)
    assert public.body == private.body and public.headers["Cache-Control"] == "no-store"
    query = Request(); query.query_string = "token=abc"
    with pytest.raises(web.HTTPNotFound):
        await device.get(query, token, key)
    await library.remove_entry(entry)
    assert not await deck.hass.async_add_executor_job(library._directory(entry).exists)
    with pytest.raises(web.HTTPNotFound):
        await device.get(Request(), token, key)


@pytest.mark.asyncio
async def test_asset_hash_resolution_relabel_and_concurrent_edit(deck, library):
    await start(deck)
    entry = deck.entry.entry_id
    asset = await library.upload(entry, png())
    layout = await save_asset(deck, asset["asset_id"])
    await api.execute(deck.hass, "apply_layout", {"entry_id": entry, "expected_revision": 1})
    await wait_until(lambda: deck.writes[-1]["image_revision"] == asset["asset_id"])
    image_url = deck.writes[-1]["image_url"]
    layout["keys"][0]["visual"]["text"] = "Relabeled"
    await api.execute(deck.hass, "save_layout", {"entry_id": entry, "expected_revision": 1, "layout": layout})
    with pytest.raises(LayoutError, match="draft_conflict"):
        await api.execute(deck.hass, "save_layout", {"entry_id": entry, "expected_revision": 1, "layout": empty_layout()})
    await api.execute(deck.hass, "apply_layout", {"entry_id": entry, "expected_revision": 2})
    await wait_until(lambda: deck.writes[-1]["label_text"] == "Relabeled")
    assert deck.writes[-1]["image_url"] == image_url
    assert "asset_id" not in deck.writes[-1]
    assert len(library.data["decks"][entry]["variants"]) == 1
    assert not deck.controller.binding_count


def test_capabilities_redacted_from_access_and_argument_logs():
    token = "a" * 64
    record = logging.LogRecord("aiohttp.access", logging.INFO, "", 0,
        "GET %s", (f"http://ha/api/esp_deck/artwork/{token}/image.png",), None)
    assert CapabilityFilter().filter(record)
    assert token not in record.getMessage() and "[redacted]" in record.getMessage()
