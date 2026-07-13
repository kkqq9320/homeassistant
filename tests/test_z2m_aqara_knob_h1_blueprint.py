import json
from pathlib import Path
import re
import unittest


BLUEPRINT_PATH = (
    Path(__file__).parents[1]
    / "blueprints"
    / "automation"
    / "z2m_aqara_knob_h1_light_control.yaml"
)


def load_source():
    return BLUEPRINT_PATH.read_text(encoding="utf-8")


def compact_whitespace(value):
    return " ".join(value.split())


def extract_input_block(source, input_name, next_input_name):
    match = re.search(
        rf"(?ms)^        {re.escape(input_name)}:\n.*?"
        rf"(?=^        {re.escape(next_input_name)}:\n)",
        source,
    )
    if match is None:
        raise AssertionError(f"Could not find input block: {input_name}")
    return match.group(0)


class AqaraKnobBlueprintTest(unittest.TestCase):
    def test_uses_one_root_topic_trigger_for_every_action_message(self):
        source = load_source()

        self.assertIn("mode: queued", source)
        self.assertEqual(source.count("platform: mqtt"), 2)
        self.assertNotIn("trigger: mqtt", source)
        self.assertIn('topic: "{{ base_topic }}/{{ knob }}"', source)
        self.assertNotIn('/{{ knob }}/action', source)
        self.assertIn("value_json.action", source)
        self.assertNotIn('topic: "{{ base_topic }}/+"', source)
        self.assertNotIn('topic: "{{ base_topic }}/#"', source)

    def test_exposes_direct_per_tick_inputs(self):
        source = load_source()
        brightness = extract_input_block(
            source, "brightness_stepsize", "color_temp_stepsize"
        )
        color_temp = extract_input_block(
            source, "color_temp_stepsize", "color_temp_min"
        )

        self.assertIn("name: Brightness per Tick", brightness)
        self.assertRegex(brightness, r"(?m)^          default: 4$")
        self.assertRegex(brightness, r"(?m)^              min: 1$")
        self.assertRegex(brightness, r"(?m)^              max: 10$")
        self.assertIn('unit_of_measurement: "%/tick"', brightness)

        self.assertIn("name: Color Temperature per Tick", color_temp)
        self.assertRegex(color_temp, r"(?m)^          default: 60$")
        self.assertRegex(color_temp, r"(?m)^              min: 1$")
        self.assertRegex(color_temp, r"(?m)^              max: 10000$")
        self.assertIn('unit_of_measurement: "K/tick"', color_temp)

    def test_documents_the_per_tick_breaking_change(self):
        source = load_source()

        self.assertIn("## Breaking Change: Direct Per-Tick Controls", source)
        self.assertIn("One knob tick is `12 degrees`", source)
        self.assertIn("open every automation created from it", source)
        self.assertIn("review these two inputs, and save it again", source)
        self.assertIn("`5` to `60 K/tick`", source)

    def test_uses_direct_signed_per_tick_deltas(self):
        source = load_source()
        compact = compact_whitespace(source)

        self.assertIn(
            "ROTATION_TICKS: >- {{ ROTATION_DELTA | float(0) / 12 }}",
            compact,
        )
        self.assertIn(
            "BRIGHTNESS_DELTA_PCT: >- {{ (ROTATION_TICKS | float(0)) * "
            "(BRIGHTNESS_STEP_PCT | float(0)) }}",
            compact,
        )
        self.assertIn(
            "COLOR_TEMP_DELTA_K: >- {{ (ROTATION_TICKS | float(0)) * "
            "(COLOR_TEMP_STEP_K | float(0)) }}",
            compact,
        )
        self.assertNotIn("/ 3.6 / 3", source)
        self.assertNotIn("2.54", source)
        self.assertNotRegex(source, r"(?m)^\s+BRIGHTNESS_DELTA:$")
        self.assertNotRegex(source, r"(?m)^\s+STEP_PCT:$")

    def test_blueprint_maps_packet_angles_to_per_tick_examples(self):
        source = load_source()
        tick_divisor = re.search(
            r"ROTATION_TICKS: >-\s+"
            r"{{ ROTATION_DELTA \| float\(0\) / (?P<degrees>\d+) }}",
            source,
        )
        self.assertIsNotNone(tick_divisor)
        degrees_per_tick = float(tick_divisor.group("degrees"))
        examples = (
            (12, 1, 1, 60),
            (60, 5, 5, 300),
            (-24, -2, -2, -120),
            (84, 7, 7, 420),
        )

        for angle_speed, ticks, brightness_pct, color_temp_k in examples:
            with self.subTest(angle_speed=angle_speed):
                calculated_ticks = angle_speed / degrees_per_tick
                self.assertEqual(calculated_ticks, ticks)
                self.assertEqual(calculated_ticks * 1, brightness_pct)
                self.assertEqual(calculated_ticks * 60, color_temp_k)

    def test_mqtt_value_templates_do_not_reference_trigger_variables(self):
        source = load_source()

        self.assertNotIn("ACTION_VALUES", source)
        self.assertEqual(
            source.count(
                "'action' if value_json.action | default('') else 'ignore'"
            ),
            2,
        )

    def test_reads_each_rotation_delta_from_the_same_payload(self):
        source = load_source()

        self.assertIn("trigger.payload_json.action_rotation_angle_speed", source)
        self.assertIn("trigger.payload_json.action_rotation_button_state", source)
        self.assertNotIn("PREVIOUS_ANGLE", source)
        self.assertNotIn("wait.trigger.payload_json", source)
        self.assertNotIn("states(SENSOR_", source)
        self.assertNotIn("_action_rotation_percent", source)

    def test_every_blueprint_input_reference_is_defined(self):
        source = load_source()
        referenced_inputs = set(re.findall(r"!input\s+([a-zA-Z0-9_]+)", source))

        for input_name in referenced_inputs:
            with self.subTest(input_name=input_name):
                self.assertRegex(source, rf"(?m)^ {{4}}(?: {{4}})?{input_name}:$")

    def test_exposes_both_hold_repeat_modes_and_release_action(self):
        source = load_source()

        for input_name in (
            "action_release",
            "hold_repeat_mode",
            "action_hold_repeat",
            "hold_repeat_interval",
            "hold_repeat_max_duration",
        ):
            self.assertRegex(source, rf"(?m)^ {{8}}{input_name}:$")
        self.assertIn("value: repeat_hold", source)
        self.assertIn("value: separate_repeat", source)
        self.assertRegex(
            source,
            r"(?s)hold_repeat_max_duration:.*?default: 60",
        )
        self.assertIn("min(HOLD_REPEAT_INTERVAL", source)

    def test_routes_release_and_both_hold_repeat_modes(self):
        source = load_source()

        self.assertRegex(
            source,
            r"(?s)conditions: \"{{ ACTION == 'release' }}\"\s+"
            r"sequence: !input action_release",
        )
        self.assertIn("HOLD_REPEAT_MODE != 'none'", source)
        self.assertRegex(
            source,
            r"(?s)HOLD_REPEAT_MODE == 'repeat_hold'.*?"
            r"sequence: !input action_hold",
        )
        self.assertRegex(
            source,
            r"(?s)HOLD_REPEAT_MODE == 'separate_repeat'.*?"
            r"sequence: !input action_hold_repeat",
        )
        self.assertRegex(
            source,
            r"(?s)value_template: \"{{ wait.completed }}\".*?"
            r"HOLD_STOPPED: true",
        )
        self.assertIn(
            "'action' if value_json.action | default('') else 'ignore'",
            source,
        )

    def test_queue_capacity_is_large_and_overflow_is_visible(self):
        source = load_source()

        self.assertRegex(source, r"(?m)^mode: queued\nmax: 1000$")
        self.assertIn("max_exceeded: warning", source)

    def test_captured_angle_speed_is_the_increment_for_each_message(self):
        captures = {
            "right": [
                (108, 108),
                (420, 312),
                (588, 168),
                (588, 0),
            ],
            "left": [(-12, -12), (-24, -12), (-24, 0)],
            "pressed": [
                (24, 24),
                (108, 84),
                (216, 108),
                (264, 48),
                (348, 84),
                (360, 12),
                (360, 0),
            ],
        }

        for name, samples in captures.items():
            with self.subTest(name=name):
                previous_angle = 0
                for angle, speed in samples:
                    payload = json.loads(
                        json.dumps(
                            {
                                "action_rotation_angle": angle,
                                "action_rotation_angle_speed": speed,
                            }
                        )
                    )
                    self.assertEqual(
                        payload["action_rotation_angle"] - previous_angle,
                        payload["action_rotation_angle_speed"],
                    )
                    previous_angle = payload["action_rotation_angle"]


if __name__ == "__main__":
    unittest.main()
