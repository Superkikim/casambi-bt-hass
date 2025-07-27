# Casambi Bluetooth Revamped

[![Discord](https://img.shields.io/discord/1186445089317326888)](https://discord.gg/jgZVugfx)

An enhanced fork of the [original Casambi Bluetooth integration](https://github.com/lkempf/casambi-bt-hass) by [@lkempf](https://github.com/lkempf), with additional features for better switch and relay support.

> ⚠️ **DEVELOPMENT WARNING**: This repository is used as a development environment. Things might break at any moment. It's recommended to wait at least 1 day after a new release before updating to ensure stability. All stable changes will be merged back to the original repository.

## What's Enhanced

- **Fixed relay status** - Properly reports the status of relay units
- **Switch event support** - Physical switch button press, hold, and release events 
- **Automation blueprints** - Ready-to-use blueprints for button automations
- **Based on casambi-bt-revamped** - Uses an enhanced version of the underlying library

## Quick Start

### Installation

#### HACS (Recommended)
1. Add this repository as a custom repository in HACS
2. Search for "Casambi Bluetooth Revamped" and install
3. Restart Home Assistant

#### Manual
1. Copy the `custom_components/casambi_bt` folder to your `config/custom_components/`
2. Restart Home Assistant

### Configuration
1. Go to Settings → Devices & Services → Add Integration
2. Search for "Casambi Bluetooth"
3. Enter your network password from the Casambi app

## Features

### 📱 Switch Button Events
Physical switches fire events for automations:
- Button press, hold, and release detection
- ~500ms press-to-hold delay
- Support for short/long press actions

[**→ Detailed Switch Event Documentation**](docs/SWITCH_EVENTS.md)

### 🎯 Automation Blueprints
Import ready-to-use blueprints with one click:

[![Toggle and Dim](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Frankjie%2Fcasambi-bt-hass%2Fmain%2Fblueprints%2Fautomation%2Fcasambi_bt%2Fbutton_toggle_and_dim.yaml) **Toggle and Dim** - All-in-one light control (short press = toggle, hold = dim)

[![Button Actions](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Frankjie%2Fcasambi-bt-hass%2Fmain%2Fblueprints%2Fautomation%2Fcasambi_bt%2Fbutton_short_long_press.yaml) **Button Actions** - Versatile automation for any button event

[![Cover Control](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Frankjie%2Fcasambi-bt-hass%2Fmain%2Fblueprints%2Fautomation%2Fcasambi_bt%2Fbutton_cover_control.yaml) **Cover Control** - Smart blind/cover control (press = open/close/stop, hold = continuous)

[**→ Blueprint Documentation & Examples**](docs/BLUEPRINTS.md)

### 💡 Supported Devices
- Lights (dimmer, color, temperature, on/off)
- Light groups
- Scenes
- Switches (as events, not entities)
- Relays

## Network Setup

**Important**: Your Casambi network must be configured correctly:
1. Enable "Bluetooth control" in the Casambi app
2. Set a network password
3. See the [original setup guide](https://github.com/lkempf/casambi-bt#casambi-network-setup) for details

## Troubleshooting

Enable debug logging in `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    CasambiBt: debug
    custom_components.casambi_bt: debug
```

For issues, please include:
- Debug logs (sanitize sensitive data)
- Your network configuration
- Device types you're trying to control

## Credits

This integration is based on the excellent work by [@lkempf](https://github.com/lkempf):
- Original integration: [casambi-bt-hass](https://github.com/lkempf/casambi-bt-hass)
- Original library: [casambi-bt](https://github.com/lkempf/casambi-bt)

## Development

For development setup and contribution guidelines, see the [original repository](https://github.com/lkempf/casambi-bt-hass#development).

## License

This project maintains the same license as the original work.