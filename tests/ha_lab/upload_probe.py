"""Encrypted upload acceptance inside a network-isolated virtual-deck container."""
import asyncio
import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import random

from aioesphomeapi import APIClient
from PIL import Image
import yaml


async def main():
    key = yaml.safe_load(Path("/lab/secrets.yaml").read_text())["api_encryption_key"]
    client = APIClient("127.0.0.1", 6053, "", noise_psk=key, client_info="Isolated artwork upload test")
    for attempt in range(100):
        try:
            await client.connect(login=True)
            break
        except Exception:
            if attempt == 99:
                raise
            await asyncio.sleep(0.1)
    try:
        _, discovered = await client.list_entities_services()
        services = {s.name: s for s in discovered}

        async def call(name, **values):
            response = await client.execute_service(services[name], values, return_response=True)
            assert response.success, response.error_message
            return json.loads(response.response_data)

        caps = await call("get_deck_capabilities")
        assert caps["artwork_upload"] == "png_chunks_v1"
        session = caps["session"]
        output = BytesIO()
        Image.frombytes("RGBA", (72, 72), random.Random(32).randbytes(72 * 72 * 4)).save(output, format="PNG")
        png = output.getvalue(); asset_id = hashlib.sha256(png).hexdigest()

        async def chunk(offset, content, **overrides):
            return await call("upload_deck_artwork", **{"session": session, "asset_id": asset_id,
                "offset": offset, "total_size": len(png), "data": base64.b64encode(content).decode(), **overrides})

        assert (await chunk(0, b"", session="0000000000000000"))["error"] == "wrong_session"
        assert (await chunk(0, b"", data="AB=="))["error"] == "invalid_chunk"
        # A complete bad hash never becomes available for rendering.
        for offset in range(0, len(png), 1024):
            rejected = await chunk(offset, png[offset:offset + 1024], asset_id="0" * 64)
        assert rejected["error"] == "upload_hash_mismatch"
        assert (await chunk(0, b""))["received"] == 0
        first = png[:1024]
        assert (await chunk(0, first))["received"] == 1024
        assert (await chunk(0, first))["received"] == 1024
        # API disconnect does not discard an in-progress transfer or tile state.
        await client.disconnect(); await client.connect(login=True)
        assert (await chunk(0, b""))["received"] == 1024
        for offset in range(1024, len(png), 1024):
            response = await chunk(offset, png[offset:offset + 1024])
            assert response["accepted"] and response["received"] == min(len(png), offset + 1024)
        assert response["complete"] and (await chunk(0, b""))["complete"]
        visual = {"session": session, "key": 0, "revision": 1, "fields": 255,
                  "image_url": "asset://" + asset_id, "image_revision": asset_id, "label_text": "API upload",
                  "font": 16, "text_color": "#FFFFFF", "outline_color": "#000000",
                  "background_color": "#000000", "fit": "contain", "binding_context": "uploadtest",
                  "text_x": 3, "text_y": 3, "text_width": 66, "text_height": 66, "text_align": 1, "text_valign": 2}

        async def apply(values):
            assert (await call("set_key_visual_v2", **values))["accepted"]
            async with asyncio.timeout(10):
                while True:
                    status = await call("get_key_visual_status", session=session, key=0)
                    assert status["error"] == "none", status
                    if status["applied_revision"] == values["revision"]:
                        return
                    await asyncio.sleep(0.05)

        await apply(visual)
        await apply({**visual, "revision": 2, "label_text": "Cached", "text_align": 0})
        await asyncio.sleep(0.2)
        snapshot = json.loads(Path("/lab/status.json").read_text())
        assert snapshot["downloads"] == 0 and snapshot["cache_hits"] >= 1
        print(json.dumps({"encrypted_api": "passed", "png_bytes": len(png), "http_downloads": 0,
                          "resume_and_hash_rejection": "passed", "simulated_usb_applied_revision": 2,
                          "label_cache": "passed", "graphics_peak": snapshot["graphics_peak"],
                          "hardware": "not tested"}))
    finally:
        await client.disconnect()


asyncio.run(main())
