# Changelog

All notable changes to this fork ([Superkikim/casambi-bt-hass](https://github.com/Superkikim/casambi-bt-hass))
are documented here. Changes are relative to the upstream fork
[@rankjie/casambi-bt-hass](https://github.com/rankjie/casambi-bt-hass).

---

## [1.9.0.dev3] — 2026-03-03

### Added
- **Translations** — full config flow + entity names for:
  - 🇫🇷 French (`fr`) — new
  - 🇮🇹 Italian (`it`) — new
  - 🇩🇪 German (`de`) — entity section added, `invalid_address` error completed
  - 🇳🇱 Dutch (`nl`) — entity section added, `invalid_address` translated, `reauth_confirm` added
- **Rain sensor** — converted from numeric `sensor` to `binary_sensor` (`device_class: moisture`)
- **PIR presence sensor** — converted from numeric `sensor` to `binary_sensor` (`device_class: motion`)

### Fixed
- **Wind and Solar sensors** — restored 6 explicit `SensorEntity` property overrides
  (`state_class`, `native_unit_of_measurement`, `options`, `last_reset`,
  `suggested_display_precision`, `suggested_unit_of_measurement`) that were
  accidentally removed during the Rain/PIR refactor. These overrides are required
  because `TypedEntityDescription` does not extend `SensorEntityDescription`, causing
  `AttributeError` when HA tries to read sensor-specific fields from the description.

---

## [1.9.0.dev2] — 2026-02-19

### Added
- **Cover support** — Winsol SO! V4.1 blinds (`EXT/1ch/Dim` + DIMMER) exposed as
  HA `cover` entities with open/close/stop and position control (0–100%)
- **Tilt control** — Winsol Lamel V4.1 TA16 supports tilt angle (0–142°) via
  `CasambiLamelCover` entity
- **White Color Balance** — RGB/TW lights with `WHITECOLORBALANCE` control now expose:
  - `white_balance` attribute on the light entity (read)
  - Number slider entity (`translation_key: white_balance`) for UI control
  - `casambi_bt.set_white_balance` service for use in automations
- **Environment Sensor Platform V4** — decodes BLE state packets cycling through 4 types:
  - Wind speed (numeric sensor)
  - Solar radiation (numeric sensor)
  - Rain detection (binary sensor, `device_class: moisture`)
  - PIR presence (binary sensor, `device_class: motion`)
- **Switch sensor improvements** — PTM215B button numbering fix, improved diagnostics
- **Translations (en)** — entity names for all new entities using `translation_key`

### Changed
- `_is_switch_unit()` — mode-based detection, no UNKNOWN fallback (prevents false positives
  for Winsol repeaters)

---

## [1.9.0.dev1] — upstream rankjie

See [rankjie/casambi-bt-hass](https://github.com/rankjie/casambi-bt-hass) for upstream
release notes. This fork is based on that version.
