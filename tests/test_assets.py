from pathlib import Path
import subprocess
import sys
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from convert_assets import convert


class AssetTests(unittest.TestCase):
    def test_hardware_pattern_matches_upstream_fixture(self):
        self.assertEqual((ROOT / "assets/native/transport_test.bmp").read_bytes(),
                         (ROOT / "tests/fixtures/asymmetric.native.bmp").read_bytes())

    def test_reference_reproducible(self):
        subprocess.run([sys.executable, "tools/generate_reference_fixtures.py", "--check"], cwd=ROOT, check=True)

    def test_alpha_is_composited(self):
        transparent = Image.new("RGBA", (72, 72), (255, 0, 0, 0))
        opaque = Image.new("RGB", (72, 72), "#001122")
        self.assertEqual(convert(transparent, "#001122", "contain"), convert(opaque, "#001122", "contain"))

    def test_scaling_outputs_fixed_native_size(self):
        for size in ((10, 200), (200, 10), (1, 1)):
            for mode in ("crop", "contain"):
                self.assertEqual(len(convert(Image.new("RGB", size, "red"), "black", mode)), 15606)
