# Switch Event Support

Switch button press/release events are fired as Home Assistant events that can be used in automations.

## Event Details
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

## Button Hold Timing
- **Press to Hold Delay**: Approximately 500-600ms
  - Short press (< 500ms): Fires `button_press` followed by `button_release`
  - Long press (> 500ms): Fires `button_press`, then `button_hold` events start after ~500ms, finally `button_release_after_hold` when released
- **Hold Event Frequency**: `button_hold` events fire continuously but at irregular intervals while the button is held
  - Each hold event has a unique payload (incrementing counter), so they are not filtered as duplicates
  - The integration only filters truly duplicate packets with identical payloads within a 10-second window

## Listening to Events
You can monitor these events in Developer Tools → Events → Listen to events by entering `casambi_bt_switch_event` as the event type.

## Important Notes

### Message Types and Event Data
- **Message Type 8**: Usually valid button press/release events
- **Message Type 16**: Sometimes also valid events - verify by listening to actual events from your switch

**Important**: The event data fields are based on guesswork and may be incorrect. However, the values are consistent enough to be usable. Sometimes the `flags` field, combined with `unit_id`, `button`, and `message_type`, creates a unique combination that can be used to identify specific button actions.

**Tip**: You can use the Casambi app to configure switch button actions while simultaneously listening to events in Home Assistant. This allows you to:
- Use Casambi's built-in button assignments for some actions
- Create custom Home Assistant automations for other buttons
- Have multiple ways to control your devices

### Finding Your Switch Configuration
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

### Handling Duplicate Events
The Casambi protocol may send multiple duplicate event packets for reliability. You'll need to implement debouncing in your automations to handle this. See the example automation below which includes a 2-second cooldown period to prevent duplicate triggers.

### Event Reliability
Button press and release events are **not guaranteed** to be captured due to the nature of Bluetooth communication:
- Sometimes `button_press` events may be missed entirely
- For better reliability, consider triggering automations on both `button_press` and `button_release` events
- Be aware that `button_release` fires for short presses while `button_release_after_hold` fires for long presses - they are distinct events

## Example Event Data
Here are examples of different switch events in Home Assistant:

### Quick Press/Release
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

### Button Hold Event (fires continuously)
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

### Release After Hold
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