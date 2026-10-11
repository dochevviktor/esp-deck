"""Real HA script engine with a mocked native-action transport (no container API)."""
from pathlib import Path
import asyncio

import pytest
import pytest_asyncio
import yaml

from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant import bootstrap, config_entries, loader
from homeassistant.setup import async_setup_component


@pytest_asyncio.fixture
async def hass(tmp_path):
    instance = HomeAssistant(str(tmp_path))
    loader.async_setup(instance)
    instance.config_entries = config_entries.ConfigEntries(instance, {})
    instance.config.time_zone = "UTC"
    assert await bootstrap.async_load_base_functionality(instance)
    await instance.async_start()
    yield instance
    await instance.async_stop()


@pytest.mark.asyncio
async def test_p4_scripts_in_real_ha(hass):
    scripts = {}
    source = Path(__file__).parents[1] / "examples"
    for name in ("runtime_scripts.yaml", "visual_patch.yaml"):
        scripts.update(yaml.safe_load((source / name).read_text()))
    writes = []
    revisions = [0] * 15

    async def get_status(call):
        return {"accepted": True, "revision": revisions[call.data["key"]], "error": "none"}

    async def set_visual(call):
        writes.append(dict(call.data))
        revisions[call.data["key"]] = call.data["revision"]
        return {"accepted": True, "revision": call.data["revision"], "error": "none", "phase": "queued"}

    hass.services.async_register("esphome", "streamdeck_original_get_key_visual_status", get_status,
                                 supports_response=SupportsResponse.ONLY)
    hass.services.async_register("esphome", "streamdeck_original_set_key_visual", set_visual,
                                 supports_response=SupportsResponse.ONLY)
    assert await async_setup_component(hass, "script", {"script": scripts})
    hass.states.async_set("sensor.stream_deck_original_visual_session", "1234567890123456")
    hass.states.async_set("light.example_lamp", "off")
    result = await hass.services.async_call("script", "stream_deck_apply", {"key": 2, "patch": {"text": "123"}},
                                             blocking=True, return_response=True)
    assert result["revision"] == 1
    assert writes[-1]["label_text"] == "123"
    assert writes[-1]["session"] == "1234567890123456"
    writes.clear()
    await hass.services.async_call("script", "stream_deck_sync_layout", blocking=True)
    assert [write["key"] for write in writes] == list(range(15))
    assert all(write["fields"] == 127 for write in writes)
    assert writes[0]["label_text"] == "Desk OFF"
    assert writes[0]["image_url"].endswith("/light_off.png")
    hass.states.async_set("light.example_lamp", "on")
    await hass.services.async_call("script", "stream_deck_sync_layout", blocking=True)
    assert writes[-15]["label_text"] == "Desk ON"


@pytest.mark.asyncio
async def test_late_action_registration_replays_without_another_sensor_change(hass):
    source = Path(__file__).parents[1] / "examples"
    scripts = {}
    for name in ("runtime_scripts.yaml", "visual_patch.yaml"):
        scripts.update(yaml.safe_load((source / name).read_text()))
    assert await async_setup_component(hass, "script", {"script": scripts})
    hass.states.async_set("sensor.stream_deck_original_visual_session", "1234567890123456")
    hass.states.async_set("light.example_lamp", "off")
    replay = yaml.safe_load((source / "runtime_automations.yaml").read_text())[0]
    assert await async_setup_component(hass, "automation", {"automation": [replay]})
    writes = []
    done = asyncio.Event()

    async def get_status(call):
        return {"accepted": True, "revision": 0, "error": "none"}

    async def set_visual(call):
        writes.append(dict(call.data))
        if call.data["key"] == 14:
            done.set()
        return {"accepted": True, "revision": 1, "error": "none"}

    # No session state change accompanies these registrations. Actual HA bus
    # service_registered events must wake the shipped replay automation.
    hass.services.async_register("esphome", "streamdeck_original_get_key_visual_status", get_status,
                                 supports_response=SupportsResponse.ONLY)
    hass.services.async_register("esphome", "streamdeck_original_set_key_visual", set_visual,
                                 supports_response=SupportsResponse.ONLY)
    await asyncio.wait_for(done.wait(), timeout=10)
    assert [write["key"] for write in writes[:15]] == list(range(15))
    assert writes[0]["label_text"] == "Desk OFF"
