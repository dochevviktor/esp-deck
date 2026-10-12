# Development and testing

No physical board is required for host tests or firmware compilation. Use
Python 3.14, Git, C99 and C++17 compilers; Node.js 22+ is needed for frontend
checks. [Pinned versions and source provenance](versions.md) explain the toolchain.

## Environment and host tests

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m unittest discover -s tests -v
```

With both `libasan` and `libubsan` installed, run native tests with sanitizers:

```sh
SANITIZE=1 UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 .venv/bin/python -m unittest discover -s tests -v
```

`halt_on_error=1` makes UBSan findings fail the process. Protocol and scheduling
remain independent of ESPHome, with byte fixtures from the pinned upstream
encoder and separate native renderer/transport checks.

## Fixtures and firmware

```sh
.venv/bin/python tools/generate_reference_fixtures.py --check
.venv/bin/python tools/generate_render_fonts.py --check
.venv/bin/python tools/generate_render_fixtures.py --check
.venv/bin/python tools/generate_png_fixtures.py --check
.venv/bin/python tools/check_firmware.py
.venv/bin/python tools/check_firmware.py --compile
.venv/bin/python tools/check_artwork_upload.py
```

The firmware checker stages isolated copies with temporary synthetic secrets.
It does not read or modify local `examples/secrets.yaml`. Validation artifacts
and logs stay under ignored `.build/firmware/`; **never flash them**.
It checks generated USB/console settings as well as compilation. Device builds
use the separate [private deployment workflow](getting-started.md#build-for-your-device).

The artwork-upload check uses an independent virtual deck to exercise the
encrypted API and production PNG/rendering path without physical hardware.

## Frontend

```sh
npm ci --prefix frontend --ignore-scripts --no-audit --no-fund
npm run check --prefix frontend
npm test --prefix frontend
```

The check verifies that the committed frontend bundle matches its sources.
Use `npm run build --prefix frontend` after changing the editor.

## Home Assistant lab

The [rootless Podman lab](ha-lab.md) runs real HA with a test-only virtual deck:

```sh
.venv/bin/python tools/ha_lab.py up
.venv/bin/python tools/ha_lab.py test-engine
.venv/bin/python tools/ha_lab.py test
.venv/bin/python tools/ha_lab.py status
.venv/bin/python tools/ha_lab.py down
```

Its default UI is `http://127.0.0.1:18123`; generated credentials and raw results
remain private in `.build/ha-lab/`. In this checkout, that instance has been
retargeted to the physical ESP. The tools refuse synthetic tests/rebuilds against
it; preserve its saved data and use a separate isolated virtual environment.
Do not run `up --fresh` to replace the physical setup.

See [test evidence and pending hardware gates](testing.md) for the distinction
between implemented, compiled, unit-tested, browser-tested and hardware-verified
behavior. [Release qualification](release.md) covers integration packaging,
installation and upgrades.
