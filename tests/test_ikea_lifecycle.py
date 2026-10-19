import asyncio
import time

from homeassistant.components.trace.util import async_get_trace, async_list_traces
from homeassistant.exceptions import HomeAssistantError

from tests.ikea_runtime import IkeaBlueprintCase


class IkeaLifecycleTest(IkeaBlueprintCase):
    def on(self, brightness=102):
        self.set_light("on", brightness=brightness, supported_color_modes=["brightness"])

    async def test_stop_during_service_prevents_later_calls(self):
        self.on()
        self.service_gate = asyncio.Event()
        await self.load()
        await self.publish({"action": "brightness_move_up"})
        await self.wait_calls(1)
        old_context = self.light_calls[0].context_id
        await self.publish({"action": "brightness_stop"})
        self.service_gate.set()
        await asyncio.sleep(0.45)
        self.assertEqual(sum(c.context_id == old_context for c in self.light_calls), 1)
        self.assertFalse(self.automation.action_script.is_running)

    async def assert_new_gesture(self, action, expected=None):
        self.on()
        self.service_gate = asyncio.Event()
        await self.load({"action_click_short": [{"action": "test.record_click", "data": {"label": "click"}}]})
        await self.publish({"action": "brightness_move_up"})
        await self.wait_calls(1)
        old_context = self.light_calls[0].context_id
        self.on(153)
        await self.publish({"action": action})
        if expected is None:
            await self.wait_clicks(1)
        else:
            await self.wait_calls(2)
            self.assertEqual(self.light_calls[1].data["brightness_pct"], expected)
            self.assertNotEqual(self.light_calls[1].context_id, old_context)
        self.service_gate.set()
        await asyncio.sleep(0.35)
        await self.publish({"action": "brightness_stop"})
        self.assertEqual(sum(c.context_id == old_context for c in self.light_calls), 1)

    async def test_opposite_direction_cancels_old_context(self):
        await self.assert_new_gesture("brightness_move_down", 58)

    async def test_same_direction_cancels_old_context(self):
        await self.assert_new_gesture("brightness_move_up", 62)

    async def test_click_cancels_old_context(self):
        await self.assert_new_gesture("toggle")

    async def test_empty_click_stops_rotation(self):
        self.on()
        await self.load()
        for action in ("toggle", "brightness_step_up", "brightness_step_down"):
            offset = len(self.light_calls)
            await self.publish({"action": "brightness_move_up"})
            await self.wait_calls(offset + 1)
            await self.publish({"action": action})
            await asyncio.sleep(0.25)
            self.assertEqual(len(self.light_calls), offset + 1)

    async def test_new_event_cancels_slow_click_sequence(self):
        await self.load({"action_click_short": [
            {"action": "test.record_click", "data": {"label": "before"}},
            {"delay": {"seconds": 1}},
            {"action": "test.record_click", "data": {"label": "after"}}]})
        await self.publish({"action": "toggle"})
        await self.wait_clicks(1)
        await self.publish({"action": "brightness_stop"})
        await asyncio.sleep(1.15)
        self.assertEqual(self.click_calls, ["before"])

    async def test_non_action_report_does_not_interrupt(self):
        self.on()
        await self.load()
        await self.publish({"action": "brightness_move_up"})
        await self.wait_calls(1)
        for payload in ("", "{bad", "null", "[]", "42", {}, {"battery": 90},
                        {"action": None}, {"action": {}}, {"action": []},
                        {"action": True}, {"action": ""}, {"action": "other"}):
            await self.publish(payload)
        await self.wait_calls(3)
        await self.publish({"action": "brightness_stop"})
        self.assertEqual([c.data["brightness_pct"] for c in self.light_calls], [42, 44, 46])
        self.assertEqual(len({c.context_id for c in self.light_calls}), 1)

    async def test_repeat_spacing_and_deadline(self):
        self.on()
        await self.load({"max_rotation_seconds": 1, "repeat_interval_ms": 200})
        started = time.monotonic()
        await self.publish({"action": "brightness_move_up"})
        await self.wait_calls(3)
        await asyncio.sleep(0.9)
        calls = self.light_calls.copy()
        self.assertFalse(self.automation.action_script.is_running)
        self.assertLess(calls[-1].at - started, 1.05)
        for before, after in zip(calls, calls[1:]):
            self.assertGreaterEqual(after.at - before.at, 0.19)
        await asyncio.sleep(0.25)
        self.assertEqual(self.light_calls, calls)

    async def test_slow_service_return_after_deadline_does_not_repeat(self):
        self.on()
        self.service_gate = asyncio.Event()
        await self.load({"max_rotation_seconds": 1})
        await self.publish({"action": "brightness_move_up"})
        await self.wait_calls(1)
        await asyncio.sleep(1.1)
        self.service_gate.set()
        await asyncio.sleep(0.3)
        self.assertEqual(len(self.light_calls), 1)
        self.assertFalse(self.automation.action_script.is_running)

    async def test_repeat_interval_starts_after_service_returns(self):
        self.on()
        self.service_gate = asyncio.Event()
        await self.load()
        await self.publish({"action": "brightness_move_up"})
        await self.wait_calls(1)
        await asyncio.sleep(0.3)
        released = time.monotonic()
        self.service_gate.set()
        await self.wait_calls(2)
        await self.publish({"action": "brightness_stop"})
        self.assertGreaterEqual(self.light_calls[1].at - released, 0.19)

    async def test_deadline_bounds_long_repeat_delay(self):
        self.on()
        await self.load({"max_rotation_seconds": 1, "repeat_interval_ms": 2000})
        await self.publish({"action": "brightness_move_up"})
        await self.wait_calls(1)
        await asyncio.sleep(1.3)
        self.assertEqual(len(self.light_calls), 1)
        self.assertFalse(self.automation.action_script.is_running)

    async def test_same_direction_restarts_deadline(self):
        self.on()
        await self.load({"max_rotation_seconds": 1})
        started = time.monotonic()
        await self.publish({"action": "brightness_move_up"})
        await self.wait_calls(4)
        old_context = self.light_calls[0].context_id
        self.on(153)
        offset = len(self.light_calls)
        await self.publish({"action": "brightness_move_up"})
        await self.wait_calls(offset + 4)
        self.assertEqual(self.light_calls[offset].data["brightness_pct"], 62)
        self.assertNotEqual(self.light_calls[offset].context_id, old_context)
        self.assertGreater(self.light_calls[-1].at - started, 1.0)
        self.assertTrue(all(c.context_id != old_context for c in self.light_calls[offset:]))
        await asyncio.sleep(0.55)
        self.assertFalse(self.automation.action_script.is_running)

    async def test_off_unknown_unavailable_stop(self):
        await self.load()
        for state in ("off", "unknown", "unavailable"):
            self.on()
            offset = len(self.light_calls)
            await self.publish({"action": "brightness_move_up"})
            await self.wait_calls(offset + 1)
            self.set_light(state, supported_color_modes=["brightness"])
            await asyncio.sleep(0.3)
            self.assertEqual(len(self.light_calls), offset + 1)
            self.assertFalse(self.automation.action_script.is_running)

    async def test_reload_cancels_rotation(self):
        self.on()
        await self.load()
        await self.publish({"action": "brightness_move_up"})
        await self.wait_calls(1)
        await self.reload_automations()
        await asyncio.sleep(0.3)
        self.assertEqual(len(self.light_calls), 1)
        self.assertFalse(self.automation.action_script.is_running)
        await self.publish({"action": "brightness_move_down"})
        await self.wait_calls(2)
        await self.publish({"action": "brightness_stop"})
        self.assertEqual(self.light_calls[1].data["brightness_pct"], 38)

    async def test_shutdown_cancels_rotation(self):
        self.on()
        await self.load()
        await self.publish({"action": "brightness_move_up"})
        await self.wait_calls(1)
        await self.hass.async_stop(force=True)
        await asyncio.sleep(0.3)
        self.assertEqual(len(self.light_calls), 1)
        self.assertFalse(self.automation.action_script.is_running)

    async def test_service_error_ends_run(self):
        self.on()
        self.service_error = HomeAssistantError("expected IKEA test failure")
        await self.load()
        with self.assertLogs("homeassistant.components.automation", level="ERROR") as logs:
            await self.publish({"action": "brightness_move_up"})
            await self.wait_calls(1)
            await asyncio.sleep(0.3)
        self.assertTrue(any("expected IKEA test failure" in line for line in logs.output))
        self.assertEqual(len(self.light_calls), 1)
        self.assertFalse(self.automation.action_script.is_running)

    async def test_new_rotation_replaces_startup_wait(self):
        self.set_light("off", supported_color_modes=["brightness"])
        await self.load({"restore_brightness": True})
        await self.publish({"action": "brightness_move_up"})
        await self.wait_calls(1)
        old_context = self.light_calls[0].context_id
        self.on()
        await self.publish({"action": "brightness_move_down"})
        await self.wait_calls(2)
        self.assertEqual(self.light_calls[1].data["brightness_pct"], 38)
        await asyncio.sleep(0.3)
        await self.publish({"action": "brightness_stop"})
        self.assertEqual(sum(c.context_id == old_context for c in self.light_calls), 1)

    async def assert_invalid_attributes(self, mode, cases):
        await self.load({"rotation_mode": mode})
        for state, attrs, reason in cases:
            with self.subTest(state=state, attributes=attrs):
                self.set_light(state, **attrs)
                await self.publish({"action": "brightness_move_up"})
                await asyncio.sleep(0.06)
                self.assertEqual(self.light_calls, [])
                self.assertFalse(self.automation.action_script.is_running)
                traces = await async_list_traces(self.hass, "automation", "automation.ikea_test")
                latest = max(traces, key=lambda trace: trace["timestamp"]["start"])
                trace = (await async_get_trace(self.hass, "automation.ikea_test", latest["run_id"]))["trace"]
                stops = [item["result"]["stop"] for items in trace.values() for item in items
                         if "stop" in item.get("result", {})]
                self.assertTrue(any(reason in stop for stop in stops), stops)

    async def test_invalid_brightness_attributes_fail_closed(self):
        modes = {"supported_color_modes": ["brightness"]}
        cases = [("on", modes | {"brightness": value}, "속성이 유효하지 않음")
                 for value in (None, "bad", True, False, float("nan"), float("inf"), -1, 256)]
        cases += [(state, modes, "상태를 사용할 수 없음") for state in ("unknown", "unavailable")]
        cases += [("on", {"supported_color_modes": ["onoff"], "brightness": 102}, "지원하지 않음")]
        await self.assert_invalid_attributes("brightness", cases)

    async def test_invalid_kelvin_attributes_fail_closed(self):
        base = {"supported_color_modes": ["color_temp"], "color_temp_kelvin": 4000,
                "min_color_temp_kelvin": 2200, "max_color_temp_kelvin": 6500}
        bad = [{key: value} for key in ("color_temp_kelvin", "min_color_temp_kelvin", "max_color_temp_kelvin")
               for value in (None, "bad", True, float("nan"), float("inf"), 0)]
        bad += [{"min_color_temp_kelvin": 7000}]
        await self.assert_invalid_attributes("color_temperature", [
            ("on", base | changes, "속성이 유효하지 않음") for changes in bad])

    async def test_invalid_hs_attributes_fail_closed(self):
        base = {"supported_color_modes": ["hs"]}
        values = [None, [], "120,50", {"0": 120}, [None, 50], ["bad", 50], [True, 50],
                  [float("nan"), 50], [float("inf"), 50], [-1, 50], [361, 50],
                  [120, True], [120, float("nan")], [120, float("inf")], [120, -1], [120, 101]]
        await self.assert_invalid_attributes("light_hue", [
            ("on", base | {"hs_color": value}, "속성이 유효하지 않음") for value in values])

    async def test_unsupported_color_mode_never_turns_on(self):
        await self.assert_invalid_attributes("light_saturation", [
            (state, {"supported_color_modes": ["color_temp"]}, "지원하지 않음") for state in ("on", "off")])
