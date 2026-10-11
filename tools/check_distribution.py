#!/usr/bin/env python3
"""Run pinned upstream distribution validators against a private staged copy.

Default: Hassfest plus HACS's actual local manifest schemas. --online additionally
runs the full HACS repository action; that requires a published GitHub repository
and GITHUB_TOKEN. It does not publish code or post PR comments.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HASSFEST = "ghcr.io/home-assistant/hassfest@sha256:4b1adfb1e0a37710af0390708eb8000230b80b2193ccffbeed0a901fa9765181"
HACS = "ghcr.io/hacs/action@sha256:dc92fdad2f6ffbe74bffb7269d781ea8e064f52d9bb486cdf3925d74e7ab6ebf"
SCHEMAS = """
import json
from pathlib import Path
from custom_components.hacs.utils.validate import HACS_MANIFEST_JSON_SCHEMA, INTEGRATION_MANIFEST_JSON_SCHEMA
root = Path('/github/workspace')
hacs = HACS_MANIFEST_JSON_SCHEMA(json.loads((root / 'hacs.json').read_text()))
INTEGRATION_MANIFEST_JSON_SCHEMA(json.loads((root / 'custom_components/esp_deck/manifest.json').read_text()))
assert not hacs.get('zip_release') or hacs.get('filename')
assert (root / 'custom_components/esp_deck/brand/icon.png').is_file()
print('Upstream HACS manifest schemas passed (local files; not online repository validation)')
"""


def run(command, logfile, *, env=None):
    with logfile.open("w") as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, env=env)
    print(f"{logfile.stem}: {'passed' if result.returncode == 0 else 'FAILED'}; {logfile.relative_to(ROOT)}", flush=True)
    return result.returncode == 0


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", choices=("podman", "docker"), default="podman")
    parser.add_argument("--online", metavar="OWNER/REPOSITORY", help="also validate an already published GitHub repository")
    args = parser.parse_args()
    parent = ROOT / ".build/distribution"
    parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix="validation-", dir=parent))
    shutil.copytree(ROOT / "custom_components", staged / "custom_components",
                    ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("hacs.json", "README.md", "LICENSE"):
        shutil.copyfile(ROOT / name, staged / name)
    base = [args.runtime, "run", "--rm", "--cap-drop=all", "--security-opt=no-new-privileges",
            "-v", f"{staged}:/github/workspace:ro,Z"]
    success = run([*base, HASSFEST], staged / "hassfest.log")
    success = run([*base, "--entrypoint", "python3", HACS, "-c", SCHEMAS], staged / "hacs-schemas.log") and success
    results = {"hassfest_image": HASSFEST, "hacs_schema_image": HACS, "local_passed": success,
               "online_repository": "not run", "hacs_install_update": "not run"}
    if args.online:
        if not os.environ.get("GITHUB_TOKEN"):
            parser.error("--online requires GITHUB_TOKEN; no credentials are read from HA or firmware")
        environment = {**os.environ, "INPUT_GITHUB_TOKEN": os.environ["GITHUB_TOKEN"]}
        online = run([*base, "--env", "INPUT_GITHUB_TOKEN", "--env", "INPUT_CATEGORY=integration",
                      "--env", "INPUT_COMMENT=false", "--env", f"GITHUB_REPOSITORY={args.online}",
                      "--env", "GITHUB_WORKSPACE=/github/workspace", HACS], staged / "hacs-online.log", env=environment)
        results["online_repository"] = "passed" if online else "failed"
        success = online and success
    (staged / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
