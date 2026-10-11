import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from generate_png_fixtures import generate


class AssetFixtureTests(unittest.TestCase):
    def test_png_fixtures_reproduce(self):
        for name, data in generate().items():
            with self.subTest(name=name):
                self.assertEqual((ROOT / "tests/fixtures/png" / name).read_bytes(), data)

    def test_inflater_pin_and_only_documented_patch(self):
        folder = ROOT / "components/stream_deck/third_party"
        manifest = json.loads((folder / "manifest.json").read_text())
        data = (folder / manifest["vendored_file"]).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), manifest["vendored_sha256"])
        self.assertEqual(data.count(b"#define MINIZ_USE_UNALIGNED_LOADS_AND_STORES 0"), 1)
        restored = data.replace(b"#define MINIZ_USE_UNALIGNED_LOADS_AND_STORES 0",
                                b"#define MINIZ_USE_UNALIGNED_LOADS_AND_STORES 1").replace(b"\n", b"\r\n")
        self.assertEqual(hashlib.sha256(restored).hexdigest(), manifest["upstream_sha256"])
