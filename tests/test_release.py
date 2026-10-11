"""Release content and installation guards, independent of HA and hardware."""
import io
import json
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools import package_release as release, ha_lab, ha_release


class ReleaseTests(unittest.TestCase):
    def test_archive_is_deterministic_complete_and_installs_without_workspace(self):
        first = release.archive_bytes()
        self.assertEqual(first, release.archive_bytes())
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "config/custom_components/esp_deck"
            manifest = release.extract_new(first, target)
            self.assertEqual(manifest["version"], "0.9.0")
            self.assertEqual({p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()},
                             set(release.FILES))
            self.assertGreater((target / "frontend/esp-deck.js").stat().st_size, 100000)
            with self.assertRaisesRegex(ValueError, "new"):
                release.extract_new(first, target)

    def test_unlisted_local_secrets_builds_and_caches_never_enter_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(release.ROOT / "custom_components", root / "custom_components")
            shutil.copytree(release.ROOT / "frontend", root / "frontend",
                            ignore=shutil.ignore_patterns("node_modules"))
            for name in ("hacs.json", "LICENSE"):
                shutil.copyfile(release.ROOT / name, root / name)
            for name in ("secrets.yaml", "credentials.json", "firmware.bin", "local.log", "__pycache__/cached.pyc"):
                path = root / "custom_components/esp_deck" / name
                path.parent.mkdir(exist_ok=True)
                path.write_text("PRIVATE_SENTINEL")
            files = release.inspect_archive(release.archive_bytes(root))
            self.assertFalse(any(b"PRIVATE_SENTINEL" in content for content in files.values()))
            source = root / "custom_components/esp_deck/const.py"
            source.unlink()
            source.symlink_to(release.ROOT / "custom_components/esp_deck/const.py")
            with self.assertRaisesRegex(ValueError, "symlinked"):
                release.archive_bytes(root)

    def test_malformed_archives_fail_before_destination_is_created(self):
        files = release.inspect_archive(release.archive_bytes())
        for mutation in ("traversal", "duplicate", "symlink", "missing", "oversized"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                output = io.BytesIO()
                with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for name, data in files.items():
                        if mutation == "missing" and name == "manifest.json":
                            continue
                        info = zipfile.ZipInfo(name)
                        if mutation == "symlink" and name == "const.py":
                            info.create_system = 3
                            info.external_attr = (stat.S_IFLNK | 0o777) << 16
                        if mutation == "oversized" and name == "const.py":
                            data = b"X" * (release.MAX_ARCHIVE + 1)
                        archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
                    if mutation == "traversal":
                        archive.writestr("../../secrets.yaml", b"bad")
                    elif mutation == "duplicate":
                        with self.assertWarns(UserWarning):
                            archive.writestr("manifest.json", files["manifest.json"])
                target = Path(directory) / "integration"
                with self.assertRaises(ValueError):
                    release.extract_new(output.getvalue(), target)
                self.assertFalse(target.exists())

    def test_lab_artifact_staging_and_engine_staging_use_archive_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "release.zip"
            artifact.write_bytes(release.archive_bytes())
            with patch.object(ha_lab, "LAB", root / "lab"), patch.object(ha_lab, "ARTIFACT", artifact):
                ha_lab.stage()
                installed = root / "lab/config/custom_components/esp_deck"
                self.assertEqual((installed / "manifest.json").read_bytes(),
                                 release.inspect_archive(artifact.read_bytes())["manifest.json"])
                ha_lab.stage_integration(root / "lab/engine/custom_components", installed=True)
                self.assertEqual((root / "lab/engine/custom_components/esp_deck/frontend/esp-deck.js").read_bytes(),
                                 (installed / "frontend/esp-deck.js").read_bytes())
                self.assertIn("sha256", json.loads((root / "lab/installation.json").read_text()))
            with patch.object(ha_lab, "LAB", root / "lab"), patch.object(ha_lab, "ARTIFACT", None):
                ha_lab.stage_integration(root / "lab/source/custom_components")
                self.assertEqual(json.loads((root / "lab/installation.json").read_text()), {"source_tree": True})

    def test_lab_refuses_replacing_running_ha_or_unowned_directory(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(ha_lab, "LAB", Path(directory) / "lab"):
            with patch.object(ha_lab, "inspect_owned", return_value={"State": {"Running": True}}):
                with self.assertRaisesRegex(RuntimeError, "stopped"):
                    ha_release.replace_stopped({})


if __name__ == "__main__":
    unittest.main()
