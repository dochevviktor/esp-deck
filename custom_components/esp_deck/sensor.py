"""A helper status entity; never claims ownership of the ESPHome device."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import SIGNAL_STATUS


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([DeckStatus(entry)])


class DeckStatus(SensorEntity):
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:keyboard"

    def __init__(self, entry):
        self.controller = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_synchronization"
        self._attr_name = f"{entry.title} synchronization"

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass,
            SIGNAL_STATUS.format(self.controller.entry.entry_id), self.async_write_ha_state))

    @property
    def native_value(self):
        return self.controller.status()["state"]

    @property
    def extra_state_attributes(self):
        return {key: value for key, value in self.controller.status().items() if key not in ("state", "tiles")}
