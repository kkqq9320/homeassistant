from pathlib import Path
import re
import unittest


BLUEPRINT_PATH = (
    Path(__file__).parents[1]
    / "blueprints"
    / "automation"
    / "z2m_aqara_knob_h1_light_control.yaml"
)
REPOSITORY_ROOT = Path(__file__).parents[1]
ATOMIC_DESIGN_PATH = (
    REPOSITORY_ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-07-13-z2m-knob-atomic-events-design.md"
)
PER_TICK_DESIGN_PATH = (
    REPOSITORY_ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-07-13-z2m-knob-per-tick-controls-design.md"
)
PER_TICK_PLAN_PATH = (
    REPOSITORY_ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-07-13-z2m-knob-per-tick-controls.md"
)
HISTORICAL_ATOMIC_PLAN_PATH = (
    REPOSITORY_ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-07-13-z2m-knob-atomic-events.md"
)
TOP_LEVEL_ACTIONS = (
    "single",
    "double",
    "hold",
    "release",
    "start_rotating",
)
MISSING = object()


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


def clamp(value, minimum, maximum):
    return min(maximum, max(minimum, value))


class RotationGestureModel:
    """Deterministic listener/worker model for cumulative rotation targets."""

    def __init__(
        self,
        *,
        base_brightness_pct=40,
        base_color_temp_k=4000,
        brightness_pct_per_tick=4,
        color_temp_k_per_tick=60,
        light_is_off=False,
        restore_brightness=False,
        restored_brightness_pct=None,
        restored_color_temp_k=None,
    ):
        self.base_brightness_pct = base_brightness_pct
        self.base_color_temp_k = base_color_temp_k
        self.brightness_pct_per_tick = brightness_pct_per_tick
        self.color_temp_k_per_tick = color_temp_k_per_tick
        self.restore_brightness = restore_brightness
        self.restored_brightness_pct = restored_brightness_pct
        self.restored_color_temp_k = restored_color_temp_k
        self.entity_brightness_pct = base_brightness_pct
        self.latest_angle = 0
        self.latest_button_state = "released"
        self.listener_done = False
        self.startup_angle = None
        self.startup_button_state = None
        self.applied_signature = None
        self.angle_offset = 0
        self.off_startup_pending = light_is_off
        self.startup_commands = []
        self.pending_brightness_publications = []
        self.brightness_commands = []
        self.color_temp_commands = []

    def listener_capture(self, angle=MISSING, button_state=MISSING):
        if angle is not MISSING:
            try:
                self.latest_angle = float(angle or 0)
            except (TypeError, ValueError):
                self.latest_angle = 0
        if button_state is not MISSING:
            self.latest_button_state = button_state or ""
        if self.startup_angle is None and self.latest_angle > 0:
            self.startup_angle = self.latest_angle
            self.startup_button_state = self.latest_button_state

    def listener_stop(self, angle=MISSING, button_state=MISSING):
        self.listener_capture(angle, button_state)
        if self.startup_angle is None and self.latest_angle > 0:
            self.startup_angle = self.latest_angle
            self.startup_button_state = self.latest_button_state
        self.listener_done = True

    def worker_apply_latest(self):
        latest_signature = (self.latest_angle, self.latest_button_state)
        startup_signature = (
            self.startup_angle,
            self.startup_button_state,
        )
        startup_requires_turn_on_only = (
            self.off_startup_pending
            and self.startup_angle is not None
            and (
                self.startup_button_state == "pressed"
                or self.restore_brightness
            )
        )
        if (
            startup_requires_turn_on_only
            and self.applied_signature != startup_signature
        ):
            work_signature = startup_signature
        else:
            work_signature = latest_signature

        if self.applied_signature == work_signature:
            return

        work_angle, work_button_state = work_signature
        ticks = (work_angle - self.angle_offset) / 12
        if (
            self.off_startup_pending
            and ticks > 0
            and (
                work_button_state == "pressed"
                or self.restore_brightness
            )
        ):
            self.startup_commands.append(work_signature)
            if (
                work_button_state == "released"
                and self.restored_brightness_pct is not None
            ):
                self.base_brightness_pct = self.restored_brightness_pct
            if (
                work_button_state == "pressed"
                and self.restored_color_temp_k is not None
            ):
                self.base_color_temp_k = self.restored_color_temp_k
            self.angle_offset = work_angle
            self.off_startup_pending = False
        elif work_button_state == "released":
            target = clamp(
                self.base_brightness_pct
                + ticks * self.brightness_pct_per_tick,
                0,
                100,
            )
            self.brightness_commands.append(target)
            self.pending_brightness_publications.append(target)
        else:
            target = clamp(
                self.base_color_temp_k + ticks * self.color_temp_k_per_tick,
                1000,
                10000,
            )
            self.color_temp_commands.append(target)
        self.applied_signature = work_signature

    def publish_all_delayed_brightness_states(self):
        for target in self.pending_brightness_publications:
            self.entity_brightness_pct = target
        self.pending_brightness_publications.clear()


