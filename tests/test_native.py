from pathlib import Path
import os
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NativeTests(unittest.TestCase):
    def test_native(self):
        build = ROOT / ".build"
        build.mkdir(exist_ok=True)
        binary = build / "test_protocol"
        sanitizer = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if os.getenv("SANITIZE") == "1" else []
        subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-g", *sanitizer,
                        "-Icomponents/stream_deck", "tests/native/test_protocol.cpp",
                        "components/stream_deck/protocol.cpp", "components/stream_deck/scheduler.cpp",
                        "-o", str(binary)], cwd=ROOT, check=True)
        subprocess.run([str(binary)], cwd=ROOT, check=True)

    def test_usb_transport(self):
        build = ROOT / ".build"
        build.mkdir(exist_ok=True)
        binary = build / "test_transport"
        sanitizer = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if os.getenv("SANITIZE") == "1" else []
        subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-g", *sanitizer,
                        "-Itests/native/fakes", "-Icomponents/stream_deck", "tests/native/test_transport.cpp",
                        "components/stream_deck/usb_transport.cpp", "components/stream_deck/protocol.cpp",
                        "components/stream_deck/scheduler.cpp", "-o", str(binary)], cwd=ROOT, check=True)
        subprocess.run([str(binary)], cwd=ROOT, check=True)
