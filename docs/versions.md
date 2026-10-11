# Version and source provenance

Baseline selected to match the owner's `hdmi2c/firmware` project. Its Wi-Fi
credentials, C6 pin assignments and device-specific workarounds were not copied.

| Dependency | Pin / resolved version |
| --- | --- |
| ESPHome | 2026.9.0; source `c6e4c87e525dd343e470d8dea368957a002f6505` |
| ESP-IDF | 5.5.5 (ESPHome-supported default, also explicit in YAML); source `b774170ff46c393eeb5e495ea37936038d3f4f4f` |
| USB host | IDF `components/usb` at that revision, with the build-local Original full-speed descriptor hook in `components/stream_deck/idf_usb/`; no separate HID driver package |
| Xtensa compiler | GCC 14.2.0, Espressif `esp-14.2.0_20260121` |
| Build system | Native ESP-IDF/CMake 3.30.2; Ninja 1.13.0 |
| Python used locally | 3.14.7, Linux x86_64 (Fedora kernel 7.1.8-200.fc44) |
| Native test compiler | GCC 16.1.1 (20260515, Red Hat 16.1.1-2) |
| Python Stream Deck reference | 0.10.0, commit `43666bb454186d1d7adeba9402f689449705d0b9` |
| Pillow / BMP fixtures | 12.3.0 |
| Runtime label font | DejaVu Sans 2.37, TTF SHA-256 `7da195a74c55bef988d0d48f9508bd5d849425c1770dba5d7bfc6ce9ed848954`; bundled with release license |
| Glyph rasterizer | ESPHome 2026.9.0 `glyph_to_glyphinfo`, freetype-py 2.5.1 / bundled FreeType 2.13.2 (existing locked Python dependency) |
| PNG inflate/CRC engine | miniz 1.15 from ESPHome's pngle 1.1.0 dependency, source `b1c68193f1d3f8642b3e0e095d457a828038e6fb`; vendored hashes/portable-load patch in `components/stream_deck/third_party/manifest.json` |
| Asset HTTP/TLS | Existing IDF 5.5.5 HTTP client and TCP/TLS transports; certificate chain/hostname/date checks, bounded custom transport, one worker |
| HIDAPI source audit only | 0.15.0, commit `d6b2a974608dec3b76fb1e36c189f22b9cf3650c` |
| mDNS IDF component | `espressif/mdns` 1.12.0, pinned by ESPHome |
| Native API/OTA crypto | `esphome/noise-c` 0.1.30, `esphome/libsodium` 1.10021.11, pinned by ESPHome |
| Home Assistant tested version | 2026.10.1 in the isolated lab, frontend 20260930.3; minimum and current stable checked 2026-10-11; production HA/device runtime acceptance pending |
| ESP Deck HA integration | Local artifact 0.9.0; bundled editor/artwork, v1/v2 adapter; HA 2026.10.1 minimum; see [P9 distribution gates](release.md) |
| HA artwork conversion | Pillow 12.3.0, supplied by the pinned HA image (no extra integration install) |
| Editor build | Node 24.13.0, npm 11.6.2, esbuild 0.25.12; `frontend/package-lock.json`; no browser runtime dependency |
| Hassfest validator | `ghcr.io/home-assistant/hassfest@sha256:4b1adfb1e0a37710af0390708eb8000230b80b2193ccffbeed0a901fa9765181` |
| HACS local schema validator | `ghcr.io/hacs/action@sha256:dc92fdad2f6ffbe74bffb7269d781ea8e064f52d9bb486cdf3925d74e7ab6ebf`, upstream source `3f3080cbf909b8f51488e227be73f62902b4ef6c`; not an installed HACS UI |
| Upgrade baseline | Actual integration 0.8.0 code at `279e58bce7303ea4e7c2cb07cf85cd4c2c9394e6`; schema versions retained in 0.9.0 |
| Current physical firmware | Example 05, compiled `2026-10-11 23:05:52 +0200`, with bounded HTTP provisioning and Redraw/applied-revision fixes; [deployment/evidence](hardware-lab.md) |
| Owner's working desktop Python revision | Not yet supplied |
| Deck firmware | `1.0.191203`, read through desktop HID Feature 4 on 2026-10-10 |

`requirements-dev.txt` contains direct pins and the immutable reference Git SHA;
`requirements-lock.txt` records the entire resolved Python dependency set.
The fixture tool checks the installed upstream commit and Pillow version before
generating or checking bytes. No desktop library runs on the ESP.

P5's image digests, ESPHome host compiler, HA/test/browser versions and separate
Python locks are in [the lab guide](ha-lab.md) and
[`tests/ha_lab/versions.json`](../tests/ha_lab/versions.json). They do not change
the firmware/fixture pins above. HACS remains uninstalled. HA 2026.10.1 is the
initial supported/tested baseline; no earlier-version compatibility is claimed.

The build uses 16 MB flash, DIO flash mode, octal PSRAM at 80 MHz, UART0 logs,
secondary USB console disabled and (driver examples) USB control data cap 8192
and periodic-OUT FIFO bias. The current Original descriptor experiment corrects
only IN to MPS 64 and keeps OUT at its advertised MPS 512. Combined with HID
startup and the 17-byte decoder, this nonstandard full-speed layout now passes
the owner's all-key image-feedback smoke test and one peripheral reconnect;
full qualification remains pending.
The generated partition table has two 7936 KiB OTA slots. These are compile-time
settings, not proven OTA behavior. A desktop `esptool 5.3.1 flash-id` query on
2026-10-10 detected ESP32-S3 revision v0.2 and 16 MB flash and reported embedded
8 MB PSRAM. A later encrypted API session confirmed PSRAM initialized and 8192 KB
available. Stress testing and PCB revision remain unverified. That identity query
did not write flash; subsequent USB/OTA uploads and the full-speed descriptor
mismatch are recorded in [hardware acceptance](hardware.md#network-and-s3-usb-session-2026-10-10).

The compatibility hook checks four original SDK file SHA-256 values stored in
`components/stream_deck/idf_usb/prepare.py` before generating the patched USBH
source. CMake configuration depends on those files and the generator; unreviewed
SDK changes fail the build. The checker verifies that the compiler used the
generated source. No installed framework source is modified. The generated
source remains byte-identical for validation and deployment builds.

Primary pinned sources:

- [ESPHome release](https://github.com/esphome/esphome/tree/c6e4c87e525dd343e470d8dea368957a002f6505)
- [ESP-IDF release](https://github.com/espressif/esp-idf/tree/b774170ff46c393eeb5e495ea37936038d3f4f4f)
- [Python reference](https://github.com/abcminiuser/python-elgato-streamdeck/tree/43666bb454186d1d7adeba9402f689449705d0b9)
- [HIDAPI transport](https://github.com/libusb/hidapi/blob/d6b2a974608dec3b76fb1e36c189f22b9cf3650c/libusb/hid.c)

Each local firmware build has generated `dependencies.lock`,
`sdkconfig.streamdeck-original`, `validation.log`, compiler metadata and artifacts
under `.build/firmware/<example>/`. These include temporary paths and synthetic
secrets and are intentionally not committed. CI actions are pinned by commit and
the CI runner is Ubuntu 24.04 / Python 3.14.7; that remote job has not yet run.
