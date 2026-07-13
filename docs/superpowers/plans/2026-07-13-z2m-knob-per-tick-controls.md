# Zigbee2MQTT Knob Direct Per-Tick Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make one 12-degree Aqara knob tick change brightness by the exact UI-selected percentage and pressed-rotation color temperature by the exact UI-selected Kelvin value, while preserving atomic MQTT packet handling and the existing exact device topic.

**Architecture:** Keep the current `{{ base_topic }}/{{ knob }}` MQTT trigger, `mode: queued`, and packet-local `trigger.payload_json.action_rotation_angle_speed`. Convert that signed angle increment to `rotation_ticks` once, derive brightness and color-temperature deltas directly from it, and feed those deltas into the existing restore, clamp, transition, and light-service branches. Retain the existing input IDs for migration compatibility, but replace their legacy multiplier semantics and clearly document the breaking change.

**Tech Stack:** Home Assistant automation Blueprint YAML, Home Assistant Jinja templates, Python standard-library `unittest`, PyYAML and Jinja2 for static validation.

## Global Constraints

- Keep `base_topic`, the manually entered Zigbee2MQTT `knob` friendly name, and the exact topic `{{ base_topic }}/{{ knob }}`. Do not add a Home Assistant device selector or an MQTT wildcard.
- Keep the root MQTT trigger and the hold-loop MQTT wait filter on raw JSON messages whose payload contains `action`.
- Keep `mode: queued`, `max: 1000`, `max_exceeded: warning`, and arrival-order processing.
- Use only the current packet's `action_rotation_angle_speed`; do not introduce previous-message state, helper entities, or generated Zigbee2MQTT sensor entities.
- Define one tick as exactly 12 degrees. Preserve the sign for left/right rotation.
- Keep brightness limits, color-temperature limits, restore-brightness behavior, default color temperature, and transition behavior.
- Keep the deprecated `translate_friendly_name` compatibility input as an unused no-op.
- Preserve all single, double, hold, release, and hold-repeat behavior.
- Treat the existing input IDs `brightness_stepsize` and `color_temp_stepsize` as stable IDs even though their names and meanings change.

---

### Task 1: Lock the direct per-tick contract with failing tests

**Files:**

- Modify: `tests/test_z2m_aqara_knob_h1_blueprint.py`
- Test target: `blueprints/automation/z2m_aqara_knob_h1_light_control.yaml`

- [ ] **Step 1: Add helpers for inspecting individual Blueprint input blocks**

Add these helpers immediately after `load_source()`:

```python
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
```

- [ ] **Step 2: Add tests for the new selector ranges and migration text**

Add these methods to `AqaraKnobBlueprintTest`:

```python
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
```

- [ ] **Step 3: Add tests for the direct formulas and representative packets**

Add these methods to the same test class:

```python
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
```

- [ ] **Step 4: Strengthen the existing trigger test against the rejected wildcard approach**

In `test_uses_one_root_topic_trigger_for_every_action_message`, add:

```python
        self.assertNotIn('topic: "{{ base_topic }}/+"', source)
        self.assertNotIn('topic: "{{ base_topic }}/#"', source)
```

- [ ] **Step 5: Run the focused tests and confirm the new contract fails for the expected legacy behavior**

Run from `C:\Users\JJ\Documents\Codex\2026-07-13\new-chat-2\work\homeassistant`:

```powershell
python -m unittest tests.test_z2m_aqara_knob_h1_blueprint -v
```

Expected: existing atomic-event tests pass; the new selector, formula, and breaking-change tests fail because the Blueprint still exposes legacy step-size semantics.

- [ ] **Step 6: Commit the failing contract tests**

```powershell
git add tests/test_z2m_aqara_knob_h1_blueprint.py
git commit -m "test: specify direct per-tick knob controls"
```

---

### Task 2: Implement direct per-tick brightness and color-temperature control

**Files:**

- Modify: `blueprints/automation/z2m_aqara_knob_h1_light_control.yaml`
- Test: `tests/test_z2m_aqara_knob_h1_blueprint.py`

- [ ] **Step 1: Add the breaking-change and migration notice to the Blueprint description**

Insert this section after the packet-processing notes and before `## Customizing Options`:

```yaml
    ## Breaking Change: Direct Per-Tick Controls
      - The legacy step-size multiplier behavior is deprecated. The existing input IDs are retained, but their values now have direct physical meanings.
      - One knob tick is `12 degrees`.
      - Brightness is now configured as `1-10 %/tick`; the default is exactly `4 %/tick`.
      - Pressed-rotation color temperature is now configured as `1-10000 K/tick`; the default is `60 K/tick`.
      - After re-importing this blueprint, open every automation created from it, review these two inputs, and save it again.
      - Existing brightness values above `10` are no longer valid and must be changed to a value from `1` through `10`.
      - To preserve the old default color-temperature response, change a saved value of `5` to `60 K/tick`.

```

- [ ] **Step 2: Replace the two selectors while retaining their input IDs**

Replace the `brightness_stepsize` and `color_temp_stepsize` blocks with:

