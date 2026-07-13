# Z2M Aqara Knob Atomic Events Implementation Plan

> **Status: Superseded.** This historical plan is retained for context only. Do not
> implement its queued packet-per-run or `action_rotation_angle_speed` instructions.
> The final architecture and validation steps are in
> [2026-07-13-z2m-knob-per-tick-controls.md](2026-07-13-z2m-knob-per-tick-controls.md):
> Home Assistant Core 2025.4+, global `parallel`, one top-level `start_rotating` run,
> cumulative angle capture, and one sequential light worker per gesture.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Aqara H1 Blueprint consume atomic Zigbee2MQTT JSON events, serialize each rotation, and support configurable Hold repetition plus Release actions.

**Architecture:** Queue every actionable device-state packet at arrival. Apply the packet-local `action_rotation_angle_speed` increment in one run at a time; Hold repetition uses a bounded wait loop that hands control to the queued next action.

**Tech Stack:** Home Assistant Blueprint YAML, MQTT triggers, Jinja templates, Python standard-library `unittest`; PyYAML and Jinja supplied only by the validation environment.

## Global Constraints

- Keep Home Assistant Core compatibility at `2024.08` or newer.
- Add no Home Assistant helpers and no runtime dependencies.
- Preserve existing control inputs and effective brightness/color-temperature step formulas.
- Keep `translate_friendly_name` as a deprecated compatibility input but do not use it.
- Hold repeat maximum defaults to exactly 60 seconds.
- Allow 1000 queued runs and warn on overflow rather than silently dropping packets.

---

### Task 1: Add the Blueprint contract regression test

**Files:**
- Create: `tests/test_z2m_aqara_knob_h1_blueprint.py`
- Test: `blueprints/automation/z2m_aqara_knob_h1_light_control.yaml`

**Interfaces:**
- Consumes: captured Zigbee2MQTT fields `action`, `action_rotation_angle`, `action_rotation_angle_speed`, and `action_rotation_button_state`.
- Produces: executable checks for root-topic filtering, queued processing, packet-local rotation deltas, Hold modes, Release, and deadlines.

- [ ] **Step 1: Write the failing test**

  Read the Blueprint with the standard library, then assert:
  - one root-topic trigger accepts messages with a non-empty `value_json.action` without referencing trigger variables from the MQTT value template;
  - automation mode is `queued` and Core 2024.08-compatible `platform: mqtt` syntax is used;
  - no `states(SENSOR_...)` or derived sensor entity IDs remain;
  - inputs include `action_release`, `hold_repeat_mode`, `action_hold_repeat`, `hold_repeat_interval`, and `hold_repeat_max_duration`;
  - the action reads `action_rotation_angle_speed` from the same trigger payload without previous-angle state;
  - captured `action_rotation_angle_speed` values equal the right deltas `[108, 312, 168, 0]`, left deltas `[-12, -12, 0]`, and pressed deltas `[24, 84, 108, 48, 84, 12, 0]`.

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

- [x] **Step 2: Filter top-level triggers**

  Add one MQTT trigger for the root device topic with:
  ```yaml
  topic: "{{ base_topic }}/{{ knob }}"
  value_template: "{{ value_json.action | default('') }}"
  payload: action
  value_template: "{{ 'action' if value_json.action in [...] else 'ignore' }}"
  ```

- [x] **Step 3: Implement sequential rotation processing**

  Set `mode: queued`. For each `start_rotating` or `rotation` packet, read `action_rotation_angle_speed` and `action_rotation_button_state` from `trigger.payload_json`, then run the existing brightness or color-temperature branch with that packet-local delta. Ignore the zero-delta `stop_rotating` packet.

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
