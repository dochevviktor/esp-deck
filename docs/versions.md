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
| HIDAPI source audit only | 0.15.0, commit `d6b2a974608dec3b76fb1e36c189f22b9cf3650c` |
| mDNS IDF component | `espressif/mdns` 1.12.0, pinned by ESPHome |
| Native API/OTA crypto | `esphome/noise-c` 0.1.30, `esphome/libsodium` 1.10021.11, pinned by ESPHome |
| Home Assistant tested version | None; not connected/tested |
| Owner's working desktop Python revision | Not yet supplied |
| Deck firmware | `1.0.191203`, read through desktop HID Feature 4 on 2026-10-10 |

`requirements-dev.txt` contains direct pins and the immutable reference Git SHA;
`requirements-lock.txt` records the entire resolved Python dependency set.
The fixture tool checks the installed upstream commit and Pillow version before
generating or checking bytes. No desktop library runs on the ESP.

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
