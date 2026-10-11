#!/usr/bin/env python3
"""Private, rootless P5 lab. Never reads examples/secrets.yaml or talks to an ESP.

The only published port is the HA UI on 127.0.0.1:18123. All resources carry a
repository-specific ownership label, checked before reuse, restart or removal.
down removes the two lab containers/network and retains private config/results.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / ".build/ha-lab"
FIXTURES = ROOT / "tests/ha_lab"
LOCK = json.loads((FIXTURES / "versions.json").read_text())
OWNER = hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
PREFIX = f"esp-deck-lab-{OWNER}"
LABEL = "io.esp-deck.lab"
URL = "http://127.0.0.1:18123"
PORTABLE = ("protocol", "runtime_image", "scheduler", "visual_state", "visual_api",
            "asset_policy", "asset_pipeline", "asset_png", "renderer", "render_font")


def podman(*args, check=True, log=None):
    result = subprocess.run(["podman", *map(str, args)], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if log:
        log.write_text(result.stdout)
        log.chmod(0o600)
    if check and result.returncode:
        # Runtime/build output may contain generated credentials. Keep it private.
        if not log and LAB.is_dir():
            private_write(LAB / "last-command.log", result.stdout)
        raise RuntimeError(f"Podman {args[0]} failed; see {log or LAB / 'last-command.log'}")
    return result


def private_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(content)
    path.chmod(0o600)


def owned_directory():
    if LAB.is_symlink() or LAB.parent.is_symlink():
        raise RuntimeError("Refusing a symlinked lab directory")
    LAB.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = LAB / "owner.json"
    expected = {"repository": str(ROOT), "owner": OWNER}
    if marker.exists():
        if json.loads(marker.read_text()) != expected:
            raise RuntimeError("Lab directory ownership mismatch")
    elif any(LAB.iterdir()):
        raise RuntimeError("Refusing an existing unmarked lab directory")
    else:
        private_write(marker, json.dumps(expected))
    LAB.chmod(0o700)


def inspect_owned(kind, name):
    result = podman(kind, "inspect", name, check=False)
    if result.returncode:
        # Do not treat a Podman malfunction/permission failure as absence.
        exists = podman(kind, "exists", name, check=False)
        if exists.returncode == 1:
            return None
        raise RuntimeError(f"Cannot inspect {kind} {name}")
    item = json.loads(result.stdout)[0]
    labels = item.get("labels", {}) if kind == "network" else item["Config"].get("Labels", {})
    if (labels or {}).get(LABEL) != OWNER:
        raise RuntimeError(f"Refusing unowned {kind}: {name}")
    return item


def wait_for(function, *, timeout=120, description="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = function()
            if result:
                return result
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(0.3)
    raise RuntimeError(f"Timed out waiting for {description}")


def credentials():
    return json.loads((LAB / "credentials.json").read_text())


def request(path, data=None, *, method=None, auth=True):
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = "Bearer " + credentials()["access_token"]
    req = urllib.request.Request(URL + path, None if data is None else json.dumps(data).encode(),
                                 headers, method=method)
    with urllib.request.urlopen(req, timeout=75) as response:
        return json.load(response)


def stage():
    import yaml
    owned_directory()
    if not (LAB / "credentials.json").exists():
        private_write(LAB / "credentials.json", json.dumps({
            "username": "deck_lab", "password": secrets.token_urlsafe(32),
            "api_encryption_key": base64.b64encode(secrets.token_bytes(32)).decode(),
        }))
    host = LAB / "deck"
    component = host / "components/virtual_deck"
    component.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURES / "components/virtual_deck", component, dirs_exist_ok=True)
    production = ROOT / "components/stream_deck"
    for stem in PORTABLE:
        for extension in (".h", ".cpp"):
            shutil.copy2(production / (stem + extension), component)
    for name in ("asset_fetch.h", "asset_memory.h", "asset_inflate.h", "asset_inflate.c", "render_font_data.cpp"):
        shutil.copy2(production / name, component)
    shutil.copytree(production / "third_party", component / "third_party", dirs_exist_ok=True)
    shutil.copy2(FIXTURES / "host.yaml", host / "host.yaml")
    shutil.copy2(FIXTURES / "fetch_asset.py", host / "fetch_asset.py")
    shutil.copy2(FIXTURES / "native_probe.py", host / "native_probe.py")
    # Reuse action definitions and their C++ lambdas byte-for-byte. Only the
    # ESP32-specific stream_deck schema entry is replaced by the host adapter.
    package = (ROOT / "examples/packages/runtime_api.yaml").read_text()
    private_write(host / "runtime_api.yaml", "api:\n" + package.split("\napi:\n", 1)[1])
    private_write(host / "secrets.yaml", yaml.safe_dump({"api_encryption_key": credentials()["api_encryption_key"]}))
    config = LAB / "config"
    config.mkdir(exist_ok=True)
    scripts = {}
    for name in ("visual_patch.yaml", "runtime_scripts.yaml"):
        scripts.update(yaml.safe_load((ROOT / "examples/home_assistant" / name).read_text()))
    scripts["stream_deck_sync_layout"]["sequence"][0]["variables"]["artwork_base"] = "http://ha:8123/local/streamdeck"
    private_write(config / "scripts.yaml", yaml.safe_dump(scripts, sort_keys=False))
    shutil.copy2(ROOT / "examples/home_assistant/runtime_automations.yaml", config / "automations.yaml")
    shutil.copy2(FIXTURES / "configuration.yaml", config / "configuration.yaml")
    artwork = config / "www/streamdeck"
    artwork.mkdir(parents=True, exist_ok=True)
    for name in ("light_on.png", "light_off.png", "unknown.png"):
        shutil.copy2(ROOT / "assets/source" / name, artwork / name)
    shutil.copy2(ROOT / "tests/fixtures/png/invalid_truncated.png", artwork / "invalid.png")
    # Only lab-owned copies get SELinux relabels; never mount/relabel the repo.
    tests = LAB / "pytest"
    shutil.copytree(ROOT / "tests/ha", tests / "tests", dirs_exist_ok=True)
    shutil.copytree(ROOT / "examples/home_assistant", tests / "examples", dirs_exist_ok=True)
    shutil.copytree(ROOT / "custom_components", config / "custom_components", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "custom_components", tests / "custom_components", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))


def ensure_image(key):
    image = LOCK[key]["image"]
    if podman("image", "exists", image, check=False).returncode:
        print(f"Pulling pinned {key} {LOCK[key]['tag']}", flush=True)
        podman("pull", "--platform", LOCK["platform"], image, log=LAB / f"pull-{key}.log")
    return image


def build():
    for suffix in ("ha", "deck"):
        current = inspect_owned("container", PREFIX + "-" + suffix)
        if current:
            raise RuntimeError("Run down before rebuilding an existing lab")
    stage()
    image = ensure_image("esphome_host")
    print("Compiling virtual deck with pinned ESPHome host target", flush=True)
    name = PREFIX + "-build"
    if inspect_owned("container", name):
        raise RuntimeError("Another lab build is present")
    podman("run", "--rm", "--name", name, "--label", f"{LABEL}={OWNER}", "--cap-drop=all",
           "--security-opt=no-new-privileges", "-v", f"{LAB / 'deck'}:/lab:Z", "-w", "/lab",
           "--entrypoint", "esphome", image, "compile", "/lab/host.yaml", log=LAB / "host-build.log")
    binary = LAB / "deck/.esphome/build/.pioenvs/streamdeck-original/program"
    if not binary.is_file():
        raise RuntimeError("ESPHome host output missing")
    return binary


def start_container(suffix, image, args):
    name = PREFIX + "-" + suffix
    item = inspect_owned("container", name)
    if item:
        if item["State"]["Running"]:
            return
        podman("start", name)
        return
    podman("run", "-d", "--name", name, "--label", f"{LABEL}={OWNER}",
           "--network", PREFIX, "--network-alias", suffix,
           "--cap-drop=all", "--security-opt=no-new-privileges", *args, image,
           *( ["-m", "homeassistant", "--config", "/config"] if suffix == "ha" else []))


def onboard():
    wait_for(lambda: request("/api/onboarding", auth=False), description="HA onboarding endpoint")
    creds = credentials()
    steps = request("/api/onboarding", auth=False)
    if not any(step["step"] == "user" and step["done"] for step in steps):
        result = request("/api/onboarding/users", {
            "client_id": URL + "/", "name": "Deck Lab", "username": creds["username"],
            "password": creds["password"], "language": "en"}, auth=False)
        data = urllib.parse.urlencode({"grant_type": "authorization_code", "code": result["auth_code"],
                                      "client_id": URL + "/"}).encode()
        with urllib.request.urlopen(URL + "/auth/token", data, timeout=30) as response:
            creds.update(json.load(response))
        private_write(LAB / "credentials.json", json.dumps(creds))
    for step in request("/api/onboarding", auth=False):
        if step["done"]:
            continue
        if step["step"] in ("core_config", "analytics"):
            request("/api/onboarding/" + step["step"], {})
        elif step["step"] == "integration":
            request("/api/onboarding/integration", {"client_id": URL + "/", "redirect_uri": URL + "/"})


def refresh_token():
    creds = credentials()
    if "refresh_token" not in creds:
        return
    data = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": creds["refresh_token"],
                                  "client_id": URL + "/"}).encode()
    with urllib.request.urlopen(URL + "/auth/token", data, timeout=30) as response:
        creds.update(json.load(response))
    private_write(LAB / "credentials.json", json.dumps(creds))


def pair():
    entries = request("/api/config/config_entries/entry")
    if not any(entry["domain"] == "esphome" for entry in entries):
        flow = request("/api/config/config_entries/flow", {"handler": "esphome", "show_advanced_options": False})
        flow = request("/api/config/config_entries/flow/" + flow["flow_id"], {"host": "deck", "port": 6053})
        if flow.get("step_id") == "encryption_key":
            flow = request("/api/config/config_entries/flow/" + flow["flow_id"],
                           {"noise_psk": credentials()["api_encryption_key"]})
        if flow.get("type") != "create_entry":
            raise RuntimeError(f"ESPHome pairing failed at {flow.get('step_id')}: {flow.get('errors')}")
    wait_for(lambda: any(service["domain"] == "esphome" and
                         "streamdeck_original_get_key_visual_status" in service["services"]
                         for service in request("/api/services")), description="ESPHome response actions")
    wait_for(lambda: request("/api/states/sensor.stream_deck_original_visual_session")["state"]
             not in ("unknown", "unavailable"), description="visual session entity")


def up():
    info = json.loads(podman("info", "--format", "json").stdout)
    if not info["host"]["security"]["rootless"]:
        raise RuntimeError("This lab requires rootless Podman")
    running = inspect_owned("container", PREFIX + "-deck")
    if running and running["State"]["Running"]:
        # A running executable/config must not be rebuilt or relabeled in place.
        # Use down/build/up to apply source changes.
        print("Reusing running virtual deck; down/up applies source/config changes", flush=True)
    else:
        # Rebuilding relabels staged files. Retire stopped containers carrying
        # old private mount labels, and any remaining HA, before staging again.
        if running or inspect_owned("container", PREFIX + "-ha"):
            down()
        build()
    if not inspect_owned("network", PREFIX):
        podman("network", "create", "--label", f"{LABEL}={OWNER}", PREFIX)
    start_container("deck", ensure_image("esphome_host"), [
        "-v", f"{LAB / 'deck'}:/lab:Z", "-w", "/lab", "--entrypoint",
        "/lab/.esphome/build/.pioenvs/streamdeck-original/program"])
    start_container("ha", ensure_image("home_assistant"), [
        "-p", "127.0.0.1:18123:8123", "-v", f"{LAB / 'config'}:/config:Z", "--entrypoint", "python"])
    print("Waiting for fresh HA and pairing the encrypted virtual deck", flush=True)
    # Already-onboarded HA returns 401/404 on the onboarding endpoint.
    creds = credentials()
    if "refresh_token" not in creds:
        onboard()
    else:
        wait_for(lambda: urllib.request.urlopen(URL + "/", timeout=2).status == 200, description="HA UI")
        refresh_token()
    pair()
    record_versions()
    print(f"Lab ready: {URL} (credentials in private .build/ha-lab/credentials.json)", flush=True)


def record_versions():
    report = {"locks": LOCK, "podman": json.loads(podman("version", "--format", "json").stdout),
              "host_python": sys.version, "tested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    for suffix in ("ha", "deck"):
        item = inspect_owned("container", PREFIX + "-" + suffix)
        report[suffix] = {"image_id": item["Image"], "image_digest": item.get("ImageDigest")}
    report["ha"]["packages"] = json.loads(podman("exec", PREFIX + "-ha", "python", "-c",
        'import json,sys,importlib.metadata as m; print(json.dumps({"python":sys.version, **{x:m.version(x) for x in '
        '("homeassistant","home-assistant-frontend","aioesphomeapi","aiohttp")}}))').stdout)
    report["deck"]["packages"] = json.loads(podman("exec", PREFIX + "-deck", "python", "-c",
        'import json,sys,importlib.metadata as m; print(json.dumps({"python":sys.version, **{x:m.version(x) for x in '
        '("esphome","aioesphomeapi","platformio")}}))').stdout)
    report["deck"]["compiler"] = podman("exec", PREFIX + "-deck", "g++", "-dumpfullversion").stdout.strip()
    if report["ha"]["packages"]["homeassistant"] != LOCK["home_assistant"]["tag"]:
        raise RuntimeError("HA image version differs from the lock")
    if report["deck"]["packages"]["esphome"] != LOCK["esphome_host"]["tag"]:
        raise RuntimeError("ESPHome image version differs from the lock")
    binary = LAB / "deck/.esphome/build/.pioenvs/streamdeck-original/program"
    report["deck"]["binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
    private_write(LAB / "versions.json", json.dumps(report, indent=2) + "\n")


def status():
    result = {"url": URL, "containers": {}}
    for suffix in ("ha", "deck"):
        item = inspect_owned("container", PREFIX + "-" + suffix)
        result["containers"][suffix] = item["State"]["Status"] if item else "absent"
    print(json.dumps(result, indent=2))


def down():
    # No prune, volume deletion, process-name matching, workspace deletion or
    # access to unrelated containers. Config and private test results survive.
    for suffix in ("ha", "deck"):
        name = PREFIX + "-" + suffix
        if inspect_owned("container", name):
            podman("stop", "--time", "10", name)
            podman("rm", name)
    if inspect_owned("network", PREFIX):
        podman("network", "rm", PREFIX)
    print("Lab containers/network removed; private configuration and results retained.")


def fresh():
    if LAB.exists():
        owned_directory()
        down()
        archive = LAB.with_name("ha-lab-archive-" + time.strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(3))
        LAB.rename(archive)
        print(f"Previous private lab preserved at {archive.relative_to(ROOT)}", flush=True)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("up", "build", "status", "test", "test-engine", "down"))
    parser.add_argument("--fresh", action="store_true", help="up only: archive the previous lab and use fresh accounts/data")
    args = parser.parse_args()
    if args.fresh and args.command != "up":
        parser.error("--fresh is only valid with up")
    if args.command == "status":
        status()
        return
    ROOT.joinpath(".build").mkdir(exist_ok=True)
    with (ROOT / ".build/ha-lab.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another lab command is active") from error
        if args.fresh:
            fresh()
        if args.command in ("test", "test-engine"):
            from ha_lab_tests import run_tests, run_engine_tests
            (run_tests if args.command == "test" else run_engine_tests)()
        else:
            globals()[args.command]()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, urllib.error.HTTPError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
