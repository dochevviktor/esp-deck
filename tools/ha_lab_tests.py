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


def run_engine_tests():
    lab.owned_directory()
    # The HA-image Python and installed HA packages are the engine-test oracle.
    test_root = lab.LAB / "pytest"
    shutil.copytree(lab.ROOT / "tests/ha", test_root / "tests", dirs_exist_ok=True)
    shutil.copytree(lab.ROOT / "examples/home_assistant", test_root / "examples", dirs_exist_ok=True)
    lab.stage_integration(test_root / "custom_components", installed=True)
    lab.podman("run", "--rm", "--name", lab.PREFIX + "-pytest", "--label", f"{lab.LABEL}={lab.OWNER}",
        "--cap-drop=all", "--security-opt=no-new-privileges", "-v", f"{test_root}:/tests:Z",
        "--entrypoint", "sh", lab.LOCK["home_assistant"]["image"], "-c",
        "python -m venv --system-site-packages /tests/venv && "
        "/tests/venv/bin/pip install --no-deps -r /tests/tests/requirements.txt && "
        "cd /tests && /tests/venv/bin/python -m pytest -q /tests/tests --junitxml=/tests/ha-engine.xml",
        log=lab.LAB / "ha-engine.log")
    print("HA engine tests passed (mock native transport)", flush=True)


def run_tests(*, release_only=False):
    lab.owned_directory()
    lab.ensure_virtual_target()
    for suffix in ("ha", "deck"):
        item = lab.inspect_owned("container", lab.PREFIX + "-" + suffix)
        if not item or not item["State"]["Running"]:
            raise RuntimeError("Run tools/ha_lab.py up before test")
    lab.refresh_token()
    if not release_only:
        run_engine_tests()
    # Preserve the lab mount's SELinux label (copy2 would copy workspace xattrs).
    shutil.copyfile(lab.FIXTURES / "native_probe.py", lab.LAB / "deck/native_probe.py")
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
    receipt = lab.LAB / "installation.json"
    release_tests = ([str(lab.FIXTURES / "test_release.py")]
                     if receipt.is_file() and "sha256" in json.loads(receipt.read_text()) else [])
    if release_only and not release_tests:
        raise RuntimeError("test-release requires an installed release ZIP")
    if not release_tests:
        print("P9 archive scenarios require up --artifact; running development regression suites", flush=True)
    paths = release_tests if release_only else [str(lab.FIXTURES / name) for name in (
        "test_live.py", "test_backend.py", "test_editor.py", "test_v2.py")] + release_tests
    prefix = "release" if release_only else "live"
    try:
        logged([str(runner / "bin/python"), "-m", "pytest", "-v", "-x", *paths,
                "--junitxml=" + str(lab.LAB / f"{prefix}.xml")], lab.LAB / f"{prefix}-tests.log", env=environment)
    finally:
        # Raw logs stay private. Tests/report contain only synthetic payloads.
        for suffix in ("ha", "deck"):
            lab.podman("logs", lab.PREFIX + "-" + suffix, log=lab.LAB / f"{suffix}.log", check=False)
    lab.record_versions()
    lab.private_write(lab.LAB / ("release-results.json" if release_only else "results.json"), json.dumps({
        "ha_engine": "not run" if release_only else "passed (mock native transport)",
        "real_ha_native_api_browser": "passed (P9 only)" if release_only else "passed", "hardware": "not tested",
        "archive_lifecycle": "passed" if release_tests else "not run (source-tree install)",
        "versions": json.loads((lab.LAB / "versions.json").read_text()),
    }, indent=2) + "\n")
    print("Real HA/native-API and browser tests passed; results in .build/ha-lab/", flush=True)
