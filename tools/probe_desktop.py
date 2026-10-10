"""Read Original 0FD9:0060 USB evidence on Linux without changing device state.

Uses sysfs, standard GET_DESCRIPTOR requests and GET_REPORT(Feature 4) only.
Does not claim an interface, detach a driver, reset the deck, query its serial
number, or send images/brightness. Optional input capture reads whole reports
from hidraw, without the pinned desktop library's 16-byte read limit.
"""
import argparse
import ctypes
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import select
import sys
import time


class ControlTransfer(ctypes.Structure):
    _fields_ = [
        ("request_type", ctypes.c_uint8), ("request", ctypes.c_uint8),
        ("value", ctypes.c_uint16), ("index", ctypes.c_uint16),
        ("length", ctypes.c_uint16), ("timeout", ctypes.c_uint32),
        ("data", ctypes.c_void_p),
    ]


def find_deck():
    matches = []
    for device in Path("/sys/bus/usb/devices").iterdir():
        try:
            vid = (device / "idVendor").read_text().strip()
            pid = (device / "idProduct").read_text().strip()
        except FileNotFoundError:
            continue
        if (vid, pid) == ("0fd9", "0060"):
            matches.append(device.resolve())
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one 0FD9:0060; found {len(matches)}")
    return matches[0]


def get_descriptor(fd, descriptor_type, length):
    if descriptor_type not in (6, 7):
        raise ValueError("Only device qualifier and other-speed configuration are queried")
    buffer = ctypes.create_string_buffer(length)
    request = ControlTransfer(0x80, 6, descriptor_type << 8, 0, length, 1500,
                              ctypes.addressof(buffer))
    # Linux USBDEVFS_CONTROL: _IOWR('U', 0, struct usbdevfs_ctrltransfer).
    command = (3 << 30) | (ctypes.sizeof(ControlTransfer) << 16) | (ord("U") << 8)
    actual = fcntl.ioctl(fd, command, request)
    return buffer.raw[:actual]


def capture_input(fd, seconds):
    reports = []
    started = time.monotonic()
    if seconds:
        print(f"Listening for Stream Deck keys for {seconds:g}s (up to 256 reports)...",
              file=sys.stderr, flush=True)
    while len(reports) < 256:
        remaining = seconds - (time.monotonic() - started)
        if remaining <= 0:
            break
        readable, _, _ = select.select([fd], [], [], min(remaining, 1))
        if readable:
            data = os.read(fd, 512)
            if not data:
                raise RuntimeError("Stream Deck disconnected during input capture")
            reports.append({"elapsed_seconds": round(time.monotonic() - started, 3),
                            "length": len(data), "hex": data.hex(" ")})
    return reports


def probe(seconds):
    device = find_deck()
    raw = (device / "descriptors").read_bytes()
    if len(raw) < 27 or raw[:2] != b"\x12\x01" or raw[8:12] != b"\xd9\x0f\x60\x00":
        raise RuntimeError("Unexpected Original device descriptor")
    if raw[17] != 1 or raw[18:20] != b"\x09\x02":
        raise RuntimeError("Expected one USB configuration")
    size = int.from_bytes(raw[20:22], "little")
    if len(raw) != 18 + size:
        raise RuntimeError("Incomplete configuration descriptor")
    result = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "vid_pid": "0fd9:0060",
        "speed_mbps": int((device / "speed").read_text().strip()),
        "device_descriptor_hex": raw[:18].hex(" "),
        "configuration_descriptor_hex": raw[18:].hex(" "),
        "errors": [],
    }
    # Descriptor bytes contain string indices only; never read USB serial strings.
    bus = int((device / "busnum").read_text())
    address = int((device / "devnum").read_text())
    try:
        fd = os.open(f"/dev/bus/usb/{bus:03}/{address:03}", os.O_RDWR)
        try:
            result["device_qualifier_hex"] = get_descriptor(fd, 6, 10).hex(" ")
            header = get_descriptor(fd, 7, 9)
            if len(header) != 9 or header[:2] != b"\x09\x07":
                raise RuntimeError("Incomplete other-speed configuration header")
            size = int.from_bytes(header[2:4], "little")
            if not 9 <= size <= 4096:
                raise RuntimeError("Invalid other-speed configuration length")
            other = get_descriptor(fd, 7, size)
            if len(other) != size:
                raise RuntimeError("Incomplete other-speed configuration")
            result["other_speed_configuration_hex"] = other.hex(" ")
        finally:
            os.close(fd)
    except (OSError, RuntimeError) as exc:
        result["errors"].append(f"USB descriptor query: {exc}")

    hidraw = [entry for entry in Path("/sys/class/hidraw").glob("hidraw*")
              if device in (entry / "device").resolve().parents]
    if len(hidraw) != 1:
        raise RuntimeError(f"Expected one hidraw interface for this deck; found {len(hidraw)}")
    report_descriptor = (hidraw[0] / "device" / "report_descriptor").read_bytes()
    result["hid_report_descriptor_hex"] = report_descriptor.hex(" ")
    try:
        fd = os.open(f"/dev/{hidraw[0].name}", os.O_RDONLY | os.O_NONBLOCK)
        try:
            payload = bytearray(17)
            payload[0] = 4
            # HIDIOCGFEATURE(17), firmware only. Feature 3 contains the serial.
            actual = fcntl.ioctl(fd, (3 << 30) | (17 << 16) | (ord("H") << 8) | 7, payload)
            if actual != 17 or payload[:5] != b"\x04\x55\xaa\xd4\x04":
                raise RuntimeError("Unexpected firmware feature response")
            result["firmware_version"] = payload[5:].split(b"\0", 1)[0].decode("ascii")
            result["input_capture_seconds"] = seconds
            result["input_reports"] = capture_input(fd, seconds)
        finally:
            os.close(fd)
    except (OSError, RuntimeError, UnicodeError) as exc:
        result["errors"].append(f"HID query/capture: {exc}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=0,
                        help="Listen for input for 0–300 seconds; default: descriptors only")
    args = parser.parse_args()
    if not 0 <= args.seconds <= 300:
        parser.error("--seconds must be between 0 and 300")
    try:
        result = probe(args.seconds)
    except (OSError, RuntimeError) as exc:
        parser.exit(1, f"Probe failed: {exc}\n")
    print(json.dumps(result, indent=2))
    return bool(result["errors"])


if __name__ == "__main__":
    sys.exit(main())
