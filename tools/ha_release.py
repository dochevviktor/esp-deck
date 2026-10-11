#!/usr/bin/env python3
"""Install release archives in the owned HA lab, retaining previous code.

Never operates on production HA. It stops only the ownership-checked lab HA
container, replaces its integration directory, and restarts it. Layouts,
artwork, ESPHome pairing and the virtual deck process are preserved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess

try:
    from . import ha_lab as lab, package_release
except ImportError:
    import ha_lab as lab
    import package_release

UPGRADE_BASELINE = "279e58bce7303ea4e7c2cb07cf85cd4c2c9394e6"


def baseline_files():
    """Read the actual P8 source snapshot, not current code with an old version."""
    prefix = "custom_components/esp_deck/"
    names = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", UPGRADE_BASELINE, "--", prefix],
                                    cwd=lab.ROOT, text=True).splitlines()
    files = {}
    for name in names:
        relative = name.removeprefix(prefix)
        if relative not in package_release.FILES:
            raise ValueError("Unexpected file in pinned upgrade baseline")
        files[relative] = subprocess.check_output(["git", "show", f"{UPGRADE_BASELINE}:{name}"], cwd=lab.ROOT)
    if json.loads(files["manifest.json"])["version"] != "0.8.0":
        raise ValueError("Wrong upgrade baseline version")
    return files


def replace_stopped(files):
    """Swap lab code only after complete archive validation and stopping HA."""
    lab.owned_directory()
    item = lab.inspect_owned("container", lab.PREFIX + "-ha")
    if not item or item["State"]["Running"]:
        raise RuntimeError("The owned HA lab container must be stopped before replacing integration code")
    target = lab.LAB / "config/custom_components/esp_deck"
    if target.is_symlink() or any(path.is_symlink() for path in target.parents):
        raise RuntimeError("Refusing symlinked lab integration")
    history = lab.LAB / "installations" / secrets.token_hex(8)
    history.mkdir(parents=True, mode=0o700)
    incoming = history / "incoming"
    incoming.mkdir()
    for name, data in files.items():
        if name not in package_release.FILES:
            raise ValueError("Unexpected installation file")
        path = incoming / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    previous = history / "previous"
    if target.exists():
        target.rename(previous)
    try:
        incoming.rename(target)
    except BaseException:
        if previous.exists():
            previous.rename(target)
        raise
    return previous


def install(files, *, artifact=None, baseline=False):
    lab.owned_directory()
    item = lab.inspect_owned("container", lab.PREFIX + "-ha")
    if not item:
        raise RuntimeError("Start the isolated lab before installing a release")
    was_running = item["State"]["Running"]
    if was_running:
        lab.podman("stop", "--time", "10", lab.PREFIX + "-ha")
    try:
        previous = replace_stopped(files)
        record = {"version": json.loads(files["manifest.json"])["version"],
                  "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
        if artifact is not None:
            (lab.LAB / "installed-release.zip").write_bytes(artifact)
            record["sha256"] = hashlib.sha256(artifact).hexdigest()
        if baseline:
            record["upgrade_baseline"] = UPGRADE_BASELINE
        lab.private_write(lab.LAB / "installation.json", json.dumps(record, indent=2) + "\n")
    finally:
        if was_running:
            # New files need the lab mount's SELinux label. Recreate the owned
            # stopped container to apply :Z only to its private config copy.
            lab.start_ha(recreate=True)
    if was_running:
        lab.wait_for_ha()
    return previous


def main():
    import fcntl
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    payload = args.artifact.read_bytes()
    files = package_release.inspect_archive(payload)
    lab.owned_directory()
    with (lab.ROOT / ".build/ha-lab.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        install(files, artifact=payload)
    print("Release installed in the private lab; previous code and HA data retained")


if __name__ == "__main__":
    main()
