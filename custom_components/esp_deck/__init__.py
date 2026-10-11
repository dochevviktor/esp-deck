"""HA-owned layouts and bindings for the Original Stream Deck runtime API."""

from homeassistant.const import Platform, __version__ as HA_VERSION
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import issue_registry as ir
from awesomeversion import AwesomeVersion

from .api import register
from .const import DOMAIN, MIN_HA_VERSION
from .controller import DeckController
from .model import LayoutError, empty_layout, entity_preset, validate_layout
from .storage import LayoutRepository
from .artwork import DATA_KEY


async def async_setup(hass, config):
    if AwesomeVersion(HA_VERSION) < AwesomeVersion(MIN_HA_VERSION):
        raise ConfigEntryError(f"ESP Deck requires Home Assistant {MIN_HA_VERSION} or newer")
    register(hass)
    from .panel import setup_panel
    await setup_panel(hass)
    return True


async def async_setup_entry(hass, entry):
    repository = LayoutRepository(hass, entry.entry_id)
    await hass.data[DATA_KEY].ensure(entry.entry_id)
    try:
        await repository.load()
    except (LayoutError, KeyError, TypeError, ValueError) as err:
        raise ConfigEntryError("Layout storage needs repair; restore an HA backup") from err
    if repository.data["draft_revision"] == 0 and entry.data.get("initial_entity"):
        from .adapter import pin_references
        layout = empty_layout()
        layout["keys"][0] = entity_preset(entry.data["initial_entity"], entry.data["initial_label"])
        await repository.save(pin_references(hass, validate_layout(layout)), 0)
        await repository.apply(1)
    entry.runtime_data = controller = DeckController(hass, entry, repository)
    await controller.start()
    try:
        await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR, Platform.SELECT])
    except Exception:
        await controller.stop()
        raise
    return True


async def async_unload_entry(hass, entry):
    if not await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR, Platform.SELECT]):
        return False
    await entry.runtime_data.stop()
    return True


async def async_remove_entry(hass, entry):
    await LayoutRepository(hass, entry.entry_id).store.async_remove()
    if library := hass.data.get(DATA_KEY):
        await library.remove_entry(entry.entry_id)
    ir.async_delete_issue(hass, DOMAIN, f"{entry.entry_id}_connection")