```yaml
        brightness_stepsize:
          name: Brightness per Tick
          description:
            Set the exact brightness percentage change for one 12-degree knob tick.
            <br>For example, `1` means `1%` per tick and a 60-degree packet changes brightness by `5%`.
            <br>The default value is `4%` per tick.
          default: 4
          selector:
            number:
              min: 1
              max: 10
              step: 1
              unit_of_measurement: "%/tick"
              mode: slider

        color_temp_stepsize:
          name: Color Temperature per Tick
          description:
            Set the exact Kelvin change for one 12-degree pressed-rotation tick.
            <br>For example, `60` means `60 K` per tick and a 60-degree packet changes color temperature by `300 K`.
            <br>The default value is `60 K` per tick.
          default: 60
          selector:
            number:
              min: 1
              max: 10000
              step: 1
              unit_of_measurement: "K/tick"
              mode: box
```

The color-temperature selector uses `mode: box` because a 1-to-10000 slider cannot offer practical one-Kelvin entry precision.

- [ ] **Step 3: Give the retained input IDs names that express their new units**

In the first action-variable block, replace:

```yaml
      BRIGHTNESS_STEPSIZE: !input brightness_stepsize
      TEMP_STEPSIZE: !input color_temp_stepsize
```

with:

```yaml
      BRIGHTNESS_STEP_PCT: !input brightness_stepsize
      COLOR_TEMP_STEP_K: !input color_temp_stepsize
```

- [ ] **Step 4: Replace the legacy coefficients with direct 12-degree tick arithmetic**

Replace the first `variables` action under the rotation branch with two sequential variable actions so `ROTATION_TICKS` is defined before the deltas use it:

```yaml
          - variables:
              ROTATION_TICKS: >-
                {{ ROTATION_DELTA | float(0) / 12 }}

          - variables:
              BRIGHTNESS_DELTA_PCT: >-
                {{ (ROTATION_TICKS | float(0)) *
                  (BRIGHTNESS_STEP_PCT | float(0)) }}
              COLOR_TEMP_DELTA_K: >-
                {{ (ROTATION_TICKS | float(0)) *
                  (COLOR_TEMP_STEP_K | float(0)) }}
```

This deliberately preserves fractional signed ticks if a future device packet is not an exact multiple of 12 degrees; the final service values continue through the existing rounding and clamp boundaries.

- [ ] **Step 5: Feed percentage deltas directly into the existing brightness branch**

Change the restore condition to:

```yaml
                          {{ states(TARGET_LIGHT) == 'off' and
                            RESTORE_BRIGHTNESS and
                            BRIGHTNESS_DELTA_PCT | float(0) > 0 }}
```

Keep the current-state conversion from Home Assistant's 0-to-255 brightness attribute to percent, delete `STEP_PCT`, and replace `PROPOSED_PCT` with:

```yaml
                          PROPOSED_PCT: >-
                            {{ ((CURRENT_PCT | float(0)) +
                              (BRIGHTNESS_DELTA_PCT | float(0))) |
                              round(0) }}
```

Do not change `CLAMPED_PCT`, the minimum/maximum inputs, the state-change guard, the transition, or `brightness_pct` service data.

- [ ] **Step 6: Keep the color-temperature branch and make its positive-delta test explicitly numeric**

Change only the off-light condition to:

```yaml
                          {{ states(TARGET_LIGHT) == 'off' and
                            COLOR_TEMP_DELTA_K | float(0) > 0 }}
```

Keep `LIGHT_TEMP_MIN`, `LIGHT_TEMP_MAX`, `COLOR_TEMP_MIN`, `COLOR_TEMP_MAX`, `SAFE_TEMP_BASE`, `CURRENT_TEMP`, the transition, and the final clamp around `CURRENT_TEMP + COLOR_TEMP_DELTA_K` unchanged.

- [ ] **Step 7: Run the focused tests and confirm they pass**

```powershell
python -m unittest tests.test_z2m_aqara_knob_h1_blueprint -v
```

Expected: all atomic-event, hold/release, topic, selector, migration, and direct-arithmetic tests pass.

- [ ] **Step 8: Run the complete repository test suite**

```powershell
python -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 9: Commit the Blueprint implementation**

```powershell
git add blueprints/automation/z2m_aqara_knob_h1_light_control.yaml
git commit -m "feat: expose direct per-tick knob controls"
```

---

### Task 3: Validate Home Assistant syntax, migration artifacts, and the user-readable copy

**Files:**

- Validate: `blueprints/automation/z2m_aqara_knob_h1_light_control.yaml`
- Validate: `tests/test_z2m_aqara_knob_h1_blueprint.py`
- Validate: `docs/superpowers/specs/2026-07-13-z2m-knob-per-tick-controls-design.md`
- Modify: `C:\Users\JJ\Documents\Codex\2026-07-13\new-chat-2\outputs\z2m_aqara_knob_h1_light_control.yaml`

- [ ] **Step 1: Parse the Blueprint YAML and every embedded Jinja template**

Run from the repository root:

```powershell
$env:PYTHONPATH='C:\Users\JJ\Documents\Codex\2026-07-13\new-chat-2\work\python-deps'
@'
from pathlib import Path

