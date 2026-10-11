"""Execute the shipped HA templates/sequence logic against a fake API.

This is not a running HA integration or a network/device test. Native tests
separately exercise the production visual API, pipeline and USB scheduler.
"""
from copy import deepcopy
from pathlib import Path
import re
from types import SimpleNamespace
import unittest

from jinja2 import StrictUndefined
from jinja2.nativetypes import NativeEnvironment
import yaml

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples/home_assistant"
SESSION_ENTITY = "sensor.stream_deck_original_visual_session"


class ScriptReturn(Exception):
    def __init__(self, result):
        self.result = result


class Harness:
    def __init__(self):
        self.scripts = yaml.safe_load((EXAMPLES / "runtime_scripts.yaml").read_text())
        self.scripts.update(yaml.safe_load((EXAMPLES / "visual_patch.yaml").read_text()))
        self.environment = NativeEnvironment(undefined=StrictUndefined)
        self.environment.filters["regex_match"] = lambda value, pattern: re.match(pattern, value) is not None
        self.states = {SESSION_ENTITY: "abcdef0123456789", "light.example_lamp": "off"}
        self.environment.globals["states"] = lambda entity: self.states.get(entity, "unknown")
        self.revisions = [0] * 15
        self.writes = []
        self.calls = []
        self.reject = False

    def render(self, value, context):
        if isinstance(value, dict):
            return {key: self.render(item, context) for key, item in value.items()}
        if isinstance(value, list):
            return [self.render(item, context) for item in value]
        if isinstance(value, str) and ("{{" in value or "{%" in value):
            return self.environment.from_string(value).render(context)
        return value

    def run(self, name, **inputs):
        try:
            self.steps(self.scripts[name]["sequence"], dict(inputs))
        except ScriptReturn as result:
            return result.result

    def steps(self, sequence, context):
        for step in sequence:
            if "variables" in step:
                for name, value in step["variables"].items():
                    context[name] = self.render(value, context)
            elif "if" in step:
                if self.render(step["if"], context):
                    self.steps(step["then"], context)
            elif "repeat" in step:
                for index in range(1, step["repeat"]["count"] + 1):
                    context["repeat"] = {"index": index}
                    self.steps(step["repeat"]["sequence"], context)
            elif "stop" in step:
                if step.get("error"):
                    raise ValueError(self.render(step["stop"], context))
                raise ScriptReturn(context[step["response_variable"]])
            elif "action" in step:
                name = step["action"]
                data = self.render(step.get("data", {}), context)
                self.calls.append((name, deepcopy(data)))
                if name.startswith("script."):
                    result = self.run(name.removeprefix("script."), **data)
                elif name.endswith("get_key_visual_status"):
                    result = {"accepted": True, "revision": self.revisions[data["key"]], "error": "none"}
                elif name.endswith("set_key_visual"):
                    result = {"accepted": not self.reject, "revision": data["revision"],
                              "error": "invalid_text" if self.reject else "none", "phase": "queued"}
                    self.writes.append(data)
                    if not self.reject:
                        self.revisions[data["key"]] = data["revision"]
                else:
                    raise AssertionError(name)
                if "response_variable" in step:
                    context[step["response_variable"]] = result
            else:
                raise AssertionError(step)


