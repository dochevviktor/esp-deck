from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from check_firmware import EXAMPLES, stage


class ConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="esp-deck-schema-")
        cls.folder = Path(cls.temporary.name)
        stage(cls.folder)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_config(self, source, valid=True, expected=""):
        path = self.folder / "examples" / "test.yaml"
        path.write_text(source)
        result = subprocess.run([sys.executable, "-m", "esphome", "config", str(path)],
                                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if valid:
            self.assertEqual(result.returncode, 0, result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn(expected, result.stdout)

    def base(self):
        return (self.folder / "examples" / "02_keys_brightness.yaml").read_text()

    def test_all_examples_validate(self):
        for name in EXAMPLES:
            with self.subTest(example=name):
                self.run_config((self.folder / "examples" / f"{name}.yaml").read_text())

    def test_duplicate_keys(self):
        self.run_config(self.base() + "\nbinary_sensor:\n  - platform: stream_deck\n    name: Duplicate\n    key: 0\n",
                        False, "Duplicate stream_deck key")

    def test_duplicate_brightness(self):
        self.run_config(self.base() + "\nnumber:\n  - platform: stream_deck\n    name: Duplicate brightness\n",
                        False, "Duplicate stream_deck brightness")

    def test_invalid_key(self):
        self.run_config(self.base() + "\nbinary_sensor:\n  - platform: stream_deck\n    name: Invalid\n    key: 15\n",
                        False, "at most 14")

    def test_exclusive_host_ownership(self):
        self.run_config(self.base() + "\nusb_host:\n", False, "usb_host")

    def test_logger_ownership(self):
        self.run_config(self.base() + "\nlogger:\n  hardware_uart: USB_SERIAL_JTAG\n", False, "UART0")

    def test_reject_other_mcu(self):
        self.run_config(self.base() + "\nesp32:\n  variant: esp32s2\npsram:\n  mode: quad\n", False, "ESP32S3")

    def test_reject_arduino(self):
        self.run_config(self.base() + "\nesp32:\n  framework:\n    type: arduino\n    version: recommended\n", False, "ESP-IDF")

    def test_initial_edge_automations_are_rejected(self):
        self.run_config(self.base() + "\nbinary_sensor:\n  - platform: stream_deck\n    key: 2\n"
                        "    name: Unsafe trigger\n    trigger_on_initial_state: true\n", False, "synchronization")

    def test_malformed_bmp(self):
        (self.folder / "assets" / "invalid.bmp").write_bytes(b"BM" + bytes(15604))
        source = (self.folder / "examples" / "03_images_home_assistant.yaml").read_text()
        self.run_config(source.replace("../assets/native/light_on.bmp", "../assets/invalid.bmp"), False, "BMP")

    def test_action_key_bounds(self):
        source = (self.folder / "examples" / "03_images_home_assistant.yaml").read_text()
        self.run_config(source.replace("key: 0", "key: -1"), False, "at least 0")
