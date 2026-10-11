"""Retry after enabling/replacing entities, or use the explicit options mapping."""

import probatio as vol
from homeassistant.components.repairs import RepairsFlow
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

from .adapter import Adapter, AdapterError


class ConnectionRepair(RepairsFlow):
    def __init__(self, entry_id):
        super().__init__()
        self.entry_id = entry_id

    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            entry = self.hass.config_entries.async_get_entry(self.entry_id)
            if entry is None:
                return self.async_abort(reason="entry_removed")
            try:
                await Adapter(self.hass, entry.data).probe()
            except AdapterError:
                errors["base"] = "not_repaired"
            else:
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_create_entry(data={})
        issue = ir.async_get(self.hass).async_get_issue(DOMAIN, f"{self.entry_id}_connection")
        return self.async_show_form(step_id="init", data_schema=vol.Schema({}), errors=errors,
            description_placeholders={"error": (issue.translation_placeholders or {}).get("error", "offline")
                                      if issue else "offline"})


async def async_create_fix_flow(hass, issue_id, data):
    return ConnectionRepair(data["entry_id"])
