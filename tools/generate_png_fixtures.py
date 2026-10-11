"""PNG inputs and decoded RGBA expectations, independently checked with Pillow."""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import struct
import zlib

from PIL import Image
from generate_reference_fixtures import asymmetric_image

ROOT = Path(__file__).resolve().parents[1]


def chunk(name, data):
    return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data))


def png(width, height, depth, color, compressed, before=b"", after=b"", interlace=0):
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, color, 0, 0, interlace))
            + before + chunk(b"IDAT", compressed) + after + chunk(b"IEND", b""))


def generate():
    files, valid, invalid = {}, [], []

    def good(name, data, expected=None):
        with Image.open(BytesIO(data)) as decoded:
            width, height = decoded.size
            actual = decoded.convert("RGBA").tobytes()
        if expected is not None:
            assert actual == expected, name
        files[name + ".png"] = data
        files[name + ".rgba"] = actual
        valid.append({"name": name, "width": width, "height": height})

    for name, image in (("asymmetric", asymmetric_image()),
                        ("rgba", Image.frombytes("RGBA", (37, 19), bytes((x * 29 + x // 4 * 7) % 256 for x in range(37 * 19 * 4)))),
                        ("grey", Image.frombytes("L", (13, 7), bytes(range(91)))),
                        ("grey_alpha", Image.frombytes("LA", (7, 9), bytes(range(126)))),
                        ("maximum", Image.new("RGBA", (256, 256), (31, 90, 185, 127)))):
        stream = BytesIO(); image.save(stream, format="PNG"); good(name, stream.getvalue())
    palette = Image.new("P", (17, 11))
    palette.putpalette([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 0] + [0] * (768 - 12))
    palette.putdata([n % 4 for n in range(17 * 11)])
    stream = BytesIO(); palette.save(stream, format="PNG", bits=2, transparency=bytes([255, 128, 0, 255]))
    good("palette2", stream.getvalue())
    for depth in (1, 2, 4):
        good(f"grey{depth}", png(8, 1, depth, 0, zlib.compress(b"\0" + bytes([0x1b, 0xe4, 0x12, 0xab])[:depth])))
    # Exercise every PNG row filter; Pillow independently checks the hand-built stream.
    rows = [bytes((n * 17 + y * 23) % 256 for n in range(9 * 3)) for y in range(5)]
    raw = bytearray()
    for y, row in enumerate(rows):
        raw.append(y)
        for x, value in enumerate(row):
            a = row[x - 3] if x >= 3 else 0
            b = rows[y - 1][x] if y else 0
            c = rows[y - 1][x - 3] if y and x >= 3 else 0
            p = a + b - c
            paeth = min((a, b, c), key=lambda v: abs(p - v))
            predictor = (0, a, b, (a + b) // 2, paeth)[y]
            raw.append((value - predictor) % 256)
    expected = b"".join(row[x:x + 3] + b"\xff" for row in rows for x in range(0, len(row), 3))
    good("filters", png(9, 5, 8, 2, zlib.compress(raw)), expected)
    grey16 = png(3, 1, 16, 0, zlib.compress(b"\0" + struct.pack(">HHH", 0, 32768, 65535)))
    # Pillow's I-mode conversion clips instead of scaling 16-bit samples. The
    # contract normalizes the full 16-bit range; these values have exact expectations.
    files["grey16.png"] = grey16
    files["grey16.rgba"] = bytes([0, 0, 0, 255, 128, 128, 128, 255, 255, 255, 255, 255])
    valid.append({"name": "grey16", "width": 3, "height": 1})
    # Explicit 16-bit expectations also cover transparency comparisons before
    # down-conversion and the maximum filtered-source allocation (RGBA16).
    for name, width, height, color, samples, before, expected in (
        ("rgb16_transparent", 2, 1, 2, struct.pack(">6H", 65535, 0, 32768, 0, 65535, 0),
         chunk(b"tRNS", struct.pack(">3H", 65535, 0, 32768)), bytes([255, 0, 128, 0, 0, 255, 0, 255])),
        ("grey_alpha16", 2, 1, 4, struct.pack(">4H", 32768, 32768, 65535, 0), b"",
         bytes([128, 128, 128, 128, 255, 255, 255, 0])),
        ("maximum16", 256, 256, 6, struct.pack(">4H", 65535, 32768, 0, 65535) * 256, b"",
         bytes([255, 128, 0, 255]) * (256 * 256)),
    ):
        data = png(width, height, 16, color, zlib.compress((b"\0" + samples) * height), before=before)
        with Image.open(BytesIO(data)) as decoded:
            decoded.verify()
        files[name + ".png"] = data; files[name + ".rgba"] = expected
        valid.append({"name": name, "width": width, "height": height})
    base = png(1, 1, 8, 2, zlib.compress(b"\0\x12\x34\x56"))
    split = base[:33] + b"".join(chunk(b"IDAT", piece) for piece in (base[41:44], b"", base[44:-16])) + base[-12:]
    good("split_idat", split)
    good("transparent_rgb", png(1, 1, 8, 2, zlib.compress(b"\0\x12\x34\x56"),
                                 before=chunk(b"tRNS", struct.pack(">HHH", 0x12, 0x34, 0x56))))

    cases = {
        "truncated": base[:-1], "trailing": base + b"x",
        "bad_crc": base[:29] + bytes([base[29] ^ 1]) + base[30:],
        "wide": png(257, 1, 8, 2, zlib.compress(b"\0" * 772)),
        "huge": png(0xffffffff, 0xffffffff, 8, 6, zlib.compress(b"\0")),
        "zero": png(0, 1, 8, 2, zlib.compress(b"\0")),
        "interlaced": png(1, 1, 8, 2, zlib.compress(b"\0\x12\x34\x56"), interlace=1),
        "animation": png(1, 1, 8, 2, zlib.compress(b"\0\x12\x34\x56"), before=chunk(b"acTL", struct.pack(">II", 1, 0))),
        "critical": png(1, 1, 8, 2, zlib.compress(b"\0\x12\x34\x56"), before=chunk(b"BADX", b"")),
        "short_pixels": png(1, 1, 8, 2, zlib.compress(b"\0\x12")),
        "bomb": png(1, 1, 8, 2, zlib.compress(b"\0" * 4000000)),
        "bad_adler": png(1, 1, 8, 2, zlib.compress(b"\0\x12\x34\x56")[:-1] + b"x"),
        "missing_adler": png(1, 1, 8, 2, zlib.compress(b"\0\x12\x34\x56")[:-4]),
        "extra_zlib": png(1, 1, 8, 2, zlib.compress(b"\0\x12\x34\x56") + b"extra"),
        "bad_filter": png(1, 1, 8, 2, zlib.compress(b"\5\x12\x34\x56")),
        "palette_index": png(1, 1, 8, 3, zlib.compress(b"\0\5"), before=chunk(b"PLTE", b"\xff\0\0")),
        "late_transparency": png(1, 1, 8, 2, zlib.compress(b"\0\x12\x34\x56"), after=chunk(b"tRNS", bytes(6))),
        "many_chunks": png(1, 1, 8, 2, zlib.compress(b"\0\x12\x34\x56"), before=chunk(b"teSt", b"") * 256),
    }
    for name, data in cases.items():
        files["invalid_" + name + ".png"] = data; invalid.append("invalid_" + name)
    manifest = {"method": "Pillow plus PNG chunks/zlib; Pillow independently verifies decoded RGBA except documented 16-bit normalization",
                "valid": valid, "invalid": invalid,
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    files["manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    lines = ['// Generated by tools/generate_png_fixtures.py', 'struct PngCase { const char *name; unsigned width, height; };',
             'const PngCase VALID_PNGS[] = {']
    lines.extend(f'  {{"{case["name"]}", {case["width"]}, {case["height"]}}},' for case in valid)
    lines.extend(['};', 'const char *INVALID_PNGS[] = {', *(f'  "{name}",' for name in invalid), '};', ''])
    files["cases.h"] = "\n".join(lines).encode()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--check", action="store_true")
    args = parser.parse_args(); folder = ROOT / "tests/fixtures/png"
    if not args.check: folder.mkdir(parents=True, exist_ok=True)
    for name, data in generate().items():
        if args.check:
            if (folder / name).read_bytes() != data: raise SystemExit(f"PNG fixture differs: {name}")
        else: (folder / name).write_bytes(data)
    print("PNG fixtures verified" if args.check else "PNG fixtures generated")


if __name__ == "__main__": main()
