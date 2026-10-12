"""Direct artwork delivery in the pinned HA engine; native actions are mocked."""
import base64
from copy import deepcopy
import hashlib
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aioesphomeapi import UserService, UserServiceArg, UserServiceArgType, SupportsResponseType
from homeassistant.core import SupportsResponse
import pytest

from custom_components.esp_deck import adapter
from custom_components.esp_deck.const import V2_SIGNATURES, UPLOAD_SIGNATURES
from custom_components.esp_deck.model import empty_layout, validate_layout, LayoutError
from test_backend import deck, engine  # noqa: F401
from test_artwork import library, png  # noqa: F401


def enable_upload(deck):
    caps = {"session": "1234567890123456", "protocol_version": 2, "model": "0FD9:0060", "keys": 15,
            "width": 72, "height": 72, "fonts": [12, 16, 20], "visual_fields": 255,
            "input_correlation": "pull_context_v2", "input_lease_ms": 1000,
            "positioning": True, "origin_provisioning": True, "origins": [],
            "artwork_upload": "png_chunks_v1", "upload_max_bytes": 32768, "upload_chunk_bytes": 1024}
    calls, received = [], {}

    async def native(call):
        values = dict(call.data)
        if call.service.endswith("get_deck_capabilities"):
            return deepcopy(caps)
        if call.service.endswith("upload_deck_artwork"):
            calls.append(values)
            buf = received.setdefault(values["asset_id"], bytearray())
            if values["data"]:
                assert values["offset"] == len(buf)
                chunk = base64.b64decode(values["data"], validate=True)
                assert len(chunk) <= 1024
                buf.extend(chunk)
            complete = len(buf) == values["total_size"]
            if complete:
                assert hashlib.sha256(buf).hexdigest() == values["asset_id"]
            return {"session": caps["session"], "accepted": True, "error": "none",
                    "received": len(buf), "complete": complete}
        if call.service.endswith("set_key_visual_v2"):
            deck.writes.append(values)
            response = deck.responses[values["key"]]
            response.update(revision=values["revision"], rendered_revision=values["revision"],
                request_revision=values["revision"], phase="rendered", applied_revision=values["revision"],
                usb_generation=1, context=values["binding_context"])
            return dict(response)
        raise AssertionError(call.service)

    for name, signature in {**V2_SIGNATURES, **UPLOAD_SIGNATURES}.items():
        key = len(deck.source.runtime_data.services)
        service = UserService(name=name, key=key, supports_response=SupportsResponseType.ONLY,
            args=[UserServiceArg(name=arg, type=UserServiceArgType[kind]) for arg, kind in signature.items()])
        deck.source.runtime_data.services[key] = service
        deck.hass.services.async_register("esphome", "lab_deck_" + name, native, supports_response=SupportsResponse.ONLY)
    return SimpleNamespace(caps=caps, calls=calls, received=received)


@pytest.mark.asyncio
async def test_direct_artwork_needs_no_origin_and_labels_never_upload(deck, library):
    native = enable_upload(deck)
    entry = deck.entry.entry_id
    library.data["decks"][entry]["origin"] = ""
    asset = await library.upload(entry, png())
    layout = empty_layout()
    layout["keys"][0]["visual"].update(asset_id=asset["asset_id"], text="Desk")
    controller = deck.controller
    controller.repository.data["applied"] = validate_layout(layout)
    controller.active = True
    await controller._synchronize(False)
    assert native.calls and deck.writes[0]["image_url"] == "asset://" + asset["asset_id"]
    assert bytes(native.received[asset["asset_id"]]) == await library.read(entry, asset["asset_id"])
    count = len(native.calls)
    controller.repository.data["applied"]["keys"][0]["visual"].update(text="New", text_align=0)
    await controller._synchronize(False)
    assert len(native.calls) == count and deck.writes[-1]["label_text"] == "New"
    # HA reconnect probes the ESP cache instead of assuming the file was lost.
    controller.connected = False
    await controller._synchronize(False)
    assert len(native.calls) == count + 1 and native.calls[-1]["data"] == ""
    # Reboot clears the device cache; replay sends bytes again.
    native.received.clear(); controller.connected = False
    await controller._synchronize(False)
    assert len(native.calls) > count + 2
    assert "asset_id" in controller.repository.data["applied"]["keys"][0]["visual"]
    assert not controller.repository.data["applied"]["keys"][0]["visual"]["image_url"]


