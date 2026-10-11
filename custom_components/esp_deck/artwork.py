"""Bounded HA artwork library. Only canonical PNGs reach the device route."""

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import hashlib
import hmac
from functools import wraps
from io import BytesIO
import math
import os
from pathlib import Path
import re
import secrets
import struct
import tempfile
import time
from urllib.parse import urlsplit
import warnings
import zlib

from PIL import Image, ImageCms, ImageOps

from .model import LayoutError, mapping

DATA_KEY = "esp_deck_artwork"
MAX_UPLOAD = 10 * 1024 * 1024
MAX_DIMENSION = 4096
MAX_PIXELS = 16_777_216
MAX_PNG = 32 * 1024
MAX_LIBRARY_BYTES = 64 * 1024 * 1024
MAX_SOURCES = 64
MAX_VARIANTS = 256
MAX_DECKS = 16
GRACE_SECONDS = 120
DEVICE_PATH = "/api/esp_deck/artwork/"
HASH = re.compile(r"[a-f0-9]{64}\Z")


def identifier(value):
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise LayoutError("invalid_artwork_id")
    return value


def origin(value, *, max_bytes=180):
    if not isinstance(value, str):
        raise LayoutError("invalid_artwork_origin")
    try:
        parsed = urlsplit(value)
        if (len(value) > max_bytes or not value.isascii() or any(ord(c) <= 32 or ord(c) == 127 for c in value)
                or parsed.scheme not in ("http", "https") or not parsed.hostname
                or not re.fullmatch(r"[A-Za-z0-9.-]+", parsed.hostname)
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ("", "/") or any(c in value for c in "\\?#")
                or (parsed.port is not None and not 1 <= parsed.port <= 65535)):
            raise ValueError
    except (TypeError, ValueError) as err:
        raise LayoutError("invalid_artwork_origin") from err
    return value.rstrip("/")


def transform_options(value):
    mapping(value, ("fit", "zoom", "x", "y"))
    result = {"fit": "contain", "zoom": 1, "x": 0, "y": 0, **value}
    if result["fit"] not in ("contain", "crop"):
        raise LayoutError("invalid_fit")
    for field, low, high in (("zoom", 1, 4), ("x", -1, 1), ("y", -1, 1)):
        item = result[field]
        if type(item) not in (int, float) or not math.isfinite(item) or not low <= item <= high:
            raise LayoutError("invalid_crop")
    return result


