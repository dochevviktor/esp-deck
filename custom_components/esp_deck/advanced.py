"""Capability-gated pages and the bounded v2 input stream on HA's native client."""
import asyncio
from copy import deepcopy
import re
import secrets
import time

from homeassistant.core import Context

from .adapter import AdapterError
from .const import EVENT_KEY, MAX_REVISION
from .model import LayoutError, resolve_keys


class AdvancedController:
    def init_advanced(self):
        self.capabilities = {"protocol_version": 1}
        self.page = self.overlay = self.modifier = None
        self.contexts = {}
        self.captured = {}
        self.input_worker = None
        self.reset_reader()

    def reset_reader(self):
        self.reader = secrets.token_hex(16)
        self.input_ack = 0
        self.input_reset = None
        self.captured.clear()
        self.overlay = self.modifier = None

    def active_keys(self):
        layout = self.repository.data["applied"]
        if layout["version"] == 2:
            if self.page not in {page["id"] for page in layout["pages"]}:
                self.page = layout["default_page"]
            if self.overlay not in {layer["id"] for layer in layout["overlays"]}:
                self.overlay = None
        return resolve_keys(layout, self.page, self.overlay)

    def prepare_contexts(self):
        for key, config in enumerate(self.active_keys()):
            identity = (self.page, self.overlay, config)
            if key not in self.contexts or self.contexts[key]["identity"] != identity:
                self.contexts[key] = {"token": secrets.token_hex(16), "identity": deepcopy(identity),
                                      "config": deepcopy(config)}

    def select_page(self, page):
        if self.capabilities.get("input_correlation") != "pull_context_v2":
            raise LayoutError("firmware_upgrade_required")
        if self.repository.data["applied"]["version"] != 2:
            raise LayoutError("pages_not_enabled")
        resolve_keys(self.repository.data["applied"], page)
        self.page, self.overlay, self.modifier = page, None, None
        self._pages_changed()

    def _pages_changed(self):
        self.epoch += 1
        if self.inflight_key is not None:
            self.sent.pop(self.inflight_key, None)
        self.prepare_contexts()  # Reject old presses immediately, including same-image keys.
        self.request_sync()
        self._publish()

    async def _inputs(self):
        while self.active:
            await asyncio.sleep(0.1)
            if not self.connected or self.capabilities.get("input_correlation") != "pull_context_v2":
                continue
            reader, ack = self.reader, self.input_ack
            started = time.monotonic()
            try:
                deck = self.adapter.resolve()
                result = await self.adapter.raw_call(deck, "read_deck_inputs", session=deck.session, reader=reader, ack=ack)
                if reader != self.reader:
                    continue
                if time.monotonic() - started >= 1:
                    raise AdapterError("input_delivery_timeout")
                if (result.get("session") != self.session or result.get("accepted") is not True
                        or any(type(result.get(k)) is not int or not 0 <= result[k] <= 0xffffffff
                               for k in ("generation", "reset", "sequence", "count"))
                        or not 0 <= result["count"] <= 32 or result["sequence"] > MAX_REVISION):
                    raise AdapterError("invalid_input_response")
                events = result.get("events") or []
                if not isinstance(events, list) or len(events) != result["count"]:
                    raise AdapterError("invalid_input_response")
                reset = (result["generation"], result["reset"])
                if reset != self.input_reset:
                    self.captured.clear()
                    if self.overlay:
                        self.overlay = self.modifier = None
                        self._pages_changed()
                    self.input_reset = reset
                    # The first response and all reset responses are synchronization,
                    # not actionable input. Never infer missing press/release edges.
                    self.input_ack = result["sequence"]
                    continue
                for packet in events:
                    if (not isinstance(packet, dict) or type(packet.get("key")) is not int
                            or not 0 <= packet["key"] < 15 or packet.get("edge") not in ("press", "release")
                            or type(packet.get("sequence")) is not int or packet["sequence"] != self.input_ack + 1
                            or type(packet.get("revision")) is not int or not 1 <= packet["revision"] <= MAX_REVISION
                            or packet.get("generation") != result["generation"]
                            or not isinstance(packet.get("context"), str)
                            or not re.fullmatch(r"[a-f0-9]{32}", packet["context"])):
                        raise AdapterError("invalid_input_response")
                    self.input_ack = packet["sequence"]
                    self._correlated_edge(packet)
                if self.input_ack != result["sequence"]:
                    raise AdapterError("input_sequence_gap")
            except AdapterError:
                self._invalidate_input()
                self.contexts.clear()
                self.request_sync()

    def _correlated_edge(self, packet):
        if self.input_blocked:
            return
        key, edge, token = packet["key"], packet["edge"], packet["context"]
        if edge == "press":
            current = self.contexts.get(key)
            if not current or current["token"] != token or key in self.captured:
                return
            config = deepcopy(current["config"])
            self.captured[key] = (token, config)
        else:
            captured = self.captured.pop(key, None)
            if not captured or captured[0] != token:
                return
            config = captured[1]
        if nav := config.get("navigation"):
            if edge == "release":
                if nav["kind"] == "momentary" and self.modifier == (key, token):
                    self.overlay = self.modifier = None
                    self._pages_changed()
            elif nav["kind"] == "page":
                self.select_page(nav["target"])
            elif nav["kind"] == "overlay":
                self.overlay = None if self.overlay == nav["target"] else nav["target"]
                self.modifier = None
                self._pages_changed()
            elif self.modifier is None:
                self.overlay, self.modifier = nav["target"], (key, token)
                self._pages_changed()
            return
        context = Context()
        if config["mode"] == "automation":
            self.hass.bus.async_fire(EVENT_KEY, {"entry_id": self.entry.entry_id, **packet}, context=context)
            return
        if binding := config[edge]:
            if len(self.queue) >= 32:
                self._invalidate_input()
                self.input_blocked = True
                self.binding_error = "binding_queue_overflow"
                self._publish()
                return
            self.queue.append((self.binding_epoch, deepcopy(binding), context))
            if self.binding_worker is None or self.binding_worker.done():
                self.binding_worker = self.hass.async_create_background_task(self._bindings(), "ESP Deck bindings")
