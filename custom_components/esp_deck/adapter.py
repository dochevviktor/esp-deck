"""Only module coupled to HA 2026.10.1 ESPHome discovery metadata.

Never reads credentials or calls/creates an APIClient. All I/O uses HA services.
Registry UUIDs survive HA entity renames; native service names are resolved anew.
"""

import asyncio
import base64
from dataclasses import dataclass
import re

from aioesphomeapi import EventInfo, TextSensorInfo, build_device_unique_id
from homeassistant.components.esphome.manager import build_service_name
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import KEY_COUNT, MAX_REVISION, SIGNATURES, V2_SIGNATURES, UPLOAD_SIGNATURES
from .model import LayoutError, references


class AdapterError(HomeAssistantError):
    """Bounded, credential-free compatibility/connectivity error."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass
class ResolvedDeck:
    session: str
    session_entity: str
    events: list[str]
    actions: dict[str, str]


def candidates(hass):
    registry = dr.async_get(hass)
    result = {}
    for device in registry.devices.values():
        entry = hass.config_entries.async_get_entry(device.config_entry_id)
        if entry and entry.domain == "esphome" and not device.disabled_by and not entry.disabled_by:
            result[device.id] = device.name_by_user or device.name or entry.title
    return result


def source(hass, device_id):
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise AdapterError("device_missing")
    entry = hass.config_entries.async_get_entry(device.config_entry_id)
    if device.disabled_by or entry is None or entry.disabled_by:
        raise AdapterError("device_disabled")
    if entry.domain != "esphome":
        raise AdapterError("incompatible_device")
    runtime = getattr(entry, "runtime_data", None)
    if runtime is None or not runtime.available or not runtime.device_info:
        raise AdapterError("offline")
    return device, entry, runtime


def registry_entity(hass, ref, *, device_id=None, domain=None):
    entity = er.async_get(hass).async_get(ref)
    if entity is None or (device_id and entity.device_id != device_id):
        raise AdapterError("entity_missing")
    if entity.disabled_by:
        raise AdapterError("entity_disabled")
    if domain and entity.domain != domain:
        raise AdapterError("incompatible_entity")
    return entity


def discover(hass, device_id, overrides=None):
    device, entry, runtime = source(hass, device_id)
    registry = er.async_get(hass)
    resolved = {}
    for info_type, domain in ((TextSensorInfo, "sensor"), (EventInfo, "event")):
        for info in runtime.info.get(info_type, {}).values():
            # v1 has conventional object IDs, not capabilities. Explicit repair
            # selectors handle changed firmware names without guessing key order.
            role = "session" if info_type is TextSensorInfo and info.object_id == "visual_session" else None
            if info_type is EventInfo and (match := re.fullmatch(r"key_(\d+)_edge", info.object_id)):
                if 0 <= (key := int(match[1])) < KEY_COUNT:
                    role = f"key_{key}"
            if role is None:
                continue
            entity_id = registry.async_get_entity_id(domain, "esphome",
                build_device_unique_id(runtime.device_info.mac_address, info))
            if entity_id and registry.async_get(entity_id).device_id == device_id:
                if role in resolved:
                    raise AdapterError("ambiguous_entities")
                resolved[role] = registry.async_get(entity_id).id
    if overrides:
        resolved.update(overrides)
    if set(resolved) != {"session", *(f"key_{key}" for key in range(KEY_COUNT))}:
        raise AdapterError("incompatible_firmware")
    data = {"device_id": device.id, "esphome_entry_id": entry.entry_id, "entities": resolved}
    Adapter(hass, data).resolve()
    return data


class Adapter:
    def __init__(self, hass, data):
        self.hass, self.data = hass, data

    def resolve(self):
        device, entry, runtime = source(self.hass, self.data["device_id"])
        if entry.entry_id != self.data["esphome_entry_id"]:
            raise AdapterError("device_changed")
        actions = {}
        signatures = dict(SIGNATURES)
        if any(service.name in V2_SIGNATURES for service in runtime.services.values()):
            signatures.update(V2_SIGNATURES)
        if any(service.name in UPLOAD_SIGNATURES for service in runtime.services.values()):
            signatures.update(UPLOAD_SIGNATURES)
        for name, signature in signatures.items():
            matches = [service for service in runtime.services.values() if service.name == name]
            if len(matches) != 1:
                raise AdapterError("incompatible_firmware")
            service = matches[0]
            if (len(service.args) != len(signature)
                    or {arg.name: getattr(arg.type, "name", None) for arg in service.args} != signature
                    or getattr(service.supports_response, "name", None) != "ONLY"):
                raise AdapterError("incompatible_firmware")
            action = build_service_name(runtime.device_info, service)
            if not self.hass.services.has_service("esphome", action):
                raise AdapterError("actions_unavailable")
            if self.hass.services.supports_response("esphome", action) != SupportsResponse.ONLY:
                raise AdapterError("incompatible_firmware")
            actions[name] = action
        refs = self.data["entities"]
        session_entity = registry_entity(self.hass, refs["session"], device_id=device.id, domain="sensor")
        events = []
        for key in range(KEY_COUNT):
            entity = registry_entity(self.hass, refs[f"key_{key}"], device_id=device.id, domain="event")
            state = self.hass.states.get(entity.entity_id)
            if state is None or set(state.attributes.get("event_types", [])) != {"press", "release"}:
                raise AdapterError("incompatible_entity")
            events.append(entity.entity_id)
        if len(set(events)) != KEY_COUNT:
            raise AdapterError("ambiguous_entities")
        state = self.hass.states.get(session_entity.entity_id)
        if state is None or not re.fullmatch(r"[0-9a-fA-F]{16}", state.state):
            raise AdapterError("offline")
        return ResolvedDeck(state.state, session_entity.entity_id, events, actions)

    async def call(self, deck, operation, key, **values):
        return check_response(await self.raw_call(deck, operation, session=deck.session, key=key, **values), deck.session, key)

    async def raw_call(self, deck, operation, **values):
        # Recheck connectivity/names before every outbound request; no second client.
        current = self.resolve()
        if current.session != deck.session or current.actions != deck.actions:
            raise AdapterError("session_changed")
        try:
            async with asyncio.timeout(10):
                result = await self.hass.services.async_call("esphome", deck.actions[operation],
                    values, blocking=True, return_response=True)
        except (HomeAssistantError, TimeoutError) as err:
            raise AdapterError("native_action_failed") from err
        if not isinstance(result, dict):
            raise AdapterError("invalid_native_response")
        return result

    async def capabilities(self, deck):
        if "get_deck_capabilities" not in deck.actions:
            return {"protocol_version": 1, "positioning": False, "origin_provisioning": False}
        result = await self.raw_call(deck, "get_deck_capabilities")
        if (result.get("session") != deck.session or result.get("protocol_version") != 2
                or result.get("model") != "0FD9:0060" or result.get("keys") != 15
                or result.get("width") != 72 or result.get("height") != 72
                or result.get("fonts") != [12, 16, 20] or result.get("visual_fields") != 255
                or result.get("input_correlation") != "pull_context_v2"
                or result.get("input_lease_ms") != 1000
                or type(result.get("positioning")) is not bool or type(result.get("origin_provisioning")) is not bool
                or not isinstance(result.get("origins"), (list, type(None)))
                or len(result.get("origins") or []) > 4):
            raise AdapterError("incompatible_capabilities")
        from .artwork import origin
        try:
            for address in result.get("origins") or []:
                origin(address, max_bytes=272)
        except (LayoutError, TypeError):
            raise AdapterError("incompatible_capabilities") from None
        if "artwork_upload" in result:
            if (result["artwork_upload"] != "png_chunks_v1" or "upload_deck_artwork" not in deck.actions
                    or type(result.get("upload_max_bytes")) is not int or result["upload_max_bytes"] != 32768
                    or type(result.get("upload_chunk_bytes")) is not int or result["upload_chunk_bytes"] != 1024):
                raise AdapterError("incompatible_capabilities")
        return result

    async def upload_artwork(self, deck, asset_id, payload, current=lambda: True):
        """Probe/resume one bounded immutable file, awaiting each chunk's ack."""
        from .artwork import identifier, MAX_PNG
        identifier(asset_id)
        if not 0 < len(payload) <= MAX_PNG:
            raise AdapterError("upload_size")
        offset, data = 0, ""
        while current():
            result = await self.raw_call(deck, "upload_deck_artwork", session=deck.session,
                asset_id=asset_id, offset=offset, total_size=len(payload), data=data)
            if not current():
                return False
            if (result.get("session") != deck.session or type(result.get("accepted")) is not bool
                    or not isinstance(result.get("error"), str)
                    or not re.fullmatch(r"[a-z_]{1,48}", result["error"])):
                raise AdapterError("invalid_native_response")
            if not result["accepted"]:
                raise AdapterError(result["error"])
            received = result.get("received")
            if (type(received) is not int or not 0 <= received <= len(payload)
                    or type(result.get("complete")) is not bool or result["error"] != "none"
                    or result["complete"] != (received == len(payload))
                    or (data and received != offset + len(base64.b64decode(data)))):
                raise AdapterError("invalid_native_response")
            if result["complete"]:
                return True
            offset = received
            data = base64.b64encode(payload[offset:offset + 1024]).decode("ascii")
        return False

    async def probe(self):
        deck = self.resolve()
        await self.capabilities(deck)
        response = await self.call(deck, "get_key_visual_status", 0)
        if not response["accepted"]:
            raise AdapterError("incompatible_firmware")