def normalize(payload, options):
    """Run exclusively in an executor, after bounding the encoded request."""
    options = transform_options(options)
    if not payload:
        raise LayoutError("invalid_image")
    if len(payload) > MAX_UPLOAD:
        raise LayoutError("upload_too_large")
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        at, chunks, seen_idat, ended = 8, 0, False, False
        view = memoryview(payload)
        while at < len(payload):
            if at + 12 > len(payload) or chunks >= 1024 or ended:
                raise LayoutError("invalid_image")
            size = struct.unpack_from(">I", payload, at)[0]
            kind = payload[at + 4:at + 8]
            if (at + size + 12 > len(payload)
                    or zlib.crc32(view[at + 4:at + 8 + size]) != struct.unpack_from(">I", payload, at + 8 + size)[0]):
                raise LayoutError("invalid_image")
            if chunks == 0 and (kind != b"IHDR" or size != 13):
                raise LayoutError("invalid_image")
            if kind in (b"acTL", b"fcTL", b"fdAT"):
                raise LayoutError("animated_image")
            if kind[:1].isupper() and kind not in (b"IHDR", b"PLTE", b"IDAT", b"IEND"):
                raise LayoutError("invalid_image")
            seen_idat |= kind == b"IDAT"
            ended = kind == b"IEND" and size == 0
            at += size + 12
            chunks += 1
        if not seen_idat or not ended:
            raise LayoutError("invalid_image")
    elif not (payload.startswith(b"\xff\xd8") and payload.endswith(b"\xff\xd9")):
        raise LayoutError("invalid_image")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with Image.open(BytesIO(payload), formats=("PNG", "JPEG")) as probe:
                width, height = probe.size
                if (width < 1 or height < 1 or max(width, height) > MAX_DIMENSION
                        or width * height > MAX_PIXELS):
                    raise LayoutError("image_dimensions_exceeded")
                if getattr(probe, "is_animated", False) or getattr(probe, "n_frames", 1) != 1:
                    raise LayoutError("animated_image")
                probe.verify()
            with Image.open(BytesIO(payload), formats=("PNG", "JPEG")) as source:
                source.load()  # Reject truncated JPEGs as well as PNG CRC failures.
                if raw_exif := source.info.get("exif"):
                    tiff = raw_exif[6:]
                    if (not raw_exif.startswith(b"Exif\x00\x00") or len(tiff) < 10
                            or tiff[:4] not in (b"II*\x00", b"MM\x00*")):
                        raise LayoutError("invalid_exif")
                    offset = struct.unpack_from("<I" if tiff[:2] == b"II" else ">I", tiff, 4)[0]
                    if not 8 <= offset <= len(tiff) - 2:
                        raise LayoutError("invalid_exif")
                exif = source.getexif()
                if exif.get(274, 1) not in range(1, 9):
                    raise LayoutError("invalid_exif")
                oriented = ImageOps.exif_transpose(source)
                rgba = oriented.convert("RGBA")
                if profile := source.info.get("icc_profile"):
                    rgb = ImageCms.profileToProfile(oriented.convert("RGB"),
                        ImageCms.ImageCmsProfile(BytesIO(profile)), ImageCms.createProfile("sRGB"), outputMode="RGB")
                    rgb.putalpha(rgba.getchannel("A"))
                    rgba = rgb
                scale = 72 / (max(rgba.size) if options["fit"] == "contain" else min(rgba.size)) * options["zoom"]
                # Offsets traverse the cropped (or padded) span; no huge intermediate raster.
                left = (rgba.width - 72 / scale) * (options["x"] + 1) / 2
                top = (rgba.height - 72 / scale) * (options["y"] + 1) / 2
                tile = rgba.convert("RGBa").transform((72, 72), Image.Transform.AFFINE,
                    (1 / scale, 0, left, 0, 1 / scale, top), Image.Resampling.BICUBIC).convert("RGBA")
                tile.info.clear()
                output = BytesIO()
                tile.save(output, format="PNG", compress_level=9)
                result = output.getvalue()
                if len(result) > MAX_PNG or result[28] != 0:
                    raise LayoutError("normalized_image_too_large")
                return result
    except LayoutError:
        raise
    except (OSError, ValueError, SyntaxError, Warning, ImageCms.PyCMSError) as err:
        raise LayoutError("invalid_image") from err


def asset_references(layout):
    if not layout:
        return set()
    result = set()
    from .model import all_keys
    for key in all_keys(layout):
        visuals = [key["visual"]]
        if key["state"]:
            visuals += [key["state"][state] for state in ("on", "off", "unavailable")]
        result.update(v["asset_id"] for v in visuals if v.get("asset_id"))
    return result


def saved_references(repository):
    return set().union(*(asset_references(repository.data[name]) for name in ("draft", "applied", "backup")))


def _write_new(path, payload):
    """Immutable files; replace only our own temporary file, never an existing asset."""
    if path.is_symlink() or path.parent.is_symlink():
        raise LayoutError("artwork_storage_invalid")
    if path.exists():
        if _read(path) != payload:
            raise LayoutError("artwork_storage_invalid")
        return False
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".upload-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def _read(path, limit=MAX_UPLOAD):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        return stream.read(limit + 1)


def finish_on_cancel(method):
    """Keep the conversion slot/transaction owned until its executor job retires."""
    @wraps(method)
    async def wrapped(*args, **kwargs):
        task = asyncio.create_task(method(*args, **kwargs))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not task.cancelled():
                task.exception()  # Retrieve a failure even when the caller went away.
            raise
    return wrapped


