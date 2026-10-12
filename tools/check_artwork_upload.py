#!/usr/bin/env python3
"""Build and test real encrypted API uploads in a fresh, network-isolated host deck.

Uses synthetic secrets and the pinned ESPHome image. Never opens an ESP address
or touches existing HA lab data. Private artifacts are retained under .build/.
"""
from pathlib import Path
import shutil
import tempfile

import ha_lab as lab
from ha_lab_tests import run_engine_tests


def main():
    lab.ROOT.joinpath(".build").mkdir(exist_ok=True)
    lab.LAB = Path(tempfile.mkdtemp(prefix="artwork-upload-", dir=lab.ROOT / ".build"))
    lab.PREFIX += "-" + lab.LAB.name
    print(f"Isolated upload validation: {lab.LAB}", flush=True)
    binary = lab.build()
    run_engine_tests()
    shutil.copyfile(lab.FIXTURES / "upload_probe.py", lab.LAB / "deck/upload_probe.py")
    name = lab.PREFIX + "-deck"
    lab.podman("run", "-d", "--name", name, "--label", f"{lab.LABEL}={lab.OWNER}", "--network=none",
        "--cap-drop=all", "--security-opt=no-new-privileges", "-v", f"{lab.LAB / 'deck'}:/lab:Z", "-w", "/lab",
        "--entrypoint", "/lab/" + str(binary.relative_to(lab.LAB / "deck")), lab.ensure_image("esphome_host"))
    try:
        result = lab.podman("exec", name, "python", "/lab/upload_probe.py", log=lab.LAB / "upload-test.log")
        print(result.stdout.strip(), flush=True)
    finally:
        if lab.inspect_owned("container", name):
            lab.podman("logs", name, log=lab.LAB / "virtual-deck.log", check=False)
            lab.podman("stop", "-t", "5", name)
            lab.podman("rm", name)


if __name__ == "__main__":
    main()
