"""Atomic layouts with optimistic edits and a retained previous applied layout."""

import asyncio
from copy import deepcopy
import os

from homeassistant.core import CoreState
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .model import LayoutError, bounded_json, empty_layout, mapping, validate_layout


class LayoutStore(Store):
    async def async_save(self, data):
        # HA 2026.10.1 Store logs WriteError instead of raising it. An editor
        # must not acknowledge/activate a layout that failed to reach disk.
        if self.hass.state is CoreState.stopping or self._read_only:
            raise LayoutError("storage_unavailable")
        self._write_failed = False
        await super().async_save(data)
        if self._write_failed:
            raise LayoutError("storage_write_failed")

    async def _async_write_data(self, data):
        try:
            await super()._async_write_data(data)
        except Exception:
            self._write_failed = True
            raise

    async def _async_migrate_func(self, old_major_version, old_minor_version, old_data):
        # Explicit legacy single-layout envelope; future/unknown formats fail closed.
        if old_major_version == 0:
            layout = validate_layout(old_data["layout"])
            return {"draft_revision": 1, "applied_revision": 1, "draft": layout,
                    "applied": deepcopy(layout), "backup": None}
        raise LayoutError("unsupported_storage_version")


class LayoutRepository:
    def __init__(self, hass, entry_id):
        self.store = LayoutStore(hass, 1, f"{DOMAIN}.{entry_id}", private=True, atomic_writes=True)
        self.lock = asyncio.Lock()
        self.data = None

    async def load(self):
        existed = await self.store.hass.async_add_executor_job(os.path.exists, self.store.path)
        saved = await self.store.async_load()
        if saved is None:
            if existed:
                # Store preserves corrupt files with a suffix and returns None.
                # Retain its repair issue, but do not activate a new blank layout.
                raise LayoutError("invalid_storage")
            saved = {"draft_revision": 0, "applied_revision": 0, "draft": empty_layout(),
                     "applied": empty_layout(), "backup": None}
        mapping(saved, ("draft_revision", "applied_revision", "draft", "applied", "backup"),
                ("draft_revision", "applied_revision", "draft", "applied", "backup"))
        for name in ("draft_revision", "applied_revision"):
            if type(saved[name]) is not int or not 0 <= saved[name] <= 2**53 - 1:
                raise LayoutError("invalid_storage")
        if saved["applied_revision"] > saved["draft_revision"]:
            raise LayoutError("invalid_storage")
        saved["draft"] = validate_layout(saved["draft"])
        saved["applied"] = validate_layout(saved["applied"])
        if saved["backup"] is not None:
            saved["backup"] = validate_layout(saved["backup"])
        self.data = saved

    def check_revision(self, expected):
        if type(expected) is not int or expected != self.data["draft_revision"]:
            raise LayoutError("draft_conflict")

    async def save(self, layout, expected):
        validated = validate_layout(layout)
        async with self.lock:
            self.check_revision(expected)
            if expected >= 2**53 - 1:
                raise LayoutError("layout_revision_exhausted")
            updated = {**self.data, "draft": validated, "draft_revision": expected + 1}
            await self.store.async_save(deepcopy(updated))
            self.data = updated

    async def apply(self, expected):
        async with self.lock:
            self.check_revision(expected)
            if self.data["applied_revision"] == expected:
                return False
            updated = {**self.data, "backup": self.data["applied"],
                       "applied": deepcopy(self.data["draft"]), "applied_revision": expected}
            await self.store.async_save(deepcopy(updated))
            self.data = updated
            return True

    def export(self, which="draft"):
        if which not in ("draft", "applied", "backup") or self.data[which] is None:
            raise LayoutError("missing_layout")
        return {"format": "esp_deck_layout", "version": 1, "layout": deepcopy(self.data[which])}

    async def import_layout(self, document, expected):
        bounded_json(document)
        mapping(document, ("format", "version", "layout"), ("format", "version", "layout"))
        if document["format"] != "esp_deck_layout" or type(document["version"]) is not int or document["version"] != 1:
            raise LayoutError("unsupported_export_version")
        await self.save(document["layout"], expected)
