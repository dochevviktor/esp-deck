"""Deterministic diagnostic artwork; no downloaded icons or font dependencies."""
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from convert_assets import convert
from reference import PILLOW_VERSION, REVISION

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / "assets"
    (folder / "source").mkdir(parents=True, exist_ok=True)
    (folder / "native").mkdir(parents=True, exist_ok=True)
    manifest = {"reference_revision": REVISION, "pillow": PILLOW_VERSION, "files": {}}
    for name, fill, label in (("light_on", "#eec84b", "ON"), ("light_off", "#526170", "OFF"),
                              ("unknown", "#dc7054", "?")):
        artwork = Image.new("RGB", (72, 72), "#101820")
        draw = ImageDraw.Draw(artwork)
        draw.rectangle((3, 3, 7, 7), fill="red")
        draw.ellipse((20, 10, 51, 41), fill=fill)
        draw.rectangle((29, 37, 42, 49), fill=fill)
        draw.line((29, 53, 42, 53), fill="white", width=2)
        draw.text((27 if len(label) == 2 else 24, 58), label, fill="white")
        artwork.save(folder / "source" / f"{name}.png")
        native = convert(artwork, "#101820", "contain")
        (folder / "native" / f"{name}.bmp").write_bytes(native)
        manifest["files"][f"{name}.bmp"] = {"size": len(native), "sha256": hashlib.sha256(native).hexdigest()}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Generated three firmware-resident demo images")


if __name__ == "__main__":
    main()
