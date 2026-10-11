"""OTA preflight guards; no network, physical flash or real credentials."""
import asyncio
import hashlib
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from tools import upload_firmware as upload


class UploadTests(unittest.TestCase):
    def test_requires_matching_private_artifact_not_validation_image(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(upload, "ROOT", Path(directory)):
            data = b"synthetic test image, never flashed"
            digest = hashlib.sha256(data).hexdigest()
            validation = Path(directory) / ".build/firmware/05_home_assistant_runtime/build/firmware.ota.bin"
            validation.parent.mkdir(parents=True)
            validation.write_bytes(data)
            with self.assertRaises(ValueError):
                upload.artifact("05_home_assistant_runtime", digest)
            private = Path(directory) / ".build/deploy/05_home_assistant_runtime/build/firmware.ota.bin"
            private.parent.mkdir(parents=True)
            private.symlink_to(validation)
            with self.assertRaisesRegex(ValueError, "symlinked"):
                upload.artifact("05_home_assistant_runtime", digest)
            private.unlink()
            private.write_bytes(data)
            self.assertEqual(upload.artifact("05_home_assistant_runtime", digest), private)
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                upload.artifact("05_home_assistant_runtime", "0" * 64)

    def test_wrong_identity_disconnects_before_ota(self):
        identity = "02:00:00:00:00:01"
        device = SimpleNamespace(name="streamdeck-original", model="esp32-s3", mac_address=identity)
        client = SimpleNamespace(connect=AsyncMock(), device_info=AsyncMock(return_value=device), disconnect=AsyncMock())
        with patch.object(upload, "APIClient", return_value=client), patch.object(upload.espota2, "run_ota") as ota:
            with self.assertRaisesRegex(RuntimeError, "identity mismatch"):
                asyncio.run(upload.verify_identity("192.168.1.2", "test-key", "0" * 64))
            client.disconnect.assert_awaited_once()
            ota.assert_not_called()
            asyncio.run(upload.verify_identity("192.168.1.2", "test-key", hashlib.sha256(identity.encode()).hexdigest()))
