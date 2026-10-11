#!/usr/bin/env python3
"""Read-only encrypted API capture for an explicitly selected physical ESP.

Reads local examples/secrets.yaml; stores raw device logs only in a new private
directory under .build/device-sessions. Printed reports omit network credentials,
MAC/serial identifiers and artwork URLs. Never changes visuals, inputs or flash.
"""
import argparse
import asyncio
from dataclasses import asdict
import hashlib
import json
import logging
import os
from pathlib import Path
import tempfile
import time

from aioesphomeapi import APIClient
import yaml

ROOT = Path(__file__).resolve().parents[1]


async def probe(host, seconds, destination):
    key = yaml.safe_load((ROOT / "examples/secrets.yaml").read_text())["api_encryption_key"]
    client = APIClient(host, 6053, "", noise_psk=key, client_info="ESP Deck bench observer")
    records = []
    states = {}
    started = time.monotonic()
    with (destination / "api.log").open("w") as raw:
        await client.connect(login=True, log_errors=False)
        try:
            info = await client.device_info()
            if info.name != "streamdeck-original":
                raise RuntimeError("Selected API device is not streamdeck-original")
            entities, services = await client.list_entities_services()
            names = {entity.key: entity.name for entity in entities}

            def on_state(state):
                record = asdict(state)
                record.pop("key", None)
                name = names.get(state.key, str(state.key))
                states[name] = record
                records.append({"seconds": round(time.monotonic() - started, 3), "entity": name, **record})

            def on_log(entry):
                message = entry.message.decode(errors="replace") if isinstance(entry.message, bytes) else entry.message
                raw.write(f"{time.monotonic() - started:.3f} {message}\n")
                raw.flush()

            client.subscribe_states(on_state)
            client.subscribe_logs(on_log, log_level=5, dump_config=True)
            capabilities = None
            for service in services:
                if service.name == "get_deck_capabilities":
                    response = await client.execute_service(service, {}, return_response=True, timeout=15)
                    if response and response.success:
                        data = response.response_data
                        capabilities = json.loads(data) if isinstance(data, (str, bytes)) else data
            await asyncio.sleep(seconds)
            report = {"name": info.name, "esphome_version": info.esphome_version,
                "compilation_time": info.compilation_time, "model": info.model,
                "identity_sha256": hashlib.sha256(info.mac_address.encode()).hexdigest(),
                "actions": sorted(service.name for service in services),
                "entities": len(entities), "states": states, "events": records,
                "capabilities": capabilities}
            (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n")
            summary = {key: report[key] for key in (
                "name", "esphome_version", "compilation_time", "model", "identity_sha256", "actions", "entities")}
            summary["diagnostics"] = {name: value for name, value in states.items() if any(word in name.lower()
                for word in ("heap", "usb", "queue", "brightness", "visual session"))}
            if capabilities:
                summary["protocol_version"] = capabilities.get("protocol_version")
            print(json.dumps(summary, indent=2))
        finally:
            await client.disconnect()


def main():
    os.umask(0o077)
    logging.getLogger("aioesphomeapi").setLevel(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--seconds", type=int, default=15, choices=range(1, 601), metavar="1..600")
    args = parser.parse_args()
    parent = ROOT / ".build/device-sessions"
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = Path(tempfile.mkdtemp(prefix="probe-", dir=parent))
    try:
        asyncio.run(probe(args.host, args.seconds, destination))
    except Exception as error:
        (destination / "error.txt").write_text(repr(error))
        print(f"Device probe failed ({type(error).__name__}); private details in {destination.relative_to(ROOT)}")
        raise SystemExit(1) from None
    print(f"Private capture: {destination.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
