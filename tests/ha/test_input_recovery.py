"""Production v2 reader recovery and bounded work in the pinned HA engine."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from custom_components.esp_deck.adapter import AdapterError
from custom_components.esp_deck.model import empty_layout, entity_preset
from test_backend import deck, engine, apply, wait_until  # noqa: F401


@pytest_asyncio.fixture
async def reader(deck):
    """Use the real controller and HA lifecycle, with a deterministic native peer."""
    controller = deck.controller
    resolved = controller.adapter.resolve()
    calls = []

    async def toggle(call):
        calls.append(call)

    deck.hass.services.async_register("light", "toggle", toggle)
    deck.hass.states.async_set("light.lab", "off")
    layout = empty_layout()
    layout["keys"][0] = entity_preset("light.lab", "Lamp")
    await apply(deck, layout)
    packets = []
    reads = []
    writes = []
    statuses = [dict(status, applied_revision=0, context="") for status in deck.responses]

    async def native_call(_deck, operation, key, **values):
        if operation in ("set_key_visual_v2", "set_key_visual"):
            writes.append((key, dict(values)))
            statuses[key].update(revision=values["revision"], applied_revision=values["revision"],
                                 rendered_revision=values["revision"], phase="rendered",
                                 context=values.get("binding_context", ""))
        return dict(statuses[key])

    async def read(_deck, operation, **values):
        assert operation == "read_deck_inputs"
        reads.append(dict(values))
        events, packets[:] = list(packets), []
        sequence = values["ack"]
        for packet in events:
            sequence += 1
            packet["sequence"] = sequence
        return {"session": resolved.session, "accepted": True, "generation": 1,
                "reset": 1, "sequence": sequence, "count": len(events), "events": events}

    def press():
        token = controller.contexts[0]["token"]
        for edge in ("press", "release"):
            packets.append({"key": 0, "edge": edge, "context": token,
                            "revision": statuses[0]["revision"], "generation": 1})

    with (patch.object(controller.adapter, "capabilities", AsyncMock(return_value={
              "protocol_version": 2, "input_correlation": "pull_context_v2", "positioning": True})),
          patch.object(controller.adapter, "call", side_effect=native_call),
          patch.object(controller.adapter, "raw_call", side_effect=read)):
        await controller.start()
        await wait_until(lambda: controller.status()["state"] == "ready" and controller.input_reset is not None)
        yield SimpleNamespace(deck=deck, controller=controller, read=read, reads=reads,
                              writes=writes, calls=calls, press=press)
        await controller.stop()


@pytest.mark.asyncio
async def test_obsolete_reader_failure_does_not_reset_replacement(reader):
    controller = reader.controller
    entered, release = asyncio.Event(), asyncio.Event()
    first = True

    async def stale_failure(*args, **kwargs):
        nonlocal first
        if first:
            first = False
            entered.set()
            await release.wait()
            raise AdapterError("native_action_failed")
        return await reader.read(*args, **kwargs)

    with patch.object(controller.adapter, "raw_call", side_effect=stale_failure):
        await asyncio.wait_for(entered.wait(), 2)
        controller.layout_changed()
        replacement_reader, replacement_epoch = controller.reader, controller.epoch
        replacement_contexts = deepcopy(controller.contexts)
        release.set()
        await wait_until(lambda: controller.input_reset is not None)
        assert controller.reader == replacement_reader
        assert controller.epoch == replacement_epoch
        assert controller.contexts == replacement_contexts
        reader.press()
        await wait_until(lambda: len(reader.calls) == 1)


@pytest.mark.asyncio
async def test_failed_input_read_keeps_visual_contexts_and_recovers_actions(reader):
    controller = reader.controller
    original_contexts = deepcopy(controller.contexts)
    original_writes = len(reader.writes)
    failed = asyncio.Event()
    first = True

    async def fail_once(*args, **kwargs):
        nonlocal first
        if first:
            first = False
            failed.set()
            raise AdapterError("input_delivery_timeout")
        return await reader.read(*args, **kwargs)

    with patch.object(controller.adapter, "raw_call", side_effect=fail_once):
        await asyncio.wait_for(failed.wait(), 2)
        await wait_until(lambda: controller.input_reset is not None and controller.worker is None)
        assert controller.contexts == original_contexts
        assert len(reader.writes) == original_writes
        reader.press()
        await wait_until(lambda: len(reader.calls) == 1)


@pytest.mark.asyncio
async def test_input_response_wait_is_bounded_by_reader_lease(reader):
    controller = reader.controller
    entered, canceled = asyncio.Event(), asyncio.Event()
    first = True
    original_contexts = deepcopy(controller.contexts)
    original_writes = len(reader.writes)

    async def stalled_once(*args, **kwargs):
        nonlocal first
        if first:
            first = False
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                canceled.set()
        return await reader.read(*args, **kwargs)

    with patch.object(controller.adapter, "raw_call", side_effect=stalled_once):
        await asyncio.wait_for(entered.wait(), 2)
        # A response action otherwise has the adapter's ten-second timeout.
        await asyncio.wait_for(canceled.wait(), 1.5)
        await wait_until(lambda: controller.input_reset is not None and controller.worker is None)
        assert controller.contexts == original_contexts
        assert len(reader.writes) == original_writes
        reader.press()
        await wait_until(lambda: len(reader.calls) == 1)


@pytest.mark.asyncio
async def test_repeated_offline_wakes_keep_tasks_listeners_and_queues_bounded(reader):
    controller = reader.controller
    input_worker = controller.input_worker
    unsubs = tuple(controller.unsubs)
    listeners = reader.deck.hass.bus.async_listeners()
    resolved = controller.adapter.resolve()
    with patch.object(controller.adapter, "resolve", side_effect=AdapterError("offline")):
        # Accelerate repeated offline retry cycles and bursts of state updates.
        # This checks retained work, not elapsed-time or real heap-soak behavior.
        for _ in range(120):
            for _ in range(72):
                controller._wake()
            await wait_until(lambda: not controller.connected and controller.worker is None)
            assert controller.input_worker is input_worker and not input_worker.done()
            assert tuple(controller.unsubs) == unsubs
            assert reader.deck.hass.bus.async_listeners() == listeners
            assert not controller.queue and not controller.held and not controller.captured
            assert len(controller.contexts) <= 15 and len(controller.sent) <= 15
            assert controller.poll_cancel is None
            workers = [task for task in asyncio.all_tasks()
                       if task.get_name().startswith("ESP Deck") and not task.done()]
            assert workers == [input_worker]
    with patch.object(controller.adapter, "resolve", return_value=resolved):
        controller.request_sync()
        await wait_until(lambda: controller.status()["state"] == "ready" and controller.input_reset is not None)
        reader.press()
        await wait_until(lambda: len(reader.calls) == 1)
        assert controller.input_worker is input_worker
    await controller.stop()
    assert input_worker.done() and not controller.unsubs
    assert not controller.queue and controller.poll_cancel is None


@pytest.mark.asyncio
async def test_stream_reset_discards_queued_bindings_and_cancels_running_action(reader):
    controller = reader.controller
    entered, canceled = asyncio.Event(), asyncio.Event()
    calls = []

    async def delayed(call):
        calls.append(call)
        if len(calls) == 1:
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                canceled.set()

    reader.deck.hass.services.async_register("light", "toggle", delayed)
    reader.press()
    await asyncio.wait_for(entered.wait(), 2)
    reader.press()
    await wait_until(lambda: len(controller.queue) == 1)
    previous_reader = controller.reader

    async def reset_stream(*args, **kwargs):
        result = await reader.read(*args, **kwargs)
        result["reset"] = 2
        return result

    with patch.object(controller.adapter, "raw_call", side_effect=reset_stream):
        await wait_until(lambda: controller.input_reset == (1, 2))
        await asyncio.wait_for(canceled.wait(), 1)
        assert controller.reader == previous_reader
        assert not controller.queue and not controller.captured
        assert len(calls) == 1
        reader.press()
        await wait_until(lambda: len(calls) == 2)
        assert controller.binding_count == 1


@pytest.mark.asyncio
async def test_sustained_read_failures_keep_work_bounded_and_report_recovery(reader):
    controller = reader.controller
    original_contexts = deepcopy(controller.contexts)
    original_writes = len(reader.writes)
    original_epoch = controller.epoch
    original_polls = controller.input_polls
    attempts = 0
    recovering = asyncio.Event()

    async def outage(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if not recovering.is_set():
            raise AdapterError("native_action_failed")
        return await reader.read(*args, **kwargs)

    with patch.object(controller.adapter, "raw_call", side_effect=outage):
        await wait_until(lambda: attempts >= 12)
        status = controller.status()
        assert status["state"] == "failed" and status["input_error"] == "native_action_failed"
        assert status["input_failures"] == attempts
        assert status["input_polls"] == original_polls
        assert status["input_worker_running"] and status["binding_queue_depth"] == 0
        assert controller.epoch == original_epoch + 1
        assert controller.contexts == original_contexts
        assert len(reader.writes) == original_writes
        recovering.set()
        await wait_until(lambda: controller.status()["state"] == "ready" and controller.input_reset is not None)
        status = controller.status()
        assert status["input_error"] is None and status["input_failures"] >= 12
        assert status["input_polls"] > original_polls and status["input_stream_resets"] >= 2
        reader.press()
        await wait_until(lambda: len(reader.calls) == 1)


@pytest.mark.asyncio
async def test_read_failure_clears_momentary_overlay_and_restores_base_bindings(reader):
    controller = reader.controller
    keys = deepcopy(controller.repository.data["applied"]["keys"])
    keys[1]["navigation"] = {"kind": "momentary", "target": "shift"}
    layout = {"version": 2, "default_page": "main",
              "pages": [{"id": "main", "name": "Main", "keys": keys}],
              "overlays": [{"id": "shift", "name": "Shift",
                            "keys": {"0": {"visual": {"text": "Shift"}}}}]}
    await apply(reader.deck, layout)
    await wait_until(lambda: controller.status()["state"] == "ready" and controller.input_reset is not None)
    controller._correlated_edge({"key": 1, "edge": "press", "context": controller.contexts[1]["token"],
                                 "revision": 1, "generation": 1, "sequence": 1})
    await wait_until(lambda: controller.overlay == "shift" and controller.worker is None)
    assert controller.active_keys()[0]["visual"]["text"] == "Shift"
    first = True
    failed = asyncio.Event()

    async def fail_once(*args, **kwargs):
        nonlocal first
        if first:
            first = False
            failed.set()
            raise AdapterError("native_action_failed")
        return await reader.read(*args, **kwargs)

    with patch.object(controller.adapter, "raw_call", side_effect=fail_once):
        await asyncio.wait_for(failed.wait(), 2)
        await wait_until(lambda: controller.status()["state"] == "ready" and controller.input_reset is not None)
        assert controller.overlay is None and controller.modifier is None
        assert not controller.captured
        assert controller.active_keys()[0]["visual"]["text"] == "Lamp"
        assert all(context["identity"][1] is None for context in controller.contexts.values())
        assert [values["label_text"] for key, values in reader.writes if key == 0][-1] == "Lamp"
        reader.press()
        await wait_until(lambda: len(reader.calls) == 1)


@pytest.mark.asyncio
async def test_reconnect_to_v1_firmware_clears_old_v2_input_error(reader):
    controller = reader.controller
    controller.input_error = "native_action_failed"
    controller.connected = False
    with patch.object(controller.adapter, "capabilities", AsyncMock(return_value={"protocol_version": 1})):
        await controller._synchronize(False)
    assert controller.input_error is None
    assert controller.capabilities["protocol_version"] == 1
    assert controller.status()["state"] == "ready"
