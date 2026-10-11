"""Compile portable asset tests with the pinned allocation-free inflater."""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
def build_assets(test_name="test_assets"):
    build = ROOT / ".build"; build.mkdir(exist_ok=True)
    sanitize = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if os.getenv("SANITIZE") == "1" else []
    obj = build / "asset_inflate.o"
    subprocess.run(["gcc", "-std=c99", "-g", *sanitize, "-Icomponents/stream_deck", "-c",
                    "components/stream_deck/asset_inflate.c", "-o", str(obj)], cwd=ROOT, check=True)
    sources = ["asset_png.cpp", "asset_policy.cpp", "asset_pipeline.cpp", "runtime_image.cpp", "protocol.cpp",
               "visual_state.cpp", "visual_api.cpp", "scheduler.cpp", "renderer.cpp", "render_font.cpp", "render_font_data.cpp"]
    binary = build / test_name
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-g", *sanitize,
                    "-Icomponents/stream_deck", f"tests/native/{test_name}.cpp",
                    *("components/stream_deck/" + name for name in sources), str(obj), "-o", str(binary)], cwd=ROOT, check=True)
    return binary


def build_http():
    binary = ROOT / ".build/test_asset_http"
    binary.parent.mkdir(exist_ok=True)
    sanitize = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if os.getenv("SANITIZE") == "1" else []
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-g", *sanitize,
                    "-DUSE_STREAM_DECK_ASSETS", "-Itests/native/http_fakes", "-Itests/native/fakes", "-Icomponents/stream_deck",
                    "tests/native/test_asset_http.cpp", "components/stream_deck/asset_http_transfer.cpp",
                    "components/stream_deck/asset_policy.cpp", "components/stream_deck/visual_state.cpp",
                    "components/stream_deck/runtime_image.cpp", "components/stream_deck/protocol.cpp",
                    "components/stream_deck/scheduler.cpp", "-o", str(binary)], cwd=ROOT, check=True)
    return binary

if __name__ == "__main__":
    subprocess.run([str(build_assets())], cwd=ROOT, check=True)
    subprocess.run([str(build_http())], cwd=ROOT, check=True)
