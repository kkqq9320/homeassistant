# Z2M Aqara Knob Per-Tick Controls Design

## Goal

Replace the user-facing brightness and color-temperature `stepsize` multipliers
with direct per-tick units. A user selecting `1%` must get a 1% brightness
change for one 12-degree knob tick. Turning five ticks in one MQTT event (60
degrees) must produce a 5% change. Color temperature follows the same rule in
Kelvin per tick.

This change affects only the rotation calculations and the related Blueprint
input descriptions. Atomic MQTT payload handling, queued execution, Hold and
Release actions, brightness restoration, min/max limits, transition behavior,
and pressed/released rotation mappings remain unchanged.

## Final Review Correction

The original packet-local calculation was vulnerable to delayed light state and
is superseded by gesture-level cumulative processing:

- Require Home Assistant Core 2025.4. Its `variables` action can update an
  existing variable across nested and parallel action scopes, which the shared
  listener/worker run state requires.
- Keep the global mode `queued`. Internal parallel blocks are limited to an MQTT
  listener beside one sequential worker; light service commands remain sequential
  and never run in competing branches.
- Start one rotation run on `start_rotating`. Its listener consumes `rotation` and
  `stop_rotating`, captures the newest cumulative angle and button state, and ends
  on a different action or bounded inactivity timeout. Intermediate packets may be
  coalesced, reducing top-level traces without losing movement.
- Snapshot base brightness and color temperature once at gesture start. Every
  command is an absolute target computed from that base plus the cumulative signed
  angle. Never rebase from an entity state that may still reflect an earlier command.

## Tick and Event Model

- Treat 12 degrees as one knob tick. This value is an internal constant and is
  not exposed in the Blueprint UI.
- Read the newest cumulative `action_rotation_angle` from the active gesture's
  MQTT listener. Do not read a derived entity or retain previous-message state.
- Calculate signed ticks as `(cumulative_angle - gesture_angle_offset) / 12`.
- Do not round the tick count before applying it. Captured device values are
  multiples of 12, while a future non-multiple value will remain proportional
  instead of being discarded.
- Positive values increase brightness or color temperature; negative values
  decrease them.

Examples:

| Cumulative gesture angle | Tick delta | At 1%/tick | At 60 K/tick |
| ---: | ---: | ---: | ---: |
| 12 | 1 | 1% | 60 K |
| 60 | 5 | 5% | 300 K |
| -24 | -2 | -2% | -120 K |
| 84 | 7 | 7% | 420 K |

## Blueprint Inputs

Retain the existing input IDs so existing automations still reference valid
Blueprint inputs. Deprecate their old multiplier semantics and change their UI
labels, descriptions, units, ranges, and defaults to direct per-tick units.

### Brightness per Tick

- Existing input ID: `brightness_stepsize`
- UI meaning: percentage-point brightness change per 12-degree tick
- Range: 1 through 10
- Step: 1
- Unit: `%/tick`
- Default: 4

The default preserves approximately the current real-world response: the
existing formula produces about 4% for a captured 12-degree event when its
legacy stepsize is 4.

### Color Temperature per Tick

- Existing input ID: `color_temp_stepsize`
- UI meaning: Kelvin change per 12-degree tick
- Range: 1 through 10000
- Step: 1
- Unit: `K/tick`
- Default: 60

The default preserves the current response because the existing default
multiplier is 5 K per degree and `12 * 5 = 60 K` per tick.

Home Assistant number-selector bounds are static numeric configuration. The
color-temperature per-tick selector therefore uses a fixed upper bound of
10000 K; it cannot dynamically inherit the separate `color_temp_max` input.
The calculated target remains clamped to `color_temp_min` and
`color_temp_max` at runtime.

## Internal Calculation

Use direct units and remove the legacy brightness conversion coefficients.

```text
rotation_ticks = (cumulative_angle - gesture_angle_offset) / 12
brightness_target = base_brightness_pct + rotation_ticks * brightness_pct_per_tick
color_temp_target = base_color_temp_k + rotation_ticks * color_temp_k_per_tick
```

Brightness and color temperature apply those absolute targets with the existing
rounding and configured min/max clamps. The base values are captured once at
gesture start; later commands do not reread brightness or color temperature. If a
restore-only positive startup packet is consumed, its cumulative angle becomes the
gesture offset so later movement starts from the restored base without double-counting
the startup packet.

