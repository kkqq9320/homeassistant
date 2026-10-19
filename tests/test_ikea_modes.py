import asyncio

from tests.ikea_runtime import ENTITY, IkeaBlueprintCase


class IkeaModesTest(IkeaBlueprintCase):
    async def assert_steps(self, mode, attributes, field, right, left):
        self.set_light("on", **attributes)
        await self.load({"rotation_mode": mode})
        for action, expected in (("brightness_move_up", right), ("brightness_move_down", left)):
            offset = len(self.light_calls)
            await self.publish({"action": action})
            await self.wait_calls(offset + len(expected))
            await self.publish({"action": "brightness_stop"})
            calls = self.light_calls[offset:]
            self.assertEqual([call.data[field] for call in calls], expected)
            for call in calls:
                self.assertEqual(set(call.data), {"entity_id", field})
                self.assertEqual(call.data["entity_id"], [ENTITY])

    async def test_brightness_steps(self):
        await self.assert_steps("brightness", {"brightness": 102, "supported_color_modes": ["brightness"]},
                                "brightness_pct", [42, 44], [38, 36])

    async def test_kelvin_steps(self):
        await self.assert_steps("color_temperature", {
            "color_temp_kelvin": 4000, "min_color_temp_kelvin": 2200,
            "max_color_temp_kelvin": 6500, "supported_color_modes": ["color_temp"]},
            "color_temp_kelvin", [4100, 4200], [3900, 3800])

    async def test_hue_wraps(self):
        await self.assert_steps("light_hue", {"hs_color": [358, 70], "supported_color_modes": ["hs"]},
                                "hs_color", [[5.2, 70], [12.4, 70]], [[350.8, 70], [343.6, 70]])

    async def test_saturation_steps(self):
        await self.assert_steps("light_saturation", {"hs_color": [120, 50], "supported_color_modes": ["xy"]},
                                "hs_color", [[120, 52], [120, 54]], [[120, 48], [120, 46]])

    async def test_delayed_state_does_not_reset_targets(self):
        self.set_light("on", brightness=102, supported_color_modes=["brightness"])
        await self.load()
        await self.publish({"action": "brightness_move_up"})
        await self.wait_calls(3)
        await self.publish({"action": "brightness_stop"})
        self.assertEqual([c.data["brightness_pct"] for c in self.light_calls], [42, 44, 46])

    async def assert_limits(self, mode, base, cases):
        await self.load({"rotation_mode": mode, "repeat_interval_ms": 100})
        for attributes, action in cases:
            with self.subTest(attributes=attributes, action=action):
                self.set_light("on", **(base | attributes))
                await self.publish({"action": action})
                await asyncio.sleep(0.25)
                await self.publish({"action": "brightness_stop"})
                self.assertEqual(self.light_calls, [])

    async def test_brightness_limits_suppress_duplicate_calls(self):
        await self.assert_limits("brightness", {"supported_color_modes": ["brightness"]}, [
            ({"brightness": 2.55}, "brightness_move_down"),
            ({"brightness": 255}, "brightness_move_up")])

    async def test_kelvin_limits_suppress_duplicate_calls(self):
        await self.assert_limits("color_temperature", {"supported_color_modes": ["color_temp"],
            "min_color_temp_kelvin": 2200, "max_color_temp_kelvin": 6500}, [
                ({"color_temp_kelvin": 2200}, "brightness_move_down"),
                ({"color_temp_kelvin": 6500}, "brightness_move_up")])

    async def test_saturation_limits_suppress_duplicate_calls(self):
        await self.assert_limits("light_saturation", {"supported_color_modes": ["rgb"]}, [
            ({"hs_color": [120, 0]}, "brightness_move_down"),
            ({"hs_color": [120, 100]}, "brightness_move_up")])

    async def test_hue_360_and_zero_saturation(self):
        await self.assert_steps("light_hue", {"hs_color": [360, 0], "supported_color_modes": ["rgbw"]},
                                "hs_color", [[7.2, 0]], [[352.8, 0]])

    async def test_missing_or_non_numeric_saturation_defaults_to_50(self):
        await self.load({"rotation_mode": "light_hue"})
        for hs in ([120], [120, None], [120, "bad"]):
            with self.subTest(hs=hs):
                self.set_light("on", hs_color=hs, supported_color_modes=["rgbww"])
                offset = len(self.light_calls)
                await self.publish({"action": "brightness_move_up"})
                await self.wait_calls(offset + 1)
                await self.publish({"action": "brightness_stop"})
                self.assertEqual(self.light_calls[-1].data["hs_color"], [127.2, 50])

    async def test_out_of_range_saturation_is_rejected(self):
        await self.load({"rotation_mode": "light_hue"})
        for saturation in (-1, 101):
            self.set_light("on", hs_color=[120, saturation], supported_color_modes=["hs"])
            await self.publish({"action": "brightness_move_up"})
            await asyncio.sleep(0.05)
            self.assertEqual(self.light_calls, [])