import yaml
from jinja2 import Environment


path = Path("blueprints/automation/z2m_aqara_knob_h1_light_control.yaml")
source = path.read_text(encoding="utf-8")


class BlueprintLoader(yaml.SafeLoader):
    pass


BlueprintLoader.add_constructor(
    "!input", lambda loader, node: loader.construct_scalar(node)
)
document = yaml.load(source, Loader=BlueprintLoader)
environment = Environment()
template_count = 0


def validate_templates(value):
    global template_count
    if isinstance(value, dict):
        for child in value.values():
            validate_templates(child)
    elif isinstance(value, list):
        for child in value:
            validate_templates(child)
    elif isinstance(value, str) and ("{{" in value or "{%" in value):
        environment.parse(value)
        template_count += 1


validate_templates(document)
assert document["mode"] == "queued"
assert document["max"] == 1000
assert document["trigger"][0]["topic"] == "{{ base_topic }}/{{ knob }}"
print(f"Validated YAML and {template_count} Jinja templates")
'@ | python -
```

Expected: the command prints the number of validated Jinja templates and exits with status 0.

- [ ] **Step 2: Render representative arithmetic independently of service state**

```powershell
$env:PYTHONPATH='C:\Users\JJ\Documents\Codex\2026-07-13\new-chat-2\work\python-deps'
@'
from jinja2 import Environment


environment = Environment()
tick_template = environment.from_string("{{ angle | float(0) / 12 }}")
brightness_template = environment.from_string(
    "{{ (ticks | float(0)) * (brightness | float(0)) }}"
)
temperature_template = environment.from_string(
    "{{ (ticks | float(0)) * (temperature | float(0)) }}"
)
examples = (
    (12, 1, 1, 60),
    (60, 5, 5, 300),
    (-24, -2, -2, -120),
    (84, 7, 7, 420),
)

for angle, expected_ticks, expected_brightness, expected_temperature in examples:
    ticks = float(tick_template.render(angle=angle))
    brightness = float(brightness_template.render(ticks=ticks, brightness=1))
    temperature = float(
        temperature_template.render(ticks=ticks, temperature=60)
    )
    assert ticks == expected_ticks
    assert brightness == expected_brightness
    assert temperature == expected_temperature

print("Validated direct per-tick arithmetic examples")
'@ | python -
```

- [ ] **Step 3: Mirror the finished Blueprint into the workspace output file**

Use `apply_patch` to make the changed description, selector, variable, and calculation hunks in `C:\Users\JJ\Documents\Codex\2026-07-13\new-chat-2\outputs\z2m_aqara_knob_h1_light_control.yaml` byte-for-byte equivalent to the repository Blueprint. Then verify both files:

```powershell
$sourceHash = (Get-FileHash blueprints\automation\z2m_aqara_knob_h1_light_control.yaml).Hash
$outputHash = (Get-FileHash C:\Users\JJ\Documents\Codex\2026-07-13\new-chat-2\outputs\z2m_aqara_knob_h1_light_control.yaml).Hash
if ($sourceHash -ne $outputHash) { throw "Blueprint output copy differs from repository source" }
$sourceHash
```

Expected: both SHA256 hashes are identical.

- [ ] **Step 4: Confirm the forum migration draft remains available**

```powershell
rg -n "Forum|Breaking|12|60 K/tick|save" docs\superpowers\specs\2026-07-13-z2m-knob-per-tick-controls-design.md C:\Users\JJ\Documents\Codex\2026-07-13\new-chat-2\outputs\z2m-knob-per-tick-controls-design.md
```

Expected: both design copies contain the breaking-change explanation and forum-ready migration notes.

- [ ] **Step 5: Run final regression and whitespace checks**

```powershell
python -m unittest discover -s tests -v
git diff --check
git status --short
git log -4 --oneline
```

Expected: tests pass, `git diff --check` prints nothing, the repository working tree is clean, and the test and feature commits are present. The output copy is outside the repository and therefore does not appear in `git status`.

- [ ] **Step 6: Inspect the final change against the pre-feature base**

```powershell
git diff --stat 2f2bcd6..HEAD
git diff 2f2bcd6..HEAD -- blueprints/automation/z2m_aqara_knob_h1_light_control.yaml tests/test_z2m_aqara_knob_h1_blueprint.py
```

Confirm all of the following before reporting completion:

- The only root MQTT topic remains `{{ base_topic }}/{{ knob }}`; no wildcard or device-picker path was introduced.
- Rotation values come from the same triggering JSON packet and stay queued in arrival order.
- A 60-degree packet is five ticks, not one event or one fixed UI increment.
- Brightness uses exact `%/tick`; pressed rotation uses exact `K/tick`.
- The old `/ 3.6 / 3`, `2.54`, and 0-to-255 delta round trip are gone.
- Current light brightness still converts from Home Assistant's 0-to-255 state attribute into percentage.
- Brightness and color-temperature clamps, restore behavior, transitions, and press actions remain intact.
- The Blueprint itself explains the deprecated semantics, invalid saved brightness values above 10, the old color-temperature value 5 to new value 60 migration, and the need to open/review/save automations.
