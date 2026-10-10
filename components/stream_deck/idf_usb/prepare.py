"""Patch a build-local copy of pinned IDF USBH; never modify the SDK installation."""
import argparse
import hashlib
from pathlib import Path

EXPECTED = {
    "usbh.c": "0c6e108d5ce61e7325da6b5d33fff603a0644bd033426e52ba8506fc7067a061",
    "usb_host.c": "90c363001ce460d2d1648db89f2db4a7aab126446ce2f6840e27c462a009f83f",
    "CMakeLists.txt": "9d1795dec7d80f1bc003505ddb0cd81be52d71364ab3335fd3a29677051baba4",
    "Kconfig": "1ccc477bba307a41ecc7fc118b2580fe0ca791e2fb47e339a65a372d7a28577a",
}
INCLUDE = '#include "usb/usb_types_ch9.h"\n'
COPY = '    memcpy(new_desc, config_desc_full, config_desc_full->wTotalLength);\n'
HOOK = '''
    // ESP Deck local compatibility patch, pinned IDF 5.5.5.
    // Modify only our new, unpublished copy; endpoint allocation sees the same
    // normalized descriptor as the class driver, without mutating a const view.
    if (dev_obj->constant.desc != NULL &&
            stream_deck_normalize_config(dev_obj->constant.desc->idVendor,
                                         dev_obj->constant.desc->idProduct,
                                         dev_obj->constant.speed == USB_SPEED_FULL,
                                         (uint8_t *)new_desc, config_desc_full->wTotalLength)) {
        ESP_LOGW(USBH_TAG, "Stream Deck Original full-speed endpoint quirk: 512 -> 64");
    }
'''


def patch_source(source):
    if source.count(INCLUDE) != 1 or source.count(COPY) != 1:
        raise RuntimeError("Pinned USBH patch anchors differ; review the SDK before building")
    if "stream_deck_normalize_config" in source:
        raise RuntimeError("Refusing an already patched USBH source")
    return source.replace(INCLUDE, INCLUDE + '#include "stream_deck_quirk.h"\n').replace(COPY, COPY + HOOK)


def prepare(upstream, output):
    if output.resolve().is_relative_to(upstream.resolve()):
        raise RuntimeError("The patched output must be outside the SDK USB source directory")
    sources = {}
    for name, expected in EXPECTED.items():
        data = (upstream / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError(f"Unsupported IDF USB source: {name}; expected the pinned 5.5.5 revision")
        sources[name] = data
    patched = patch_source(sources["usbh.c"].decode()).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists() or output.read_bytes() != patched:
        output.write_bytes(patched)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.upstream, args.output)


if __name__ == "__main__":
    main()
