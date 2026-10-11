"""Runs only inside the virtual-deck container, against localhost's real API."""
import asyncio
import json
from pathlib import Path
import sys

from aioesphomeapi import APIClient, APIConnectionError
import yaml


async def main():
    key = yaml.safe_load(Path("/lab/secrets.yaml").read_text())["api_encryption_key"]
    if sys.argv[-1] == "encryption":
        rejected = 0
        for candidate in (None, "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE="):
            client = APIClient("127.0.0.1", 6053, "", noise_psk=candidate)
            try:
                await client.connect(login=True)
            except APIConnectionError:
                rejected += 1
            finally:
                await client.disconnect()
        assert rejected == 2, "Unencrypted/wrong-key client was accepted"
    client = APIClient("127.0.0.1", 6053, "", noise_psk=key, client_info="P5 lab logger")
    await client.connect(login=True)
    try:
        info = await client.device_info()
        entities, services = await client.list_entities_services()
        client.subscribe_logs(lambda entry: None, log_level=3, dump_config=True)
        await asyncio.sleep(3)
        print(json.dumps({"name": info.name, "version": info.esphome_version,
                          "entities": len(entities), "actions": sorted(service.name for service in services)}))
    finally:
        await client.disconnect()


asyncio.run(main())
