"""Page selection is an ordinary HA control, independent of the editor."""
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.exceptions import HomeAssistantError

from .const import SIGNAL_STATUS
from .model import LayoutError


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([DeckPage(entry)])


class DeckPage(SelectEntity):
    _attr_should_poll = False
    _attr_icon = "mdi:book-open-page-variant"

    def __init__(self, entry):
        self.controller = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_page"
        self._attr_name = f"{entry.title} page"

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass,
            SIGNAL_STATUS.format(self.controller.entry.entry_id), self.async_write_ha_state))

    @property
    def options(self):
        return [page["id"] for page in self.controller.repository.data["applied"].get("pages", [])]

    @property
    def current_option(self):
        return self.controller.page

    @property
    def available(self):
        return bool(self.options) and self.controller.connected and self.controller.capabilities.get("protocol_version") == 2

    async def async_select_option(self, option):
        try:
            self.controller.select_page(option)
        except LayoutError as err:
            raise HomeAssistantError(str(err)) from None
