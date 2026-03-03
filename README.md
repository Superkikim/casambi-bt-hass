> **Fork notice**: This is a fork of [@rankjie/casambi-bt-hass](https://github.com/rankjie/casambi-bt-hass),
> maintained by [@Superkikim](https://github.com/Superkikim).
> It adds Winsol blind/cover support, Sensor Platform V4 environment sensors,
> White Color Balance control, and translations (FR, IT, DE, NL).
> Generic improvements are submitted upstream via PR when applicable.

# Casambi Bluetooth Revamped

[![Discord](https://img.shields.io/discord/1186445089317326888)](https://discord.gg/jgZVugfx)

An enhanced fork of the [original Casambi Bluetooth integration](https://github.com/lkempf/casambi-bt-hass) by [@lkempf](https://github.com/lkempf), with additional features for better switch, relay, cover, light and sensor support.

> ⚠️ **DEVELOPMENT WARNING**: This repository is used as a development environment. Things might break at any moment. It's recommended to wait at least 1 day after a new release before updating to ensure stability. All stable changes will be merged back to the original repository.
>
> **When to use this fork**: Use this version if you need Classic firmware support, Winsol blind/cover control, environment sensors (wind, rain, solar, PIR), or White Color Balance control. Otherwise, consider the upstream integration.

## What's Enhanced

- **Classic protocol support** - Lighting fixtures on Classic (legacy) Casambi firmware networks: on/off, dimming, and live state sync from the Casambi app. More testers welcome!
- **Switch event support** - Physical switch button press/hold/release events (wired + wireless), fired as `casambi_bt_button_event` HA events for clean automation triggers
- **Motor-driven covers** - Blinds and shutters appear as HA cover entities with open/close/stop and position control
- **Tilt control** - Louvre-type blinds (e.g. Winsol Lamel V4.1 TA16) support tilt angle control (0–142°)
- **White/Color balance** - RGB/TW lights with a WHITECOLORBALANCE control expose a `white_balance` attribute, a number slider, and a `set_white_balance` service
- **Environment sensors** - Casambi Sensor Platform V4 units expose wind speed, solar radiation, rain (binary), and PIR presence (binary) as HA entities
- **Localization** - Full translations for French (fr), Italian (it), German (de), and Dutch (nl)
- **Automation blueprints** - Ready-to-use blueprints for button automations
- **Fixed relay status** - Properly reports the status of relay units (also merged to the original integration)
- **Based on casambi-bt-revamped** - Uses an enhanced version of the underlying library (protocol-level INVOCATION parsing)

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
Physical switches fire `casambi_bt_button_event` HA events:
- Commands: `pressed`, `held`, `released`, `released_after_hold`
- Works with EnOcean PTM215B (Kinetic) and wired switches
- Use event data `unit_name`, `button`, `command` in automations

[**→ Detailed Switch Event Documentation**](docs/SWITCH_EVENTS.md)

### 🪟 Motor-Driven Covers
Casambi `EXT/1ch/Dim` units (blinds, shutters) are exposed as HA cover entities:
- Open, close, stop
- Position control (0–100%)
- Tilt angle for louvre-type blinds (where supported, e.g. Winsol Lamel V4.1 TA16)

### 💡 Light Features
- Dimmer, color (RGB), color temperature (TW), on/off
- **White/Color balance**: RGB/TW lights with a WHITECOLORBALANCE control expose:
  - A `white_balance` attribute on the light entity (0% = pure white, 100% = pure color)
  - A number slider entity for direct control from the UI
  - A `casambi_bt.set_white_balance` service for use in automations

### 🌦 Environment Sensors (Sensor Platform V4)
Casambi Sensor Platform V4 units expose four sensors:
- **Wind** — numeric sensor (speed)
- **Solar radiation** — numeric sensor
- **Rain** — binary sensor (`device_class: moisture`)
- **Motion (PIR)** — binary sensor (`device_class: motion`)

### 🌍 Localization
Entity names and config flow are translated for:
- 🇬🇧 English (`en`)
- 🇫🇷 French (`fr`)
- 🇮🇹 Italian (`it`)
- 🇩🇪 German (`de`)
- 🇳🇱 Dutch (`nl`)

### 🎯 Automation Blueprints
Import ready-to-use blueprints with one click:

[![Toggle and Dim](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Frankjie%2Fcasambi-bt-hass%2Fmain%2Fblueprints%2Fautomation%2Fcasambi_bt%2Fbutton_toggle_and_dim.yaml) **Toggle and Dim** - All-in-one light control (short press = toggle, hold = dim)

[![Button Actions](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Frankjie%2Fcasambi-bt-hass%2Fmain%2Fblueprints%2Fautomation%2Fcasambi_bt%2Fbutton_short_long_press.yaml) **Button Actions** - Versatile automation for any button event

[![Cover Control](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Frankjie%2Fcasambi-bt-hass%2Fmain%2Fblueprints%2Fautomation%2Fcasambi_bt%2Fbutton_cover_control.yaml) **Cover Control** - Smart blind/cover control (press = open/close/stop, hold = continuous)

[**→ Blueprint Documentation & Examples**](docs/BLUEPRINTS.md)

### 💡 Supported Devices
- Lights (dimmer, color, temperature, on/off, white/color balance)
- Light groups
- Scenes
- Switches (as events, not entities)
- Motor-driven covers (blinds, shutters, louvre blinds with tilt)
- Relays
- Environment sensors (Sensor Platform V4: wind, solar, rain, PIR)

Classic (legacy) firmware notes:
- Discovery includes both EVO (`FE4D`) and Classic (`CA5A`) advertisements.
- On/off, dimming, and bidirectional state sync are working for lighting fixtures.
- Changes made in the Casambi app are reflected in HA in real time.
- More testers welcome — if you have a Classic network, please [open an issue](https://github.com/rankjie/casambi-bt-hass/issues) with your experience.

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

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the full history of changes in this fork.

## Credits

This integration builds on the work of:
- [@lkempf](https://github.com/lkempf) — original integration: [casambi-bt-hass](https://github.com/lkempf/casambi-bt-hass) and library [casambi-bt](https://github.com/lkempf/casambi-bt)
- [@rankjie](https://github.com/rankjie) — revamped fork: [casambi-bt-hass](https://github.com/rankjie/casambi-bt-hass) with Classic protocol, switch events, covers and more

## Development

For development setup and contribution guidelines, see the [upstream repository](https://github.com/rankjie/casambi-bt-hass).

## License

This project maintains the same license as the original work.
