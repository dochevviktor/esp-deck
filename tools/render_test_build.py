"""Build the portable renderer plus production PSRAM adapter with fake heap APIs."""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def build_renderer():
    binary = ROOT / ".build/test_renderer"
    binary.parent.mkdir(exist_ok=True)
    sanitizer = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if os.getenv("SANITIZE") == "1" else []
    sources = ["protocol.cpp", "scheduler.cpp", "runtime_image.cpp", "visual_state.cpp",
               "renderer.cpp", "render_font.cpp", "render_font_data.cpp", "render_memory.cpp"]
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-g", *sanitizer,
                    "-Itests/native/fakes", "-Icomponents/stream_deck", "tests/native/test_renderer.cpp",
                    *("components/stream_deck/" + name for name in sources), "-o", str(binary)],
                   cwd=ROOT, check=True)
    return binary
