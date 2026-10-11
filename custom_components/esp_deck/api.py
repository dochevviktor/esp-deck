"""Admin-authorized services and WebSocket configuration API for P6/P7."""

from copy import deepcopy

import probatio as vol

from homeassistant.components import websocket_api
from homeassistant.core import SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.service import async_register_admin_service

from .adapter import pin_references, resolve_reference
from .const import DOMAIN
from .model import LayoutError, bounded_json, entity_preset, mapping, references, validate_layout

OPERATIONS = {
    "get_layout": {}, "status": {}, "sync": {},
    "save_layout": {vol.Required("layout"): dict, vol.Required("expected_revision"): int},
    "apply_layout": {vol.Required("expected_revision"): int},
    "export_layout": {vol.Optional("which", default="draft"): vol.In(("draft", "applied", "backup"))},
    "import_layout": {vol.Required("document"): dict, vol.Required("expected_revision"): int},
    "preset": {vol.Required("entity_id"): str, vol.Required("label"): str},
}


def controller(hass, entry_id):
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or not (result := getattr(entry, "runtime_data", None)) or not result.active:
        raise LayoutError("entry_not_loaded")
    return result


async def execute(hass, operation, data):
    """Called only after the service/WS boundary has checked authorization."""
    deck = controller(hass, data["entry_id"])
    async with deck.configuration_lock:
        if not deck.active:
            raise LayoutError("entry_not_loaded")
        return await _execute_locked(hass, deck, operation, data)


async def _execute_locked(hass, deck, operation, data):
    repo = deck.repository
    if operation == "status":
        return deck.status()
    if operation == "get_layout":
        return deepcopy(repo.data)
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
        await repo.save(layout, data["expected_revision"])
    elif operation == "import_layout":
        bounded_json(data["document"])
        document = deepcopy(data["document"])
        # Validate the export envelope before consuming nested data.
        mapping(document, ("format", "version", "layout"), ("format", "version", "layout"))
        document["layout"] = pin_references(hass, validate_layout(document["layout"]))
        await repo.import_layout(document, data["expected_revision"])
    elif operation == "apply_layout":
        # Fail before activation if a saved entity has since been removed/disabled.
        pin_references(hass, deepcopy(repo.data["draft"]))
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
    except (LayoutError, HomeAssistantError, vol.Invalid) as err:
        code = str(err) if isinstance(err, LayoutError) else "operation_failed"
        connection.send_error(msg["id"], code, code)
    else:
        connection.send_result(msg["id"], result)


@callback
def register(hass):
    websocket_api.async_register_command(hass, websocket_command)
    for operation, fields in OPERATIONS.items():
        async def handle(call, operation=operation):
            try:
                return await execute(hass, operation, dict(call.data))
            except LayoutError as err:
                raise HomeAssistantError(str(err)) from err
        async_register_admin_service(hass, DOMAIN, operation, handle,
            schema=vol.Schema({vol.Required("entry_id"): str, **fields}), supports_response=SupportsResponse.ONLY)
