"""Run the separate HA engine, real-session and browser P5 test layers."""
import json
import os
import subprocess
import shutil
import venv

import ha_lab as lab


def logged(command, path, *, env=None):
    with path.open("w") as output:
        result = subprocess.run(command, cwd=lab.ROOT, env=env, stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"Test step failed; see {path}")


def run_tests():
    lab.owned_directory()
    for suffix in ("ha", "deck"):
        item = lab.inspect_owned("container", lab.PREFIX + "-" + suffix)
        if not item or not item["State"]["Running"]:
            raise RuntimeError("Run tools/ha_lab.py up before test")
    lab.refresh_token()
    # The HA-image Python and installed HA packages are the engine-test oracle.
    test_root = lab.LAB / "pytest"
    shutil.copytree(lab.ROOT / "tests/ha", test_root / "tests", dirs_exist_ok=True)
    shutil.copytree(lab.ROOT / "examples/home_assistant", test_root / "examples", dirs_exist_ok=True)
    # Preserve the lab mount's SELinux label (copy2 would copy workspace xattrs).
    shutil.copyfile(lab.FIXTURES / "native_probe.py", lab.LAB / "deck/native_probe.py")
    lab.podman("run", "--rm", "--name", lab.PREFIX + "-pytest", "--label", f"{lab.LABEL}={lab.OWNER}",
        "--cap-drop=all", "--security-opt=no-new-privileges", "-v", f"{test_root}:/tests:Z",
        "--entrypoint", "sh", lab.LOCK["home_assistant"]["image"], "-c",
        "python -m venv --system-site-packages /tests/venv && "
        "/tests/venv/bin/pip install --no-deps -r /tests/tests/requirements.txt && "
        "/tests/venv/bin/python -m pytest -q /tests/tests --junitxml=/tests/ha-engine.xml",
        log=lab.LAB / "ha-engine.log")
    print("HA engine tests passed (mock native transport)", flush=True)
    runner = lab.LAB / "runner"
    if not (runner / "bin/python").exists():
        venv.EnvBuilder(with_pip=True).create(runner)
    logged([str(runner / "bin/pip"), "install", "-r", str(lab.FIXTURES / "requirements-lock.txt")],
           lab.LAB / "runner-install.log")
    environment = {**os.environ, "PYTHONPATH": str(lab.ROOT),
                   "PLAYWRIGHT_BROWSERS_PATH": str(lab.LAB / "browsers")}
    logged([str(runner / "bin/python"), "-m", "playwright", "install", "chromium", "--only-shell"],
           lab.LAB / "browser-install.log", env=environment)
    print("Running real HA/native-API and browser scenarios", flush=True)
    try:
        logged([str(runner / "bin/python"), "-m", "pytest", "-v", "-x", str(lab.FIXTURES / "test_live.py"),
                "--junitxml=" + str(lab.LAB / "live.xml")], lab.LAB / "live-tests.log", env=environment)
    finally:
        # Raw logs stay private. Tests/report contain only synthetic payloads.
        for suffix in ("ha", "deck"):
            lab.podman("logs", lab.PREFIX + "-" + suffix, log=lab.LAB / f"{suffix}.log", check=False)
    lab.record_versions()
    lab.private_write(lab.LAB / "results.json", json.dumps({
        "ha_engine": "passed (mock native transport)",
        "real_ha_native_api_browser": "passed", "hardware": "not tested",
        "versions": json.loads((lab.LAB / "versions.json").read_text()),
    }, indent=2) + "\n")
    print("Real HA/native-API and browser tests passed; results in .build/ha-lab/", flush=True)
