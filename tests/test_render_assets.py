import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from generate_reference_fixtures import asymmetric_image
from generate_render_fonts import generate


class RenderAssetTests(unittest.TestCase):
    def test_fonts_reproduce_from_pinned_esphome_rasterizer(self):
        for path, expected in generate().items():
            with self.subTest(file=path.name):
                self.assertEqual(path.read_bytes(), expected)

    def test_rendering_snapshot_manifest_and_independent_input(self):
        folder = ROOT / "tests/fixtures/rendering"
        manifest = json.loads((folder / "manifest.json").read_text())
        self.assertEqual((folder / "asymmetric.rgb").read_bytes(), asymmetric_image().tobytes())
        self.assertEqual((folder / "asymmetric.native.bmp").read_bytes(),
                         (ROOT / "tests/fixtures/asymmetric.native.bmp").read_bytes())
        for name, info in manifest["files"].items():
            with self.subTest(file=name):
                data = (folder / name).read_bytes()
                self.assertEqual(len(data), info["bytes"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), info["sha256"])
        self.assertEqual(manifest["font_manifest_sha256"],
                         hashlib.sha256((ROOT / "assets/fonts/manifest.json").read_bytes()).hexdigest())
