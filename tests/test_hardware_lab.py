"""Physical-lab isolation checks; never contacts the ESP or reads its secrets."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml
from tools import ha_bench


class HardwareLabTests(unittest.TestCase):
    def test_stage_excludes_virtual_deck_and_manual_writers(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(ha_bench.lab, "LAB", Path(directory) / "bench"):
            configured = {"bind": "192.168.122.72", "asset_origin": "http://192.168.10.2:18124",
                          "device": "192.168.10.238", "port": 18124}
            with patch.object(ha_bench.lab, "stage_integration"), patch("tools.package_release.build", return_value=Path("artifact.zip")):
                ha_bench.stage(configured)
            root = Path(directory) / "bench"
            config = yaml.safe_load((root / "config/configuration.yaml").read_text())
            self.assertNotIn("script", config)
            self.assertNotIn("automation", config)
            self.assertEqual(config["homeassistant"]["internal_url"], configured["asset_origin"])
            self.assertFalse((root / "deck").exists())
            self.assertNotIn("api_encryption_key", json.loads((root / "credentials.json").read_text()))
            self.assertEqual((root / "credentials.json").stat().st_mode & 0o777, 0o600)

    def test_no_wildcard_public_or_loopback_bind(self):
        for address in ("0.0.0.0", "127.0.0.1", "8.8.8.8", "224.0.0.1"):
            with self.subTest(address=address), self.assertRaises(ValueError):
                ha_bench.validate_settings(address, "http://192.168.10.2:18124", "192.168.10.238")
        for origin in ("file:///etc/passwd", "http://user:secret@ha", "http://ha/path", "http://ha?secret=x"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                ha_bench.validate_settings("192.168.122.72", origin, "192.168.10.238")

    def test_down_only_targets_named_hardware_lab(self):
        with patch.object(ha_bench.lab, "inspect_owned", return_value={}), patch.object(ha_bench.lab, "podman") as command:
            ha_bench.down()
            self.assertFalse(command.called)
        with patch.object(ha_bench.lab, "inspect_owned", return_value={"State": {"Running": True}}), \
                patch.object(ha_bench.lab, "podman") as command, patch("builtins.print"):
            ha_bench.down()
            targets = [call.args[-1] for call in command.call_args_list]
            self.assertEqual(targets, [ha_bench.lab.PREFIX + "-ha", ha_bench.lab.PREFIX + "-ha", ha_bench.lab.PREFIX])
            self.assertTrue(all("-bench-" in name for name in targets))
