"""Validate synthetic builds; explicitly use --deploy for a local device build."""
import argparse
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ("01_usb_probe", "02_keys_brightness", "03_images_home_assistant", "04_hardware_test", "renderer_probe")


def stage(folder, device_secrets=None):
    for name in ("components", "assets", "examples"):
        shutil.copytree(ROOT / name, folder / name,
                        ignore=shutil.ignore_patterns("secrets.yaml", ".esphome", "__pycache__"))
    secrets = folder / "examples" / "secrets.yaml"
    if device_secrets is not None:
        shutil.copyfile(device_secrets, secrets)
        secrets.chmod(0o600)
    else:
        secrets.write_text(
            'wifi_ssid: "CI-NOT-A-REAL-NETWORK"\n'
            'wifi_password: "CI-NOT-A-REAL-PASSWORD"\n'
            f'api_encryption_key: "{base64.b64encode(bytes(range(32))).decode()}"\n')


def check(folder, name, compile_firmware=False, extra=None, deployment=False):
    build = ROOT / ".build" / ("deploy" if deployment else "firmware") / name
    args = [sys.executable, "-m", "esphome", "-s", "build_dir", str(build),
            "compile" if compile_firmware else "config", str(folder / "examples" / f"{name}.yaml")]
    if extra:
        args.extend(extra)
    # Deployment logs/artifacts may contain credentials; the CLI protects their
    # directory and never prints raw compiler/configuration output in that mode.
    result = subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if compile_firmware:
        build.mkdir(parents=True, exist_ok=True)
        (build / "validation.log").write_text(result.stdout)
    if result.returncode:
        if not deployment:
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
        if name != "01_usb_probe":
            if "CONFIG_USB_HOST_HW_BUFFER_BIAS_PERIODIC_OUT=y" not in actual.read_text():
                raise RuntimeError("The Original 512-byte output endpoint requires the periodic-OUT FIFO bias")
            commands = json.loads((build / "build" / "compile_commands.json").read_text())
            if not any(Path(command["file"]).name == "usbh_stream_deck.c" for command in commands):
                raise RuntimeError("The build did not compile the pinned Stream Deck USB compatibility source")
            transport = next(command for command in commands if Path(command["file"]).name == "usb_transport.cpp")
            if "/components/usb/include" not in transport["command"]:
                raise RuntimeError("The application did not receive the USB component's public include directory")
    print(f"{name}: {'compiled' if compile_firmware else 'configuration valid'}", flush=True)
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--example", choices=EXAMPLES)
    parser.add_argument("--deploy", action="store_true",
                        help="Build with local examples/secrets.yaml for upload; requires --compile and --example")
    args = parser.parse_args()
    if args.deploy and (not args.compile or not args.example):
        parser.error("--deploy requires --compile and one --example")
    device_secrets = ROOT / "examples" / "secrets.yaml" if args.deploy else None
    if args.deploy:
        if not device_secrets.is_file():
            parser.error("Deployment requires local examples/secrets.yaml")
        os.umask(0o077)
        private = ROOT / ".build" / "deploy"
        private.mkdir(parents=True, exist_ok=True, mode=0o700)
        private.chmod(0o700)
        print("Deployment build: local credentials; private artifacts under .build/deploy/", flush=True)
    with tempfile.TemporaryDirectory(prefix="esp-deck-check-") as temporary:
        folder = Path(temporary)
        stage(folder, device_secrets)
        for name in ((args.example,) if args.example else EXAMPLES):
            print(f"Checking {name}...", flush=True)
            check(folder, name, args.compile, deployment=args.deploy)


if __name__ == "__main__":
    main()
