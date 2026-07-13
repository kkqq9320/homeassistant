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

## Tick and Event Model

- Treat 12 degrees as one knob tick. This value is an internal constant and is
  not exposed in the Blueprint UI.
- Continue reading the packet-local increment from
  `trigger.payload_json.action_rotation_angle_speed`. Do not read a derived
  entity or retain the previous MQTT message.
- Calculate signed ticks as `action_rotation_angle_speed / 12`.
- Do not round the tick count before applying it. Captured device values are
  multiples of 12, while a future non-multiple value will remain proportional
  instead of being discarded.
- Positive values increase brightness or color temperature; negative values
  decrease them.

Examples:

| Packet-local angle | Tick delta | At 1%/tick | At 60 K/tick |
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
rotation_ticks = action_rotation_angle_speed / 12
brightness_delta_pct = rotation_ticks * brightness_pct_per_tick
color_temp_delta_k = rotation_ticks * color_temp_k_per_tick
```

Brightness applies `brightness_delta_pct` to the current brightness percentage,
then keeps the existing integer rounding and configured min/max clamp. Color
temperature applies `color_temp_delta_k` to the existing color-temperature base
and keeps the existing Kelvin min/max clamp.

The implementation must not retain the legacy `/ 3.6 / 3`, `2.54`, or the
conversion of the requested delta into a 0-255 value and back. Converting the
light entity's current `brightness` attribute from 0-255 to a percentage is
still required. Applying the requested change in direct percentage points
removes the avoidable round trip and its extra rounding.

## Compatibility and Migration

This is a breaking semantic change for saved Blueprint inputs:

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
> One Aqara knob tick is treated as 12 degrees. Brightness can now be configured
> from 1-10% per tick (default 4%), and pressed-rotation color temperature from
> 1-10000 K per tick (default 60 K). A five-tick/60-degree event applies five
> times the selected value. Existing step-size multiplier semantics are
> deprecated. After updating, open every automation created from this Blueprint,
> review the two rotation values, and save. In particular, change a previous
> color-temperature stepsize of 5 to 60 K/tick to preserve the old response,
> and replace any previous brightness value above 10 with a value from 1-10.

The final forum text may add a release version or link, but must not change the
migration facts above.

## Error Handling and Limits

- Missing, null, or nonnumeric `action_rotation_angle_speed` continues to
  resolve to zero and causes no rotation action.
- `stop_rotating` continues to cause no light adjustment because its packet-local
  increment is zero.
- Brightness and color-temperature results remain clamped to their configured
  ranges.
- Queued automation mode remains unchanged so packets cannot race while reading
  and updating a light.

## Verification

Extend the standard-library tests to prove:

- The brightness selector exposes 1-10 `%/tick` with default 4.
- The color-temperature selector exposes 1-10000 `K/tick` with default 60.
- With brightness set to 1, angles 12, 60, -24, and 84 produce 1%, 5%, -2%,
  and 7% respectively.
- With color temperature set to 60, the same angles produce 60 K, 300 K,
  -120 K, and 420 K respectively.
- Rotation still reads `action_rotation_angle_speed` from the current trigger
  payload, and the Blueprint remains in queued mode.
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
- Zigbee2MQTT Aqara ZNXNKG02LM exposes:
  <https://www.zigbee2mqtt.io/devices/ZNXNKG02LM.html>
