# What's revamped?

This is an enhanced version of the original Casambi Bluetooth integration with the following improvements:

- **Fixed relay status** - Properly reports the status of relay units
- **Switch event support** - Physical switch/button press, hold, and release events are fired as Home Assistant events for automations
- **Based on modified casambi-bt library** - Uses an enhanced version of the underlying library for better device support

## Switch Event Support

Switch button press/release events are fired as Home Assistant events that can be used in automations.

### Event Details
- **Event Type**: `casambi_bt_switch_event`
- **Event Data**:
  - `entry_id`: The config entry ID
  - `unit_id`: The Casambi unit ID that sent the event
  - `button`: Button number (0-based)
  - `action`: Event type - one of:
    - `"button_press"` - Initial button press
    - `"button_hold"` - Sent continuously while button is held down
    - `"button_release"` - Quick press and release
    - `"button_release_after_hold"` - Release after holding (also fires a compatibility `button_release` event)
  - `message_type`: Raw message type from the device
  - `flags`: Additional flags from the message
  - `original_action`: (Only in compatibility events) The original action before compatibility mapping

### Example Automations

#### Simple Toggle on Press
```yaml
automation:
  - alias: "Casambi Switch Button Press"
    mode: single  # Prevents duplicate executions
    trigger:
      - platform: event
        event_type: casambi_bt_switch_event
        event_data:
          unit_id: 123  # Your switch unit ID
          button: 0     # Button number (0-based)
          action: button_press
    condition:
      # Prevent re-triggering within 2 seconds
      - condition: template
        value_template: >
          {{ (as_timestamp(now()) - as_timestamp(state_attr('automation.casambi_switch_button_press', 'last_triggered') | default(0))) > 2 }}
    action:
      - service: light.toggle
        target:
          entity_id: light.living_room
```

#### Dimming with Hold
```yaml
automation:
  - alias: "Casambi Switch Dimming"
    mode: restart  # Restart if triggered again while running
    trigger:
      - platform: event
        event_type: casambi_bt_switch_event
        event_data:
          unit_id: 123  # Your switch unit ID
          button: 0     # Button number (0-based)
          action: button_hold
    action:
      - repeat:
          while:
            - condition: template
              value_template: "{{ true }}"  # Continues until automation is stopped
          sequence:
            - service: light.turn_on
              target:
                entity_id: light.living_room
              data:
                brightness: >
                  {% set current = state_attr('light.living_room', 'brightness') | default(0) %}
                  {% set new = current + 10 %}
                  {{ [new, 255] | min }}
            - delay:
                milliseconds: 200

  - alias: "Stop Dimming on Release"
    trigger:
      - platform: event
        event_type: casambi_bt_switch_event
        event_data:
          unit_id: 123
          button: 0
          action: button_release_after_hold
    action:
      - service: automation.turn_off
        entity_id: automation.casambi_switch_dimming
      - delay:
          seconds: 1
      - service: automation.turn_on
        entity_id: automation.casambi_switch_dimming
```

#### Different Actions for Short Press vs Long Press
```yaml
automation:
  - alias: "Casambi Switch Short Press"
    trigger:
      - platform: event
        event_type: casambi_bt_switch_event
        event_data:
          unit_id: 123
          button: 0
          action: button_release  # Quick press/release
    condition:
      - condition: template
        value_template: >
          {{ trigger.event.data.get('original_action') != 'button_release_after_hold' }}
    action:
      - service: light.toggle
        entity_id: light.living_room

  - alias: "Casambi Switch Long Press"
    trigger:
      - platform: event
        event_type: casambi_bt_switch_event
        event_data:
          unit_id: 123
          button: 0
          action: button_release_after_hold
    action:
      - service: scene.turn_on
        entity_id: scene.movie_time
```

### Listening to Events
You can monitor these events in Developer Tools → Events → Listen to events by entering `casambi_bt_switch_event` as the event type.

### Important Notes for Switch Events

#### Message Types and Event Data
- **Message Type 8**: Usually valid button press/release events
- **Message Type 16**: Sometimes also valid events - verify by listening to actual events from your switch

**Important**: The event data fields are based on guesswork and may be incorrect. However, the values are consistent enough to be usable. Sometimes the `flags` field, combined with `unit_id`, `button`, and `message_type`, creates a unique combination that can be used to identify specific button actions.

**Tip**: You can use the Casambi app to configure switch button actions while simultaneously listening to events in Home Assistant. This allows you to:
- Use Casambi's built-in button assignments for some actions
- Create custom Home Assistant automations for other buttons
- Have multiple ways to control your devices

#### Finding Your Switch Configuration
To identify your switch's unit ID:
1. Open the Casambi app
2. Go to More → Switches
3. Select your switch
4. Tap Details → Note the Unit ID

