#!/usr/bin/env python3
"""Build a deterministic HACS ZIP containing only the HA integration.

The archive's root is the integration directory's contents, as required by
HACS zip_release. Extract it into config/custom_components/esp_deck for a direct
installation. Never include firmware, local configuration, tests or credentials.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "esp_deck"
FILES = (
    "__init__.py", "adapter.py", "advanced.py", "api.py", "artwork.py",
    "config_flow.py", "const.py", "controller.py", "diagnostics.py", "model.py",
    "panel.py", "repairs.py", "select.py", "sensor.py", "storage.py",
    "manifest.json", "services.yaml", "strings.json", "translations/en.json",
    "frontend/esp-deck.js", "frontend/LICENSE-DejaVu.txt",
    "brand/icon.png", "brand/icon@2x.png", "LICENSE", "NOTICE",
)
MAX_ARCHIVE = 4 * 1024 * 1024


def validate(root=ROOT):
    integration = root / "custom_components" / DOMAIN
    manifest = json.loads((integration / "manifest.json").read_text())
    hacs = json.loads((root / "hacs.json").read_text())
    frontend = json.loads((root / "frontend/package.json").read_text())
    lock = json.loads((root / "frontend/package-lock.json").read_text())
    if manifest["domain"] != DOMAIN or not manifest.get("config_flow"):
        raise ValueError("Wrong integration domain/config flow")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-(?:alpha|beta|rc)\.[0-9]+)?", manifest["version"]):
        raise ValueError("Release version must be a semantic version, never a path")
    if len({manifest["version"], frontend["version"], lock["version"], lock["packages"][""]["version"]}) != 1:
        raise ValueError("Integration/frontend versions disagree")
    if hacs != {"name": "ESP Deck", "homeassistant": "2026.10.1", "zip_release": True, "filename": "esp_deck.zip"}:
        raise ValueError("Unexpected HACS packaging or minimum HA version")
    if (integration / "strings.json").read_bytes() != (integration / "translations/en.json").read_bytes():
        raise ValueError("English translations differ from strings.json")
    if (integration / "LICENSE").read_bytes() != (root / "LICENSE").read_bytes():
        raise ValueError("Packaged project license differs")
    if {path.name for path in integration.glob("*.py")} != {name for name in FILES if name.endswith(".py")}:
        raise ValueError("Python module list changed: review the release allowlist")
    for name in FILES:
        path = integration / name
        if not path.is_file() or path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise ValueError(f"Missing or symlinked release file: {name}")
    return manifest


def archive_bytes(root=ROOT):
    validate(root)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(FILES):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (root / "custom_components" / DOMAIN / name).read_bytes(), compresslevel=9)
    payload = output.getvalue()
    inspect_archive(payload)
    return payload


def inspect_archive(payload):
    """Validate completely before installation; never use unchecked extractall."""
    if len(payload) > MAX_ARCHIVE:
        raise ValueError("Release archive too large")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(FILES):
            raise ValueError("Release archive has unexpected or missing files")
        total = 0
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            if (path.is_absolute() or ".." in path.parts or "\\" in item.filename
                    or stat.S_ISLNK(item.external_attr >> 16) or item.is_dir()):
                raise ValueError("Unsafe release archive member")
            total += item.file_size
            if total > MAX_ARCHIVE:
                raise ValueError("Expanded release archive too large")
        files = {name: archive.read(name) for name in names}
    manifest = json.loads(files["manifest.json"])
    if manifest.get("domain") != DOMAIN:
        raise ValueError("Wrong release domain")
    return files


def extract_new(payload, destination):
    """Install into a new staging directory, never overwrite existing HA data."""
    files = inspect_archive(payload)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink() or any(p.is_symlink() for p in destination.parents):
        raise ValueError("Release destination must be new and not symlinked")
    destination.mkdir(parents=True, mode=0o700)
    for name, content in files.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return json.loads(files["manifest.json"])


def build(root=ROOT, output=None):
    manifest = validate(root)
    directory = output or root / ".build/release" / manifest["version"]
    directory.mkdir(parents=True, exist_ok=True)
    payload = archive_bytes(root)
    artifact = directory / "esp_deck.zip"
    artifact.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    (directory / "SHA256SUMS").write_text(f"{digest}  esp_deck.zip\n")
    (directory / "release.json").write_text(json.dumps({
        "version": manifest["version"], "sha256": digest,
        "files": {name: hashlib.sha256(data).hexdigest()
                  for name, data in inspect_archive(payload).items()},
    }, indent=2) + "\n")
    return artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate without writing an archive")
    args = parser.parse_args()
    if args.check:
        archive_bytes()
        print("Release contents, versions and archive safety passed local checks")
    else:
        print(build().relative_to(ROOT))


if __name__ == "__main__":
    main()
