# Z2M Aqara Knob Atomic Events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Aqara H1 Blueprint consume atomic Zigbee2MQTT JSON events, serialize each rotation, and support configurable Hold repetition plus Release actions.

**Architecture:** Filter the device-state topic into one top-level run per high-level gesture. A rotation run owns a `wait_for_trigger` loop and applies cumulative-angle differences sequentially; Hold repetition uses a separate bounded wait loop while `parallel` mode lets Release respond immediately.

**Tech Stack:** Home Assistant Blueprint YAML, MQTT triggers, Jinja templates, Python standard-library `unittest`, PyYAML supplied by the validation environment.

## Global Constraints

- Keep Home Assistant Core compatibility at `2024.08` or newer.
- Add no Home Assistant helpers and no runtime dependencies.
- Preserve existing control inputs and effective brightness/color-temperature step formulas.
- Keep `translate_friendly_name` as a deprecated compatibility input but do not use it.
- Rotation inactivity timeout is exactly 2 seconds.
- Hold repeat maximum defaults to exactly 60 seconds.

---

### Task 1: Add the Blueprint contract regression test

**Files:**
- Create: `tests/test_z2m_aqara_knob_h1_blueprint.py`
- Test: `blueprints/automation/z2m_aqara_knob_h1_light_control.yaml`

**Interfaces:**
- Consumes: captured Zigbee2MQTT fields `action`, `action_rotation_angle`, and `action_rotation_button_state`.
- Produces: executable checks for root-topic filtering, serialized rotation deltas, Hold modes, Release, and timeouts.

- [ ] **Step 1: Write the failing test**

  Define a PyYAML loader for `!input`, load the Blueprint, then assert:
  - top-level trigger payloads are `single`, `double`, `hold`, `release`, and `start_rotating`;
  - all trigger topics are the root device topic and use `value_json.action`;
  - no `states(SENSOR_...)` or derived sensor entity IDs remain;
  - inputs include `action_release`, `hold_repeat_mode`, `action_hold_repeat`, `hold_repeat_interval`, and `hold_repeat_max_duration`;
  - the action text contains `wait.trigger.payload_json`, the exact two-second rotation timeout, and cumulative-angle subtraction;
  - captured angles produce right deltas `[108, 312, 168, 0]`, left deltas `[-12, -12, 0]`, and pressed deltas `[24, 84, 108, 48, 84, 12, 0]`.

- [ ] **Step 2: Run test to verify it fails**

  Run: `python -m unittest tests.test_z2m_aqara_knob_h1_blueprint -v`

  Expected: FAIL because the current Blueprint subscribes to `/action`, reads sensor entities, and has no Release or Hold-repeat inputs.

- [ ] **Step 3: Commit the failing regression test**

  Run:
  ```powershell
  git add tests/test_z2m_aqara_knob_h1_blueprint.py
  git commit -m "test: specify atomic knob event handling"
  ```

### Task 2: Implement atomic rotation and press handling

**Files:**
- Modify: `blueprints/automation/z2m_aqara_knob_h1_light_control.yaml`

**Interfaces:**
- Consumes: one Zigbee2MQTT JSON object per MQTT packet on `{{ base_topic }}/{{ knob }}`.
- Produces: sequential light changes, the existing press actions, optional Hold repetition, and Release action execution.

- [ ] **Step 1: Replace entity-derived inputs and descriptions**

  Mark `translate_friendly_name` deprecated, remove sensor-entity prerequisites, document atomic MQTT JSON processing, and add the five Hold/Release inputs covered by Task 1.

- [ ] **Step 2: Filter top-level triggers**

  Add one MQTT trigger per high-level action with:
  ```yaml
  topic: "{{ base_topic }}/{{ knob }}"
  value_template: "{{ value_json.action | default('') }}"
  payload: <action>
  id: <action>
  ```

- [ ] **Step 3: Implement sequential rotation processing**

  On `start_rotating`, initialize `PREVIOUS_ANGLE` to zero and repeat: calculate `DELTA_ANGLE`, run the existing brightness or color-temperature branch, update `PREVIOUS_ANGLE`, then wait up to two seconds for the next device-state packet. Process `rotation` and the final `stop_rotating`; stop on timeout or any other action.

- [ ] **Step 4: Implement Hold modes and Release**

  Execute `action_hold` once. When repetition is enabled, wait for an actionable MQTT event for the configured interval; on timeout repeat either `action_hold` or `action_hold_repeat`, and stop on an event or the configured maximum duration. Execute `action_release` from the separate `release` trigger.

- [ ] **Step 5: Run the focused test**

  Run: `python -m unittest tests.test_z2m_aqara_knob_h1_blueprint -v`

  Expected: PASS.

- [ ] **Step 6: Commit the implementation**

  Run:
  ```powershell
  git add blueprints/automation/z2m_aqara_knob_h1_light_control.yaml
  git commit -m "feat: process Aqara knob events atomically"
  ```

### Task 3: Validate and package the deliverable

**Files:**
- Verify: `blueprints/automation/z2m_aqara_knob_h1_light_control.yaml`
- Create outside repository: `outputs/z2m_aqara_knob_h1_light_control.yaml`

**Interfaces:**
- Consumes: the completed Blueprint and regression test.
- Produces: a verified standalone Blueprint file for the user.

- [ ] **Step 1: Run all repository tests**

  Run: `python -m unittest discover -s tests -v`

  Expected: all tests PASS with zero failures.

- [ ] **Step 2: Parse the final YAML and inspect the diff**

  Run the test loader against the final YAML, run `git diff origin/main...HEAD --check`, and inspect `git diff origin/main...HEAD` for unrelated edits.

- [ ] **Step 3: Perform the requested code review**

  Review the branch against `origin/main` for Home Assistant syntax risks, MQTT sequence races, compatibility regressions, and missing requirements. Fix any actionable finding and rerun Steps 1-2.

- [ ] **Step 4: Copy the standalone Blueprint to outputs**

  Create `outputs/z2m_aqara_knob_h1_light_control.yaml` with byte-identical content to the verified Blueprint and compare their SHA-256 hashes.
