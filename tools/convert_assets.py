"""Convert artwork to an upstream-native 72x72 RGB BMP and SHA-256 manifest."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageOps
from StreamDeck.ImageHelpers import PILHelper

from reference import PILLOW_VERSION, REVISION, make_deck


def convert(source, background, fit):
    deck, _ = make_deck()
    rgba = ImageOps.exif_transpose(source).convert("RGBA")
    # Explicitly flatten alpha before scaling, including fully transparent pixels.
    canvas = Image.new("RGBA", rgba.size, background)
    canvas.alpha_composite(rgba)
    rgb = canvas.convert("RGB")
    if fit == "crop":
        rgb = ImageOps.fit(rgb, (72, 72), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    else:
        scaled = ImageOps.contain(rgb, (72, 72), method=Image.Resampling.LANCZOS)
        rgb = Image.new("RGB", (72, 72), background)
        rgb.paste(scaled, ((72 - scaled.width) // 2, (72 - scaled.height) // 2))
    return PILHelper.to_native_key_format(deck, rgb)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--background", required=True, help="Explicit RGB color, e.g. '#101820'")
    parser.add_argument("--fit", choices=("contain", "crop"), default="contain")
    args = parser.parse_args()
    with Image.open(args.source) as source:
        native = convert(source, args.background, args.fit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(native)
    manifest = {"source": args.source.name, "file": args.output.name, "size": len(native),
                "sha256": hashlib.sha256(native).hexdigest(), "background": args.background,
                "fit": args.fit, "reference_revision": REVISION, "pillow": PILLOW_VERSION}
    args.output.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{args.output}: {len(native)} bytes, SHA-256 {manifest['sha256']}")


if __name__ == "__main__":
    main()
