# Z2M Aqara Knob Atomic Events Design

## Goal

Update `z2m_aqara_knob_h1_light_control.yaml` so every knob update is derived from one Zigbee2MQTT device-state JSON message instead of reading separately updated Home Assistant sensor entities.

## Event model

- Subscribe to `{{ base_topic }}/{{ knob }}`.
- Filter top-level MQTT triggers by `value_json.action` so only `single`, `double`, `hold`, `release`, and `start_rotating` create automation runs.
- A `start_rotating` run owns the complete rotation and waits for subsequent `rotation` and `stop_rotating` messages sequentially.
- Calculate each real-time increment as `current action_rotation_angle - previous action_rotation_angle`. Derive brightness percent from angle (`360 degrees = 100 percent`) so rotations beyond the device's capped `action_rotation_percent` remain usable.
- Apply a two-second inactivity timeout. Any non-rotation action also ends the rotation run.
- Use `action_rotation_button_state` from the same JSON message: `released` adjusts brightness and `pressed` adjusts color temperature.

## Press actions

- Preserve `single`, `double`, and the existing `hold` action.
- Add a `release` action.
- Add hold repeat modes: disabled, repeat the existing hold action, or execute the hold action once and repeat a separate action.
- Make the repeat interval configurable and cap a repeating hold run at 60 seconds by default.
- A release or any other actionable knob event ends the repeat loop. The release action is still executed by its own top-level run.

## Concurrency

Keep `mode: parallel` so release can execute immediately while a hold repeat run exists. Rotation messages are not top-level triggers, so exactly one run updates the light during each rotation and brightness calculations cannot race across MQTT packets.

## Compatibility

- Preserve all brightness, color-temperature, transition, target, and action inputs.
- Keep the obsolete `translate_friendly_name` input as a deprecated no-op so existing blueprint instances with a saved value continue loading.
- Add no integrations, helpers, scripts, or dependencies.

## Verification

A standard-library `unittest` test parses the Blueprint with a minimal `!input` YAML constructor and checks trigger filtering, absence of entity-state reads, sequential rotation processing, two-second timeout, all hold modes, release handling, and delta calculations against the captured right, left, and pressed-rotation payloads.
