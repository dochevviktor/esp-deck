"""Admin-authorized services and WebSocket configuration API for P6/P7."""

from copy import deepcopy
from contextlib import nullcontext

import probatio as vol

from homeassistant.components import websocket_api
from homeassistant.core import SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.service import async_register_admin_service

from .adapter import pin_references, resolve_reference
from .const import DOMAIN
from .artwork import DATA_KEY
from .model import LayoutError, bounded_json, entity_preset, mapping, references, validate_layout

OPERATIONS = {
    "get_layout": {}, "status": {}, "sync": {},
    "save_layout": {vol.Required("layout"): dict, vol.Required("expected_revision"): int},
    "apply_layout": {vol.Required("expected_revision"): int},
    "export_layout": {vol.Optional("which", default="draft"): vol.In(("draft", "applied", "backup"))},
    "import_layout": {vol.Required("document"): dict, vol.Required("expected_revision"): int},
    "preset": {vol.Required("entity_id"): str, vol.Required("label"): str},
    "artwork_list": {},
    "artwork_variant": {vol.Required("source_id"): str, vol.Required("transform"): dict},
    "artwork_configure": {vol.Required("origin"): str},
    "artwork_revoke": {},
    "artwork_collect": {},
    "artwork_delete": {vol.Required("asset_id"): str},
}


def controller(hass, entry_id):
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or not (result := getattr(entry, "runtime_data", None)) or not result.active:
        raise LayoutError("entry_not_loaded")
    return result


async def execute(hass, operation, data):
    """Called only after the service/WS boundary has checked authorization."""
    deck = controller(hass, data["entry_id"])
    library = hass.data.get(DATA_KEY)
    # Reserve before waiting on the deck lock; queued conversions are bounded too.
    slot = library.slot() if operation == "artwork_variant" and library else nullcontext()
    async with slot:
        async with deck.configuration_lock:
            if not deck.active:
                raise LayoutError("entry_not_loaded")
            return await _execute_locked(hass, deck, operation, data)


async def _execute_locked(hass, deck, operation, data):
    repo = deck.repository
    library = hass.data.get(DATA_KEY)
    entry_id = deck.entry.entry_id
    if operation.startswith("artwork_"):
        if library is None:
            raise LayoutError("artwork_unavailable")
        if operation == "artwork_list":
            return library.listing(entry_id, repo)
        if operation == "artwork_variant":
            return await library.variant(entry_id, data["source_id"], data["transform"])
        if operation in ("artwork_delete", "artwork_collect"):
            return await library.collect(entry_id, repo, asset_id=data.get("asset_id"))
        await library.configure(entry_id, data.get("origin"), revoke=operation == "artwork_revoke")
        deck.request_sync(retry=True)
        return library.listing(entry_id, repo)
    if operation == "status":
        return deck.status()
    if operation == "get_layout":
        result = deepcopy(repo.data)
        # Show current registry names while retaining stable IDs and repairable
        # missing references. Reading the editor does not rewrite storage.
        from .adapter import AdapterError
        for name in ("draft", "applied", "backup"):
            if result[name]:
                for ref in references(result[name]):
                    try:
                        ref["entity_id"] = resolve_reference(hass, ref)
                    except AdapterError:
                        pass
        return result
    if operation == "preset":
        layout = {"version": 1, "keys": [entity_preset(data["entity_id"], data["label"])] + [{}] * 14}
        return {"key": pin_references(hass, validate_layout(layout))["keys"][0]}
    if operation == "export_layout":
        document = repo.export(data.get("which", "draft"))
        for ref in references(document["layout"]):
            # Export portable current entity names, not installation-specific UUIDs.
            # Missing IDs require repair; never silently bind a reused old name.
            ref["entity_id"] = resolve_reference(hass, ref)
            ref.pop("registry_id", None)
        return document
    if operation == "save_layout":
        layout = pin_references(hass, validate_layout(data["layout"]))
        if library:
            library.validate(entry_id, layout)
            library.retain(entry_id, repo)
        await repo.save(layout, data["expected_revision"])
    elif operation == "import_layout":
        bounded_json(data["document"])
        document = deepcopy(data["document"])
        # Validate the export envelope before consuming nested data.
        mapping(document, ("format", "version", "layout"), ("format", "version", "layout"))
        document["layout"] = pin_references(hass, validate_layout(document["layout"]))
        if library:
            library.validate(entry_id, document["layout"])
            library.retain(entry_id, repo)
        await repo.import_layout(document, data["expected_revision"])
    elif operation == "apply_layout":
        # Fail before activation if a saved entity has since been removed/disabled.
        pin_references(hass, deepcopy(repo.data["draft"]))
        if library:
            library.validate(entry_id, repo.data["draft"])
            library.retain(entry_id, repo)
        if await repo.apply(data["expected_revision"]):
            deck.layout_changed()
    elif operation == "sync":
        deck.request_sync(retry=True)
    else:
        raise LayoutError("unknown_operation")
    deck._publish()
    return deck.status()


@websocket_api.websocket_command({
    vol.Required("type"): "esp_deck/command",
    vol.Required("operation"): vol.In(OPERATIONS),
    vol.Required("entry_id"): str,
    vol.Optional("parameters", default={}): dict,
})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_command(hass, connection, msg):
    try:
        operation = msg["operation"]
        parameters = vol.Schema(OPERATIONS[operation])(msg["parameters"])
        result = await execute(hass, operation, {**parameters, "entry_id": msg["entry_id"]})
    except (LayoutError, HomeAssistantError, vol.Invalid, OSError) as err:
        code = str(err) if isinstance(err, LayoutError) else "operation_failed"
        connection.send_error(msg["id"], code, code)
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): "esp_deck/entries"})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_entries(hass, connection, msg):
    connection.send_result(msg["id"], [{"entry_id": e.entry_id, "title": e.title,
        "loaded": bool(getattr(e, "runtime_data", None) and e.runtime_data.active)}
        for e in hass.config_entries.async_entries(DOMAIN)])


@callback
def register(hass):
    websocket_api.async_register_command(hass, websocket_command)
    websocket_api.async_register_command(hass, websocket_entries)
    for operation, fields in OPERATIONS.items():
        async def handle(call, operation=operation):
            try:
                return await execute(hass, operation, dict(call.data))
            except (LayoutError, OSError) as err:
                raise HomeAssistantError(str(err) if isinstance(err, LayoutError) else "storage_operation_failed") from None
        async_register_admin_service(hass, DOMAIN, operation, handle,
            schema=vol.Schema({vol.Required("entry_id"): str, **fields}), supports_response=SupportsResponse.ONLY)
