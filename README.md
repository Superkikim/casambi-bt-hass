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
    - `"button_release_after_hold"` - Release after holding
  - `message_type`: Raw message type from the device
  - `flags`: Additional flags from the message

### Button Hold Timing
- **Press to Hold Delay**: Approximately 500-600ms
  - Short press (< 500ms): Fires `button_press` followed by `button_release`
  - Long press (> 500ms): Fires `button_press`, then `button_hold` events start after ~500ms, finally `button_release_after_hold` when released
- **Hold Event Frequency**: `button_hold` events fire continuously but at irregular intervals while the button is held
  - Each hold event has a unique payload (incrementing counter), so they are not filtered as duplicates
  - The integration only filters truly duplicate packets with identical payloads within a 10-second window

### Automation Blueprints

This integration includes several automation blueprints to make it easy to set up switch button automations:

1. **Casambi Button Press Action** - Simple action on button press/release
   
   [![Import Button Press Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Frankjie%2Fcasambi-bt-hass%2Fmain%2Fblueprints%2Fautomation%2Fcasambi_bt%2Fbutton_press_action.yaml)

2. **Casambi Button Hold Dimming** - Dim lights while holding a button (requires an input_text helper)
   
   [![Import Button Hold Dimming Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Frankjie%2Fcasambi-bt-hass%2Fmain%2Fblueprints%2Fautomation%2Fcasambi_bt%2Fbutton_hold_dimming.yaml)

3. **Casambi Button Short/Long Press Actions** - Different actions for short vs long press
   
   [![Import Short/Long Press Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Frankjie%2Fcasambi-bt-hass%2Fmain%2Fblueprints%2Fautomation%2Fcasambi_bt%2Fbutton_short_long_press.yaml)

To use these blueprints:

**Easy Method - Import Links:**
1. Click any of the "Import Blueprint" buttons above
2. This will open the blueprint import dialog in your Home Assistant
3. Click "Preview Blueprint" and then "Import Blueprint"
4. Create an automation from the imported blueprint

**Alternative Method - Manual:**
If the import buttons don't work or you prefer manual installation:

For HACS installations:
1. After installing/updating the integration, restart Home Assistant
2. The blueprints may appear in Settings → Automations & Scenes → Blueprints
3. If not, manually copy the `blueprints` folder to your HA config directory

For manual installations:
1. Copy BOTH folders to your Home Assistant config directory:
   - `custom_components/casambi_bt/` → `config/custom_components/casambi_bt/`
   - `blueprints/` → `config/blueprints/`
2. Restart Home Assistant
3. Go to Settings → Automations & Scenes → Blueprints

**For the Button Hold Dimming blueprint:**
- First create an input_text helper: Settings → Devices & Services → Helpers → Create Helper → Text
- Name it something like "casambi_button_123_0_state" (for unit 123, button 0)
- Use this helper in the blueprint configuration

All blueprints include:
- Optional message type filtering (useful if your switch sends different types)
- Configurable debounce time to prevent duplicate triggers
- Clear descriptions for each setting

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

#### Dimming with Hold (Single Automation with Helper)
```yaml
# First create an input_text helper for button state tracking:
# Settings → Devices & Services → Helpers → Create Helper → Text

automation:
  - alias: "Casambi Switch Dimming"
    mode: parallel  # Allow multiple instances
    trigger:
      - platform: event
        event_type: casambi_bt_switch_event
        event_data:
          unit_id: 123  # Your switch unit ID
          button: 0     # Button number (0-based)
    condition:
      - condition: template
        value_template: >
          {{ trigger.event.data.action in ['button_hold', 'button_release_after_hold'] }}
    action:
      - choose:
          # Update helper on release
          - conditions:
              - condition: template
                value_template: "{{ trigger.event.data.action == 'button_release_after_hold' }}"
            sequence:
              - service: input_text.set_value
                target:
                  entity_id: input_text.casambi_button_state
                data:
                  value: "released"
          # Start dimming on hold
          - conditions:
              - condition: template
                value_template: "{{ trigger.event.data.action == 'button_hold' }}"
            sequence:
              - service: input_text.set_value
                target:
                  entity_id: input_text.casambi_button_state
                data:
                  value: "holding"
              - repeat:
                  while:
                    - condition: state
                      entity_id: input_text.casambi_button_state
                      state: "holding"
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
          action: button_release  # Only triggered on quick press/release
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
          action: button_release_after_hold  # Only triggered after holding
    action:
      - service: scene.turn_on
        entity_id: scene.movie_time
```

#### Reliable Short Press (handles missed button_press events)
```yaml
automation:
  - alias: "Casambi Switch Toggle Light"
    mode: single
    trigger:
      # Trigger on both press and release for reliability
      - platform: event
        event_type: casambi_bt_switch_event
        event_data:
          unit_id: 123
          button: 0
          action: button_press
      - platform: event
        event_type: casambi_bt_switch_event
        event_data:
          unit_id: 123
          button: 0
          action: button_release
    condition:
      # Prevent double triggers and ignore release after hold
      - condition: template
        value_template: >
          {{ 
            (trigger.event.data.action != 'button_release' or 
             (as_timestamp(now()) - as_timestamp(this.attributes.last_triggered | default(0))) > 2)
          }}
    action:
      - service: light.toggle
        entity_id: light.living_room
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
Button press and release events are **not guaranteed** to be captured due to the nature of Bluetooth communication:
- Sometimes `button_press` events may be missed entirely
- For better reliability, consider triggering automations on both `button_press` and `button_release` events
- Be aware that `button_release` fires for short presses while `button_release_after_hold` fires for long presses - they are distinct events

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
