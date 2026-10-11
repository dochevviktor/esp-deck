"""P8 model, capability gates, captured bindings and transient navigation in HA."""
from copy import deepcopy
from unittest.mock import Mock

import pytest

from custom_components.esp_deck import adapter, api
from custom_components.esp_deck.artwork import asset_references
from custom_components.esp_deck.model import (
    LayoutError, empty_layout, validate_layout, resolve_keys, require_capabilities, all_keys,
)
from custom_components.esp_deck.storage import LayoutRepository
from test_backend import deck, engine, wait_until  # noqa: F401 (shared real-engine fixtures)


def pages():
    keys = empty_layout()["keys"]
    return validate_layout({"version": 2, "default_page": "main",
        "pages": [{"id": "main", "name": "Main", "keys": keys},
                  {"id": "second", "name": "Second", "keys": deepcopy(keys)}],
        "overlays": [{"id": "shift", "name": "Shift", "keys": {"0": None, "1": {"visual": {"text": "Layer"}}}}]})


def test_pages_precedence_clear_inherit_bounds_and_all_references():
    layout = pages()
    layout["pages"][0]["keys"][0]["visual"]["text"] = "Base"
    layout["pages"][0]["keys"][2]["visual"]["text"] = "Inherited"
    resolved = resolve_keys(layout, "main", "shift")
    assert resolved[0]["visual"]["text"] == ""
    assert resolved[1]["visual"]["text"] == "Layer"
    assert resolved[2]["visual"]["text"] == "Inherited"
    assert len(list(all_keys(layout))) == 31
    layout["overlays"][0]["keys"]["1"]["visual"]["asset_id"] = "a" * 64
    assert asset_references(layout) == {"a" * 64}
    for patch in ({"pages": layout["pages"] * 5}, {"overlays": layout["overlays"] * 5},
                  {"default_page": "missing"}):
        with pytest.raises(LayoutError):
            validate_layout({**layout, **patch})
    bad = pages(); bad["overlays"][0]["keys"]["15"] = None
    with pytest.raises(LayoutError):
        validate_layout(bad)


def test_v1_compatibility_and_capabilities_fail_closed():
    require_capabilities(empty_layout(), {"protocol_version": 1})
    with pytest.raises(LayoutError, match="firmware_upgrade_required"):
        require_capabilities(pages(), {"protocol_version": 1})
    layout = empty_layout(); layout["keys"][0]["visual"]["text_align"] = 0
    with pytest.raises(LayoutError, match="firmware_upgrade_required"):
        require_capabilities(layout, {"protocol_version": 1})
    require_capabilities(pages(), {"input_correlation": "pull_context_v2", "positioning": True})
    layout["keys"][0]["visual"].update(text_x=60)
    with pytest.raises(LayoutError, match="invalid_position"):
        validate_layout(layout)
    layout = pages(); layout["pages"][0]["keys"][0]["navigation"] = {"kind": "page", "target": "missing"}
    with pytest.raises(LayoutError, match="invalid_navigation_target"):
        validate_layout(layout)


@pytest.mark.asyncio
async def test_pages_atomic_export_import_and_restart(deck):
    layout = pages()
    await deck.repo.save(layout, 0); await deck.repo.apply(1)
    document = deck.repo.export("applied")
    restored = LayoutRepository(deck.hass, deck.entry.entry_id)
    await restored.load()
    assert restored.data["applied"] == layout
    await restored.import_layout(document, 1)
    assert restored.data["draft"] == layout and restored.data["draft_revision"] == 2


def arm(deck, layout):
    controller = deck.controller
    controller.repository.data["applied"] = validate_layout(layout)
    controller.active = controller.connected = True
    controller.session = "1234567890123456"
    controller.capabilities = {"protocol_version": 2, "input_correlation": "pull_context_v2", "positioning": True}
    controller.request_sync = Mock()
    controller.prepare_contexts()
    return controller