@pytest.mark.asyncio
async def test_chunk_resume_ack_validation_and_obsolete_work(deck):
    native = enable_upload(deck)
    client = deck.controller.adapter
    resolved = client.resolve()
    payload = random.Random(42).randbytes(6500)
    asset_id = hashlib.sha256(payload).hexdigest()
    native.received[asset_id] = bytearray(payload[:1024])
    assert await client.upload_artwork(resolved, asset_id, payload)
    assert native.calls[1]["offset"] == 1024 and native.received[asset_id] == payload
    assert max(len(c["data"]) for c in native.calls) <= 1368
    for bad in ({"received": True}, {"received": -1}, {"received": 6501}, {"complete": True},
                {"session": "old"}, {"accepted": 1}, {"error": "raw unsafe details"}):
        response = {"session": resolved.session, "accepted": True, "error": "none", "received": 0, "complete": False, **bad}
        with patch.object(client, "raw_call", AsyncMock(return_value=response)), pytest.raises(adapter.AdapterError):
            await client.upload_artwork(resolved, asset_id, payload)
    with patch.object(client, "raw_call", AsyncMock(return_value={"session": resolved.session,
            "accepted": False, "error": "upload_hash_mismatch"})), pytest.raises(adapter.AdapterError, match="hash_mismatch"):
        await client.upload_artwork(resolved, asset_id, payload)
    current = True
    async def obsolete(*args, **kwargs):
        nonlocal current
        current = False
        return {"session": resolved.session, "accepted": True, "error": "none", "received": 0, "complete": False}
    with patch.object(client, "raw_call", AsyncMock(side_effect=obsolete)) as call:
        assert not await client.upload_artwork(resolved, asset_id, payload, current=lambda: current)
        assert call.await_count == 1


@pytest.mark.asyncio
async def test_capability_negotiation_preserves_old_firmware_and_rejects_false_claims(deck, library):
    client = deck.controller.adapter
    assert (await client.capabilities(client.resolve()))["protocol_version"] == 1
    native = enable_upload(deck)
    resolved = client.resolve()
    assert (await client.capabilities(resolved))["artwork_upload"] == "png_chunks_v1"
    for field, value in (("upload_chunk_bytes", True), ("upload_chunk_bytes", 32768),
                         ("upload_max_bytes", 0), ("artwork_upload", "unknown")):
        original = native.caps[field]; native.caps[field] = value
        with pytest.raises(adapter.AdapterError, match="incompatible_capabilities"):
            await client.capabilities(resolved)
        native.caps[field] = original
    key = next(key for key, service in deck.source.runtime_data.services.items() if service.name == "upload_deck_artwork")
    del deck.source.runtime_data.services[key]
    with pytest.raises(adapter.AdapterError, match="incompatible_capabilities"):
        await client.capabilities(client.resolve())
    for field in ("artwork_upload", "upload_max_bytes", "upload_chunk_bytes"):
        native.caps.pop(field)
    assert "artwork_upload" not in await client.capabilities(client.resolve())
    asset = await library.upload(deck.entry.entry_id, png())
    visual = {"asset_id": asset["asset_id"]}
    assert library.resolve(deck.entry.entry_id, visual)["image_url"].startswith("http://ha:8123/")
    library.data["decks"][deck.entry.entry_id]["origin"] = ""
    with pytest.raises(LayoutError, match="artwork_origin_required"):
        library.resolve(deck.entry.entry_id, visual)
    assert library.resolve(deck.entry.entry_id, visual, direct=True)["image_url"].startswith("asset://")


@pytest.mark.asyncio
async def test_layout_change_during_upload_never_applies_obsolete_visual(deck, library):
    enable_upload(deck)
    asset = await library.upload(deck.entry.entry_id, png())
    layout = empty_layout(); layout["keys"][0]["visual"]["asset_id"] = asset["asset_id"]
    controller = deck.controller
    controller.repository.data["applied"] = validate_layout(layout); controller.active = True
    real_call = controller.adapter.raw_call
    async def change(*args, **kwargs):
        result = await real_call(*args, **kwargs)
        if args[1] == "upload_deck_artwork":
            controller.epoch += 1
        return result
    with patch.object(controller.adapter, "raw_call", side_effect=change):
        await controller._synchronize(False)
    assert not deck.writes
