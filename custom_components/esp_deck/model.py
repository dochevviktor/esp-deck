"""Bounded, JSON-only HA layout model. No firmware or HA imports."""

from copy import deepcopy
import json
import math
import re
from urllib.parse import urlsplit

from .const import DEFAULT_VISUAL, KEY_COUNT, MAX_LAYOUT_BYTES


class LayoutError(ValueError):
    """An error code safe to expose without echoing configuration or URLs."""


def bounded_json(value, limit=MAX_LAYOUT_BYTES):
    """Reject deep/non-JSON structures before serializing or copying them."""
    remaining = 8192

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
    mapping(value, DEFAULT_VISUAL)
    result = dict(value) if partial else {**DEFAULT_VISUAL, **value}
    for field, item in result.items():
        if field == "font":
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
    if "image_revision" in result and "image_url" not in result:
        raise LayoutError("invalid_image")
    if "image_url" in result:
        url, revision = result["image_url"], result.get("image_revision", "")
        if not url:
            if revision:
                raise LayoutError("invalid_image")
            result["image_revision"] = ""
        else:
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
    mapping(value, ("visual", "mode", "press", "release", "state"))
    mode = value.get("mode", "managed")
    if mode not in ("managed", "automation"):
        raise LayoutError("invalid_mode")
    result = {"visual": visual(value.get("visual", {})), "mode": mode,
              "press": action(value.get("press")), "release": action(value.get("release")), "state": None}
    if mode == "automation" and (result["press"] or result["release"]):
        raise LayoutError("competing_bindings")
    if (rule := value.get("state")) is not None:
        mapping(rule, ("entity", "on", "off", "unavailable"), ("entity",))
        result["state"] = {"entity": entity_ref(rule["entity"]),
                           **{state: visual(rule.get(state, {}), partial=True)
                              for state in ("on", "off", "unavailable")}}
    return result


def validate_layout(value):
    bounded_json(value)
    mapping(value, ("version", "keys"), ("version", "keys"))
    if type(value["version"]) is not int or value["version"] != 1:
        raise LayoutError("unsupported_layout_version")
    if not isinstance(value["keys"], list) or len(value["keys"]) != KEY_COUNT:
        raise LayoutError("expected_15_keys")
    return {"version": 1, "keys": [key_config(key) for key in value["keys"]]}


def empty_layout():
    return validate_layout({"version": 1, "keys": [{} for _ in range(KEY_COUNT)]})


def references(layout):
    """Yield mutable references for registry pinning and rename-aware export."""
    for key in layout["keys"]:
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
