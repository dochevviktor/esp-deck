"""Hardware/container-independent guards for the P5 lab boundary."""
import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from tools import ha_lab

spec = importlib.util.spec_from_file_location("lab_fetch", ha_lab.FIXTURES / "fetch_asset.py")
fetcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetcher)


class LabTests(unittest.TestCase):
    def test_unowned_containers_and_networks_are_never_removed(self):
        for kind in ("container", "network"):
            item = {"Config": {"Labels": {ha_lab.LABEL: "someone-else"}}, "labels": {ha_lab.LABEL: "someone-else"}}
            result = subprocess.CompletedProcess([], 0, json.dumps([item]))
            with patch.object(ha_lab, "podman", return_value=result) as command:
                with self.assertRaisesRegex(RuntimeError, "unowned"):
                    ha_lab.inspect_owned(kind, "foreign")
                command.assert_called_once_with(kind, "inspect", "foreign", check=False)

    def test_inspection_failure_is_not_treated_as_resource_absence(self):
        result = subprocess.CompletedProcess([], 125, "daemon error")
        with patch.object(ha_lab, "podman", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "Cannot inspect"):
                ha_lab.inspect_owned("container", "lab")

    def test_down_targets_only_owned_named_resources_and_retains_data(self):
        item = {"State": {"Running": True}}
        with patch.object(ha_lab, "inspect_owned", return_value=item) as inspect:
            with patch.object(ha_lab, "podman") as command, patch("builtins.print"):
                ha_lab.down()
                self.assertEqual(command.call_args_list[-1].args, ("network", "rm", ha_lab.PREFIX))
                self.assertTrue(all(call.args[-1] in (ha_lab.PREFIX, ha_lab.PREFIX + "-ha",
                                                     ha_lab.PREFIX + "-deck") for call in command.call_args_list))
                self.assertEqual(inspect.call_count, 3)

    def test_private_staging_copies_production_sources_and_the_real_api(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "lab"
            with patch.object(ha_lab, "LAB", directory):
                ha_lab.stage()
                self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
                self.assertEqual((directory / "credentials.json").stat().st_mode & 0o777, 0o600)
                self.assertEqual((directory / "deck/secrets.yaml").stat().st_mode & 0o777, 0o600)
                source = ha_lab.ROOT / "components/stream_deck"
                for stem in ha_lab.PORTABLE:
                    for extension in (".cpp", ".h"):
                        name = stem + extension
                        self.assertEqual((directory / "deck/components/virtual_deck" / name).read_bytes(),
                                         (source / name).read_bytes())
                original = (ha_lab.ROOT / "examples/packages/runtime_api.yaml").read_text().split("\napi:\n")[1]
                v2 = (ha_lab.ROOT / "examples/packages/runtime_api_v2.yaml").read_text().split("  actions:\n", 1)[1]
                self.assertEqual((directory / "deck/runtime_api.yaml").read_text(), "api:\n" + original + v2)
                self.assertFalse((directory / "deck/components/virtual_deck/usb_transport.cpp").exists())
                self.assertFalse((directory / "deck/components/virtual_deck/asset_http.cpp").exists())

    def test_staging_refuses_unmarked_or_symlinked_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "valuable").write_text("keep")
            with patch.object(ha_lab, "LAB", root):
                with self.assertRaisesRegex(RuntimeError, "unmarked"):
                    ha_lab.owned_directory()
            alias = root / "alias"
            alias.symlink_to(root, target_is_directory=True)
            with patch.object(ha_lab, "LAB", alias):
                with self.assertRaisesRegex(RuntimeError, "symlinked"):
                    ha_lab.owned_directory()

    def test_host_fetch_bounds_redirects_types_and_actual_body(self):
        requests = []
        png = (ha_lab.ROOT / "tests/fixtures/png/rgba.png").read_bytes()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                requests.append(self.path)
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "/should-not-fetch")
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/html" if self.path == "/html" else "image/png")
                if self.path == "/declared-big":
                    self.send_header("Content-Length", str(fetcher.LIMIT + 1))
                self.end_headers()
                try:
                    self.wfile.write(b"X" * (fetcher.LIMIT + 1) if self.path == "/stream-big" else png)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            origin = f"http://127.0.0.1:{server.server_port}"
            try:
                self.assertEqual(fetcher.fetch(origin + "/png"), (200, 0, png))
                self.assertEqual(fetcher.fetch(origin + "/redirect")[:2], (302, 2))
                self.assertEqual(fetcher.fetch(origin + "/html")[:2], (200, 3))
                self.assertEqual(fetcher.fetch(origin + "/declared-big")[:2], (200, 4))
                self.assertEqual(fetcher.fetch(origin + "/stream-big")[:2], (200, 4))
                self.assertNotIn("/should-not-fetch", requests)
            finally:
                server.shutdown()
                thread.join()


if __name__ == "__main__":
    unittest.main()