def check_response(value, session, key):
    if (not isinstance(value, dict) or value.get("session") != session
            or type(value.get("key")) is not int or value["key"] != key
            or type(value.get("accepted")) is not bool
            or any(type(value.get(field)) is not int or not 0 <= value[field] <= MAX_REVISION
                   for field in ("revision", "rendered_revision", "request_revision"))
            or value.get("phase") not in ("idle", "queued", "rendering", "rendered", "failed")
            or not isinstance(value.get("error"), str)
            or not re.fullmatch(r"[a-z_]{1,48}", value["error"])):
        raise AdapterError("invalid_native_response")
    result = {field: value[field] for field in ("accepted", "revision", "rendered_revision", "phase", "error")}
    if "applied_revision" in value:
        if (type(value["applied_revision"]) is not int or not 0 <= value["applied_revision"] <= MAX_REVISION
                or type(value.get("usb_generation")) is not int or not 0 <= value["usb_generation"] <= 0xffffffff
                or not isinstance(value.get("context"), str) or not re.fullmatch(r"[a-zA-Z0-9]{0,32}", value["context"])):
            raise AdapterError("invalid_native_response")
        result.update({field: value[field] for field in ("applied_revision", "usb_generation", "context")})
    return result


def pin_references(hass, layout):
    for ref in references(layout):
        entity = er.async_get(hass).async_get(ref.get("registry_id", ref["entity_id"]))
        if "registry_id" in ref and entity is None:
            raise LayoutError("entity_missing")
        if entity:
            if entity.disabled_by:
                raise LayoutError("entity_disabled")
            ref.update(entity_id=entity.entity_id, registry_id=entity.id)
        elif hass.states.get(ref["entity_id"]) is None:
            raise LayoutError("entity_missing")
    return layout


def resolve_reference(hass, ref):
    if "registry_id" in ref:
        entity = registry_entity(hass, ref["registry_id"])
        return entity.entity_id
    return ref["entity_id"]
