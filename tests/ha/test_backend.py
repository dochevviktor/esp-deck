"""P6 in the pinned real HA engine; only the ESPHome transport is mocked."""

import asyncio
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import pytest_asyncio
from aioesphomeapi import (DeviceInfo, EventInfo, TextSensorInfo, UserService, UserServiceArg,
                          UserServiceArgType, SupportsResponseType, build_device_unique_id)
from homeassistant import bootstrap, config_entries, loader
from homeassistant.core import Context, HomeAssistant, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, Unauthorized, UnsupportedStorageVersionError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.storage import Store

from custom_components.esp_deck import adapter, api
from custom_components.esp_deck.config_flow import ESPDeckConfigFlow
from custom_components.esp_deck.const import DEFAULT_VISUAL, SIGNATURES
from custom_components.esp_deck.controller import DeckController
from custom_components.esp_deck.diagnostics import async_get_config_entry_diagnostics
from custom_components.esp_deck.model import (LayoutError, empty_layout, entity_preset,
                                             validate_layout)
from custom_components.esp_deck.storage import LayoutRepository


def make_entry(hass, domain, data=None):
    entry = config_entries.ConfigEntry(domain=domain, data=data or {}, options={}, title="Test deck",
        version=1, minor_version=1, source="user", unique_id=None, discovery_keys={}, subentries_data=[])
    hass.config_entries._entries[entry.entry_id] = entry
    return entry


@pytest_asyncio.fixture
async def engine(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    loader.async_setup(hass)
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    hass.config.time_zone = "UTC"
    assert await bootstrap.async_load_base_functionality(hass)
    await hass.async_start()
    yield hass
    await hass.async_stop()


@pytest_asyncio.fixture
async def deck(engine):
    hass = engine
    entry = make_entry(hass, "esphome")
    info = DeviceInfo(name="lab-deck", mac_address="02:00:00:DE:CC:01")
    device = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id,
        identifiers={("esphome", info.mac_address)}, name="Lab deck")
    registry = er.async_get(hass)
    entities = {}
    metadata = {TextSensorInfo: {}, EventInfo: {}}
    for index in range(16):
        cls, domain, object_id, name = (TextSensorInfo, "sensor", "visual_session", "Visual session") if index == 15 else (
            EventInfo, "event", f"key_{index}_edge", f"Key {index} edge")
        record = cls(object_id=object_id, key=index + 1, name=name)
        metadata[cls][(0, record.key)] = record
        entity = registry.async_get_or_create(domain, "esphome", build_device_unique_id(info.mac_address, record),
            config_entry=entry, device_id=device.id, suggested_object_id=object_id, original_name=name)
        entities[object_id] = entity
        hass.states.async_set(entity.entity_id, "1234567890123456" if domain == "sensor" else "unknown",
                              {"event_types": ["press", "release"]} if domain == "event" else {})
    native_services = {}
    for index, (name, signature) in enumerate(SIGNATURES.items()):
        native_services[index] = UserService(name=name, key=index, supports_response=SupportsResponseType.ONLY,
            args=[UserServiceArg(name=arg, type=UserServiceArgType[kind]) for arg, kind in signature.items()])
    entry.runtime_data = SimpleNamespace(available=True, device_info=info, services=native_services, info=metadata)
    responses = [{"session": "1234567890123456", "key": key, "accepted": True, "revision": 0,
                  "request_revision": 0, "rendered_revision": 0, "phase": "idle", "error": "none"}
                 for key in range(15)]
    writes = []

    async def native(call):
        key = call.data["key"]
        if call.service.endswith("set_key_visual"):
            writes.append(dict(call.data))
            responses[key].update(revision=call.data["revision"], request_revision=call.data["revision"],
                                  rendered_revision=call.data["revision"], phase="rendered")
        return dict(responses[key])

    for service in native_services.values():
        hass.services.async_register("esphome", "lab_deck_" + service.name, native, supports_response=SupportsResponse.ONLY)
    data = adapter.discover(hass, device.id)
    integration = make_entry(hass, "esp_deck", data)
    repository = LayoutRepository(hass, integration.entry_id)
    await repository.load()
    controller = DeckController(hass, integration, repository)
    integration.runtime_data = controller
    yield SimpleNamespace(hass=hass, source=entry, entry=integration, device=device, entities=entities,
                          controller=controller, repo=repository, writes=writes, responses=responses)
    await controller.stop()


async def wait_until(predicate):
    async with asyncio.timeout(5):
        while not predicate():
            await asyncio.sleep(0.02)


