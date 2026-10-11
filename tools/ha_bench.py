#!/usr/bin/env python3
"""Separate, explicit LAN-facing HA lab for the owner's physical ESP Deck.

No virtual deck or manual replay automations run here. Fresh lab credentials and
the installed integration stay under private .build/ha-bench. Only pair reads the
local ESP API key; no real credentials enter the synthetic regression lab.
"""
import argparse
import fcntl
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import urllib.parse
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("_esp_deck_physical_lab", ROOT / "tools/ha_lab.py")
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)
lab.LAB = ROOT / ".build/ha-bench"
lab.PREFIX = lab.PREFIX.replace("-lab-", "-bench-")
lab.URL = "http://127.0.0.1:18124"


def settings():
    return json.loads((lab.LAB / "settings.json").read_text())


def validate_settings(bind, origin, device):
    for value in (bind, device):
        address = ipaddress.IPv4Address(value)
        if address.is_unspecified or address.is_multicast or address.is_loopback or not address.is_private:
            raise ValueError("Bench bind and device must be explicit private IPv4 addresses")
    parsed = urllib.parse.urlsplit(origin)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ("", "/") or len(origin) > 180):
        raise ValueError("Artwork origin must be an exact HTTP(S) address without credentials/path/query")
    # Verifies the bind address belongs to this machine without changing routes.
    with socket.socket() as endpoint:
        endpoint.bind((bind, 0))
    return {"bind": bind, "asset_origin": origin.rstrip("/"), "device": device, "port": 18124}


def stage(configured):
    try:
        from .package_release import build
    except ImportError:
        from package_release import build
    lab.owned_directory()
    if not (lab.LAB / "credentials.json").exists():
        lab.private_write(lab.LAB / "credentials.json", json.dumps({
            "username": "deck_bench", "password": secrets.token_urlsafe(32)}))
    config = lab.LAB / "config"
    config.mkdir(exist_ok=True)
    # Reuse only synthetic entities; exclude P4 replay/writers and all virtual
    # controls. The managed integration will be the sole physical visual writer.
    class LabLoader(yaml.SafeLoader):
        pass
    LabLoader.add_constructor("!include", lambda loader, node: node.value)
    document = yaml.load((ROOT / "tests/ha_lab/configuration.yaml").read_text(), Loader=LabLoader)
    document.pop("script")
    document.pop("automation")
    document["homeassistant"].update(name="ESP Deck Hardware Lab", internal_url=configured["asset_origin"])
    lab.private_write(config / "configuration.yaml", yaml.safe_dump(document, sort_keys=False))
    lab.ARTIFACT = build()
    lab.stage_integration(config / "custom_components")
    lab.private_write(lab.LAB / "settings.json", json.dumps(configured, indent=2) + "\n")


def up(configured):
    item = lab.inspect_owned("container", lab.PREFIX + "-ha")
    if item and item["State"]["Running"]:
        if configured != settings():
            raise RuntimeError("Run down before changing the hardware lab's network settings")
        print("Reusing running hardware HA lab")
    else:
        if item:
            lab.podman("rm", lab.PREFIX + "-ha")
        stage(configured)
        if not lab.inspect_owned("network", lab.PREFIX):
            lab.podman("network", "create", "--label", f"{lab.LABEL}={lab.OWNER}", lab.PREFIX)
        lab.start_container("ha", lab.ensure_image("home_assistant"), [
            "-p", "127.0.0.1:18124:8123", "-p", f"{configured['bind']}:18124:8123",
            "-v", f"{lab.LAB / 'config'}:/config:Z", "--entrypoint", "python"])
    if "refresh_token" not in lab.credentials():
        lab.onboard()
    else:
        lab.wait_for(lambda: urllib.request.urlopen(lab.URL + "/", timeout=2).status == 200)
        lab.refresh_token()
    print(f"Hardware HA ready: {configured['bind']}:18124; artwork origin {configured['asset_origin']}")
    print("Not paired yet. Use pair after the requested firmware deployment. Credentials remain private.")


def pair():
    lab.owned_directory()
    configured = settings()
    lab.refresh_token()
    entries = lab.request("/api/config/config_entries/entry")
    existing = [entry for entry in entries if entry["domain"] == "esphome"]
    if not existing:
        key = yaml.safe_load((ROOT / "examples/secrets.yaml").read_text())["api_encryption_key"]
        flow = lab.request("/api/config/config_entries/flow", {"handler": "esphome", "show_advanced_options": False})
        flow = lab.request("/api/config/config_entries/flow/" + flow["flow_id"], {"host": configured["device"], "port": 6053})
        if flow.get("step_id") == "encryption_key":
            flow = lab.request("/api/config/config_entries/flow/" + flow["flow_id"], {"noise_psk": key})
        if flow.get("type") != "create_entry":
            raise RuntimeError("Physical ESPHome pairing did not complete")
    elif len(existing) != 1:
        raise RuntimeError("Hardware lab must have exactly one ESPHome entry")
    lab.wait_for(lambda: any(group["domain"] == "esphome" and
        "streamdeck_original_get_deck_capabilities" in group["services"]
        for group in lab.request("/api/services")), description="physical runtime v2 actions")
    print("Physical runtime paired through HA's encrypted ESPHome integration")


def down():
    item = lab.inspect_owned("container", lab.PREFIX + "-ha")
    if item:
        lab.podman("stop", "--time", "10", lab.PREFIX + "-ha")
        lab.podman("rm", lab.PREFIX + "-ha")
    if lab.inspect_owned("network", lab.PREFIX):
        lab.podman("network", "rm", lab.PREFIX)
    print("Hardware lab stopped; private config and credentials retained")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("up", "pair", "status", "down"))
    parser.add_argument("--bind")
    parser.add_argument("--asset-origin")
    parser.add_argument("--device")
    args = parser.parse_args()
    if args.command == "up" and not all((args.bind, args.asset_origin, args.device)):
        parser.error("up requires --bind, --asset-origin and --device")
    lab.owned_directory()
    with (ROOT / ".build/ha-bench.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == "up":
            up(validate_settings(args.bind, args.asset_origin, args.device))
        elif args.command == "status":
            item = lab.inspect_owned("container", lab.PREFIX + "-ha")
            print(json.dumps({"state": item["State"]["Status"] if item else "absent",
                              "settings": settings() if (lab.LAB / "settings.json").exists() else None}))
        else:
            globals()[args.command]()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        lab.owned_directory()
        lab.private_write(lab.LAB / "last-error.txt", repr(error))
        print(f"Hardware lab operation failed ({type(error).__name__}); see private .build/ha-bench/last-error.txt")
        raise SystemExit(1) from None