**Identifying Button Numbers**: Due to potential parsing differences, the button number shown in Home Assistant events may not directly match the Casambi app numbering. To find the correct button number for your automations:
1. Go to Developer Tools → Events in Home Assistant
2. Start listening for `casambi_bt_switch_event`
3. Press the physical button on your switch
4. Check the captured event data for the actual `button` value
5. Use this value in your automations

This is the most reliable way to identify button mappings for your specific switch model.

#### Handling Duplicate Events
The Casambi protocol may send multiple duplicate event packets for reliability. You'll need to implement debouncing in your automations to handle this. See the example automation above which includes a 2-second cooldown period to prevent duplicate triggers.

#### Event Reliability
Button press and release events are **not guaranteed** to be captured due to the nature of Bluetooth communication. For better reliability, it's recommended to trigger automations on both `button_press` and `button_release` events rather than relying on just one type.

### Example Event Data
Here are examples of different switch events in Home Assistant:

#### Quick Press/Release
```yaml
event_type: casambi_bt_switch_event
data:
  entry_id: fc8461de92e186495147fdb327fddea9
  unit_id: 31
  button: 0
  action: button_release
  message_type: 8
  flags: 3
origin: LOCAL
```

#### Button Hold Event (fires continuously)
```yaml
event_type: casambi_bt_switch_event
data:
  entry_id: fc8461de92e186495147fdb327fddea9
  unit_id: 31
  button: 0
  action: button_hold
  message_type: 16
  flags: 2
origin: LOCAL
```

#### Release After Hold
```yaml
event_type: casambi_bt_switch_event
data:
  entry_id: fc8461de92e186495147fdb327fddea9
  unit_id: 31
  button: 0
  action: button_release_after_hold
  message_type: 16
  flags: 2
origin: LOCAL
```

#### Compatibility Event (automatically fired with button_release_after_hold)
```yaml
event_type: casambi_bt_switch_event
data:
  entry_id: fc8461de92e186495147fdb327fddea9
  unit_id: 31
  button: 0
  action: button_release
  original_action: button_release_after_hold  # Indicates this is a compatibility event
  message_type: 16
  flags: 2
origin: LOCAL
```

# Home Assistant integration for Casambi using Bluetooth

[![Discord](https://img.shields.io/discord/1186445089317326888)](https://discord.gg/jgZVugfx)

This is a Home Assistant integration for Casambi networks using Bluetooth. Since this is an unofficial implementation of the rather complex undocumented protocol used by the Casambi app there may be issues in networks configured differently to the one used to test this integration.
Please see the information below on how to report such issues.

A more mature HA integration for Casambi networks can be found under [https://github.com/hellqvio86/home_assistant_casambi](https://github.com/hellqvio86/home_assistant_casambi). This integration requires a network gateway to always connect the network to the Casambi cloud.

## Network configuration

See [https://github.com/lkempf/casambi-bt#casambi-network-setup](https://github.com/lkempf/casambi-bt#casambi-network-setup) for the proper network configuration. If you get "Unexcpected error" or "Failed to connect" different network configurations are the most common cause. Due to the high complexity of the protocol I won't be able to support all configurations allthough I might try if the suggested config doesn't work and the fix isn't to complex.

## Installation

### Manual

Place the `casambi_bt` folder in the `custom_components` folder.

### HACS

Add this repository as custom repository in the HACS store (HACS -> integrations -> custom repositories):

1. Setup HACS https://hacs.xyz/
2. Select HACS from the left sidebar
3. Search for `Casambi **Bluetooth**` in the searchbar at the top and select it. If you can't find it you might have to add this repository as a custom repository.
4. Click the Download button at the bottom right
5. Restart Home Assistant

## Features

Functionality exposed to HA:
- Lights
- Light groups
- Scenes
- Switches* (not as Home Assistant switch entities - but switch events are published as `casambi_bt_switch_event`)

Supported control types:
- Dimmer
- White
- Rgb
- OnOff
- Temperature (Only for units since there are some open problems for groups.)
- Vertical

Not supported yet:
- Sensors
- Additional control types (e.g. temperature, ...)
- Networks with classic firmware

## Reporting issues

Before reporting issues make sure that you have the debug log enabled for all relevant components. This can be done by placing the following in `configuration.yaml` of your HA installation:

```yaml
logger:
  default: info
  logs:
    CasambiBt: debug
    custom_components.casambi_bt: debug
```

The log might contain sensitive information about the network (including your network password and the email address used for the network) so sanitize it first or mail it to the address on my github profile referencing your issue.

## Development

When developing you might also want to change [https://github.com/lkempf/casambi-bt](casambi-bt). To make this more convenient run
```
pip install -e PATH_TO_CASAMBI_BT_REPO
```
in the homeassistant venv and then start HA with
```
hass -c config --skip-pip-packages casambi-bt
```

If you are unsure what these terms mean you might want to have a look at [https://developers.home-assistant.io/docs/development_environment](https://developers.home-assistant.io/docs/development_environment) first.
