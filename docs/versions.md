# Version and source provenance

Baseline selected to match the owner's `hdmi2c/firmware` project. Its Wi-Fi
credentials, C6 pin assignments and device-specific workarounds were not copied.

| Dependency | Pin / resolved version |
| --- | --- |
| ESPHome | 2026.9.0; source `c6e4c87e525dd343e470d8dea368957a002f6505` |
| ESP-IDF | 5.5.5 (ESPHome-supported default, also explicit in YAML); source `b774170ff46c393eeb5e495ea37936038d3f4f4f` |
| USB host | IDF built-in `components/usb` at that IDF revision; no separate HID/USB package |
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
| Owner's desktop Python revision / deck firmware | Not yet supplied |

`requirements-dev.txt` contains direct pins and the immutable reference Git SHA;
`requirements-lock.txt` records the entire resolved Python dependency set.
The fixture tool checks the installed upstream commit and Pillow version before
generating or checking bytes. No desktop library runs on the ESP.

The build uses 16 MB flash, DIO flash mode, octal PSRAM at 80 MHz, UART0 logs,
secondary USB console disabled and (driver examples) USB control data cap 8192.
The generated partition table has two 7936 KiB OTA slots. These are compile-time
settings, not measured board memory or proven OTA behavior. Boot memory detection
and board revision still need validation.

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
