from pathlib import Path
import unittest

from jinja2 import StrictUndefined
from jinja2.nativetypes import NativeEnvironment
import yaml

ROOT = Path(__file__).resolve().parents[1]


class VisualContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = yaml.safe_load((ROOT / "examples/home_assistant/visual_patch.yaml").read_text())["stream_deck_visual_patch"]
        cls.environment = NativeEnvironment(undefined=StrictUndefined)

    def render(self, patch):
        context = {"session": "0123456789abcdef", "key": 0, "revision": 1, "patch": patch}
        for step in self.script["sequence"]:
            if "if" in step:
                if self.environment.from_string(step["if"]).render(context):
                    raise ValueError(step["then"][0]["stop"])
            else:
                return {name: self.environment.from_string(template).render(context)
                        for name, template in step["data"].items()}
        self.fail("No native API action in helper")

    def test_helper_fixed_arguments_and_presence(self):
        signature = yaml.safe_load((ROOT / "tests/fixtures/visual_api.yaml").read_text())["variables"]
        for patch, mask in (({"image_url": "http://ha.local/a.png", "image_revision": "v1"}, 1),
                            ({"text": "Desk"}, 2), ({"image_url": "", "text": ""}, 3),
                            ({"image_url": "http://ha.local/a.png", "image_revision": "v2", "text": "Desk"}, 3),
                            ({"font": 12, "text_color": "#ffffff", "outline_color": "#000000",
                              "background_color": "#102030", "fit": "contain"}, 124)):
            with self.subTest(patch=patch):
                result = self.render(patch)
                self.assertEqual(set(result), set(signature))
                self.assertEqual(result["fields"], mask)
                self.assertEqual(result["session"], "0123456789abcdef")
                for name, value in patch.items():
                    self.assertEqual(result["label_text" if name == "text" else name], value)

    def test_helper_rejects_ambiguous_or_unknown_fields(self):
        for patch in ({}, None, "Desk", {"texxt": "Desk"}, {"image_revision": "v2"},
                      {"text": None}, {"image_url": None}, {"text": 123}, {"font": True}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.render(patch)

    def test_helper_distinguishes_empty_from_omitted(self):
        preserved = self.render({"font": 16})
        cleared = self.render({"text": ""})
        self.assertEqual(preserved["label_text"], cleared["label_text"])
        self.assertEqual(preserved["fields"], 4)
        self.assertEqual(cleared["fields"], 2)
