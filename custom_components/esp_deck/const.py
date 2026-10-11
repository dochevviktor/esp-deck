"""The deliberately small v1 integration/firmware boundary."""

DOMAIN = "esp_deck"
MIN_HA_VERSION = "2026.10.1"
KEY_COUNT = 15
MAX_REVISION = 2_147_483_647
MAX_LAYOUT_BYTES = 131_072
EVENT_KEY = "esp_deck_key"
SIGNAL_STATUS = "esp_deck_status_{}"
P4_AUTOMATION_IDS = {
    "stream_deck_replay_layout", "stream_deck_key_0_press", "stream_deck_key_0_release",
}
P4_SCRIPTS = (
    "script.stream_deck_apply", "script.stream_deck_sync_layout", "script.stream_deck_visual_patch",
)
DEFAULT_VISUAL = {
    "image_url": "", "image_revision": "", "text": "", "font": 16,
    "text_color": "#FFFFFF", "outline_color": "#000000",
    "background_color": "#000000", "fit": "contain",
}
# Native argument types are checked against discovery, not inferred from names.
SIGNATURES = {
    "get_key_visual_status": {"session": "STRING", "key": "INT"},
    "set_key_visual": {
        "session": "STRING", "key": "INT", "revision": "INT", "fields": "INT",
        "image_url": "STRING", "image_revision": "STRING", "label_text": "STRING",
        "font": "INT", "text_color": "STRING", "outline_color": "STRING",
        "background_color": "STRING", "fit": "STRING",
    },
    "clear_key_visual": {"session": "STRING", "key": "INT", "revision": "INT"},
    "refresh_key_image": {
        "session": "STRING", "key": "INT", "revision": "INT", "image_revision": "STRING",
    },
}
