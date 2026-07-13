# Z2M Aqara Knob Atomic Events Design

## Goal

Update `z2m_aqara_knob_h1_light_control.yaml` so every knob update is derived from one Zigbee2MQTT device-state JSON message instead of reading separately updated Home Assistant sensor entities.

## Event model

- Subscribe to `{{ base_topic }}/{{ knob }}`.
- Filter the root-topic MQTT trigger by `value_json.action` so only the seven actionable messages create automation runs.
- Queue every actionable message at arrival and process runs in order.
- Use `action_rotation_angle_speed` as the packet-local rotation increment. The captured right, left, and pressed sequences show that it exactly equals `current action_rotation_angle - previous action_rotation_angle`, so no previous-message state or MQTT wait window is required.
- Ignore `stop_rotating` for light adjustment because its increment is zero.
- Use `action_rotation_button_state` from the same JSON message: `released` adjusts brightness and `pressed` adjusts color temperature.

## Press actions

- Preserve `single`, `double`, and the existing `hold` action.
- Add a `release` action.
- Add hold repeat modes: disabled, repeat the existing hold action, or execute the hold action once and repeat a separate action.
- Make the repeat interval configurable and cap a repeating hold run at 60 seconds by default.
- A release or any other actionable knob event received while the repeat loop is waiting ends the loop. Its queued top-level run then executes normally.
- Keep repeated user actions short because Home Assistant cannot interrupt an arbitrary action sequence while that sequence itself is executing.

## Concurrency

Use `mode: queued`. MQTT payloads are captured when their triggers fire, and one run at a time reads and updates the light, preventing the brightness races possible with `parallel` mode. A Hold repeat run listens for the next action itself; after it exits, that same action's queued run executes. Allow up to 1000 queued runs and emit a warning instead of silently dropping a message if that safety limit is ever reached.

## Compatibility

- Preserve all brightness, color-temperature, transition, target, and action inputs.
- Keep the obsolete `translate_friendly_name` input as a deprecated no-op so existing blueprint instances with a saved value continue loading.
- Add no integrations, helpers, scripts, or dependencies.

## Verification

A standard-library `unittest` test checks root-topic filtering, queued mode, legacy MQTT trigger syntax for Core 2024.08, absence of entity-state reads, all Hold modes, Release, defined inputs, and the packet-local deltas against the captured right, left, and pressed-rotation payloads. A separate validation step parses the YAML and every Jinja template with externally supplied validation libraries.
