#!/usr/bin/env python3
"""Supervised physical-deck controls in the dedicated HA hardware lab.

setup pairs no new device; it selects the already paired ESP and installs a
bounded test layout. All bindings target synthetic lab entities. No synthetic
key input, automatic physical reboot, flash or power operation is performed.
"""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import time
import urllib.request
import urllib.error

try:
    from .ha_bench import lab
except ImportError:
    from ha_bench import lab


def entry_id():
    entries = [entry for entry in lab.request("/api/config/config_entries/entry") if entry["domain"] == "esp_deck"]
    if len(entries) != 1:
        raise RuntimeError("Expected exactly one ESP Deck controller in the hardware lab")
    return entries[0]["entry_id"]


def command(operation, **parameters):
    response = lab.request(f"/api/services/esp_deck/{operation}?return_response",
                           {"entry_id": entry_id(), **parameters})
    return response["service_response"]


def ready(timeout=60):
    return lab.wait_for(lambda: result if (result := command("status"))["state"] == "ready" else None,
                        timeout=timeout, description="physical USB-applied tiles")


def save_apply(layout):
    current = command("get_layout")
    saved = command("save_layout", layout=layout, expected_revision=current["draft_revision"])
    command("apply_layout", expected_revision=saved["draft_revision"])
    return ready()


def setup():
    entries = lab.request("/api/config/config_entries/entry")
    if not any(entry["domain"] == "esp_deck" for entry in entries):
        flow = lab.request("/api/config/config_entries/flow", {"handler": "esp_deck", "show_advanced_options": False})
        choices = next(field for field in flow["data_schema"] if field["name"] == "device_id")["selector"]["select"]["options"]
        if len(choices) != 1:
            raise RuntimeError("Hardware lab must offer exactly one ESPHome device")
        flow = lab.request("/api/config/config_entries/flow/" + flow["flow_id"], {"device_id": choices[0]["value"]})
        if flow.get("step_id") != "handoff" or flow.get("errors"):
            raise RuntimeError("Physical ESP runtime compatibility check failed")
        flow = lab.request("/api/config/config_entries/flow/" + flow["flow_id"], {
            "exclusive_control": True, "preset_entity": "light.example_lamp", "label": "Light"})
        if flow.get("type") != "create_entry":
            raise RuntimeError("Physical ESP controller setup failed")
    ready()
    main = [{"visual": {"text": str(key + 1), "font": (12, 16, 20)[key // 5],
              "background_color": ("#24374B", "#245D44", "#64412C")[key // 5]}, "mode": "automation"}
            for key in range(15)]
    main[0] = command("preset", entity_id="light.example_lamp", label="Light")["key"]
    main[0]["state"]["on"]["text"] = "Light ON"
    main[0]["state"]["off"]["text"] = "Light OFF"
    main[1] = {"visual": {"text": "Page 2", "background_color": "#234F72"},
               "navigation": {"kind": "page", "target": "second"}}
    main[2] = {"visual": {"text": "Hold", "background_color": "#624286"},
               "navigation": {"kind": "momentary", "target": "shift"}}
    main[3]["visual"].update(text="TOP LEFT", text_x=0, text_y=0, text_width=72, text_height=72,
                              text_align=0, text_valign=0)
    second = deepcopy(main)
    for key in range(3, 15):
        second[key]["visual"].update(text=f"P2 {key + 1}", background_color="#7C293E")
    second[1] = {"visual": {"text": "Main", "background_color": "#234F72"},
                 "navigation": {"kind": "page", "target": "main"}}
    layout = {"version": 2, "default_page": "main", "pages": [
        {"id": "main", "name": "Main", "keys": main}, {"id": "second", "name": "Second", "keys": second}],
        "overlays": [{"id": "shift", "name": "Shift", "keys": {"3": {"visual": {
            "text": "SHIFT", "background_color": "#854A12"}, "mode": "automation"}}}]}
    started = time.monotonic()
    status = save_apply(layout)
    report = {"state": status["state"], "protocol_version": status["capabilities"]["protocol_version"],
        "applied_tiles": sum(tile.get("applied_revision", 0) == tile.get("revision") for tile in status["tiles"]),
        "apply_to_status_seconds": round(time.monotonic() - started, 3), "display_readback": False}
    lab.private_write(lab.LAB / "physical-setup.json", json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


def provision(origin=None):
    address = origin or command("artwork_list")["origin"]
    if not address:
        raise RuntimeError("Select a device-reachable artwork origin first")
    result = command("artwork_configure", origin=address)
    print(json.dumps({"verified_origin": result["origin"]}))


def artwork():
    payload = (lab.ROOT / "assets/source/transport_test.png").read_bytes()
    request = urllib.request.Request(lab.URL + "/api/esp_deck/upload/" + entry_id(), payload, {
        "Content-Type": "image/png", "Authorization": "Bearer " + lab.credentials()["access_token"]})
    with urllib.request.urlopen(request, timeout=30) as response:
        asset = json.load(response)
    layout = command("get_layout")["draft"]
    # Three corners/center give asymmetric artwork, combined text and a retained
    # text-only key. Content hashes are the only saved image reference.
    for key, text in ((4, ""), (7, "Artwork"), (14, "Bottom")):
        layout["pages"][0]["keys"][key]["visual"].update(asset_id=asset["asset_id"], image_url="",
                                                        image_revision="", text=text)
    started = time.monotonic()
    status = save_apply(layout)
    print(json.dumps({"asset_id": asset["asset_id"], "state": status["state"],
                      "apply_to_status_seconds": round(time.monotonic() - started, 3)}))


def status():
    result = command("status")
    print(json.dumps({key: result[key] for key in (
        "state", "connected", "error", "binding_error", "binding_count", "active_page", "active_overlay")}, indent=2))


def main():
    global lab
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("setup", "status", "provision", "artwork"))
    parser.add_argument("--instance", choices=("lab", "bench"), required=True,
                        help="explicitly select HA 18123 (lab) or HA 18124 (bench)")
    parser.add_argument("--origin", help="provision only: exact HA address reachable from the ESP")
    args = parser.parse_args()
    if args.origin and args.command != "provision":
        parser.error("--origin is only valid with provision")
    if args.instance == "lab":
        try:
            from . import ha_lab as selected
        except ImportError:
            import ha_lab as selected
        lab = selected
    lab.owned_directory()
    lab.refresh_token()
    if args.command == "provision":
        provision(args.origin)
    else:
        globals()[args.command]()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        details = repr(error)
        if isinstance(error, urllib.error.HTTPError):
            details += "\n" + error.read().decode(errors="replace")
        lab.private_write(lab.LAB / "last-control-error.txt", details)
        print(f"Hardware test operation failed ({type(error).__name__}); details retained privately")
        raise SystemExit(1) from None