async def start(deck):
    await deck.controller.start()
    await wait_until(lambda: deck.controller.status()["state"] == "ready")


async def apply(deck, layout):
    await deck.repo.save(adapter.pin_references(deck.hass, validate_layout(layout)), deck.repo.data["draft_revision"])
    await deck.repo.apply(deck.repo.data["draft_revision"])
    deck.controller.layout_changed()


def edge(deck, key, name, stamp):
    entity_id = deck.entities[f"key_{key}_edge"].entity_id
    deck.hass.states.async_set(entity_id, stamp, {"event_types": ["press", "release"], "event_type": name})


@pytest.mark.parametrize("mutation", [
    lambda x: x.update(version=2), lambda x: x.update(version=True),
    lambda x: x["keys"].pop(), lambda x: x["keys"].append({}),
    lambda x: x["keys"][0]["visual"].update(text="x" * 49),
    lambda x: x["keys"][0]["visual"].update(text="\x00"),
    lambda x: x["keys"][0]["visual"].update(text="\ud800"),
    lambda x: x["keys"][0]["visual"].update(font=14),
    lambda x: x["keys"][0]["visual"].update(text_color="white"),
    lambda x: x["keys"][0]["visual"].update(fit="stretch"),
    lambda x: x["keys"][0]["visual"].update(image_url="http://user:pw@ha/a.png", image_revision="v1"),
    lambda x: x["keys"][0]["visual"].update(image_url="http://ha/a.png?token=secret", image_revision="v1"),
    lambda x: x["keys"][0]["visual"].update(image_url="http://ha/a.png", image_revision=""),
    lambda x: x["keys"][0].update(mode="automation", press={"action": "light.toggle"}),
    lambda x: x["keys"][0].update(press={"action": "esp_deck.sync"}),
    lambda x: x["keys"][0].update(press={"action": "light.toggle", "data": {"entity_id": "light.x"}}),
])
def test_layout_rejects_invalid_or_ambiguous_contract(mutation):
    layout = empty_layout()
    mutation(layout)
    with pytest.raises(LayoutError):
        validate_layout(layout)


def test_preset_actual_state_clear_and_partial_style():
    key = entity_preset("light.lab", "123")
    assert key["press"]["action"] == "light.toggle"
    assert key["state"]["entity"] == {"entity_id": "light.lab"}
    assert key["visual"]["text"] == "123"
    assert entity_preset("scene.lab", "Scene")["press"]["action"] == "scene.turn_on"
    layout = empty_layout()
    layout["keys"][0]["state"] = {"entity": "light.lab", "on": {"image_url": ""}}
    assert validate_layout(layout)["keys"][0]["state"]["on"] == {"image_url": "", "image_revision": "", "asset_id": ""}


