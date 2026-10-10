from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from check_firmware import stage


class FirmwareStagingTests(unittest.TestCase):
    def test_device_secrets_are_explicit_and_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "device.yaml"
            contents = 'wifi_ssid: "TEST-DEVICE-NETWORK"\nwifi_password: "TEST-DEVICE-PASSWORD"\n'
            source.write_text(contents)
            stage(root / "device", source)
            staged = root / "device" / "examples" / "secrets.yaml"
            self.assertEqual(staged.read_text(), contents)
            self.assertEqual(staged.stat().st_mode & 0o777, 0o600)
            self.assertEqual(source.read_text(), contents)
            stage(root / "validation")
            synthetic = (root / "validation" / "examples" / "secrets.yaml").read_text()
            self.assertIn("CI-NOT-A-REAL-NETWORK", synthetic)
            self.assertNotIn("TEST-DEVICE-NETWORK", synthetic)

    def test_deployment_requires_a_single_compilation_target(self):
        for args in (("--deploy",), ("--deploy", "--compile"),
                     ("--deploy", "--example", "01_usb_probe")):
            result = subprocess.run([sys.executable, "tools/check_firmware.py", *args],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("--deploy requires --compile and one --example", result.stderr)