class ArtworkLibrary:
    def __init__(self, hass):
        from .storage import LayoutStore
        self.hass = hass
        self.store = LayoutStore(hass, 1, "esp_deck.artwork", private=True, atomic_writes=True)
        self.root = Path(hass.config.path("esp_deck_artwork"))
        self.data = {"decks": {}}
        self.lock = asyncio.Lock()
        self.conversion = asyncio.Semaphore(1)
        self.pending = 0
        self.leases = {}
        self.read_leases = {}
        self.invalid_window = (0, 0)

    async def load(self):
        existed = await self.hass.async_add_executor_job(os.path.exists, self.store.path)
        saved = await self.store.async_load()
        if existed and saved is None:
            raise LayoutError("artwork_storage_invalid")
        if saved is not None:
            try:
                mapping(saved, ("decks",), ("decks",))
                if not isinstance(saved["decks"], dict) or len(saved["decks"]) > MAX_DECKS:
                    raise ValueError
                for entry_id, deck in saved["decks"].items():
                    mapping(deck, ("token", "origin", "sources", "variants"),
                            ("token", "origin", "sources", "variants"))
                    identifier(deck["token"])
                    if deck["origin"]:
                        origin(deck["origin"])
                    for kind in ("sources", "variants"):
                        for asset_id, item in deck[kind].items():
                            identifier(asset_id)
                            if type(item["bytes"]) is not int or not 0 < item["bytes"] <= MAX_UPLOAD:
                                raise ValueError
                            if kind == "variants":
                                identifier(item["source_id"])
                                transform_options(item["transform"])
                                self.leases[entry_id, asset_id] = time.monotonic() + GRACE_SECONDS
                self._quota(saved)
            except (KeyError, TypeError, ValueError) as err:
                raise LayoutError("artwork_storage_invalid") from err
            self.data = saved
        await self.hass.async_add_executor_job(self._reconcile_files)

    def _directory(self, entry_id):
        return self.root / hashlib.sha256(entry_id.encode()).hexdigest()

    def path(self, entry_id, asset_id, *, source=False):
        identifier(asset_id)
        return self._directory(entry_id) / (f"s-{asset_id}" if source else f"v-{asset_id}.png")

    def _reconcile_files(self):
        if self.root.is_symlink():
            raise LayoutError("artwork_storage_invalid")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        expected = {self.path(entry, key, source=kind == "sources")
                    for entry, deck in self.data["decks"].items()
                    for kind in ("sources", "variants") for key in deck[kind]}
        directories = {self._directory(entry) for entry in self.data["decks"]}
        # Crash leftovers from an interrupted atomic metadata transaction are not a library.
        for directory in self.root.iterdir():
            if directory.is_symlink() or not directory.is_dir() or not HASH.fullmatch(directory.name):
                raise LayoutError("artwork_storage_invalid")
            for path in directory.iterdir():
                if path.is_symlink() or not path.is_file():
                    raise LayoutError("artwork_storage_invalid")
                if path not in expected:
                    if not (re.fullmatch(r"s-[a-f0-9]{64}|v-[a-f0-9]{64}\.png", path.name)
                            or path.name.startswith(".upload-")):
                        raise LayoutError("artwork_storage_invalid")
                    path.unlink()
            if directory not in directories:
                directory.rmdir()  # Removed entries must not accumulate empty directories.

    def _quota(self, data):
        decks = data["decks"].values()
        if (len(data["decks"]) > MAX_DECKS
                or sum(len(d["sources"]) for d in decks) > MAX_SOURCES
                or sum(len(d["variants"]) for d in decks) > MAX_VARIANTS
                or sum(item["bytes"] for d in decks for kind in ("sources", "variants")
                       for item in d[kind].values()) > MAX_LIBRARY_BYTES):
            raise LayoutError("artwork_library_full")

    async def _commit(self, data):
        self._quota(data)
        await self.store.async_save(deepcopy(data))
        self.data = data

    async def ensure(self, entry_id):
        async with self.lock:
            if entry_id in self.data["decks"]:
                return
            from homeassistant.helpers.network import NoURLAvailableError, get_url
            try:
                initial_origin = origin(get_url(self.hass, allow_external=False, allow_cloud=False))
            except (NoURLAvailableError, LayoutError):
                initial_origin = ""
            updated = deepcopy(self.data)
            updated["decks"][entry_id] = {"token": secrets.token_hex(32), "origin": initial_origin,
                                          "sources": {}, "variants": {}}
            await self._commit(updated)

    @asynccontextmanager
    async def slot(self):
        if self.pending >= 3:
            raise LayoutError("artwork_busy")
        self.pending += 1
        try:
            yield
        finally:
            self.pending -= 1

    @finish_on_cancel
    async def upload(self, entry_id, payload, options=None):
        # Caller reserves before reading the body: at most three 10 MiB bodies.
        async with self.conversion:
            png = await self.hass.async_add_executor_job(normalize, payload, options or {})
            return await self._insert(entry_id, payload, png, options or {})

    @finish_on_cancel
    async def variant(self, entry_id, source_id, options):
        identifier(source_id)
        options = transform_options(options)
        async with self.conversion, self.lock:
            if source_id not in self.data["decks"][entry_id]["sources"]:
                raise LayoutError("artwork_not_found")
            payload = await self.hass.async_add_executor_job(_read, self.path(entry_id, source_id, source=True))
            png = await self.hass.async_add_executor_job(normalize, payload, options)
            return await self._insert_locked(entry_id, payload, png, options)

    async def _insert(self, entry_id, payload, png, options):
        async with self.lock:
            return await self._insert_locked(entry_id, payload, png, options)

    async def _insert_locked(self, entry_id, payload, png, options):
        source_id, asset_id = hashlib.sha256(payload).hexdigest(), hashlib.sha256(png).hexdigest()
        updated = deepcopy(self.data)
        deck = updated["decks"][entry_id]
        deck["sources"][source_id] = {"bytes": len(payload)}
        deck["variants"][asset_id] = {"source_id": source_id, "bytes": len(png),
                                     "transform": transform_options(options)}
        self._quota(updated)
        # Fail admission if crash/failed-delete leftovers cannot be cleaned; they
        # must not accumulate outside the metadata quota on repeated attempts.
        await self.hass.async_add_executor_job(self._reconcile_files)
        created = []
        try:
            for path, content in ((self.path(entry_id, source_id, source=True), payload),
                                  (self.path(entry_id, asset_id), png)):
                if await self.hass.async_add_executor_job(_write_new, path, content):
                    created.append(path)
            await self._commit(updated)
        except BaseException:
            for path in created:
                await self.hass.async_add_executor_job(path.unlink, True)
            raise
        self.leases[entry_id, asset_id] = time.monotonic() + GRACE_SECONDS
        return {"asset_id": asset_id, "source_id": source_id, "bytes": len(png), "transform": transform_options(options)}

    def listing(self, entry_id, repository):
        deck = self.data["decks"][entry_id]
        refs = saved_references(repository)
        return {"origin": deck["origin"], "variants": [
            {"asset_id": key, **item, "referenced": key in refs} for key, item in deck["variants"].items()],
            "bytes": sum(item["bytes"] for kind in ("sources", "variants") for item in deck[kind].values()),
            "max_library_bytes": MAX_LIBRARY_BYTES}

    def validate(self, entry_id, layout):
        known = self.data["decks"][entry_id]["variants"]
        if asset_references(layout) - known.keys():
            raise LayoutError("artwork_not_found")

    def retain(self, entry_id, repository):
        for asset_id in saved_references(repository):
            self.leases[entry_id, asset_id] = time.monotonic() + GRACE_SECONDS
            self.read_leases[entry_id, asset_id] = time.monotonic() + GRACE_SECONDS

    def resolve(self, entry_id, visual):
        result = dict(visual)
        asset_id = result.pop("asset_id", "")
        if asset_id:
            deck = self.data["decks"][entry_id]
            if asset_id not in deck["variants"]:
                raise LayoutError("artwork_not_found")
            if not deck["origin"]:
                raise LayoutError("artwork_origin_required")
            self.leases[entry_id, asset_id] = time.monotonic() + GRACE_SECONDS
            result.update(image_url=f"{deck['origin']}{DEVICE_PATH}{deck['token']}/{asset_id}.png",
                          image_revision=asset_id)
        return result

    @finish_on_cancel
    async def configure(self, entry_id, value=None, *, revoke=False):
        async with self.lock:
            updated = deepcopy(self.data)
            deck = updated["decks"][entry_id]
            if value is not None:
                deck["origin"] = origin(value)
            if revoke:
                deck["token"] = secrets.token_hex(32)
            await self._commit(updated)

    def authorize(self, token, asset_id, repositories):
        # A global fixed-window bound avoids an unbounded per-IP dictionary.
        now = int(time.monotonic() // 60)
        window, failures = self.invalid_window
        if now != window:
            failures = 0
        if HASH.fullmatch(token) and HASH.fullmatch(asset_id):
            for entry_id, deck in self.data["decks"].items():
                if hmac.compare_digest(token, deck["token"]):
                    repo = repositories.get(entry_id)
                    referenced = repo is not None and asset_id in saved_references(repo)
                    retained = self.read_leases.get((entry_id, asset_id), 0) > time.monotonic()
                    if asset_id in deck["variants"] and (referenced or retained):
                        return entry_id
        self.invalid_window = (now, failures + 1)
        if failures >= 120:
            raise LayoutError("artwork_rate_limited")
        raise LayoutError("artwork_not_found")

    async def read(self, entry_id, asset_id):
        identifier(asset_id)
        async with self.lock:
            if asset_id not in self.data["decks"][entry_id]["variants"]:
                raise LayoutError("artwork_not_found")
            result = await self.hass.async_add_executor_job(_read, self.path(entry_id, asset_id), MAX_PNG)
            if len(result) > MAX_PNG or hashlib.sha256(result).hexdigest() != asset_id:
                raise LayoutError("artwork_storage_invalid")
            # A response owns these bytes, even if GC/revocation runs while it drains.
            return result

    @finish_on_cancel
    async def collect(self, entry_id, repository, *, asset_id=None):
        async with self.lock:
            refs = saved_references(repository)
            updated = deepcopy(self.data)
            deck = updated["decks"][entry_id]
            candidates = [identifier(asset_id)] if asset_id else list(deck["variants"])
            removed = []
            for key in candidates:
                if key in refs or self.leases.get((entry_id, key), 0) > time.monotonic():
                    if asset_id:
                        raise LayoutError("artwork_in_use")
                    continue
                if deck["variants"].pop(key, None):
                    removed.append(self.path(entry_id, key))
            sources = {v["source_id"] for v in deck["variants"].values()}
            for key in list(deck["sources"]):
                if key not in sources:
                    del deck["sources"][key]
                    removed.append(self.path(entry_id, key, source=True))
            await self._commit(updated)
            for key in candidates:
                if key not in deck["variants"]:
                    self.leases.pop((entry_id, key), None)
                    self.read_leases.pop((entry_id, key), None)
            for path in removed:
                await self.hass.async_add_executor_job(path.unlink, True)
            return {"removed_files": len(removed)}

    async def remove_entry(self, entry_id):
        async with self.lock:
            updated = deepcopy(self.data)
            deck = updated["decks"].pop(entry_id, None)
            if deck is None:
                return
            await self._commit(updated)  # Revoke first, then remove exact owned files.
            for key in deck["variants"]:
                self.leases.pop((entry_id, key), None)
                self.read_leases.pop((entry_id, key), None)
            for kind in ("sources", "variants"):
                for key in deck[kind]:
                    await self.hass.async_add_executor_job(self.path(entry_id, key, source=kind == "sources").unlink, True)
            await self.hass.async_add_executor_job(self._reconcile_files)
