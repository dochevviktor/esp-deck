"""One coalescing visual writer and bounded, non-replayed bindings per deck."""

import asyncio
from collections import deque
from copy import deepcopy
from datetime import timedelta
import time

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_STATE_CHANGED
from homeassistant.core import Context, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.util.dt import utcnow

from .adapter import Adapter, AdapterError, resolve_reference
from .const import DOMAIN, EVENT_KEY, KEY_COUNT, MAX_REVISION, SIGNAL_STATUS, POSITION_DEFAULTS
from .artwork import DATA_KEY
from .model import LayoutError, require_capabilities
from .advanced import AdvancedController


class DeckController(AdvancedController):
    def __init__(self, hass, entry, repository):
        self.hass, self.entry, self.repository = hass, entry, repository
        self.adapter = Adapter(hass, entry.data)
        self.active = False
        self.epoch = 0
        self.binding_epoch = 0
        self.connected = False
        self.error = None
        self.binding_error = None
        self.session = None
        self.events = {}
        self.session_entity = None
        self.watched = set()
        self.sent = {}
        self.tiles = [{} for _ in range(KEY_COUNT)]
        self.pending = False
        self.force = False
        self.worker = None
        self.binding_worker = None
        self.queue = deque()
        self.held = set()
        self.unsubs = []
        self.poll_cancel = None
        self.binding_count = 0
        self.inflight_key = None
        self.input_after = utcnow()
        self.input_blocked = False
        self.configuration_lock = asyncio.Lock()
        self.init_advanced()

    async def start(self):
        self.active = True
        self.unsubs = [self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._state_changed),
                      self.hass.bus.async_listen(EVENT_HOMEASSISTANT_STARTED, self._wake),
                      async_track_time_interval(self.hass, self._wake, timedelta(seconds=30))]
        for event in ("entity_registry_updated", "device_registry_updated", "service_registered", "service_removed"):
            self.unsubs.append(self.hass.bus.async_listen(event, self._registry_changed))
        self.request_sync()
        self.input_worker = self.hass.async_create_background_task(self._inputs(), "ESP Deck correlated inputs")

    async def stop(self):
        self.active = False
        self.epoch += 1
        for unsub in self.unsubs:
            unsub()
        self.unsubs.clear()
        if self.poll_cancel:
            self.poll_cancel()
            self.poll_cancel = None
        tasks = [task for task in (self.worker, self.binding_worker, self.input_worker) if task and not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.queue.clear()
        self.held.clear()
        # Finish any already-accepted disk transaction before a replacement
        # controller can load this entry. New API mutations now reject inactive.
        async with self.configuration_lock:
            pass

    @callback
    def _invalidate_input(self):
        self.reset_reader()
        self.epoch += 1
        self.binding_epoch += 1
        self.input_after = utcnow()
        if self.inflight_key is not None:
            # A previous request may still reach the ESP. Re-query its revision
            # on the next pass instead of reporting our own write as a rival.
            self.sent.pop(self.inflight_key, None)
            self.pending = True
        self.held.clear()
        self.queue.clear()
        if self.binding_worker and not self.binding_worker.done():
            self.binding_worker.cancel()

    @callback
    def layout_changed(self):
        self._invalidate_input()
        self.contexts.clear()
        self.prepare_contexts()
        self.binding_error = None
        self.input_blocked = False
        self.request_sync()

    @callback
    def _wake(self, _=None):
        self.request_sync()

    @callback
    def _registry_changed(self, event):
        if event.event_type.startswith("service_") and event.data.get("domain") != "esphome":
            return
        self.request_sync()

    @callback
    def request_sync(self, *, retry=False):
        if not self.active:
            return
        if retry and self.input_blocked:
            self._invalidate_input()
            self.input_blocked = False
            self.binding_error = None
        self.pending = True
        self.force |= retry
        if self.worker is None or self.worker.done():
            self.worker = self.hass.async_create_background_task(self._run(), "ESP Deck synchronization")

    @callback
    def _poll(self, _):
        self.poll_cancel = None
        self.request_sync()

    @callback
    def _publish(self):
        async_dispatcher_send(self.hass, SIGNAL_STATUS.format(self.entry.entry_id))

    def status(self):
        phases = {tile.get("phase") for tile in self.tiles}
        if not self.connected:
            state = "offline" if self.error in (None, "offline", "actions_unavailable", "native_action_failed") else "repair_required"
        elif self.error or self.binding_error or "failed" in phases:
            state = "failed"
        elif self.pending or "queued" in phases or "rendering" in phases or None in phases or (
                self.capabilities.get("protocol_version") == 2 and any(
                    tile.get("applied_revision", 0) != tile.get("revision", -1) for tile in self.tiles)):
            state = "syncing"
        else:
            state = "ready"
        return {"state": state, "connected": self.connected, "error": self.error,
                "binding_error": self.binding_error, "binding_count": self.binding_count,
                "draft_revision": self.repository.data["draft_revision"],
                "applied_revision": self.repository.data["applied_revision"],
                "tiles": deepcopy(self.tiles), "rendered_is_display_readback": False,
                "capabilities": self.capabilities, "active_page": self.page, "active_overlay": self.overlay}

    def _issue(self, error=None):
        issue_id = f"{self.entry.entry_id}_connection"
        if error and error not in ("offline", "actions_unavailable", "native_action_failed", "session_changed"):
            ir.async_create_issue(self.hass, DOMAIN, issue_id, is_fixable=True,
                severity=ir.IssueSeverity.WARNING, translation_key="connection",
                translation_placeholders={"error": error}, data={"entry_id": self.entry.entry_id})
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    async def _run(self):
        try:
            # A single boolean pending flag coalesces arbitrarily many state updates.
            while self.active and self.pending:
                await asyncio.sleep(0.05)
                self.pending, force = False, self.force
                self.force = False
                try:
                    await self._synchronize(force)
                    self._issue()
                except (AdapterError, LayoutError) as err:
                    code = err.code if isinstance(err, AdapterError) else str(err)
                    self.error = code
                    if self.connected:
                        self._invalidate_input()
                    self.connected = False
                    self.sent.clear()
                    self._issue(code)
                self._publish()
        finally:
            self.worker = None

    def _visual(self, key):
        result = dict(key["visual"])
        if rule := key["state"]:
            try:
                entity_id = resolve_reference(self.hass, rule["entity"])
                self.watched.add(entity_id)
                state = self.hass.states.get(entity_id)
                variant = state.state if state and state.state in ("on", "off") else "unavailable"
            except AdapterError:
                variant = "unavailable"
                self.binding_error = "entity_missing_or_disabled"
            result.update(rule[variant])
        if library := self.hass.data.get(DATA_KEY):
            return library.resolve(self.entry.entry_id, result)
        result.pop("asset_id", None)
        return result

    async def _synchronize(self, force):
        deck = self.adapter.resolve()
        if not self.connected or self.session != deck.session:
            self._invalidate_input()
            self.sent.clear()
            self.contexts.clear()
            self.capabilities = await self.adapter.capabilities(deck)
            self.input_blocked = False
            if self.binding_error == "binding_queue_overflow":
                self.binding_error = None
        self.session, self.connected, self.error = deck.session, True, None
        if self.binding_error == "entity_missing_or_disabled":
            self.binding_error = None
        self.events = {entity: key for key, entity in enumerate(deck.events)}
        self.session_entity = deck.session_entity
        self.watched = set()
        require_capabilities(self.repository.data["applied"], self.capabilities)
        self.prepare_contexts()
        configs = self.active_keys()
        v2 = self.capabilities.get("protocol_version") == 2
        epoch = self.epoch
        pending_render = False
        for key in range(KEY_COUNT):
            if not self.active or epoch != self.epoch:
                return
            status = await self.adapter.call(deck, "get_key_visual_status", key)
            if epoch != self.epoch or not self.active:
                return
            if not status["accepted"]:
                raise AdapterError(status["error"])
            desired = self._visual(configs[key])
            if v2:
                desired = {**POSITION_DEFAULTS, **desired}
            else:
                desired = {k: v for k, v in desired.items() if k not in POSITION_DEFAULTS}
            previous = self.sent.get(key)
            unchanged = previous and previous["visual"] == desired and previous["revision"] == status["revision"]
            if v2:
                unchanged = unchanged and status.get("context") == self.contexts[key]["token"]
            if previous and previous["revision"] != status["revision"] and not force:
                self.tiles[key] = {**status, "phase": "failed", "error": "competing_writer"}
                continue
            retry_failed = force and status["phase"] == "failed"
            if not unchanged or retry_failed:
                if status["revision"] >= MAX_REVISION:
                    self.tiles[key] = {**status, "phase": "failed", "error": "revision_exhausted"}
                    continue
                values = {**desired, "label_text": desired["text"], "fields": 127, "revision": status["revision"] + 1}
                del values["text"]
                if v2:
                    values.update(fields=255, binding_context=self.contexts[key]["token"])
                self.inflight_key = key
                try:
                    status = await self.adapter.call(deck, "set_key_visual_v2" if v2 else "set_key_visual", key, **values)
                finally:
                    self.inflight_key = None
                if epoch != self.epoch or not self.active:
                    return
                if status["accepted"]:
                    self.sent[key] = {"visual": desired, "revision": status["revision"], "since": time.monotonic()}
                else:
                    # Validation failures are retained until an edit or explicit retry.
                    self.sent[key] = {"visual": desired, "revision": status["revision"], "since": time.monotonic(),
                                      "rejection": status["error"]}
            if (sent := self.sent.get(key)) and sent.get("rejection"):
                if force:
                    self.sent.pop(key)
                    self.pending = True
                status = {**status, "phase": "failed", "error": sent["rejection"]}
            elif status["phase"] in ("queued", "rendering"):
                if time.monotonic() - self.sent.get(key, {}).get("since", 0) < 30:
                    pending_render = True
                else:
                    status = {**status, "phase": "failed", "error": "render_timeout"}
            self.tiles[key] = status
            if v2 and status["phase"] == "rendered" and status.get("applied_revision") != status["revision"]:
                if time.monotonic() - self.sent.get(key, {}).get("since", time.monotonic()) < 30:
                    pending_render = True
                else:
                    self.tiles[key] = {**status, "phase": "failed", "error": "usb_apply_timeout"}
        if pending_render and self.poll_cancel is None and self.active:
            self.poll_cancel = async_call_later(self.hass, 0.5, self._poll)

    @callback
    def _state_changed(self, event):
        entity = event.data["entity_id"]
        old, new = event.data.get("old_state"), event.data.get("new_state")
        if entity == self.session_entity:
            if new is None or old is None or old.state != new.state:
                self._invalidate_input()
                self.request_sync()
            return
        if entity in self.watched:
            self.request_sync()
        if self.capabilities.get("input_correlation") == "pull_context_v2":
            return
        if entity not in self.events:
            return
        if new is None or new.state == "unavailable":
            self._invalidate_input()
            self.request_sync()
            return
        if (not self.active or not self.connected or self.input_blocked or old is None or old.state == "unavailable"
                or event.time_fired < self.input_after
                or new.state in ("unknown", "unavailable") or old.state == new.state
                or new.attributes.get("restored") or new.attributes.get("event_type") not in ("press", "release")):
            return
        try:
            if self.adapter.resolve().session != self.session:
                return
        except AdapterError:
            self._invalidate_input()
            return
        key, edge = self.events[entity], new.attributes["event_type"]
        if edge == "press":
            if key in self.held:
                return
            self.held.add(key)
        elif key not in self.held:
            return
        else:
            self.held.remove(key)
        config = self.repository.data["applied"]["keys"][key]
        context = Context(parent_id=event.context.id)
        if config["mode"] == "automation":
            self.hass.bus.async_fire(EVENT_KEY, {"entry_id": self.entry.entry_id, "key": key, "edge": edge}, context=context)
            return
        if not (binding := config[edge]):
            return
        if len(self.queue) >= 32:
            self._invalidate_input()
            self.input_blocked = True
            self.binding_error = "binding_queue_overflow"
            self._publish()
            return
        self.queue.append((self.binding_epoch, deepcopy(binding), context))
        if self.binding_worker is None or self.binding_worker.done():
            self.binding_worker = self.hass.async_create_background_task(self._bindings(), "ESP Deck bindings")

    async def _bindings(self):
        try:
            while self.active and self.queue:
                epoch, binding, context = self.queue.popleft()
                if epoch != self.binding_epoch:
                    continue
                try:
                    if self.adapter.resolve().session != self.session:
                        self._invalidate_input()
                        return
                    targets = [resolve_reference(self.hass, ref) for ref in binding["target"]["entity_id"]]
                    domain, service = binding["action"].split(".", 1)
                    data = deepcopy(binding["data"])
                    if targets:
                        data["entity_id"] = targets
                    async with asyncio.timeout(10):
                        await self.hass.services.async_call(domain, service, data, blocking=True, context=context)
                    if epoch == self.binding_epoch:
                        self.binding_count += 1
                        self.binding_error = None
                except (HomeAssistantError, TimeoutError):
                    self.binding_error = "binding_action_failed"
                self._publish()
        finally:
            self.binding_worker = None
            if self.active and self.queue:
                self.binding_worker = self.hass.async_create_background_task(self._bindings(), "ESP Deck bindings")
