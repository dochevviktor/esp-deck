"""HA image normalization versus Pillow and the production C++ PNG decoder."""
import importlib
import os
from io import BytesIO
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import types
import unittest
import zlib

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
# Import the pure image/model code without executing HA's integration entrypoint.
package = types.ModuleType("_esp_deck_image_test")
package.__path__ = [str(ROOT / "custom_components/esp_deck")]
sys.modules[package.__name__] = package
art = importlib.import_module(package.__name__ + ".artwork")


def encoded(image, kind="PNG", **options):
    buffer = BytesIO()
    image.save(buffer, format=kind, **options)
    return buffer.getvalue()


class ArtworkTests(unittest.TestCase):
    def test_images_normalize_and_decode_with_production_firmware(self):
        build = ROOT / ".build"
        build.mkdir(exist_ok=True)
        obj, binary = build / "upload_inflate.o", build / "check_uploaded_png"
        sanitize = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if os.getenv("SANITIZE") == "1" else []
        subprocess.run(["gcc", "-std=c99", *sanitize, "-Icomponents/stream_deck", "-c", "components/stream_deck/asset_inflate.c", "-o", str(obj)], cwd=ROOT, check=True)
        subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *sanitize, "-Icomponents/stream_deck", "-Itests/native",
                        "tests/native/check_uploaded_png.cpp", "components/stream_deck/asset_png.cpp", "components/stream_deck/visual_state.cpp",
                        "components/stream_deck/runtime_image.cpp", "components/stream_deck/protocol.cpp", "components/stream_deck/scheduler.cpp",
                        "components/stream_deck/renderer.cpp", "components/stream_deck/render_font.cpp", "components/stream_deck/render_font_data.cpp",
                        str(obj), "-o", str(binary)], cwd=ROOT, check=True)
        rgba = Image.new("RGBA", (180, 90))
        rgba.putdata([(x % 256, y * 2, 220, (x * 7) % 256) for y in range(90) for x in range(180)])
        exif = Image.Exif(); exif[274] = 6; exif[270] = "Must be stripped"
        inputs = [encoded(rgba), encoded(rgba.convert("RGB"), "JPEG", exif=exif),
                  encoded(Image.new("RGB", (4096, 4096), "red"), "JPEG"),
                  encoded(rgba.convert("P")), encoded(Image.new("L", (100, 200), 80))]
        args = [str(binary)]
        with tempfile.TemporaryDirectory(dir=build) as directory:
            for i, payload in enumerate(inputs):
                for j, options in enumerate(({}, {"fit": "crop", "zoom": 2.3, "x": -0.5, "y": 1})):
                    png = art.normalize(payload, options)
                    self.assertLessEqual(len(png), 32768)
                    self.assertEqual(png[28], 0)
                    tile = Image.open(BytesIO(png))
                    self.assertEqual((tile.size, tile.mode, tile.info), ((72, 72), "RGBA", {}))
                    name = Path(directory) / f"normalized-{i}-{j}"
                    name.with_suffix(".png").write_bytes(png)
                    name.with_suffix(".rgba").write_bytes(tile.tobytes())
                    args.extend([str(name.with_suffix(".png")), str(name.with_suffix(".rgba"))])
            subprocess.run(args, cwd=ROOT, check=True)

    def test_alpha_exif_orientation_and_no_native_flip(self):
        image = Image.new("RGBA", (72, 72), (20, 30, 40, 128))
        image.putpixel((0, 0), (255, 0, 0, 255))
        png = art.normalize(encoded(image), {})
        normalized = Image.open(BytesIO(png))
        self.assertEqual(normalized.getpixel((0, 0)), (255, 0, 0, 255))
        self.assertEqual(normalized.getpixel((20, 20))[3], 128)
        rgb = Image.new("RGB", (72, 72), "black")
        for y in range(20):
            for x in range(20):
                rgb.putpixel((x, y), (255, 0, 0))
        exif = Image.Exif(); exif[274] = 6
        rotated = Image.open(BytesIO(art.normalize(encoded(rgb, "JPEG", exif=exif), {})))
        self.assertGreater(rotated.getpixel((65, 5))[0], 240)
        self.assertLess(rotated.getpixel((5, 5))[0], 20)

    def test_malformed_animated_truncated_metadata_and_limits(self):
        png = encoded(Image.new("RGBA", (72, 72), "red"))
        jpeg = encoded(Image.new("RGB", (72, 72), "red"), "JPEG")
        oversized = bytearray(png)
        oversized[16:20] = struct.pack(">I", 4097)
        oversized[29:33] = struct.pack(">I", zlib.crc32(oversized[12:29]))
        exif = Image.Exif(); exif[274] = 9
        animated = encoded(Image.new("RGBA", (8, 8), "red"), save_all=True,
                           append_images=[Image.new("RGBA", (8, 8), "blue")], duration=100)
        bad_exif = encoded(Image.new("RGB", (8, 8)), "JPEG", exif=b"Exif\x00\x00broken")
        for payload in (b"<svg/>", png[:-8], png + b"trailing", jpeg[:-10], bytes(oversized), animated, bad_exif,
                        encoded(Image.new("RGB", (8, 8)), "JPEG", exif=exif), b"x" * (art.MAX_UPLOAD + 1)):
            with self.subTest(length=len(payload)), self.assertRaises(art.LayoutError):
                art.normalize(payload, {})
        for options in ({"zoom": 0}, {"zoom": 5}, {"x": float("nan")}, {"fit": "stretch"}, {"y": True}):
            with self.assertRaises(art.LayoutError):
                art.normalize(png, options)

    def test_hashes_change_on_content_and_crop_never_filename(self):
        image = Image.new("RGB", (100, 50), "red")
        image.paste("blue", (50, 0, 100, 50))
        source = encoded(image)
        a = art.normalize(source, {})
        self.assertEqual(a, art.normalize(source, {}))
        self.assertNotEqual(a, art.normalize(source, {"fit": "crop", "x": -1}))
        image.putpixel((1, 1), (0, 255, 0))
        self.assertNotEqual(a, art.normalize(encoded(image), {}))

    def test_origin_and_layout_reference_validation(self):
        for value in ("http://user:secret@ha", "http://ha?token=secret", "http://ha/asset", "file:///etc/passwd", "http://ha:0", "http://ha\\evil", "http://ha\n", "http://ha:\t8123", 42):
            with self.assertRaises(art.LayoutError):
                art.origin(value)
        model = importlib.import_module(package.__name__ + ".model")
        layout = model.empty_layout()
        layout["keys"][0]["visual"]["asset_id"] = "a" * 64
        canonical = model.validate_layout(layout)
        self.assertEqual(canonical, model.validate_layout(canonical))
        self.assertEqual(art.asset_references(canonical), {"a" * 64})
        layout["keys"][0]["visual"].update(asset_id="", image_url="http://ha/api/esp_deck/artwork/secret/a.png", image_revision="v1")
        with self.assertRaisesRegex(art.LayoutError, "use_artwork_reference"):
            model.validate_layout(layout)
