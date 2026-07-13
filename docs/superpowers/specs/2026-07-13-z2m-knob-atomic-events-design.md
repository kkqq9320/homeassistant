# Z2M Aqara Knob Atomic Events Design

## Goal

Update `z2m_aqara_knob_h1_light_control.yaml` so every knob update is derived from one Zigbee2MQTT device-state JSON message instead of reading separately updated Home Assistant sensor entities.

## Final Review Correction

This correction supersedes the packet-per-run rotation and late Hold-wait details
in the original design below.

- The minimum supported version is Home Assistant Core 2025.4. That release made
  `variables` actions update existing variables across nested and parallel action
  scopes. The listener/worker coordination in this design depends on that run-scope
  behavior and gives the two branches distinct variable ownership.
- The global automation mode remains `queued` with `max: 1000` and
  `max_exceeded: warning`. Internal parallel blocks exist only to keep an MQTT
  listener alive beside a single worker; all light service commands are sequential
  in that worker.
- The top-level MQTT filter accepts only `single`, `double`, `hold`, `release`, and
  `start_rotating`. Intermediate `rotation` and terminal `stop_rotating` packets are
  consumed by the active gesture listener, reducing intermediate automation traces.
- A repeating Hold starts its listener before the initial user action. A stop event
  received during a slow action sets the run-scope stop flag immediately; the current
  action may finish, but no later repeat begins. The same Release or click remains
  queued for its normal top-level action.
- Rotation runs from `start_rotating` through `stop_rotating`. It snapshots the
  light's base values once and calculates absolute targets from the newest cumulative
  `action_rotation_angle`. This prevents a delayed integration state publication
  from dropping ticks and permits safe coalescing of intermediate packets.

## Event model

- Subscribe to `{{ base_topic }}/{{ knob }}`.
- Filter the root-topic MQTT trigger using only the incoming `value_json.action` value, so messages with no action do not create automation runs. Do not reference `trigger_variables` from the MQTT `value_template`, because Home Assistant does not pass them into incoming-payload rendering.
- Queue top-level semantic actions and rotation gesture starts in arrival order.
- Use cumulative `action_rotation_angle` within one gesture run. One tick is 12
  degrees, and the worker calculates each absolute target from the gesture-start
  snapshot rather than the integration's possibly delayed entity state.
- Treat `stop_rotating`, another action, or a bounded inactivity timeout as the end
  of the active gesture.
- Use `action_rotation_button_state` from the same JSON message: `released` adjusts brightness and `pressed` adjusts color temperature.

## Press actions

- Preserve `single`, `double`, and the existing `hold` action.
- Add a `release` action.
- Add hold repeat modes: disabled, repeat the existing hold action, or execute the hold action once and repeat a separate action.
- Make the repeat interval configurable and cap a repeating hold run at 60 seconds by default.
- A release or any other actionable knob event received at any point in the repeat
  lifetime ends the loop. Its queued top-level run then executes normally.
- An arbitrary user action already executing is allowed to finish. Because the stop
  listener remains active in parallel, every later repeat is suppressed.

## Concurrency

Keep the global mode `queued`; do not use global restart or parallel mode. Allow up
to 1000 queued runs and emit a warning instead of silently dropping a message if
that limit is reached. Internal parallelism is limited to listener/worker
coordination. The Hold worker is the only branch that runs Hold actions, and the
rotation worker is the only branch that calls a light service, so light commands
remain sequential.

## Compatibility

- Preserve all brightness, color-temperature, transition, target, and action inputs.
- Keep the obsolete `translate_friendly_name` input as a deprecated no-op so existing blueprint instances with a saved value continue loading.
- Add no integrations, helpers, scripts, or dependencies.
- Require Home Assistant Core 2025.4 or newer for the corrected variable-scope
  behavior.

## Verification

A standard-library `unittest` suite checks root-topic filtering, the Core 2025.4
scope prerequisite, global queued mode, listener/worker ownership, all Hold modes,
Release dispatch, cumulative signed angles, coalesced packets, and delayed entity
state. A deterministic Hold model injects Release during a deliberately slow action
and proves that no later repeat begins while Release still executes. A separate
validation step parses the YAML and every Jinja template with externally supplied
validation libraries.
