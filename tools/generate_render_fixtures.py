"""Record/check renderer regression snapshots; these are not independent Pillow renders."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from PIL import Image, ImageDraw
from generate_reference_fixtures import asymmetric_image
from generate_render_fonts import generate as font_files
from render_test_build import ROOT, build_renderer


def check_or_write(path, data, check):
    if check:
        if path.read_bytes() != data:
            raise SystemExit(f"Rendering fixture differs: {path}")
    else:
        path.write_bytes(data)


def preview(paths, output):
    tile_width, tile_height = 236, 260
    sheet = Image.new("RGB", (tile_width * 4, tile_height * ((len(paths) + 3) // 4)), "#d0d0d0")
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(paths):
        with Image.open(path) as image:
            image = image.transpose(Image.Transpose.ROTATE_180).resize((216, 216), Image.Resampling.NEAREST)
        x, y = (index % 4) * tile_width + 10, (index // 4) * tile_height + 10
        sheet.paste(image, (x, y))
        draw.text((x, y + 225), path.name.removesuffix(".native.bmp"), fill="black")
    sheet.save(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, contents in font_files().items():
        if path.read_bytes() != contents:
            raise SystemExit("Regenerate/verify pinned font assets first")
    folder = ROOT / "tests/fixtures/rendering"
    if not args.check:
        folder.mkdir(parents=True, exist_ok=True)
    check_or_write(folder / "asymmetric.rgb", asymmetric_image().tobytes(), args.check)
    binary = build_renderer()
    with tempfile.TemporaryDirectory(prefix="esp-deck-render-") as temporary:
        candidates = Path(temporary)
        subprocess.run([str(binary), "--record", str(candidates)], cwd=ROOT, check=True)
        for path in sorted(candidates.glob("*.native.bmp")):
            check_or_write(folder / path.name, path.read_bytes(), args.check)
    manifest = {"method": "Native renderer regression snapshots, not an independent rendering oracle",
                "independent_checks": "asymmetric BMP/pages match pinned upstream; analytical alpha/contain/crop checks in test_renderer.cpp",
                "font_manifest_sha256": hashlib.sha256((ROOT / "assets/fonts/manifest.json").read_bytes()).hexdigest(),
                "files": {path.name: {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                          for path in sorted(folder.iterdir()) if path.suffix in (".bmp", ".rgb")}}
    check_or_write(folder / "manifest.json", (json.dumps(manifest, indent=2) + "\n").encode(), args.check)
    preview(sorted(folder.glob("*.native.bmp")), ROOT / ".build/render-preview.png")
    print("Rendering fixtures verified" if args.check else "Rendering snapshots recorded; review .build/render-preview.png")


if __name__ == "__main__":
    main()