class HomeAssistantTests(unittest.TestCase):
    def test_replay_uses_current_state_and_all_fields_for_all_keys(self):
        ha = Harness()
        for state, suffix, label in (("off", "light_off.png", "Desk OFF"),
                                     ("on", "light_on.png", "Desk ON"),
                                     ("unavailable", "unknown.png", "Desk ?")):
            ha.states["light.example_lamp"] = state
            ha.writes.clear()
            ha.run("stream_deck_sync_layout")
            self.assertEqual([wire["key"] for wire in ha.writes], list(range(15)))
            self.assertTrue(all(wire["fields"] == 127 for wire in ha.writes))
            self.assertTrue(ha.writes[0]["image_url"].endswith(suffix))
            self.assertEqual(ha.writes[0]["label_text"], label)
            self.assertEqual(ha.writes[1]["label_text"], "Home Assistant")
            self.assertTrue(all(wire["image_url"] == "" for wire in ha.writes[1:]))
            self.assertTrue(all(wire["label_text"] == "" for wire in ha.writes[2:]))

    def test_ha_restart_queries_revision_and_esp_restart_uses_new_session(self):
        ha = Harness()
        ha.revisions[0] = 57  # ESP outlived HA; no local counter is restored.
        result = ha.run("stream_deck_apply", key=0, patch={"text": "123"})
        self.assertEqual(result["revision"], 58)
        self.assertEqual(ha.writes[-1]["label_text"], "123")
        self.assertEqual(ha.calls[0][0], "esphome.streamdeck_original_get_key_visual_status")
        ha.revisions = [0] * 15
        ha.states[SESSION_ENTITY] = "1234567890123456"
        ha.run("stream_deck_sync_layout")
        self.assertTrue(all(wire["revision"] == 1 for wire in ha.writes[-15:]))
        self.assertTrue(all(wire["session"] == "1234567890123456" for wire in ha.writes[-15:]))
        self.assertEqual(ha.scripts["stream_deck_apply"]["mode"], "queued")

    def test_offline_exhausted_and_rejected_requests_stop_explicitly(self):
        ha = Harness()
        for state in ("unavailable", "unknown", "", "xyz"):
            ha.states[SESSION_ENTITY] = state
            with self.assertRaisesRegex(ValueError, "session is unavailable"):
                ha.run("stream_deck_apply", key=0, patch={"text": "A"})
        self.assertFalse(ha.calls)
        ha.states[SESSION_ENTITY] = "abcdef0123456789"
        ha.revisions[0] = 2147483647
        with self.assertRaisesRegex(ValueError, "Cannot advance"):
            ha.run("stream_deck_apply", key=0, patch={"text": "A"})
        self.assertFalse(ha.writes)
        ha.revisions[0] = 0
        ha.reject = True
        with self.assertRaisesRegex(ValueError, "invalid_text"):
            ha.run("stream_deck_apply", key=0, patch={"text": "A"})

    def test_rebinding_and_artwork_choices_live_only_in_ha(self):
        ha = Harness()
        layout = ha.scripts["stream_deck_sync_layout"]["sequence"][0]["variables"]
        layout.update(lamp_entity="light.new_binding", key_0_label="New", artwork_revision="v2")
        ha.states["light.new_binding"] = "on"
        ha.run("stream_deck_sync_layout")
        self.assertEqual(ha.writes[0]["label_text"], "New ON")
        self.assertEqual(ha.writes[0]["image_revision"], "v2")
        firmware = (ROOT / "examples/05_home_assistant_runtime.yaml").read_text()
        for forbidden in ("light.example_lamp", "on_key_press:", "on_key_release:", "on_boot:", "homeassistant.action"):
            self.assertNotIn(forbidden, firmware)

    def test_event_guards_reject_restore_and_availability_transitions(self):
        automations = yaml.safe_load((EXAMPLES / "runtime_automations.yaml").read_text())
        environment = NativeEnvironment(undefined=StrictUndefined)
        for automation, kind in zip(automations[1:], ("press", "release"), strict=True):
            template = environment.from_string(automation["conditions"][0]["value_template"])
            def fires(before, after, event_type=kind, restored=False):
                state = lambda value: None if value is None else SimpleNamespace(
                    state=value, attributes={"event_type": event_type, "restored": restored})
                return template.render(trigger={"from_state": state(before), "to_state": state(after)})
            self.assertTrue(fires("unknown", "2026-10-11T10:00:00+00:00"))
            self.assertTrue(fires("old-timestamp", "new-timestamp"))
            for before, after in ((None, "timestamp"), ("unavailable", "timestamp"),
                                  ("timestamp", "unavailable"), ("timestamp", "unknown"),
                                  ("timestamp", "timestamp")):
                self.assertFalse(fires(before, after))
            self.assertFalse(fires("old", "new", restored=True))
            self.assertFalse(fires("old", "new", event_type="release" if kind == "press" else "press"))

    def test_replay_triggers_cover_restart_reconnection_and_external_state(self):
        automation = yaml.safe_load((EXAMPLES / "runtime_automations.yaml").read_text())[0]
        triggers = automation["triggers"]
        self.assertIn({"trigger": "homeassistant", "event": "start"}, triggers)
        self.assertIn({"trigger": "state", "entity_id": SESSION_ENTITY}, triggers)
        self.assertIn({"trigger": "state", "entity_id": "light.example_lamp"}, triggers)
        ha = Harness()
        for suffix in ("get_key_visual_status", "set_key_visual"):
            self.assertIn({"trigger": "event", "event_type": "service_registered", "event_data": {
                "domain": "esphome", "service": "streamdeck_original_" + suffix}}, triggers)
        waiting = automation["actions"][1]
        self.assertEqual(waiting["timeout"], "00:01:00")
        self.assertFalse(waiting["continue_on_timeout"])
        self.assertTrue(ha.render(waiting["wait_template"], {}))
        ha.states[SESSION_ENTITY] = "unavailable"
        self.assertFalse(ha.render(waiting["wait_template"], {}))
        # Real pinned ESPHome does not send stored events in subscription snapshots.
        import esphome
        source = Path(esphome.__file__).parent / "components/api/subscribe_state.cpp"
        self.assertRegex(source.read_text(), r"InitialStateIterator::on_event\(event::Event \*entity\) \{ return true; \}")

    def test_native_action_signature_and_metadata_match_contract(self):
        class Loader(yaml.SafeLoader):
            pass
        Loader.add_constructor("!lambda", lambda loader, node: loader.construct_scalar(node))
        package = yaml.load((ROOT / "examples/packages/runtime_api.yaml").read_text(), Loader=Loader)
        actions = {item["action"]: item for item in package["api"]["actions"]}
        self.assertEqual(set(actions), {"set_key_visual", "clear_key_visual", "refresh_key_image", "get_key_visual_status"})
        contract = yaml.safe_load((ROOT / "tests/fixtures/visual_api.yaml").read_text())["variables"]
        self.assertEqual({name: spec["type"] for name, spec in actions["set_key_visual"]["variables"].items()}, contract)
        for action in actions.values():
            self.assertEqual(action["supports_response"], "only")
            self.assertTrue(action["description"])
            self.assertTrue(all(spec["description"] for spec in action["variables"].values()))


if __name__ == "__main__":
    unittest.main()
