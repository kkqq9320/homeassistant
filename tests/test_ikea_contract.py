import asyncio
import re
from urllib.parse import parse_qs, unquote, urlparse

from tests.ikea_runtime import BLUEPRINT, ROOT, IkeaBlueprintCase


class IkeaContractTest(IkeaBlueprintCase):
    async def test_document_links_and_source_url(self):
        guide_relative = "blueprints/automation/z2m_ikea_e1744_light_control/README.md"
        guide = ROOT / guide_relative
        self.assertTrue(guide.is_file(), "IKEA 전용 가이드가 필요합니다")
        await self.load()
        source_url = self.blueprint.data["blueprint"]["source_url"]
        self.assertEqual(source_url, "https://github.com/kkqq9320/homeassistant/blob/main/"
                                    "blueprints/automation/z2m_ikea_e1744_light_control.yaml")
        root_readme = ROOT / "README.md"
        self.assertIn(f"]({guide_relative})", root_readme.read_text(encoding="utf-8"))
        for document in (guide, root_readme):
            links = re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8"))
            imports = [parse_qs(urlparse(link).query)["blueprint_url"][0]
                       for link in links if "blueprint_import/?blueprint_url=" in link]
            self.assertIn(source_url, imports)
            for link in links:
                parsed = urlparse(link)
                if not parsed.scheme and parsed.path:
                    self.assertTrue((document.parent / unquote(parsed.path)).exists(), link)

    async def test_blueprint_loads_with_required_inputs_and_defaults(self):
        self.assertTrue(BLUEPRINT.is_file(), "IKEA 블루프린트 파일이 필요합니다")
        await self.load()
        self.assertEqual(self.subscribed_topics, ["zigbee2mqtt/Test Knob"])
        self.assertEqual(self.hass.states.get("automation.ikea_test").state, "on")
        self.assertEqual(self.blueprint.domain, "automation")
        self.assertEqual(self.blueprint.data["blueprint"]["homeassistant"]["min_version"], "2025.4.0")
        self.assertEqual(self.blueprint_inputs.inputs_with_default["rotation_mode"], "brightness")
        self.assertFalse(self.blueprint_inputs.inputs_with_default["restore_brightness"])
        defaults = {"base_topic": "zigbee2mqtt", "brightness_step_pct": 2,
                    "color_temp_step_kelvin": 100, "hue_step_percent": 2,
                    "saturation_step_pct": 2, "repeat_interval_ms": 200,
                    "max_rotation_seconds": 10}
        for name, value in defaults.items():
            self.assertEqual(self.blueprint_inputs.inputs_with_default[name], value)
        tuning = self.blueprint.data["blueprint"]["input"]["tuning"]["input"]
        for name, upper in (("brightness_step_pct", 100), ("color_temp_step_kelvin", 10000),
                            ("hue_step_percent", 100), ("saturation_step_pct", 100),
                            ("repeat_interval_ms", 2000), ("max_rotation_seconds", 30)):
            number = tuning[name]["selector"]["number"]
            self.assertEqual(number["max"], upper)
            self.assertEqual(number["min"], 100 if name == "repeat_interval_ms" else 1)
        for name in ("action_click_short", "action_click_double", "action_click_triple"):
            self.assertEqual(self.blueprint_inputs.inputs_with_default[name], [])

    async def test_click_mapping_and_repeated_click(self):
        await self.load({
            "action_click_short": [{"action": "test.record_click", "data": {"label": "one"}}],
            "action_click_double": [{"action": "test.record_click", "data": {"label": "two"}}],
            "action_click_triple": [{"action": "test.record_click", "data": {"label": "three"}}],
        })
        for count, action in enumerate(
            ("toggle", "toggle", "brightness_step_up", "brightness_step_down"), start=1
        ):
            await self.publish({"action": action})
            await self.wait_clicks(count)
        self.assertEqual(self.click_calls, ["one", "one", "two", "three"])

    async def test_empty_clicks_and_stop_do_not_call_services(self):
        await self.load()
        for action in ("toggle", "brightness_step_up", "brightness_step_down", "brightness_stop"):
            await self.publish({"action": action})
        await asyncio.sleep(0.05)
        self.assertEqual(self.click_calls, [])
        self.assertEqual(self.light_calls, [])

    async def test_invalid_payloads_do_not_run(self):
        await self.load()
        for payload in ("", "{bad", "null", "[]", "42", {}, {"battery": 90},
                        {"action": None}, {"action": {}}, {"action": []},
                        {"action": True}, {"action": ""}, {"action": "other"}):
            await self.publish(payload)
        await asyncio.sleep(0.05)
        self.assertEqual(self.light_calls, [])
        self.assertEqual(self.click_calls, [])
        self.assertEqual(self.automation.action_script.runs, 0)
        self.assertIsNone(self.hass.states.get("automation.ikea_test").attributes["last_triggered"])

    async def test_topic_preserves_case_and_spaces(self):
        await self.load({
            "base_topic": "home/z2m", "knob": "Living Room Knob",
            "action_click_short": [{"action": "test.record_click", "data": {"label": "one"}}],
        })
        self.assertEqual(self.subscribed_topics, ["home/z2m/Living Room Knob"])
        await self.publish({"action": "toggle"}, topic="home/z2m/living room knob")
        self.assertEqual(self.click_calls, [])
        await self.publish({"action": "toggle"})
        await self.wait_clicks(1)
        self.assertEqual(self.click_calls, ["one"])
