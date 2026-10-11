from pathlib import Path
import os
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from render_test_build import build_renderer
from asset_test_build import build_assets, build_http


class NativeTests(unittest.TestCase):
    def test_key_events(self):
        binary = ROOT / ".build/test_key_events"
        binary.parent.mkdir(exist_ok=True)
        sanitizer = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if os.getenv("SANITIZE") == "1" else []
        subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-g", *sanitizer,
                        "-DUSE_STREAM_DECK_KEY_EVENTS", "-Itests/native/fakes", "-Icomponents/stream_deck",
                        "tests/native/test_key_events.cpp", "components/stream_deck/stream_deck.cpp",
                        "components/stream_deck/protocol.cpp", "components/stream_deck/scheduler.cpp",
                        "components/stream_deck/runtime_image.cpp", "-o", str(binary)], cwd=ROOT, check=True)
        subprocess.run([str(binary)], cwd=ROOT, check=True)

    def test_assets(self):
        subprocess.run([str(build_assets())], cwd=ROOT, check=True)

    def test_v2(self):
        subprocess.run([str(build_assets("test_v2"))], cwd=ROOT, check=True)

    def test_asset_http(self):
        subprocess.run([str(build_http())], cwd=ROOT, check=True)

    def test_renderer(self):
        subprocess.run([str(build_renderer())], cwd=ROOT, check=True)

    def test_native(self):
        build = ROOT / ".build"
        build.mkdir(exist_ok=True)
        binary = build / "test_protocol"
        sanitizer = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if os.getenv("SANITIZE") == "1" else []
        subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-g", *sanitizer,
                        "-Icomponents/stream_deck", "tests/native/test_protocol.cpp",
                        "components/stream_deck/protocol.cpp", "components/stream_deck/scheduler.cpp",
                        "components/stream_deck/runtime_image.cpp",
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
                        "components/stream_deck/scheduler.cpp", "components/stream_deck/runtime_image.cpp",
                        "-o", str(binary)], cwd=ROOT, check=True)
        subprocess.run([str(binary)], cwd=ROOT, check=True)

    def test_runtime(self):
        build = ROOT / ".build"
        build.mkdir(exist_ok=True)
        binary = build / "test_runtime"
        sanitizer = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if os.getenv("SANITIZE") == "1" else []
        subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-g", *sanitizer,
                        "-Icomponents/stream_deck", "tests/native/test_runtime.cpp",
                        "components/stream_deck/protocol.cpp", "components/stream_deck/scheduler.cpp",
                        "components/stream_deck/runtime_image.cpp", "components/stream_deck/visual_state.cpp",
                        "-o", str(binary)], cwd=ROOT, check=True)
        subprocess.run([str(binary)], cwd=ROOT, check=True)
