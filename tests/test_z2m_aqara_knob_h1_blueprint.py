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


class AqaraKnobBlueprintTest(unittest.TestCase):
    def test_uses_one_root_topic_trigger_for_every_action_message(self):
        source = load_source()

        self.assertIn("mode: queued", source)
        self.assertEqual(source.count("platform: mqtt"), 2)
        self.assertNotIn("trigger: mqtt", source)
        self.assertIn('topic: "{{ base_topic }}/{{ knob }}"', source)
        self.assertNotIn('/{{ knob }}/action', source)
        self.assertIn("value_json.action", source)
        for action in (
            "single",
            "double",
            "hold",
            "release",
            "start_rotating",
            "rotation",
            "stop_rotating",
        ):
            self.assertIn(f"'{action}'", source)

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
        self.assertIn("value_json.action | default('') in ACTION_VALUES", source)

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
