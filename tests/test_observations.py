"""Consistency of saved physical observations, not an automated hardware test."""
import json
from pathlib import Path
import unittest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class ObservationTests(unittest.TestCase):
    def test_s3_control_replies_match_desktop_evidence(self):
        capture = json.loads((FIXTURES / "s3_0060/control_probes.json").read_text())
        for name in ("get_configuration", "hid_report_descriptor", "firmware_feature_4"):
            with self.subTest(request=name):
                report = capture[name]
                setup, data = (bytes.fromhex(report[key]) for key in ("setup_hex", "data_hex"))
                self.assertEqual(len(setup), 8)
                self.assertEqual(len(data), int.from_bytes(setup[6:8], "little"))
                self.assertEqual(report["actual_including_setup"], len(data) + 8)
        self.assertEqual(bytes.fromhex(capture["get_configuration"]["data_hex"]), b"\x01")
        self.assertEqual(bytes.fromhex(capture["hid_report_descriptor"]["data_hex"]),
                         bytes.fromhex((FIXTURES / "desktop_0060/hid_report.hex").read_text()))
        self.assertEqual(bytes.fromhex(capture["firmware_feature_4"]["data_hex"]),
                         b"\x04\x55\xaa\xd4\x04" + b"1.0.191203\0\0")