def packet(controller, key=0, edge="press", token=None):
    return {"key": key, "edge": edge, "context": token or controller.contexts[key]["token"],
            "revision": 1, "generation": 1, "sequence": 1}


@pytest.mark.asyncio
async def test_same_image_changed_binding_rejects_old_press_and_captures_release(deck):
    layout = pages()
    for index, name in enumerate(("first", "second")):
        layout["pages"][index]["keys"][0].update(press={"action": f"script.{name}"}, release={"action": f"script.{name}_release"})
    calls = []
    async def service(call):
        calls.append(call.service)
    for name in ("first", "second", "first_release", "second_release"):
        deck.hass.services.async_register("script", name, service)
    controller = arm(deck, layout)
    old = packet(controller)
    controller._correlated_edge(old)
    await wait_until(lambda: calls == ["first"])
    controller.select_page("second")
    controller._correlated_edge({**old, "key": 1})  # Old context on another key cannot cross-bind.
    controller._correlated_edge(old)
    controller._correlated_edge({**old, "edge": "release"})
    await wait_until(lambda: calls == ["first", "first_release"])
    controller._correlated_edge(packet(controller))
    await wait_until(lambda: calls[-1] == "second")
    assert controller.status()["active_page"] == "second"


@pytest.mark.asyncio
async def test_momentary_overlay_pair_survives_own_replacement_and_resets(deck):
    layout = pages()
    layout["pages"][0]["keys"][0]["navigation"] = {"kind": "momentary", "target": "shift"}
    controller = arm(deck, layout)
    original = packet(controller)
    controller._correlated_edge(original)
    assert controller.overlay == "shift" and controller.active_keys()[0]["visual"]["text"] == ""
    controller._correlated_edge({**original, "edge": "release"})
    assert controller.overlay is None and not controller.captured
    controller._correlated_edge(packet(controller))
    assert controller.overlay == "shift"
    controller._invalidate_input()
    assert controller.overlay is None and not controller.captured
    controller._correlated_edge({**original, "edge": "release"})
    assert controller.overlay is None


@pytest.mark.asyncio
async def test_page_changes_gate_old_events_before_any_native_write(deck):
    controller = arm(deck, pages())
    old = controller.contexts[0]["token"]
    controller.select_page("second")
    second = controller.contexts[0]["token"]
    controller.select_page("main")
    assert controller.contexts[0]["token"] not in (old, second)
    controller._correlated_edge(packet(controller, token=old))
    assert not controller.captured
    with pytest.raises(LayoutError):
        controller.select_page("missing")
    controller.repository.data["applied"] = empty_layout()
    with pytest.raises(LayoutError, match="pages_not_enabled"):
        controller.select_page("main")


@pytest.mark.asyncio
async def test_concurrent_press_navigation_keeps_already_accepted_pair(deck):
    layout = pages()
    layout["pages"][0]["keys"][0].update(press={"action": "script.press"}, release={"action": "script.release"})
    layout["pages"][0]["keys"][1]["navigation"] = {"kind": "page", "target": "second"}
    calls = []
    async def service(call):
        calls.append(call.service)
    for name in ("press", "release"):
        deck.hass.services.async_register("script", name, service)
    controller = arm(deck, layout)
    press, nav = packet(controller), packet(controller, key=1)
    # Same native response, before HA's binding task has a chance to run.
    controller._correlated_edge(press)
    controller._correlated_edge(nav)
    controller._correlated_edge({**press, "edge": "release"})
    await wait_until(lambda: calls == ["press", "release"])
    assert controller.page == "second"


@pytest.mark.asyncio
async def test_v1_backend_rejects_advanced_saved_layout(deck):
    deck.controller.active = True
    with pytest.raises(LayoutError, match="firmware_upgrade_required"):
        await api.execute(deck.hass, "save_layout", {"entry_id": deck.entry.entry_id, "layout": pages(), "expected_revision": 0})
    assert deck.repo.data["draft_revision"] == 0
