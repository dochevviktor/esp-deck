"""P9 setup compatibility, repairs and removal in the real HA engine."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import issue_registry as ir

from custom_components import esp_deck
from custom_components.esp_deck.artwork import ArtworkLibrary, DATA_KEY
from custom_components.esp_deck.config_flow import ESPDeckConfigFlow
from custom_components.esp_deck.repairs import ConnectionRepair
from test_backend import engine, deck


@pytest.mark.asyncio
async def test_reject_bench_firmware_with_concrete_upgrade_instructions(deck):
    deck.source.runtime_data.info = {}
    deck.source.runtime_data.services = {}
    flow = ESPDeckConfigFlow()
    flow.hass = deck.hass
    flow.context = {"source": "user"}
    result = await flow.async_step_user({"device_id": deck.device.id})
    assert result["type"] == "form" and result["errors"] == {"base": "incompatible_firmware"}
    strings = json.loads((Path(esp_deck.__file__).parent / "translations/en.json").read_text())
    error = strings["config"]["error"]["incompatible_firmware"]
    assert "05_home_assistant_runtime.yaml" in error and "OTA" in error and "reload" in error
    assert not deck.writes


@pytest.mark.asyncio
async def test_below_minimum_ha_fails_before_registering_panel_or_services(engine):
    with patch.object(esp_deck, "HA_VERSION", "2026.9.4"):
        with pytest.raises(ConfigEntryError, match="2026.10.1"):
            await esp_deck.async_setup(engine, {})
    assert DATA_KEY not in engine.data
    assert not engine.services.has_service("esp_deck", "save_layout")


@pytest.mark.asyncio
async def test_repair_flow_shows_bounded_connection_error(deck):
    ir.async_create_issue(deck.hass, "esp_deck", f"{deck.entry.entry_id}_connection",
        is_fixable=True, severity=ir.IssueSeverity.ERROR, translation_key="connection",
        translation_placeholders={"error": "incompatible_firmware"}, data={"entry_id": deck.entry.entry_id})
    flow = ConnectionRepair(deck.entry.entry_id)
    flow.hass = deck.hass
    form = await flow.async_step_init()
    assert form["description_placeholders"] == {"error": "incompatible_firmware"}


@pytest.mark.asyncio
async def test_removing_disabled_entry_after_restart_also_removes_artwork(deck):
    library = ArtworkLibrary(deck.hass)
    await library.load()
    await library.ensure(deck.entry.entry_id)
    # A disabled entry can be deleted before async_setup ran after an HA reboot.
    assert DATA_KEY not in deck.hass.data
    await deck.repo.save(deck.repo.data["draft"], 0)
    await esp_deck.async_remove_entry(deck.hass, deck.entry)
    reopened = ArtworkLibrary(deck.hass)
    await reopened.load()
    assert deck.entry.entry_id not in reopened.data["decks"]
    assert not Path(deck.repo.store.path).exists()
    assert deck.hass.config_entries.async_get_entry(deck.source.entry_id) is deck.source
