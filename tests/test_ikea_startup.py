import asyncio
import time

from tests.ikea_runtime import IkeaBlueprintCase


class IkeaStartupTest(IkeaBlueprintCase):
    async def assert_left_stays_off(self, restore):
        self.set_light("off", supported_color_modes=["brightness"])
        await self.load({"restore_brightness": restore})
        await self.publish({"action": "brightness_move_down"})
        await asyncio.sleep(0.15)
        self.assertEqual(self.light_calls, [])
        self.assertFalse(self.automation.action_script.is_running)

    async def test_off_brightness_left_does_nothing_zero(self):
        await self.assert_left_stays_off(False)

    async def test_off_brightness_left_does_nothing_restore(self):
        await self.assert_left_stays_off(True)

    async def test_zero_start_has_no_bare_turn_on(self):
        self.set_light("off", supported_color_modes=["brightness"])
        await self.load({"restore_brightness": False})
        await self.publish({"action": "brightness_move_up"})
        await self.wait_calls(1)
        self.assertEqual(self.light_calls[0].data["brightness_pct"], 2)
        self.assertEqual(set(self.light_calls[0].data), {"entity_id", "brightness_pct"})
        self.set_light("on", brightness=5, supported_color_modes=["brightness"])
        await self.wait_calls(3)
        await self.publish({"action": "brightness_stop"})
        self.assertEqual([c.data["brightness_pct"] for c in self.light_calls], [2, 4, 6])

    async def test_zero_start_only_waits_for_on(self):
        self.set_light("off", supported_color_modes=["brightness"])
        await self.load()
        await self.publish({"action": "brightness_move_up"})
        await self.wait_calls(1)
        self.set_light("on", supported_color_modes=["brightness"])
        await self.wait_calls(2)
        await self.publish({"action": "brightness_stop"})
        self.assertEqual(self.light_calls[1].data["brightness_pct"], 4)

    async def test_restore_uses_reported_brightness(self):
        self.set_light("off", supported_color_modes=["brightness"])
        await self.load({"restore_brightness": True})
        await self.publish({"action": "brightness_move_up"})
        await self.wait_calls(1)
        self.assertEqual(set(self.light_calls[0].data), {"entity_id"})
        self.set_light("on", brightness=102, supported_color_modes=["brightness"])
        await self.wait_calls(2)
        await self.publish({"action": "brightness_stop"})
        self.assertEqual(self.light_calls[1].data["brightness_pct"], 42)
        self.assertGreaterEqual(self.light_calls[1].at - self.light_calls[0].at, 0.19)

    async def assert_color_startup(self, mode, attributes, field, expected):
        await self.load({"rotation_mode": mode, "restore_brightness": True})
        for action, result in zip(("brightness_move_up", "brightness_move_down"), expected):
            with self.subTest(action=action):
                self.set_light("off", supported_color_modes=attributes["supported_color_modes"])
                offset = len(self.light_calls)
                await self.publish({"action": action})
                await self.wait_calls(offset + 1)
                self.assertEqual(set(self.light_calls[-1].data), {"entity_id"})
                self.set_light("on", **attributes)
                await self.wait_calls(offset + 2)
                await self.publish({"action": "brightness_stop"})
                self.assertEqual(self.light_calls[-1].data[field], result)
                self.assertEqual(set(self.light_calls[-1].data), {"entity_id", field})

    async def test_color_temperature_startup_both_directions(self):
        await self.assert_color_startup("color_temperature", {
            "supported_color_modes": ["color_temp"], "color_temp_kelvin": 4000,
            "min_color_temp_kelvin": 2200, "max_color_temp_kelvin": 6500},
            "color_temp_kelvin", [4100, 3900])

    async def test_hue_startup_both_directions(self):
        await self.assert_color_startup("light_hue", {
            "supported_color_modes": ["hs"], "hs_color": [120, 50]},
            "hs_color", [[127.2, 50], [112.8, 50]])

    async def test_saturation_startup_both_directions(self):
        await self.assert_color_startup("light_saturation", {
            "supported_color_modes": ["xy"], "hs_color": [120, 50]},
            "hs_color", [[120, 52], [120, 48]])

    async def assert_startup_timeout(self, invalid_report=False):
        self.set_light("off", supported_color_modes=["brightness"])
        await self.load({"restore_brightness": True})
        await self.publish({"action": "brightness_move_up"})
        await self.wait_calls(1)
        if invalid_report:
            self.set_light("on", brightness="invalid", supported_color_modes=["brightness"])
        await asyncio.sleep(2.2)
        self.assertEqual(len(self.light_calls), 1)
        self.assertFalse(self.automation.action_script.is_running)

    async def test_startup_timeout_without_report(self):
        await self.assert_startup_timeout()

    async def test_startup_timeout_with_invalid_report(self):
        await self.assert_startup_timeout(invalid_report=True)

    async def test_stop_cancels_startup_wait(self):
        self.set_light("off", supported_color_modes=["brightness"])
        await self.load({"restore_brightness": True})
        await self.publish({"action": "brightness_move_up"})
        await self.wait_calls(1)
        await self.publish({"action": "brightness_stop"})
        self.set_light("on", brightness=102, supported_color_modes=["brightness"])
        await asyncio.sleep(0.35)
        self.assertEqual(len(self.light_calls), 1)
        self.assertFalse(self.automation.action_script.is_running)

    async def test_short_deadline_bounds_startup_wait(self):
        self.set_light("off", supported_color_modes=["brightness"])
        await self.load({"restore_brightness": True, "max_rotation_seconds": 1})
        started = time.monotonic()
        await self.publish({"action": "brightness_move_up"})
        await self.wait_calls(1)
        await asyncio.sleep(1.3)
        self.assertLess(time.monotonic() - started, 1.8)
        self.assertEqual(len(self.light_calls), 1)
        self.assertFalse(self.automation.action_script.is_running)
