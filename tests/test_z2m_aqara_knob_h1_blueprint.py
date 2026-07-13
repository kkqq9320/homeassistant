from pathlib import Path
import unittest

import yaml


BLUEPRINT_PATH = (
    Path(__file__).parents[1]
    / "blueprints"
    / "automation"
    / "z2m_aqara_knob_h1_light_control.yaml"
)


class BlueprintLoader(yaml.SafeLoader):
    pass


BlueprintLoader.add_constructor(
    "!input", lambda loader, node: {"!input": loader.construct_scalar(node)}
)


def load_blueprint():
    source = BLUEPRINT_PATH.read_text(encoding="utf-8")
    return source, yaml.load(source, Loader=BlueprintLoader)


def blueprint_inputs(document):
    inputs = document["blueprint"]["input"]
    flattened = dict(inputs)
    for value in inputs.values():
        if isinstance(value, dict) and isinstance(value.get("input"), dict):
            flattened.update(value["input"])
    return flattened


class AqaraKnobBlueprintTest(unittest.TestCase):
    def test_filters_atomic_device_messages_into_high_level_runs(self):
        _, document = load_blueprint()
        triggers = document["trigger"]

        self.assertIsInstance(triggers, list)
        self.assertEqual(
            {trigger["payload"] for trigger in triggers},
            {"single", "double", "hold", "release", "start_rotating"},
        )
        self.assertEqual(
            {trigger["id"] for trigger in triggers},
            {"single", "double", "hold", "release", "start_rotating"},
        )
        self.assertTrue(
            all(trigger["topic"] == "{{ base_topic }}/{{ knob }}" for trigger in triggers)
        )
        self.assertTrue(
            all("value_json.action" in trigger["value_template"] for trigger in triggers)
        )

    def test_reads_no_derived_rotation_sensor_entities(self):
        source, _ = load_blueprint()

        self.assertNotIn("states(SENSOR_", source)
        self.assertNotIn("_action_rotation_button_state", source)
        self.assertNotIn("_action_rotation_percent", source)
        self.assertNotIn("_action_rotation_angle", source)

    def test_exposes_hold_repeat_modes_and_release_action(self):
        _, document = load_blueprint()
        inputs = blueprint_inputs(document)

        self.assertTrue(
            {
                "action_release",
                "hold_repeat_mode",
                "action_hold_repeat",
                "hold_repeat_interval",
                "hold_repeat_max_duration",
            }.issubset(inputs)
        )
        self.assertEqual(inputs["hold_repeat_mode"]["default"], "none")
        self.assertEqual(inputs["hold_repeat_max_duration"]["default"], 60)

    def test_rotation_worker_uses_payload_json_deltas_and_two_second_timeout(self):
        source, document = load_blueprint()

        self.assertEqual(document["mode"], "parallel")
        self.assertIn("wait.trigger.payload_json", source)
        self.assertIn(
            "CURRENT_ANGLE | float(0) - PREVIOUS_ANGLE | float(0)", source
        )
        self.assertIn("seconds: 2", source)
        self.assertNotIn('/{{ knob }}/action', source)

    def test_captured_rotation_angles_produce_expected_incremental_deltas(self):
        samples = {
            "right": ([108, 420, 588, 588], [108, 312, 168, 0]),
            "left": ([-12, -24, -24], [-12, -12, 0]),
            "pressed": (
                [24, 108, 216, 264, 348, 360, 360],
                [24, 84, 108, 48, 84, 12, 0],
            ),
        }

        for name, (angles, expected) in samples.items():
            with self.subTest(name=name):
                previous = 0
                actual = []
                for current in angles:
                    actual.append(current - previous)
                    previous = current
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
