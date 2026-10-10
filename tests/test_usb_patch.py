import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("deck_usb_patch", ROOT / "components/stream_deck/idf_usb/prepare.py")
usb_patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usb_patch)

# Structural test double for the patch location, not a copy of the SDK.
SOURCE = (usb_patch.INCLUDE + "void set_config(void) {\n" + usb_patch.COPY +
          "    USBH_ENTER_CRITICAL();\n    dev_obj->constant.config_desc = new_desc;\n}\n")


class USBPatchTests(unittest.TestCase):
    def test_patch_only_touches_new_unpublished_copy(self):
        result = usb_patch.patch_source(SOURCE)
        hook = result.index("stream_deck_normalize_config")
        self.assertLess(result.index(usb_patch.COPY), hook)
        self.assertLess(hook, result.index("USBH_ENTER_CRITICAL"))
        self.assertLess(hook, result.index("dev_obj->constant.config_desc = new_desc"))
        self.assertIn("(uint8_t *)new_desc", result)
        self.assertNotIn("(uint8_t *)config_desc_full", result)

    def test_unexpected_or_repeated_anchors_are_rejected(self):
        for source in ("", SOURCE + usb_patch.COPY, SOURCE + usb_patch.INCLUDE,
                       usb_patch.patch_source(SOURCE)):
            with self.assertRaises(RuntimeError):
                usb_patch.patch_source(source)

    def test_build_local_copy_and_source_hash_guard(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            upstream = root / "sdk"
            upstream.mkdir()
            sources = {"usbh.c": SOURCE.encode(), "usb_host.c": b"host test double",
                       "CMakeLists.txt": b"cmake test double", "Kconfig": b"kconfig test double"}
            for name, data in sources.items():
                (upstream / name).write_bytes(data)
            pins = {name: hashlib.sha256(data).hexdigest() for name, data in sources.items()}
            output = root / "build/usbh_stream_deck.c"
            with patch.dict(usb_patch.EXPECTED, pins, clear=True):
                with self.assertRaisesRegex(RuntimeError, "outside the SDK"):
                    usb_patch.prepare(upstream, upstream / "usbh.c")
                usb_patch.prepare(upstream, output)
                self.assertEqual(output.read_text(), usb_patch.patch_source(SOURCE))
                for name, data in sources.items():
                    self.assertEqual((upstream / name).read_bytes(), data)
                (upstream / "usb_host.c").write_bytes(b"changed SDK")
                with self.assertRaisesRegex(RuntimeError, "Unsupported IDF USB source"):
                    usb_patch.prepare(upstream, root / "rejected.c")
                self.assertFalse((root / "rejected.c").exists())
