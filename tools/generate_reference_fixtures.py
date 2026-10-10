"""Generate byte fixtures by invoking upstream methods, never the new C++ codec."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
from StreamDeck.ImageHelpers import PILHelper

from reference import PILLOW_VERSION, REVISION, make_deck

ROOT = Path(__file__).resolve().parents[1]


def generate():
    deck, recording = make_deck()
    image = Image.new("RGB", (72, 72), (18, 22, 29))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 17, 17), fill="red")
    draw.rectangle((54, 0, 71, 17), fill="green")
    draw.rectangle((0, 54, 17, 71), fill="blue")
    draw.polygon([(18, 29), (45, 29), (45, 21), (63, 36), (45, 51), (45, 42), (18, 42)], fill="white")
    draw.text((3, 19), "TL", fill="yellow")
    native = PILHelper.to_native_key_format(deck, image)
    files = {"asymmetric.native.bmp": native}
    for percent in (0, 1, 50, 100):
        deck.set_brightness(percent)
        files[f"brightness_{percent}.bin"] = recording.features.pop()
    deck.reset()
    files["device_reset.bin"] = recording.features.pop()
    deck._reset_key_stream()
    files["stream_reset.bin"] = recording.output.pop()
    for key in (0, 4, 5, 10, 14):
        deck.set_key_image(key, native)
        assert len(recording.output) == 2
        for page, report in enumerate(recording.output, 1):
            files[f"key_{key}_page_{page}.bin"] = report
        recording.output.clear()
    manifest = {
        "reference_repository": "https://github.com/abcminiuser/python-elgato-streamdeck",
        "reference_revision": REVISION,
        "pillow": PILLOW_VERSION,
        "method": "StreamDeckOriginal + PILHelper, recording transport; no physical USB",
        "files": {name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                  for name, data in sorted(files.items())},
    }
    files["manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare with committed fixtures without changing them")
    args = parser.parse_args()
    folder = ROOT / "tests" / "fixtures"
    for name, data in generate().items():
        path = folder / name
        if args.check:
            if path.read_bytes() != data:
                raise SystemExit(f"Fixture differs: {path}")
        else:
            folder.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    print("Reference fixtures verified" if args.check else "Reference fixtures generated")


if __name__ == "__main__":
    main()
