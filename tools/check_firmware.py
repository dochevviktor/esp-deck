"""Validate/build isolated copies using synthetic secrets, never local credentials."""
import argparse
import base64
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ("01_usb_probe", "02_keys_brightness", "03_images_home_assistant")


def stage(folder):
    for name in ("components", "assets", "examples"):
        shutil.copytree(ROOT / name, folder / name,
                        ignore=shutil.ignore_patterns("secrets.yaml", ".esphome", "__pycache__"))
    (folder / "examples" / "secrets.yaml").write_text(
        'wifi_ssid: "CI-NOT-A-REAL-NETWORK"\n'
        'wifi_password: "CI-NOT-A-REAL-PASSWORD"\n'
        f'api_encryption_key: "{base64.b64encode(bytes(range(32))).decode()}"\n')


def check(folder, name, compile_firmware=False, extra=None):
    build = ROOT / ".build" / "firmware" / name
    args = [sys.executable, "-m", "esphome", "-s", "build_dir", str(build),
            "compile" if compile_firmware else "config", str(folder / "examples" / f"{name}.yaml")]
    if extra:
        args.extend(extra)
    # config output contains the synthetic values only; keep normal runs concise.
    result = subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if compile_firmware:
        build.mkdir(parents=True, exist_ok=True)
        (build / "validation.log").write_text(result.stdout)
    if result.returncode:
        print("\n".join(result.stdout.splitlines()[-90:]))
        if compile_firmware:
            print(f"Full build log: {build / 'validation.log'}")
        raise subprocess.CalledProcessError(result.returncode, args)
    if compile_firmware:
        for line in result.stdout.splitlines():
            if any(word in line for word in ("successfully compiled", "SUCCESS", "Flash:", "RAM:")):
                print(line)
        sdkconfig = build / "sdkconfig.streamdeck-original"
        candidates = [sdkconfig, build / "sdkconfig"]
        actual = next((p for p in candidates if p.is_file()), None)
        if actual is None:
            raise RuntimeError(f"No generated sdkconfig in {build}")
        if name != "01_usb_probe" and "CONFIG_USB_HOST_CONTROL_TRANSFER_MAX_SIZE=8192" not in actual.read_text():
            raise RuntimeError("Generated USB control-transfer limit does not match the transport decision")
        if "CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG=y" in actual.read_text():
            raise RuntimeError("The secondary USB console must be disabled for native USB host operation")
    print(f"{name}: {'compiled' if compile_firmware else 'configuration valid'}", flush=True)
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--example", choices=EXAMPLES)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="esp-deck-check-") as temporary:
        folder = Path(temporary)
        stage(folder)
        for name in ((args.example,) if args.example else EXAMPLES):
            print(f"Checking {name}...", flush=True)
            check(folder, name, args.compile)


if __name__ == "__main__":
    main()
