#!/usr/bin/env python3
"""Explicit identity/hash-checked encrypted application OTA from a private build.

Build first with tools/check_firmware.py --compile --deploy --example NAME.
This never accepts synthetic validation paths or updates the bootloader. The
optional TCP MSS applies to this connection only, for problematic network paths.
"""
import argparse
import asyncio
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import socket
import tempfile
import time
from unittest.mock import patch

from aioesphomeapi import APIClient
from esphome import espota2
import yaml

try:
    from .check_firmware import EXAMPLES
except ImportError:
    from check_firmware import EXAMPLES

ROOT = Path(__file__).resolve().parents[1]


def artifact(example, expected_sha256):
    if example not in EXAMPLES or not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise ValueError("An exact example and SHA-256 are required")
    path = ROOT / ".build/deploy" / example / "build/firmware.ota.bin"
    if not path.is_file() or path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("Missing or symlinked private deployment image")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("Deployment image hash mismatch")
    return path


async def verify_identity(host, key, expected):
    client = APIClient(host, 6053, "", noise_psk=key, client_info="ESP Deck OTA identity check")
    await client.connect(login=True, log_errors=False)
    try:
        info = await client.device_info()
        if (info.name != "streamdeck-original" or info.model != "esp32-s3"
                or hashlib.sha256(info.mac_address.encode()).hexdigest() != expected):
            raise RuntimeError("Physical device identity mismatch; no firmware sent")
    finally:
        await client.disconnect()


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--example", required=True, choices=EXAMPLES)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--identity-sha256", required=True, help="fingerprint printed by device_probe.py")
    parser.add_argument("--tcp-mss", type=int, choices=range(536, 1461), metavar="536..1460")
    args = parser.parse_args()
    address = ipaddress.IPv4Address(args.host)
    if not address.is_private or address.is_loopback or address.is_unspecified or address.is_multicast:
        parser.error("Select the explicit private IPv4 address of the ESP")
    if not re.fullmatch(r"[a-f0-9]{64}", args.identity_sha256):
        parser.error("An exact device identity fingerprint is required")
    firmware = artifact(args.example, args.sha256)
    key = yaml.safe_load((ROOT / "examples/secrets.yaml").read_text())["api_encryption_key"]
    descriptor, name = tempfile.mkstemp(prefix="ota-", suffix=".log", dir=firmware.parent.parent)
    os.close(descriptor)
    log = Path(name)
    # The logger is process-local; no dependency sources or system routes change.
    logging.basicConfig(filename=log, level=logging.INFO)
    original_socket = socket.socket
    class UploadSocket(original_socket):
        def connect(self, destination):
            if args.tcp_mss and destination[:2] == (args.host, 3232):
                self.setsockopt(socket.IPPROTO_TCP, socket.TCP_MAXSEG, args.tcp_mss)
            return super().connect(destination)
    started = time.monotonic()
    try:
        asyncio.run(verify_identity(args.host, key, args.identity_sha256))
        with log.open("a") as output, redirect_stdout(output), redirect_stderr(output), \
                patch.object(espota2.socket, "socket", UploadSocket):
            result, _ = espota2.run_ota(args.host, 3232, None, firmware,
                                      noise_psk=key, plaintext_fallback=False)
    except Exception as error:
        logging.error("Upload failed: %s", type(error).__name__)
        result = 1
    print(json.dumps({"result": "uploaded" if result == 0 else "failed", "example": args.example,
                      "sha256": args.sha256, "seconds": round(time.monotonic() - started, 2),
                      "private_log": str(log.relative_to(ROOT))}))
    raise SystemExit(result)


if __name__ == "__main__":
    main()