@pytest.mark.asyncio
async def test_storage_atomic_edits_backup_restore_import_and_conflict(engine):
    repo = LayoutRepository(engine, "storage-test")
    await repo.load()
    layout = empty_layout()
    layout["keys"][0]["visual"]["text"] = "First"
    await repo.save(layout, 0)
    assert repo.data["applied"]["keys"][0]["visual"]["text"] == ""
    await repo.apply(1)
    layout["keys"][0]["visual"]["text"] = "Second"
    await repo.save(layout, 1)
    with pytest.raises(LayoutError, match="draft_conflict"):
        await repo.apply(1)
    await repo.apply(2)
    assert repo.export("backup")["layout"]["keys"][0]["visual"]["text"] == "First"
    reopened = LayoutRepository(engine, "storage-test")
    await reopened.load()
    assert reopened.data == repo.data
    await reopened.import_layout(repo.export("backup"), 2)
    assert reopened.data["applied_revision"] == 2 and reopened.data["draft_revision"] == 3
    with patch.object(reopened.store, "async_save", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            await reopened.save(empty_layout(), 3)
    assert reopened.data["draft_revision"] == 3
    assert reopened.store._atomic_writes and reopened.store._private
    doc = repo.export()
    doc["version"] = 2
    with pytest.raises(LayoutError, match="unsupported_export_version"):
        await reopened.import_layout(doc, 3)


@pytest.mark.asyncio
async def test_storage_explicit_migration_and_future_rejection(engine):
    legacy = Store(engine, 0, "esp_deck.legacy", atomic_writes=True)
    await legacy.async_save({"layout": empty_layout()})
    repo = LayoutRepository(engine, "legacy")
    await repo.load()
    assert repo.data["applied_revision"] == 1
    future = Store(engine, 99, "esp_deck.future", atomic_writes=True)
    await future.async_save({"do_not_overwrite": True})
    with pytest.raises(UnsupportedStorageVersionError):
        await LayoutRepository(engine, "future").load()


@pytest.mark.asyncio
async def test_real_store_write_error_and_corruption_do_not_activate_blank(engine):
    from homeassistant.util.file import WriteError
    repo = LayoutRepository(engine, "failure")
    await repo.load()
    with patch.object(repo.store, "_write_prepared_data", side_effect=WriteError("disk full")):
        with pytest.raises(LayoutError, match="storage_write_failed"):
            await repo.save(empty_layout(), 0)
    assert repo.data["draft_revision"] == 0
    path = Path(repo.store.path)
    path.parent.mkdir(exist_ok=True)
    path.write_text("{broken json")
    with pytest.raises(LayoutError, match="invalid_storage"):
        await LayoutRepository(engine, "failure").load()
    assert list(path.parent.glob("esp_deck.failure.corrupt.*"))


@pytest.mark.asyncio
async def test_new_layout_while_old_native_write_finishes_is_not_a_competing_writer(deck):
    await start(deck)
    entered, release = asyncio.Event(), asyncio.Event()
    async def delayed(call):
        if call.data["label_text"] == "Old":
            entered.set()
            await release.wait()
        deck.writes.append(dict(call.data))
        item = deck.responses[call.data["key"]]
        item.update(revision=call.data["revision"], rendered_revision=call.data["revision"],
                    request_revision=call.data["revision"], phase="rendered")
        return dict(item)
    deck.hass.services.async_register("esphome", "lab_deck_set_key_visual", delayed, supports_response=SupportsResponse.ONLY)
    layout = empty_layout()
    layout["keys"][0]["visual"]["text"] = "Old"
    await apply(deck, layout)
    await asyncio.wait_for(entered.wait(), 2)
    layout["keys"][0]["visual"]["text"] = "Newest"
    await apply(deck, layout)
    release.set()
    await wait_until(lambda: deck.writes[-1]["label_text"] == "Newest")
    assert deck.controller.tiles[0]["error"] == "none"
    assert deck.writes[-1]["revision"] == 3


@pytest.mark.asyncio
async def test_adapter_probe_registry_renames_signature_and_no_device_ownership(deck):
    await deck.controller.adapter.probe()
    registry = er.async_get(deck.hass)
    old = deck.entities["visual_session"]
    registry.async_update_entity(old.entity_id, new_entity_id="sensor.renamed_session")
    deck.hass.states.async_set("sensor.renamed_session", "1234567890123456")
    assert deck.controller.adapter.resolve().session_entity == "sensor.renamed_session"
    assert dr.async_get(deck.hass).async_get(deck.device.id).config_entry_id == deck.source.entry_id
    assert len(dr.async_get(deck.hass).devices) == 1
    argument = deck.source.runtime_data.services[0].args[0]
    deck.source.runtime_data.services[0].args[0] = UserServiceArg(name=argument.name, type=None)
    with pytest.raises(adapter.AdapterError, match="incompatible_firmware"):
        deck.controller.adapter.resolve()
    deck.source.runtime_data.services[0].args[0] = argument
    deck.source.runtime_data.services[0].args.pop()
    with pytest.raises(adapter.AdapterError, match="incompatible_firmware"):
        deck.controller.adapter.resolve()


@pytest.mark.asyncio
async def test_adapter_missing_disabled_and_ambiguous_entities(deck):
    registry = er.async_get(deck.hass)
    entity = deck.entities["key_3_edge"]
    registry.async_update_entity(entity.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    with pytest.raises(adapter.AdapterError, match="entity_disabled"):
        deck.controller.adapter.resolve()
    registry.async_update_entity(entity.entity_id, disabled_by=None)
    mapping = deepcopy(deck.entry.data["entities"])
    mapping["key_4"] = mapping["key_3"]
    with pytest.raises(adapter.AdapterError, match="ambiguous_entities"):
        adapter.discover(deck.hass, deck.device.id, mapping)
    registry.async_remove(entity.entity_id)
    with pytest.raises(adapter.AdapterError, match="entity_missing"):
        deck.controller.adapter.resolve()


@pytest.mark.asyncio
async def test_guided_flow_checks_signature_and_explicit_handoff(deck):
    flow = ESPDeckConfigFlow()
    flow.hass = deck.hass
    flow.context = {"source": "user"}
    form = await flow.async_step_user({"device_id": deck.device.id})
    assert form["step_id"] == "handoff"
    result = await flow.async_step_handoff({"exclusive_control": False})
    assert result["errors"]["base"] == "confirm_handoff"
    deck.hass.states.async_set("light.lab", "off")
    result = await flow.async_step_handoff({"exclusive_control": True, "preset_entity": "light.lab", "label": "Lab"})
    assert result["type"] == "create_entry"
    assert result["data"]["initial_entity"]["entity_id"] == "light.lab"


@pytest.mark.asyncio
async def test_writer_skips_unchanged_coalesces_and_follows_actual_state(deck):
    deck.hass.states.async_set("light.lab", "off")
    layout = empty_layout()
    layout["keys"][0] = entity_preset("light.lab", "Lamp")
    await apply(deck, layout)
    await start(deck)
    assert len(deck.writes) == 15 and deck.writes[0]["background_color"] == "#202020"
    for _ in range(4):
        deck.controller.request_sync()
    await asyncio.sleep(0.2)
    assert len(deck.writes) == 15
    for state in ("on", "off", "on", "off", "on"):
        deck.hass.states.async_set("light.lab", state)
    await wait_until(lambda: len(deck.writes) == 16)
    assert deck.writes[-1]["background_color"] == "#176B32"
    deck.hass.states.async_set("light.lab", "unavailable")
    await wait_until(lambda: len(deck.writes) == 17)
    assert deck.writes[-1]["label_text"] == "Unavailable"


@pytest.mark.asyncio
async def test_ha_reload_and_esp_reboot_replay_with_current_revisions(deck):
    await start(deck)
    await deck.controller.stop()
    deck.controller = DeckController(deck.hass, deck.entry, deck.repo)
    deck.entry.runtime_data = deck.controller
    await start(deck)
    assert len(deck.writes) == 30 and all(item["revision"] == 2 for item in deck.writes[-15:])
    for item in deck.responses:
        item.update(session="abcdef0123456789", revision=0, rendered_revision=0, request_revision=0, phase="idle")
    deck.hass.states.async_set(deck.entities["visual_session"].entity_id, "abcdef0123456789")
    await wait_until(lambda: len(deck.writes) == 45)
    assert all(item["revision"] == 1 and item["session"] == "abcdef0123456789" for item in deck.writes[-15:])


@pytest.mark.asyncio
async def test_failed_native_validation_is_actionable_and_not_busy_retried(deck):
    calls = []
    async def reject(call):
        calls.append(call.data["key"])
        return {**deck.responses[call.data["key"]], "accepted": False, "error": "origin_not_allowed"}
    deck.hass.services.async_register("esphome", "lab_deck_set_key_visual", reject, supports_response=SupportsResponse.ONLY)
    await deck.controller.start()
    await wait_until(lambda: deck.controller.tiles[-1].get("error") == "origin_not_allowed")
    assert deck.controller.connected
    deck.controller.request_sync()
    await asyncio.sleep(.2)
    assert len(calls) == 15
    deck.controller.request_sync(retry=True)
    await wait_until(lambda: len(calls) == 30)
    await asyncio.sleep(.2)
    assert len(calls) == 30


@pytest.mark.asyncio
async def test_revision_exhaustion_and_competing_writer(deck):
    await start(deck)
    deck.responses[0]["revision"] += 1
    deck.controller.request_sync()
    await wait_until(lambda: deck.controller.tiles[0].get("error") == "competing_writer")
    assert len(deck.writes) == 15
    deck.responses[0]["revision"] = 2_147_483_647
    deck.controller.request_sync(retry=True)
    await wait_until(lambda: deck.controller.tiles[0].get("error") == "revision_exhausted")


@pytest.mark.asyncio
async def test_binding_context_no_restore_replay_and_release_pairing(deck):
    deck.hass.states.async_set("light.lab", "off")
    calls = []
    async def toggle(call):
        calls.append(call)
    deck.hass.services.async_register("light", "toggle", toggle)
    layout = empty_layout()
    layout["keys"][0] = entity_preset("light.lab", "Lamp")
    layout["keys"][0]["release"] = {"action": "light.toggle", "target": {"entity_id": "light.lab"}}
    await apply(deck, layout)
    await start(deck)
    edge(deck, 0, "release", "orphan")
    edge(deck, 0, "press", "a")
    edge(deck, 0, "press", "b")
    edge(deck, 0, "release", "c")
    await wait_until(lambda: len(calls) == 2)
    assert calls[0].context.parent_id is not None
    edge(deck, 0, "press", "c")  # attribute-only, same timestamp
    deck.hass.states.async_set(deck.entities["key_0_edge"].entity_id, "unavailable")
    edge(deck, 0, "press", "restored")
    await asyncio.sleep(.2)
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_automation_mode_excludes_managed_actions_and_config_drops_held_release(deck):
    events = []
    deck.hass.bus.async_listen("esp_deck_key", lambda event: events.append(event))
    layout = empty_layout()
    layout["keys"][0]["mode"] = "automation"
    await apply(deck, layout)
    await start(deck)
    edge(deck, 0, "press", "a")
    await wait_until(lambda: len(events) == 1)
    await apply(deck, layout)
    edge(deck, 0, "release", "b")
    await asyncio.sleep(.2)
    assert len(events) == 1


@pytest.mark.asyncio
async def test_unload_cancels_delayed_sync_and_unsubscribes(deck):
    entered, release = asyncio.Event(), asyncio.Event()
    async def delayed(call):
        entered.set()
        await release.wait()
        return dict(deck.responses[call.data["key"]])
    deck.hass.services.async_register("esphome", "lab_deck_get_key_visual_status", delayed, supports_response=SupportsResponse.ONLY)
    await deck.controller.start()
    await asyncio.wait_for(entered.wait(), 2)
    await deck.controller.stop()
    release.set()
    deck.hass.states.async_set(deck.entities["visual_session"].entity_id, "abcdef0123456789")
    await asyncio.sleep(.1)
    assert not deck.writes and not deck.controller.unsubs and not deck.controller.active


@pytest.mark.asyncio
async def test_registry_target_rename_missing_id_never_rebinds_reused_name(deck):
    registry = er.async_get(deck.hass)
    entity = registry.async_get_or_create("light", "test", "lamp", suggested_object_id="lab")
    layout = empty_layout()
    layout["keys"][0] = entity_preset(entity.entity_id, "Lamp")
    adapter.pin_references(deck.hass, layout)
    ref = layout["keys"][0]["state"]["entity"]
    registry.async_update_entity(entity.entity_id, new_entity_id="light.renamed")
    assert adapter.resolve_reference(deck.hass, ref) == "light.renamed"
    registry.async_remove("light.renamed")
    registry.async_get_or_create("light", "test", "different-lamp", suggested_object_id="lab")
    with pytest.raises(adapter.AdapterError, match="entity_missing"):
        adapter.resolve_reference(deck.hass, ref)


@pytest.mark.asyncio
async def test_disabled_state_source_recovers_when_reenabled(deck):
    registry = er.async_get(deck.hass)
    entity = registry.async_get_or_create("light", "test", "repair-lamp", suggested_object_id="lab")
    deck.hass.states.async_set(entity.entity_id, "off")
    layout = empty_layout()
    layout["keys"][0] = entity_preset(entity.entity_id, "Lamp")
    await apply(deck, layout)
    await start(deck)
    registry.async_update_entity(entity.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    await wait_until(lambda: deck.controller.binding_error == "entity_missing_or_disabled")
    assert deck.writes[-1]["label_text"] == "Unavailable"
    registry.async_update_entity(entity.entity_id, disabled_by=None)
    await wait_until(lambda: deck.controller.binding_error is None and deck.writes[-1]["label_text"] == "Lamp")


@pytest.mark.asyncio
async def test_binding_queue_overflow_discards_backlog_and_cancels_old_action(deck):
    entered = asyncio.Event()
    canceled = asyncio.Event()
    calls = []
    async def delayed(call):
        calls.append(call)
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            canceled.set()
    deck.hass.services.async_register("light", "toggle", delayed)
    deck.hass.states.async_set("light.lab", "off")
    layout = empty_layout()
    layout["keys"][0] = entity_preset("light.lab", "Lamp")
    layout["keys"][0]["release"] = deepcopy(layout["keys"][0]["press"])
    await apply(deck, layout)
    await start(deck)
    edge(deck, 0, "press", "first")
    await asyncio.wait_for(entered.wait(), 2)
    # An event-loop burst, not an unbounded queue of actions to replay later.
    edge(deck, 0, "release", "initial-release")
    for index in range(30):
        edge(deck, 0, "press", f"press-{index}")
        edge(deck, 0, "release", f"release-{index}")
    await asyncio.wait_for(canceled.wait(), 2)
    await asyncio.sleep(.1)
    assert deck.controller.binding_error == "binding_queue_overflow"
    assert len(calls) == 1 and not deck.controller.queue


@pytest.mark.asyncio
async def test_failed_render_retries_only_on_explicit_sync(deck):
    await start(deck)
    deck.responses[0].update(phase="failed", error="fetch_failed", rendered_revision=0)
    deck.controller.request_sync()
    await wait_until(lambda: deck.controller.tiles[0].get("phase") == "failed")
    assert len(deck.writes) == 15 and deck.controller.connected
    deck.controller.request_sync(retry=True)
    await wait_until(lambda: len(deck.writes) == 16)
    assert deck.writes[-1]["revision"] == 2


@pytest.mark.asyncio
async def test_unload_drains_accepted_save_before_next_controller_loads(deck):
    await start(deck)
    entered, release = asyncio.Event(), asyncio.Event()
    original_save = deck.repo.store.async_save
    async def delayed_save(data):
        entered.set()
        await release.wait()
        await original_save(data)
    with patch.object(deck.repo.store, "async_save", side_effect=delayed_save):
        save = asyncio.create_task(api.execute(deck.hass, "save_layout", {
            "entry_id": deck.entry.entry_id, "layout": empty_layout(), "expected_revision": 0}))
        await asyncio.wait_for(entered.wait(), 2)
        stop = asyncio.create_task(deck.controller.stop())
        await asyncio.sleep(.05)
        assert not stop.done()
        release.set()
        await save
        await stop
    restored = LayoutRepository(deck.hass, deck.entry.entry_id)
    await restored.load()
    assert restored.data["draft_revision"] == 1
    with pytest.raises(LayoutError, match="entry_not_loaded"):
        await api.execute(deck.hass, "sync", {"entry_id": deck.entry.entry_id})


@pytest.mark.parametrize("response", [None, {}, {"accepted": True}, {"session": "secret-url"}])
def test_empty_or_malformed_response_is_not_transport_success(response):
    with pytest.raises(adapter.AdapterError, match="^invalid_native_response$"):
        adapter.check_response(response, "1234567890123456", 0)


@pytest.mark.asyncio
async def test_admin_boundary_export_import_and_redacted_diagnostics(deck):
    await start(deck)
    api.register(deck.hass)
    # HA's own admin service wrapper is exercised, not a fake permission flag.
    from homeassistant import auth
    deck.hass.auth = await auth.auth_manager_from_config(deck.hass, [{"type": "homeassistant"}], [])
    await deck.hass.auth.async_create_user("Owner")
    user = await deck.hass.auth.async_create_user("Viewer", group_ids=["system-users"])
    assert not user.is_admin
    for service in api.OPERATIONS:
        data = {"entry_id": deck.entry.entry_id}
        if service == "save_layout":
            data.update(layout=empty_layout(), expected_revision=0)
        elif service == "apply_layout":
            data.update(expected_revision=0)
        elif service == "import_layout":
            data.update(document=deck.repo.export(), expected_revision=0)
        elif service == "preset":
            data.update(entity_id="light.lab", label="Lab")
        elif service == "artwork_variant":
            data.update(source_id="a" * 64, transform={})
        elif service == "artwork_configure":
            data.update(origin="http://ha:8123")
        elif service == "artwork_delete":
            data.update(asset_id="a" * 64)
        with pytest.raises(Unauthorized):
            await deck.hass.services.async_call("esp_deck", service, data,
                blocking=True, return_response=True, context=Context(user_id=user.id))
    with pytest.raises(Unauthorized):
        api.websocket_command(deck.hass, SimpleNamespace(user=user),
                              {"id": 1, "operation": "status", "entry_id": deck.entry.entry_id, "parameters": {}})
    layout = empty_layout()
    layout["keys"][0]["visual"]["text"] = "PRIVATE LABEL"
    await api.execute(deck.hass, "save_layout", {"entry_id": deck.entry.entry_id, "layout": layout, "expected_revision": 0})
    doc = await api.execute(deck.hass, "export_layout", {"entry_id": deck.entry.entry_id})
    await api.execute(deck.hass, "import_layout", {"entry_id": deck.entry.entry_id, "document": doc, "expected_revision": 1})
    assert deck.repo.data["draft_revision"] == 2 and deck.repo.data["applied_revision"] == 0
    assert "PRIVATE LABEL" not in str(await async_get_config_entry_diagnostics(deck.hass, deck.entry))
