# Aqara Rotary Knob H1 Light Control for Zigbee2MQTT

Use an Aqara Rotary Knob H1 (ZNXNKG02LM) to control light brightness and color
temperature through Zigbee2MQTT and Home Assistant.

- [Blueprint YAML](../z2m_aqara_knob_h1_light_control.yaml)
- [Home Assistant Community topic](https://community.home-assistant.io/t/z2m-aqara-rotary-knob-h1-adjustable-brightness-color-temperature-z2m/841036)

## Import Blueprint to Home Assistant

[![Import this Blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fkkqq9320%2Fhomeassistant%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fz2m_aqara_knob_h1_light_control.yaml)

If the Blueprint is already installed, re-import it and then open every automation
created from it. Review the changed inputs and save the automation again.

## Requirements

- Home Assistant Core 2025.4 or newer
- Zigbee2MQTT and the Home Assistant MQTT integration
- Aqara Rotary Knob H1 (ZNXNKG02LM) in Zigbee2MQTT `event` operation mode
- One target `light` entity with brightness support
- Kelvin color-temperature support for pressed rotation

The Blueprint listens to the Zigbee2MQTT device topic directly. Enter the configured
Zigbee2MQTT base topic and the knob's exact Zigbee2MQTT friendly name.

## Breaking changes

- `Target Light` is now one UI-selected `light` entity. Existing templates or entity
  lists must be replaced with one light or light-group entity.
- Brightness uses direct `%/tick` values. The range is 1-100 and the default is 2.
- Pressed rotation uses direct `K/tick` values. The range is 1-10000 and the default
  is 100.
- The unused `translate_friendly_name` input has been removed.
- Hold Repeat Maximum Duration now defaults to 11 seconds and cannot be set higher.
  **RELEASE THE PHYSICAL BUTTON BEFORE 10 SECONDS** to avoid the knob entering
  networking mode.

## Configuration

1. Import or re-import the Blueprint.
2. Enter the Zigbee2MQTT base topic. Keep `zigbee2mqtt` if it was not changed.
3. Enter the knob's exact Zigbee2MQTT friendly name.
4. Select one target light or light-group entity.
5. Configure Single, Double, and Hold actions.
6. Expand `Hold Repeat & Release` only when repeated or release behavior is needed.
7. Adjust the brightness, color-temperature, transition, and limit settings.

### Multiple lights

`Target Light` accepts one entity. To control multiple lights, select a single group
entity created with either:

- [Home Assistant Light Group](https://www.home-assistant.io/integrations/group/#light-groups)
- [Cheerpipe Relative Light Group](https://github.com/Cheerpipe/relative-light-group)

Direct entity lists and templates are not supported.

## Knob controls

| Gesture | Result |
| --- | --- |
| Turn right | Increase brightness |
| Turn left | Decrease brightness |
| Press and turn right | Increase color temperature |
| Press and turn left | Decrease color temperature |
| Single / Double / Hold | Run the configured action |
| Release | Run Release Action when configured |

One 12-degree rotation is one tick. A gesture uses the knob's cumulative rotation
angle, and the calculated result is clamped to the configured light limits. Repeated
rotation at an already reached limit does not send duplicate commands for the same
target value.

## Hold Repeat & Release

The `Press Action` section contains only Single Action, Double Action, and Hold
Action. Repeating and release settings are in the separate `Hold Repeat & Release`
section, which is collapsed by default.

| Hold Repeat Mode | Behavior while held |
| --- | --- |
| Do not repeat | Run Hold Action once |
| Repeat Hold Action | Run Hold Action once, then repeat it |
| Hold once, then repeat a separate action | Run Hold Action once, then repeat Hold Repeat Action |

Repeating stops when `release`, another knob action, or the maximum duration is
reached. Release Action then runs once when a `release` event is received.

**LEAVE THIS EMPTY** unless an action is specifically needed when the knob is
released.

## Updating

Home Assistant can update an imported Blueprint by re-importing it. Open
**Settings > Automations & scenes > Blueprints**, open the Blueprint menu, and
select **Re-import blueprint**. Review the breaking changes above before saving
existing automations.

See the official [Using automation blueprints](https://www.home-assistant.io/docs/automation/using_blueprints/)
documentation for import and re-import instructions.
