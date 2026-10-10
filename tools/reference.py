"""Pinned desktop encoder, used only by offline tools and independent fixtures."""
import importlib.metadata
import json

REVISION = "43666bb454186d1d7adeba9402f689449705d0b9"
PILLOW_VERSION = "12.3.0"


def check_versions():
    distribution = importlib.metadata.distribution("streamdeck")
    direct = json.loads(distribution.read_text("direct_url.json") or "{}")
    if direct.get("vcs_info", {}).get("commit_id") != REVISION:
        raise RuntimeError("Install requirements-dev.txt: the upstream encoder must match its pinned commit")
    if importlib.metadata.version("Pillow") != PILLOW_VERSION:
        raise RuntimeError(f"Fixture generation requires Pillow {PILLOW_VERSION}")


class RecordingTransport:
    def __init__(self):
        self.output = []
        self.features = []

    def write(self, data):
        self.output.append(bytes(data))

    def write_feature(self, data):
        self.features.append(bytes(data))

    def close(self):
        pass


def make_deck():
    check_versions()
    from StreamDeck.Devices.StreamDeckOriginal import StreamDeckOriginal

    transport = RecordingTransport()
    return StreamDeckOriginal(transport), transport
