# ESP Deck

Read STREAM_DECK_ESPHOME_CODEX_HANDOVER.md and docs/decisions/usb-transport.md.
For the next stage, read docs/implementation-plan.md: HA owns runtime bindings
and visual configuration; the ESP renders images/text. It supersedes the original
handover's deferral of runtime text and URL-loaded artwork, not its hardware rules.
Target only Stream Deck Original 0FD9:0060 on XIAO ESP32-S3 Plus, ESP-IDF.
Keep protocol/scheduling independent of ESPHome and test against pinned upstream
fixtures. Native USB belongs to the host; logs use UART0. VBUS is external and
unswitched: never invent a power GPIO or claim a controller reset removes power.
Preserve local changes and secrets. Never commit credentials or build binaries.
Report implemented, compiled, unit-tested and hardware-verified separately.

Use .venv/bin/python -m unittest discover -s tests -v for host tests.
Use .venv/bin/python tools/check_firmware.py --compile for firmware validation
with temporary synthetic secrets. For an explicitly requested device flash, add
--deploy --example NAME to build privately with local examples/secrets.yaml;
never upload the synthetic validation images. No hardware is required to build.
Hardware gates and measurements in docs/hardware.md remain pending until tested.
