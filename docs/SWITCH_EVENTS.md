# Switch Event Support

Switch button press/release events are fired as Home Assistant events that can be used in automations.

## Event Details
- **Event Type**: `casambi_bt_switch_event`
- **Event Data**:
  - `entry_id`: The config entry ID
  - `unit_id`: The Casambi unit ID that sent the event
  - `button`: Button number (1-4, matching Casambi app)
  - `action`: Event type - one of:
    - `"button_press"`
    - `"button_hold"` (repeats while held, device/firmware dependent)
    - `"button_release"`
    - `"button_release_after_hold"`
    - `"input_event"` (raw NotifyInput frame; useful for diagnostics and some wired devices)
  - `message_type`: Decrypted packet type (always `7` for switch events)
  - `flags`: INVOCATION flags (uint16)
  - INVOCATION metadata:
    - `event_id`: Stable correlation id: `invoke:{origin}:{age}:{opcode}:{target}`
    - `opcode`, `target_type`, `origin`, `age`
    - `button_event_index`, `param_p`, `param_s` (for the button stream)
  - NotifyInput fields (only for `target_type == 18 / 0x12`):
    - `input_index`, `input_code`, `input_channel`, `input_value16`, `input_mapped_event`
  - Diagnostics:
    - `packet_sequence`, `arrival_sequence`, `raw_packet`, `decrypted_data`, `payload_hex`, `message_position`

## Wired vs Wireless Switches

The underlying library decodes switch events from decrypted Casambi packet type `0x07` (INVOCATION stream), matching the official Android app parsing.

- Wireless (battery) switches typically send:
  - a "button stream" (`target_type=0x06`) for press/release
  - a NotifyInput stream (`target_type=0x12`) for hold/release-after-hold
- Wired switches often only send NotifyInput (`target_type=0x12`). In that case the library maps `input_code` to semantic actions (`button_press`, `button_release`, etc).

The library suppresses same-state retransmits at the protocol layer, so Home Assistant-style time-window deduplication is unnecessary.

For the field layout and parsing logic (ground-truthed against the official Android app), see `casambi-bt/doc/PROTOCOL_PARSING.md`.

## Listening to Events
You can monitor these events in Developer Tools → Events → Listen to events by entering `casambi_bt_switch_event` as the event type.

## Important Notes

**Tip**: You can use the Casambi app to configure switch button actions while simultaneously listening to events in Home Assistant. This allows you to:
- Use Casambi's built-in button assignments for some actions
- Create custom Home Assistant automations for other buttons
- Have multiple ways to control your devices

### Finding Your Switch Configuration

#### Method 1: Using Home Assistant Developer Tools (Recommended)
1. Go to **Developer Tools → Events** in Home Assistant
2. In the "Listen to events" section, enter: `casambi_bt_switch_event`
3. Click "Start listening"
4. Press the physical button on your switch
5. Check the captured event data for:
   - `unit_id`: The switch's unit ID
   - `button`: The button number (1-4, matching the Casambi app)
   - `action`: The event type (button_press, button_release, etc.)


#### Method 2: Verifying Unit ID in Casambi App
If you see multiple events with different `unit_id` values, verify the correct one:
1. Open the Casambi app
2. Go to **More → Switches**
3. Select your switch
4. Tap **Details**
5. Note the **Unit ID** shown
6. Use this Unit ID in your automations

**Button Numbers**: Button numbers in events match the Casambi app (1-4). Always test each physical button first to verify which button number it generates.

### Event Reliability
Bluetooth is still best-effort, but the Casambi protocol itself includes retransmits and the parser handles duplicates/missed edges significantly better than naive advertisement listening.

## Example Event Data
Here are examples of different switch events in Home Assistant:

### Quick Press/Release
```yaml
event_type: casambi_bt_switch_event
data:
  entry_id: fc8461de92e186495147fdb327fddea9
  unit_id: 31
  button: 1
  action: button_press
  message_type: 7
  event_id: invoke:1f51:0007:1e:1f06
  opcode: 30
  target_type: 6
  origin: 8017
  age: 7
  flags: 2051
origin: LOCAL
```

### Button Hold Event (fires continuously)
```yaml
event_type: casambi_bt_switch_event
data:
  entry_id: fc8461de92e186495147fdb327fddea9
  unit_id: 31
  button: 1
  action: button_hold
  message_type: 7
  target_type: 18
  input_code: 9
  input_mapped_event: button_hold
origin: LOCAL
```

### Release After Hold
```yaml
event_type: casambi_bt_switch_event
data:
  entry_id: fc8461de92e186495147fdb327fddea9
  unit_id: 31
  button: 1
  action: button_release_after_hold
  message_type: 7
  target_type: 18
  input_code: 12
  input_mapped_event: button_release_after_hold
origin: LOCAL
```
