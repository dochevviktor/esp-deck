"""Select an existing deck, verify v1, and explicitly hand off manual writers."""

from copy import deepcopy

import probatio as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er, selector

from .adapter import Adapter, AdapterError, candidates, discover, pin_references
from .api import execute
from .const import DOMAIN, KEY_COUNT, P4_AUTOMATION_IDS, P4_SCRIPTS
from .model import LayoutError, empty_layout, entity_preset, resolve_keys
from .artwork import DATA_KEY


def known_manual_automations(hass):
    return [state.entity_id for state in hass.states.async_all("automation")
            if state.attributes.get("id") in P4_AUTOMATION_IDS]


def select_schema(hass):
    return vol.Schema({vol.Required("device_id"): selector.SelectSelector({
        "options": [{"value": key, "label": name} for key, name in candidates(hass).items()], "mode": "dropdown"})})


class ESPDeckConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input:
            device_id = user_input["device_id"]
            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured()
            try:
                self.selection = discover(self.hass, device_id)
                await Adapter(self.hass, self.selection).probe()
            except AdapterError as err:
                errors["base"] = err.code
            else:
                return await self.async_step_handoff()
        if not candidates(self.hass):
            return self.async_abort(reason="no_devices")
        return self.async_show_form(step_id="user", data_schema=select_schema(self.hass), errors=errors)

    async def async_step_handoff(self, user_input=None):
        errors = {}
        if user_input:
            if user_input.get("exclusive_control") is not True:
                errors["base"] = "confirm_handoff"
            else:
                try:
                    await Adapter(self.hass, self.selection).probe()
                    entity = user_input.get("preset_entity")
                    if entity:
                        layout = empty_layout()
                        layout["keys"][0] = entity_preset(entity, user_input.get("label", "Deck"))
                        pin_references(self.hass, layout)
                    automations = user_input.get("disable_automations", [])
                    if any(not value.startswith("automation.") or self.hass.states.get(value) is None for value in automations):
                        raise LayoutError("invalid_automation")
                    # Only the automation IDs explicitly selected in this form.
                    if automations:
                        await self.hass.services.async_call("automation", "turn_off",
                            {"entity_id": automations, "stop_actions": True}, blocking=True)
                    scripts = [name for name in P4_SCRIPTS if self.hass.states.get(name)]
                    if scripts:
                        await self.hass.services.async_call("script", "turn_off", {"entity_id": scripts}, blocking=True)
                except (AdapterError, LayoutError, HomeAssistantError) as err:
                    errors["base"] = err.code if isinstance(err, AdapterError) else "handoff_failed"
                else:
                    data = {**self.selection, "exclusive_control": True}
                    if entity:
                        data.update(initial_entity=layout["keys"][0]["state"]["entity"]
                                    if layout["keys"][0]["state"] else layout["keys"][0]["press"]["target"]["entity_id"][0],
                                    initial_label=user_input.get("label", "Deck"))
                    return self.async_create_entry(title=candidates(self.hass).get(data["device_id"], "ESP Deck"), data=data)
        return self.async_show_form(step_id="handoff", errors=errors, data_schema=vol.Schema({
            vol.Required("exclusive_control", default=False): selector.BooleanSelector(),
            vol.Optional("disable_automations", default=known_manual_automations(self.hass)):
                selector.EntitySelector({"domain": "automation", "multiple": True}),
            vol.Optional("preset_entity"): selector.EntitySelector({"domain": ["light", "switch", "input_boolean", "script", "scene"]}),
            vol.Optional("label", default="Deck"): selector.TextSelector(),
        }))

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input:
            device_id = user_input["device_id"]
            if any(item.unique_id == device_id and item.entry_id != entry.entry_id
                   for item in self._async_current_entries()):
                return self.async_abort(reason="already_configured")
            try:
                data = discover(self.hass, device_id)
                await Adapter(self.hass, data).probe()
            except AdapterError as err:
                errors["base"] = err.code
            else:
                self.hass.config_entries.async_update_entry(entry, unique_id=device_id)
                return self.async_update_reload_and_abort(entry, data_updates={**data, "exclusive_control": True})
        return self.async_show_form(step_id="reconfigure", data_schema=select_schema(self.hass), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ESPDeckOptionsFlow()


class ESPDeckOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        return self.async_show_menu(step_id="init", menu_options=["binding", "artwork", "repair"])

    async def async_step_artwork(self, user_input=None):
        errors = {}
        if user_input:
            try:
                await execute(self.hass, "artwork_configure", {"entry_id": self.config_entry.entry_id, **user_input})
            except (LayoutError, HomeAssistantError, TimeoutError):
                errors["base"] = "artwork_failed"
            else:
                return self.async_create_entry(data=dict(self.config_entry.options))
        origin = self.hass.data[DATA_KEY].data["decks"][self.config_entry.entry_id]["origin"]
        return self.async_show_form(step_id="artwork", errors=errors, data_schema=vol.Schema({
            vol.Required("origin", default=origin): selector.TextSelector(),
        }))

    async def async_step_binding(self, user_input=None):
        errors = {}
        if user_input:
            try:
                entry = self.config_entry
                controller = entry.runtime_data
                revision = controller.repository.data["draft_revision"]
                layout = deepcopy(controller.repository.data["draft"])
                key = int(user_input["key"])
                resolve_keys(layout, user_input.get("page"))[key] = entity_preset(user_input["entity_id"], user_input["label"])
                await execute(self.hass, "save_layout", {"entry_id": entry.entry_id, "layout": layout,
                                                       "expected_revision": revision})
                if user_input.get("apply"):
                    await execute(self.hass, "apply_layout", {"entry_id": entry.entry_id, "expected_revision": revision + 1})
            except (LayoutError, HomeAssistantError, AttributeError):
                errors["base"] = "binding_failed"
            else:
                return self.async_create_entry(data=dict(self.config_entry.options))
        fields = {
            vol.Required("key", default="0"): selector.SelectSelector({"options": [str(i) for i in range(KEY_COUNT)]}),
            vol.Required("entity_id"): selector.EntitySelector({"domain": ["light", "switch", "input_boolean", "script", "scene"]}),
            vol.Required("label", default="Deck"): selector.TextSelector(),
            vol.Required("apply", default=True): selector.BooleanSelector(),
        }
        if pages := self.config_entry.runtime_data.repository.data["draft"].get("pages"):
            fields[vol.Required("page", default=pages[0]["id"])] = selector.SelectSelector({
                "options": [{"value": page["id"], "label": page["name"]} for page in pages]})
        return self.async_show_form(step_id="binding", errors=errors, data_schema=vol.Schema(fields))

    async def async_step_repair(self, user_input=None):
        entry = self.config_entry
        errors = {}
        if user_input:
            try:
                registry = er.async_get(self.hass)
                overrides = {role: registry.async_get(entity).id for role, entity in user_input.items()}
                data = discover(self.hass, entry.data["device_id"], overrides)
                await Adapter(self.hass, data).probe()
            except (AdapterError, AttributeError) as err:
                errors["base"] = err.code if isinstance(err, AdapterError) else "entity_missing"
            else:
                self.hass.config_entries.async_update_entry(entry, data={**entry.data, **data})
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_create_entry(data=dict(entry.options))
        fields = {}
        for role in ("session", *(f"key_{key}" for key in range(KEY_COUNT))):
            entity = er.async_get(self.hass).async_get(entry.data["entities"][role])
            marker = vol.Required(role, default=entity.entity_id) if entity else vol.Required(role)
            fields[marker] = selector.EntitySelector({"domain": "sensor" if role == "session" else "event",
                                                       "integration": "esphome"})
        return self.async_show_form(step_id="repair", data_schema=vol.Schema(fields), errors=errors)
