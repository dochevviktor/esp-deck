"""Bundled admin panel and credential-safe artwork HTTP boundaries."""

import asyncio
import logging
from pathlib import Path
import re
import hmac
import struct
import zlib

from aiohttp import web
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.components.panel_custom import async_register_panel

from .api import controller
from .artwork import ArtworkLibrary, DATA_KEY, DEVICE_PATH, MAX_UPLOAD
from .const import DOMAIN
from .model import LayoutError


class CapabilityFilter(logging.Filter):
    def filter(self, record):
        text = record.getMessage()
        redacted = re.sub(r"(/api/esp_deck/(?:artwork|probe)/)[^/\s\"']+", r"\1[redacted]", text)
        if redacted != text:
            record.msg, record.args = redacted, ()
        return True


def admin(request):
    user = request.get("hass_user")
    if user is None or not user.is_admin:
        raise web.HTTPForbidden()


def failure(err):
    code = str(err) if isinstance(err, LayoutError) else "artwork_operation_failed"
    return web.json_response({"error": code}, status=429 if code == "artwork_busy" else 400)


class UploadView(HomeAssistantView):
    url = "/api/esp_deck/upload/{entry_id}"
    name = "api:esp_deck:upload"

    def __init__(self, hass):
        self.hass = hass

    async def post(self, request, entry_id):
        admin(request)
        try:
            deck = controller(self.hass, entry_id)
            library = self.hass.data[DATA_KEY]
            if request.content_type not in ("image/png", "image/jpeg"):
                raise LayoutError("unsupported_image_type")
            if request.content_length is not None and request.content_length > MAX_UPLOAD:
                raise LayoutError("upload_too_large")
            async with library.slot():
                payload = bytearray()
                async with asyncio.timeout(30):
                    async for chunk in request.content.iter_chunked(65536):
                        if len(payload) + len(chunk) > MAX_UPLOAD:
                            raise LayoutError("upload_too_large")
                        payload.extend(chunk)
                async with deck.configuration_lock:
                    if not deck.active:
                        raise LayoutError("entry_not_loaded")
                    result = await library.upload(entry_id, bytes(payload))
            return web.json_response(result)
        except (LayoutError, OSError, TimeoutError) as err:
            return failure(err)


class PreviewView(HomeAssistantView):
    url = "/api/esp_deck/preview/{entry_id}/{asset_id}"
    name = "api:esp_deck:preview"

    def __init__(self, hass):
        self.hass = hass

    async def get(self, request, entry_id, asset_id):
        admin(request)
        try:
            controller(self.hass, entry_id)
            png = await self.hass.data[DATA_KEY].read(entry_id, asset_id)
        except (LayoutError, OSError):
            raise web.HTTPNotFound() from None
        return web.Response(body=png, content_type="image/png", headers={"Cache-Control": "no-store"})


class DeviceArtworkView(HomeAssistantView):
    url = DEVICE_PATH + "{token}/{asset_id}.png"
    name = "api:esp_deck:artwork"
    requires_auth = False

    def __init__(self, hass):
        self.hass = hass

    async def get(self, request, token, asset_id):
        library = self.hass.data[DATA_KEY]
        repositories = {e.entry_id: e.runtime_data.repository
            for e in self.hass.config_entries.async_entries(DOMAIN)
            if getattr(e, "runtime_data", None) and e.runtime_data.active}
        try:
            if request.query_string:
                raise LayoutError("artwork_not_found")
            entry_id = library.authorize(token, asset_id, repositories)
            png = await library.read(entry_id, asset_id)
        except LayoutError as err:
            if str(err) == "artwork_rate_limited":
                raise web.HTTPTooManyRequests(headers={"Retry-After": "60"}) from None
            raise web.HTTPNotFound() from None
        except OSError:
            raise web.HTTPNotFound() from None
        return web.Response(body=png, content_type="image/png", headers={
            "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"})


class OriginProbeView(HomeAssistantView):
    url = "/api/esp_deck/probe/{token}"
    name = "api:esp_deck:probe"
    requires_auth = False

    def __init__(self, hass):
        self.hass = hass
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        self.png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 72, 72, 8, 6, 0, 0, 0))
                    + chunk(b"IDAT", zlib.compress(bytes(72 * (1 + 72 * 4)))) + chunk(b"IEND", b""))

    async def get(self, request, token):
        if request.query_string or not re.fullmatch(r"[a-f0-9]{64}", token) or not any(
                hmac.compare_digest(token, item["token"]) for item in self.hass.data[DATA_KEY].data["decks"].values()):
            raise web.HTTPNotFound()
        return web.Response(body=self.png, content_type="image/png", headers={"Cache-Control": "no-store"})


async def setup_panel(hass):
    library = hass.data[DATA_KEY] = ArtworkLibrary(hass)
    await library.load()
    redactor = CapabilityFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(redactor)
    for name in ("aiohttp.access", "aiohttp.server", "homeassistant.components.http.ban"):
        logging.getLogger(name).addFilter(redactor)
    for view in (UploadView, PreviewView, DeviceArtworkView, OriginProbeView):
        hass.http.register_view(view(hass))
    await hass.http.async_register_static_paths([StaticPathConfig("/esp_deck_static",
        str(Path(__file__).parent / "frontend"), cache_headers=False)])
    await async_register_panel(hass, frontend_url_path="esp-deck", webcomponent_name="esp-deck-panel",
        sidebar_title="ESP Deck", sidebar_icon="mdi:dialpad", module_url="/esp_deck_static/esp-deck.js?v=0.9.0",
        require_admin=True)
    # config_panel_domain replaces HA's options/repair control with a panel link.
    # Keep that control; the options menu links back to this editor instead.