The implementation must not retain the legacy `/ 3.6 / 3`, `2.54`, or the
conversion of the requested delta into a 0-255 value and back. Converting the
light entity's current `brightness` attribute from 0-255 to a percentage is
still required. Applying the requested change in direct percentage points
removes the avoidable round trip and its extra rounding.

## Compatibility and Migration

This is a breaking semantic change for saved Blueprint inputs:

- Home Assistant Core 2025.4 is now the minimum version because the Blueprint uses
  variables shared across nested and parallel action scopes.
- The IDs `brightness_stepsize` and `color_temp_stepsize` remain accepted, but
  their old multiplier meaning is deprecated.
- A saved brightness value of `4` becomes exactly `4%/tick`; this is close to
  its current observed effect and normally needs no adjustment.
- A saved brightness value above `10` is outside the new selector range and
  must be changed to a value from `1` through `10` before saving the automation.
- A saved color-temperature value of `5` becomes `5 K/tick`, not the previous
  effective `60 K/tick`. Users who want the old response must change it to
  `60` after updating.
- The Blueprint description must contain a clearly labeled breaking-change
  notice telling users to open each automation made from the Blueprint, review
  both per-tick inputs, and save it again.
- The old step-size terminology must be marked deprecated in the migration
  notice even though the input IDs remain unchanged for configuration
  continuity.

## Forum Update Draft

Use the following facts when updating the Home Assistant forum post:

> **Breaking change: rotation sensitivity now uses direct per-tick units.**
> This Blueprint now requires Home Assistant Core 2025.4 because Hold and rotation
> coordination relies on variables shared across nested and parallel action scopes.
> One Aqara knob tick is treated as 12 degrees. Brightness can now be configured
> from 1-10% per tick (default 4%), and pressed-rotation color temperature from
> 1-10000 K per tick (default 60 K). A five-tick/60-degree event applies five
> times the selected value. Existing step-size multiplier semantics are
> deprecated. After updating, open every automation created from this Blueprint,
> review the two rotation values, and save. In particular, change a previous
> color-temperature stepsize of 5 to 60 K/tick to preserve the old response,
> and replace any previous brightness value above 10 with a value from 1-10.
> The global automation mode remains queued. Internal parallelism only keeps a
> listener active beside a sequential worker, so light commands remain sequential.
> Rotation now uses one gesture's cumulative angle and creates fewer intermediate
> automation traces.

The final forum text may add a release version or link, but must not change the
migration facts above.

## Error Handling and Limits

- Missing, null, or nonnumeric cumulative `action_rotation_angle` resolves to zero.
- `stop_rotating` ends the gesture listener and causes no top-level light run.
- Brightness and color-temperature results remain clamped to their configured
  ranges.
- Global queued automation mode remains unchanged. The one gesture worker is the
  only branch allowed to update a light.

## Verification

Extend the standard-library tests to prove:

- The brightness selector exposes 1-10 `%/tick` with default 4.
- The color-temperature selector exposes 1-10000 `K/tick` with default 60.
- With brightness set to 1, angles 12, 60, -24, and 84 produce 1%, 5%, -2%,
  and 7% respectively.
- With color temperature set to 60, the same angles produce 60 K, 300 K,
  -120 K, and 420 K respectively.
- Rotation reads cumulative `action_rotation_angle` in one gesture run, and the
  Blueprint remains in global queued mode.
- Coalescing intermediate packets preserves the final absolute target.
- A delayed entity-state simulation ends at the full cumulative target rather than
  losing ticks.
- Legacy brightness coefficients and descriptions are absent.
- The Blueprint description contains the breaking-change and migration notice.

After the focused tests pass, parse the YAML, parse every Jinja template, render
the relevant arithmetic templates with the captured values, and confirm the
user-facing output copy is byte-identical to the tested Blueprint.

## Official References

- Home Assistant Blueprint selectors:
  <https://www.home-assistant.io/docs/blueprint/selectors/>
- Home Assistant automation trigger data:
  <https://www.home-assistant.io/docs/automation/templating/>
- Home Assistant 2025.4 variable-scope change:
  <https://www.home-assistant.io/blog/2025/04/02/release-20254/>
- Home Assistant script variable and parallel-action scopes:
  <https://www.home-assistant.io/docs/scripts/>
- Zigbee2MQTT Aqara ZNXNKG02LM exposes:
  <https://www.zigbee2mqtt.io/devices/ZNXNKG02LM.html>