class HoldRepeatModel:
    """Deterministic listener/worker model for a deliberately slow Hold action."""

    def __init__(self):
        self.listener_active = False
        self.stopped = False
        self.worker_ticks_remaining = 0
        self.hold_actions_started = 0
        self.top_level_actions_executed = []

    def start(self, slow_action_ticks):
        self.listener_active = True
        self.worker_ticks_remaining = slow_action_ticks
        self.hold_actions_started = 1

    def receive(self, action):
        if self.listener_active:
            self.stopped = True
        if action in TOP_LEVEL_ACTIONS:
            self.top_level_actions_executed.append(action)

    def advance_worker(self):
        if self.worker_ticks_remaining:
            self.worker_ticks_remaining -= 1
        if self.worker_ticks_remaining == 0 and not self.stopped:
            self.hold_actions_started += 1

    def finish_hold_run(self):
        if self.worker_ticks_remaining:
            raise AssertionError("The current Hold action is still running")
        self.listener_active = False


class AqaraKnobBlueprintTest(unittest.TestCase):
    def test_uses_one_root_topic_trigger_for_every_action_message(self):
        source = load_source()

        self.assertIn("mode: parallel", source)
        self.assertEqual(source.count("platform: mqtt"), 3)
        self.assertNotIn("trigger: mqtt", source)
        self.assertEqual(
            source.count('topic: "{{ base_topic }}/{{ knob }}"'),
            3,
        )
        self.assertNotIn('/{{ knob }}/action', source)
        self.assertIn("value_json.action", source)
        self.assertNotIn('topic: "{{ base_topic }}/+"', source)
        self.assertNotIn('topic: "{{ base_topic }}/#"', source)

    def test_top_level_trigger_starts_only_supported_gesture_actions(self):
        source = load_source()
        root_trigger = re.search(
            r"(?ms)^trigger:\n(?P<body>.*?)^action:\n",
            source,
        )
        self.assertIsNotNone(root_trigger)
        compact = compact_whitespace(root_trigger.group("body"))

        self.assertIn(
            "['single', 'double', 'hold', 'release', 'start_rotating']",
            compact,
        )
        self.assertNotIn("'rotation'", compact)
        self.assertNotIn("'stop_rotating'", compact)

    def test_global_parallel_starts_gestures_while_light_commands_stay_sequential(self):
        source = load_source()

        self.assertRegex(
            source,
            r"(?m)^mode: parallel\nmax: 1000\nmax_exceeded: warning$",
        )
        self.assertNotRegex(source, r"(?m)^mode: (?:restart|queued)$")
        self.assertEqual(source.count("          - parallel:"), 2)
        self.assertIn("alias: Hold stop listener", source)
        self.assertIn("alias: Hold repeat worker", source)
        self.assertIn("alias: Rotation gesture listener", source)
        self.assertIn("alias: Sequential light command worker", source)

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

    def test_uses_cumulative_signed_per_tick_targets(self):
        source = load_source()
        compact = compact_whitespace(source)

        self.assertIn(
            "ROTATION_TICKS: >- {{ ((ROTATION_WORK_ANGLE | float(0)) - "
            "(ROTATION_ANGLE_OFFSET | float(0))) / 12 }}",
            compact,
        )
        self.assertIn(
            "BRIGHTNESS_TARGET_PCT: >- {{ min(KNOB_MAX_BRIGHT_PCT | int, "
            "max(KNOB_MIN_BRIGHT_PCT | int, "
            "ROTATION_BASE_BRIGHTNESS_PCT | float(0) + "
            "ROTATION_TICKS | float(0) * BRIGHTNESS_STEP_PCT | float(0))) }}",
            compact,
        )
        self.assertIn(
            "COLOR_TEMP_TARGET_K: >- {{ min(ROTATION_COLOR_TEMP_MAX | int, "
            "max(ROTATION_COLOR_TEMP_MIN | int, "
            "ROTATION_BASE_COLOR_TEMP_K | int + "
            "ROTATION_TICKS | float(0) * COLOR_TEMP_STEP_K | float(0))) }}",
            compact,
        )
        self.assertIn(
            "trigger.payload_json.action_rotation_angle | float(0)",
            source,
        )
        self.assertIn(
            "wait.trigger.payload_json.action_rotation_angle | float(0)",
            source,
        )
        self.assertNotIn("action_rotation_angle_speed", source)
        self.assertEqual(
            source.count("state_attr(TARGET_LIGHT, 'brightness')"),
            4,
        )
        self.assertEqual(
            source.count("state_attr(TARGET_LIGHT, 'color_temp_kelvin')"),
            2,
        )
        self.assertNotIn("/ 3.6 / 3", source)
        self.assertNotIn("2.54", source)

    def test_cumulative_angle_model_handles_signed_and_coalesced_packets(self):
        positive = RotationGestureModel(base_brightness_pct=40)
        for angle in (12, 24, 60):
            positive.listener_capture(angle)
            positive.worker_apply_latest()
        self.assertEqual(positive.brightness_commands, [44, 48, 60])

        negative = RotationGestureModel(base_color_temp_k=4000)
        negative.listener_capture(-24, "pressed")
        negative.worker_apply_latest()
        self.assertEqual(negative.color_temp_commands, [3880])

        coalesced = RotationGestureModel(base_brightness_pct=40)
        for angle in (12, 24, 60):
            coalesced.listener_capture(angle)
        coalesced.worker_apply_latest()
        self.assertEqual(coalesced.brightness_commands, [60])

    def test_delayed_entity_state_does_not_drop_cumulative_ticks(self):
        gesture = RotationGestureModel(base_brightness_pct=40)

        for angle in (12, 24, 36):
            gesture.listener_capture(angle)
            gesture.worker_apply_latest()

        self.assertEqual(gesture.entity_brightness_pct, 40)
        self.assertEqual(gesture.brightness_commands, [44, 48, 52])
        gesture.publish_all_delayed_brightness_states()
        self.assertEqual(gesture.entity_brightness_pct, 52)

    def test_stop_packet_final_angle_is_applied_after_worker_delay(self):
        gesture = RotationGestureModel(base_brightness_pct=40)
        gesture.listener_capture(12)
        gesture.listener_capture(24)
        gesture.listener_stop(48)

        gesture.worker_apply_latest()

        self.assertTrue(gesture.listener_done)
        self.assertEqual(gesture.brightness_commands, [56])

        gesture.listener_stop()
        self.assertEqual(gesture.latest_angle, 48)
        self.assertEqual(gesture.latest_button_state, "released")

    def test_coalesced_brightness_restore_consumes_only_startup_angle(self):
        gesture = RotationGestureModel(
            base_brightness_pct=40,
            light_is_off=True,
            restore_brightness=True,
        )
        for angle in (12, 24, 36):
            gesture.listener_capture(angle, "released")

        gesture.worker_apply_latest()
        gesture.worker_apply_latest()

        self.assertEqual(gesture.startup_commands, [(12, "released")])
        self.assertEqual(gesture.angle_offset, 12)
        self.assertEqual(gesture.brightness_commands, [48])
        self.assertEqual(gesture.applied_signature, (36, "released"))

    def test_restore_refreshes_reported_base_before_applying_remaining_ticks(self):
        gesture = RotationGestureModel(
            base_brightness_pct=0,
            light_is_off=True,
            restore_brightness=True,
            restored_brightness_pct=40,
        )
        for angle in (12, 24, 36):
            gesture.listener_capture(angle, "released")

        gesture.worker_apply_latest()
        gesture.worker_apply_latest()

        self.assertEqual(gesture.startup_commands, [(12, "released")])
        self.assertEqual(gesture.base_brightness_pct, 40)
        self.assertEqual(gesture.brightness_commands, [48])

        source = load_source()
        self.assertIn("alias: Wait for restored brightness state", source)
        self.assertIn("alias: Refresh restored brightness base", source)
        self.assertIn("alias: Wait for restored color temperature state", source)
        self.assertIn("alias: Refresh restored color temperature base", source)
        self.assertGreaterEqual(source.count("continue_on_timeout: true"), 4)

    def test_coalesced_pressed_startup_consumes_only_startup_angle(self):
        gesture = RotationGestureModel(
            base_color_temp_k=4000,
            light_is_off=True,
        )
        for angle in (12, 24, 36):
            gesture.listener_capture(angle, "pressed")

        gesture.worker_apply_latest()
        gesture.worker_apply_latest()

        self.assertEqual(gesture.startup_commands, [(12, "pressed")])
        self.assertEqual(gesture.angle_offset, 12)
        self.assertEqual(gesture.color_temp_commands, [4120])
        self.assertEqual(gesture.applied_signature, (36, "pressed"))

    def test_same_angle_button_change_is_a_fresh_worker_signature(self):
        gesture = RotationGestureModel(
            base_brightness_pct=40,
            base_color_temp_k=4000,
        )
        gesture.listener_capture(12, "released")
        gesture.worker_apply_latest()
        gesture.listener_capture(12, "pressed")
        gesture.worker_apply_latest()

        self.assertEqual(gesture.brightness_commands, [44])
        self.assertEqual(gesture.color_temp_commands, [4060])
        self.assertEqual(gesture.applied_signature, (12, "pressed"))

    def test_blueprint_tracks_stop_final_startup_and_full_signature(self):
        source = load_source()
        compact = compact_whitespace(source)

        self.assertIn(
            "ROTATION_LATEST_ACTION in ['rotation', 'stop_rotating']",
            source,
        )
        self.assertIn("ROTATION_PACKET_ANGLE", source)
        self.assertIn("ROTATION_STARTUP_ANGLE", source)
        self.assertIn("ROTATION_STARTUP_BUTTON_STATE", source)
        self.assertIn("ROTATION_APPLIED_BUTTON_STATE", source)
        self.assertIn(
            "ROTATION_APPLIED_BUTTON_STATE != ROTATION_LATEST_BUTTON_STATE",
            compact,
        )
        self.assertIn(
            "ROTATION_APPLIED_BUTTON_STATE == ROTATION_LATEST_BUTTON_STATE",
            compact,
        )

    def test_missing_packet_fields_preserve_previous_values_but_null_resets_them(self):
        gesture = RotationGestureModel()
        gesture.listener_capture(48, "released")
        gesture.listener_stop()
        self.assertEqual(gesture.latest_angle, 48)
        self.assertEqual(gesture.latest_button_state, "released")

        gesture = RotationGestureModel()
        gesture.listener_capture(48, "released")
        gesture.listener_stop(None, None)
        self.assertEqual(gesture.latest_angle, 0)
        self.assertEqual(gesture.latest_button_state, "")

        source = load_source()
        self.assertIn(
            "wait.trigger.payload_json.action_rotation_angle is defined",
            source,
        )
        self.assertIn(
            "wait.trigger.payload_json.action_rotation_button_state is defined",
            source,
        )
        self.assertNotIn("default(none)", source)

    def test_mqtt_value_templates_do_not_reference_trigger_variables(self):
        source = load_source()

        self.assertNotIn("ACTION_VALUES", source)
        self.assertEqual(source.count("value_json.action | default('')"), 3)
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
        self.assertIn("HOLD_REPEAT_MODE == 'none'", source)
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
        self.assertIn("alias: Hold stop listener", source)
        self.assertIn("alias: Hold repeat worker", source)
        self.assertIn("HOLD_STOPPED: false", source)
        self.assertRegex(
            source,
            r"(?s)alias: Hold stop listener.*?wait_for_trigger:.*?"
            r"HOLD_STOPPED: true.*?alias: Hold repeat worker",
        )
        self.assertRegex(
            source,
            r"(?s)alias: Hold repeat worker.*?milliseconds: 1.*?"
            r"sequence: !input action_hold",
        )
        self.assertIn(
            "'action' if value_json.action | default('') else 'ignore'",
            source,
        )

    def test_hold_listener_stops_slow_action_before_any_later_repeat(self):
        hold = HoldRepeatModel()
        hold.start(slow_action_ticks=3)
        hold.advance_worker()
        hold.receive("release")

        self.assertTrue(hold.stopped)
        self.assertEqual(hold.hold_actions_started, 1)
        self.assertEqual(hold.top_level_actions_executed, ["release"])
        hold.advance_worker()
        hold.advance_worker()
        self.assertEqual(hold.hold_actions_started, 1)

        hold.finish_hold_run()
        self.assertEqual(hold.top_level_actions_executed, ["release"])

    def test_parallel_capacity_is_large_and_overflow_is_visible(self):
        source = load_source()

        self.assertRegex(source, r"(?m)^mode: parallel\nmax: 1000$")
        self.assertIn("max_exceeded: warning", source)

    def test_requires_core_2025_4_and_documents_the_scope_reason(self):
        blueprint = load_source()
        documents = (
            ATOMIC_DESIGN_PATH.read_text(encoding="utf-8"),
            PER_TICK_DESIGN_PATH.read_text(encoding="utf-8"),
            PER_TICK_PLAN_PATH.read_text(encoding="utf-8"),
        )

        self.assertIn("Home Assistant Core `2025.4`", blueprint)
        self.assertNotIn("Home Assistant Core `2024.08`", blueprint)
        self.assertRegex(
            blueprint,
            r"(?m)^  homeassistant:\n    min_version: 2025\.4\.0$",
        )
        for document in (blueprint, *documents):
            with self.subTest(document=document[:40]):
                self.assertIn("2025.4", document)
                self.assertRegex(
                    document,
                    r"(?is)variables.*(?:nested|outer|parallel).*scope",
                )

    def test_documents_gesture_processing_and_limited_parallelism(self):
        documents = (
            load_source(),
            ATOMIC_DESIGN_PATH.read_text(encoding="utf-8"),
            PER_TICK_DESIGN_PATH.read_text(encoding="utf-8"),
            PER_TICK_PLAN_PATH.read_text(encoding="utf-8"),
        )

        for document in documents:
            with self.subTest(document=document[:40]):
                self.assertRegex(document, r"(?is)global.*mode.*parallel")
                self.assertRegex(document, r"(?is)internal parallel")
                self.assertRegex(document, r"(?is)light.*(?:command|service).*sequential")
                self.assertRegex(document, r"(?is)cumulative.*angle")

        forum_draft = PER_TICK_DESIGN_PATH.read_text(encoding="utf-8")
        self.assertRegex(forum_draft, r"(?is)forum.*2025\.4")

        historical_plan = HISTORICAL_ATOMIC_PLAN_PATH.read_text(encoding="utf-8")
        self.assertRegex(historical_plan, r"(?is)status.*superseded")
        self.assertIn("2026-07-13-z2m-knob-per-tick-controls.md", historical_plan)


if __name__ == "__main__":
    unittest.main()
