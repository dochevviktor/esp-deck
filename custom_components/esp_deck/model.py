"""Bounded, JSON-only HA layout model. No firmware or HA imports."""

from copy import deepcopy
import json
import math
import re
from urllib.parse import urlsplit

from .const import DEFAULT_VISUAL, POSITION_DEFAULTS, KEY_COUNT, MAX_LAYOUT_BYTES


class LayoutError(ValueError):
    """An error code safe to expose without echoing configuration or URLs."""


def bounded_json(value, limit=MAX_LAYOUT_BYTES):
    """Reject deep/non-JSON structures before serializing or copying them."""
    remaining = 32768

    def visit(item, depth=0):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 12:
            raise LayoutError("layout_too_large")
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise LayoutError("invalid_json")
                visit(key, depth + 1)
                visit(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                visit(child, depth + 1)
        elif isinstance(item, str):
            if len(item) > limit:
                raise LayoutError("layout_too_large")
        elif item is not None and type(item) not in (int, float, bool):
            raise LayoutError("invalid_json")
        elif isinstance(item, float) and not math.isfinite(item):
            raise LayoutError("invalid_json")

    visit(value)
    try:
        if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")) > limit:
            raise LayoutError("layout_too_large")
    except (UnicodeError, ValueError, OverflowError) as err:
        raise LayoutError("invalid_json") from err


def mapping(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise LayoutError("invalid_fields")
    return value


def entity_ref(value):
    if isinstance(value, str):
        value = {"entity_id": value}
    mapping(value, ("entity_id", "registry_id"), ("entity_id",))
    if not isinstance(value["entity_id"], str) or not re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", value["entity_id"]):
        raise LayoutError("invalid_entity")
    if "registry_id" in value and (not isinstance(value["registry_id"], str)
                                    or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", value["registry_id"])):
        raise LayoutError("invalid_entity")
    return dict(value)


def visual(value, *, partial=False):
    mapping(value, (*DEFAULT_VISUAL, *POSITION_DEFAULTS, "asset_id"))
    result = dict(value) if partial else {**DEFAULT_VISUAL, "asset_id": "", **value}
    if "asset_id" in result:
        if not isinstance(result["asset_id"], str) or (result["asset_id"] and not re.fullmatch(r"[a-f0-9]{64}", result["asset_id"])):
            raise LayoutError("invalid_artwork_id")
        if result["asset_id"]:
            if result.get("image_url") or result.get("image_revision"):
                raise LayoutError("ambiguous_image")
            result.update(image_url="", image_revision="")
    if "image_url" in value and not value.get("asset_id"):
        result["asset_id"] = ""
    for field, item in result.items():
        if field in POSITION_DEFAULTS:
            if type(item) is not int:
                raise LayoutError("invalid_position")
        elif field == "font":
            if type(item) is not int or item not in (12, 16, 20):
                raise LayoutError("invalid_font")
        elif not isinstance(item, str):
            raise LayoutError("invalid_visual")
        elif field.endswith("_color"):
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", item):
                raise LayoutError("invalid_color")
            result[field] = item.upper()
        elif field == "fit" and item not in ("contain", "crop"):
            raise LayoutError("invalid_fit")
        elif field == "text":
            if len(item) > 48 or len(item.encode("utf-8")) > 96 or any(
                (ord(c) < 32 and c != "\n") or 127 <= ord(c) < 160 for c in item
            ):
                raise LayoutError("invalid_text")
    box = {**POSITION_DEFAULTS, **{k: v for k, v in result.items() if k in POSITION_DEFAULTS}}
    if not (0 <= box["text_x"] <= 48 and 0 <= box["text_y"] <= 71
            and 24 <= box["text_width"] <= (72 if partial else 72 - box["text_x"])
            and 1 <= box["text_height"] <= (72 if partial else 72 - box["text_y"])
            and box["text_align"] in (0, 1, 2) and box["text_valign"] in (0, 1, 2)):
        raise LayoutError("invalid_position")
    if "image_revision" in result and "image_url" not in result:
        raise LayoutError("invalid_image")
    if "image_url" in result:
        url, revision = result["image_url"], result.get("image_revision", "")
        if not url:
            if revision:
                raise LayoutError("invalid_image")
            result["image_revision"] = ""
        else:
            if "/api/esp_deck/artwork/" in url:
                raise LayoutError("use_artwork_reference")
            if not re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", revision):
                raise LayoutError("invalid_image")
            if (len(url) > 512 or not url.isascii() or any(ord(c) <= 32 or ord(c) == 127 for c in url)
                    or any(c in url for c in "\\?#") or re.search(r"%(?![a-fA-F0-9]{2})", url)):
                raise LayoutError("invalid_url")
            try:
                parsed = urlsplit(url)
                if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username
                        or parsed.password or not re.fullmatch(r"[A-Za-z0-9.-]+", parsed.hostname)
                        or (parsed.port is not None and not 1 <= parsed.port <= 65535)):
                    raise ValueError
            except ValueError as err:
                raise LayoutError("invalid_url") from err
    return result


def action(value):
    if value is None:
        return None
    mapping(value, ("action", "target", "data"), ("action",))
    name = value["action"]
    if not isinstance(name, str) or not re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", name) or name.startswith("esp_deck."):
        raise LayoutError("invalid_action")
    data = value.get("data", {})
    if not isinstance(data, dict) or "entity_id" in data:
        raise LayoutError("use_entity_target")
    bounded_json(data, 4096)
    target = value.get("target", {})
    mapping(target, ("entity_id",))
    refs = target.get("entity_id", [])
    if isinstance(refs, (str, dict)):
        refs = [refs]
    if not isinstance(refs, list) or len(refs) > 16:
        raise LayoutError("invalid_target")
    return {"action": name, "data": deepcopy(data), "target": {"entity_id": [entity_ref(ref) for ref in refs]}}


def key_config(value):
    mapping(value, ("visual", "mode", "press", "release", "state", "navigation"))
    mode = value.get("mode", "managed")
    if mode not in ("managed", "automation"):
        raise LayoutError("invalid_mode")
    result = {"visual": visual(value.get("visual", {})), "mode": mode,
              "press": action(value.get("press")), "release": action(value.get("release")), "state": None}
    if mode == "automation" and (result["press"] or result["release"]):
        raise LayoutError("competing_bindings")
    if value.get("navigation") is not None:
        nav = mapping(value["navigation"], ("kind", "target"), ("kind", "target"))
        if nav["kind"] not in ("page", "overlay", "momentary") or not valid_name(nav["target"]):
            raise LayoutError("invalid_navigation")
        if mode != "managed" or result["press"] or result["release"]:
            raise LayoutError("competing_bindings")
        result["navigation"] = dict(nav)
    if (rule := value.get("state")) is not None:
        mapping(rule, ("entity", "on", "off", "unavailable"), ("entity",))
        result["state"] = {"entity": entity_ref(rule["entity"]),
                           **{state: visual(rule.get(state, {}), partial=True)
                              for state in ("on", "off", "unavailable")}}
        for state in ("on", "off", "unavailable"):
            visual({**result["visual"], **result["state"][state]})
    return result


def validate_layout(value):
    bounded_json(value)
    if isinstance(value, dict) and type(value.get("version")) is int and value["version"] == 2:
        return validate_pages(value)
    mapping(value, ("version", "keys"), ("version", "keys"))
    if type(value["version"]) is not int or value["version"] != 1:
        raise LayoutError("unsupported_layout_version")
    if not isinstance(value["keys"], list) or len(value["keys"]) != KEY_COUNT:
        raise LayoutError("expected_15_keys")
    return {"version": 1, "keys": [key_config(key) for key in value["keys"]]}


def valid_name(value):
    return isinstance(value, str) and re.fullmatch(r"[a-z0-9_]{1,32}", value)


def validate_pages(value):
    mapping(value, ("version", "pages", "overlays", "default_page"), ("pages", "default_page"))
    if not isinstance(value["pages"], list) or not 1 <= len(value["pages"]) <= 8:
        raise LayoutError("page_limit")
    overlays = value.get("overlays", [])
    if not isinstance(overlays, list) or len(overlays) > 4:
        raise LayoutError("overlay_limit")
    result = {"version": 2, "pages": [], "overlays": [], "default_page": value["default_page"]}
    for kind, records in (("pages", value["pages"]), ("overlays", overlays)):
        ids = set()
        for item in records:
            mapping(item, ("id", "name", "keys"), ("id", "name", "keys"))
            if (not valid_name(item["id"]) or item["id"] in ids or not isinstance(item["name"], str)
                    or not 1 <= len(item["name"]) <= 48 or any(ord(c) < 32 for c in item["name"])):
                raise LayoutError("invalid_page")
            ids.add(item["id"])
            if kind == "pages":
                if not isinstance(item["keys"], list) or len(item["keys"]) != KEY_COUNT:
                    raise LayoutError("expected_15_keys")
                keys = [key_config(key) for key in item["keys"]]
            else:
                if (not isinstance(item["keys"], dict) or
                        any(key not in {str(k) for k in range(KEY_COUNT)} for key in item["keys"])):
                    raise LayoutError("invalid_overlay")
                keys = {key: key_config(tile) if tile is not None else None for key, tile in item["keys"].items()}
            result[kind].append({"id": item["id"], "name": item["name"], "keys": keys})
    pages = {page["id"] for page in result["pages"]}
    layers = {layer["id"] for layer in result["overlays"]}
    if not valid_name(result["default_page"]) or result["default_page"] not in pages:
        raise LayoutError("invalid_page")
    for key in all_keys(result):
        if nav := key.get("navigation"):
            if nav["target"] not in (pages if nav["kind"] == "page" else layers):
                raise LayoutError("invalid_navigation_target")
    return result


def all_keys(layout):
    if layout["version"] == 1:
        yield from layout["keys"]
    else:
        for page in layout["pages"]:
            yield from page["keys"]
        for layer in layout["overlays"]:
            yield from (key for key in layer["keys"].values() if key is not None)


def resolve_keys(layout, page=None, overlay=None):
    if layout["version"] == 1:
        return layout["keys"]
    page = page or layout["default_page"]
    selected = next((item for item in layout["pages"] if item["id"] == page), None)
    if selected is None:
        raise LayoutError("invalid_page")
    if not overlay:
        return selected["keys"]
    keys = list(selected["keys"])
    if overlay:
        layer = next((item for item in layout["overlays"] if item["id"] == overlay), None)
        if layer is None:
            raise LayoutError("invalid_overlay")
        for index, config in layer["keys"].items():
            keys[int(index)] = config if config is not None else key_config({})
    return keys


def require_capabilities(layout, capabilities):
    if layout["version"] == 2 and capabilities.get("input_correlation") != "pull_context_v2":
        raise LayoutError("firmware_upgrade_required")
    for key in all_keys(layout):
        if key.get("navigation") and layout["version"] != 2:
            raise LayoutError("navigation_requires_pages")
        for appearance in (key["visual"], *((key["state"] or {}).get(s, {}) for s in ("on", "off", "unavailable"))):
            if not capabilities.get("positioning") and any(
                    field in appearance and appearance[field] != default for field, default in POSITION_DEFAULTS.items()):
                raise LayoutError("firmware_upgrade_required")


def empty_layout():
    return validate_layout({"version": 1, "keys": [{} for _ in range(KEY_COUNT)]})


def references(layout):
    """Yield mutable references for registry pinning and rename-aware export."""
    for key in all_keys(layout):
        if key["state"]:
            yield key["state"]["entity"]
        for edge in ("press", "release"):
            if key[edge]:
                yield from key[edge]["target"]["entity_id"]


def entity_preset(entity, label):
    """Simple actual-state presets; complex logic stays in HA scripts."""
    ref = entity_ref(entity)
    domain = ref["entity_id"].split(".", 1)[0]
    if domain not in ("light", "switch", "input_boolean", "script", "scene"):
        raise LayoutError("unsupported_preset")
    toggle = domain in ("light", "switch", "input_boolean")
    key = {"visual": {"text": label}, "press": {
        "action": f"{domain}.{'toggle' if toggle else 'turn_on'}", "target": {"entity_id": ref},
    }}
    if toggle:
        key["state"] = {"entity": ref, "on": {"background_color": "#176B32"},
                        "off": {"background_color": "#202020"},
                        "unavailable": {"background_color": "#5C2525", "text": "Unavailable"}}
    return key_config(key)
