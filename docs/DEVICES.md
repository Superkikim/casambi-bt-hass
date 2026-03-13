# Devices, Features & Library Bypass Notes

This document inventories every device type, every feature added beyond the upstream
(`lkempf/casambi-bt-hass`), and — critically — which parts of the implementation
**bypass or work around the `casambi-bt` library** rather than using it properly.
That last column is the roadmap for future library improvements.

---

## 1. Device Inventory

All devices are on a **Winsol** Casambi BLE mesh network, tested on a live installation.

| Device | Casambi unitType.mode | Controls present | HA platform | Notes |
|--------|-----------------------|-----------------|-------------|-------|
| **Winsol SO! V4.1** (9× shutters) | `EXT/1ch/Dim` | DIMMER | `cover` | Position via dimmer; Casambi 0=open, 255=closed (inverted vs HA) |
| **Winsol Lamel V4.1 TA16** (venetian blind) | `EXT/1ch/Dim` | DIMMER + SLIDER | `cover` + `number` (tilt) | Tilt 0–142° via SLIDER control in `lamel_controls.py` |
| **Winsol Sensor Platform V4** | `EXT/Elements{...}` | SENSOR ×4, no DIMMER | `sensor` (wind, solar) + `binary_sensor` (rain, PIR) | State cycles through 4 BLE packets; decoded in `environment_sensor.py` |
| **Winsol Repeater** (×2) | `Sensor` | UNKNOWN only | — (ignored) | BT signal repeater, not a sensor; explicitly excluded |
| **EnOcean PTM215B** | `Kinetic Switch` | — | `sensor` (last event) + HA events | Energy-harvesting wireless switch; 4 buttons |
| **Occhio Mito Aura** | `EXT/1ch/Dim` | DIMMER + TEMPERATURE + VERTICAL | `light` + `number` (vertical distribution) | Luminaire that shares EXT/1ch/Dim mode with shutters — must NOT be classified as cover |
| **DALI-2 Sensor{Presence,Daylight}** | `DALI Sensor` | — (state in `_unknown_controls`) | `sensor` (lux) + `binary_sensor` (presence/motion) | State decoded from raw 16-bit BLE value via private `_unknown_controls` |
| **Starlight / T-W / RGB-TW luminaires** | `PWM/*` | DIMMER/RGB/WHITE/TEMPERATURE | `light` | Standard upstream handling, unchanged |

---

## 2. Feature Inventory

### 2.1 Cover platform (`cover.py`)

**What it does:** Exposes motor-driven blinds/shutters as HA `cover` entities with
open / close / stop and position control.

**Discriminator — `_is_cover_unit(unit)`:**
```python
mode.startswith("EXT/1ch/Dim")
AND UnitControlType.DIMMER in controls
AND NOT any light control (RGB, WHITE, TEMPERATURE, XY, VERTICAL)
```
The third condition is critical: the Occhio Mito also has `EXT/1ch/Dim` + DIMMER but
additionally carries TEMPERATURE and VERTICAL — it must remain a `light`, not become a
`cover`. Without the light-control exclusion check (as in dev2), the Mito was
misclassified.

**Position convention inversion:**
Casambi/Winsol uses dimmer=0 → fully open, dimmer=255 → fully closed.
HA uses position=100 → open, position=0 → closed. The entity inverts:
```python
ha_position = 100 - (dimmer * 100 // 255)
casambi_dimmer = (100 - ha_position) * 255 // 100
```

**Library usage:** Uses `casa.setLevel(unit, value)` — supported by the library.
No bypass needed for basic open/close/position.

---

### 2.2 Lamel tilt control (`lamel_controls.py`)

**What it does:** Exposes tilt angle (slat orientation) of venetian blinds as a
`number` entity (0–142°).

**Detection:** Unit has both `DIMMER` and `SLIDER` controls.

**Library usage:** Uses the SLIDER control via `casa.setLevel` with the second control
index. This is a supported pattern but undocumented — the library has no explicit
"tilt" API.

---

### 2.3 White Color Balance (`white_color_balance.py`)

**What it does:** For RGB/TW lights with a `WHITECOLORBALANCE` control:
- Exposes `white_balance` as a `number` slider entity
- Adds `casambi_bt.set_white_balance` HA service
- Reads/writes raw bits in the unit state byte array

**Library bypass:** `_read_bits` and `_write_bits` manipulate `unit.state.raw_state`
directly (byte-level bit manipulation). The library has no `setWhiteColorBalance` API.
This is a full bypass of the library abstraction.

**Candidate for library improvement:** Add a `setWhiteColorBalance(unit, value)` method
to `casambi-bt`, accepting a normalized 0–1 float or 0–255 int.

---

### 2.4 Sensor Platform V4 (`environment_sensor.py`)

**What it does:** Decodes the Winsol Sensor Platform V4 multi-sensor BLE state into
four HA entities:
- `sensor.wind` — wind speed (raw/4)
- `sensor.solar` — solar radiation (raw/4)
- `binary_sensor.rain` — rain detection (`device_class: moisture`)
- `binary_sensor.pir` — PIR presence (`device_class: motion`)

**BLE state format (reverse-engineered):**
The device cycles through 4 BLE state packets (~every 4 s), one per sensor type:
```
byte[0] = 0x04   (constant)
byte[1] bits[7:6] = packet type:
    00 → rain   (0=dry, ≥2=raining)
    01 → wind   (raw/4 = value)
    10 → solar  (raw/4 = value)
    11 → PIR    (0=absent, 1=present)
byte[2] = raw value
byte[3] = 0x00
byte[4] = 0x3C
```

**Library bypass:** Uses `unit.state.raw_state` (raw bytes) directly. The library
decodes unit state into typed controls for known control types, but `SENSOR` type is
not decoded — the library returns the raw bytes unchanged.

**Accumulator pattern:** Because all 4 HA entities share the same `unit.state` (which
always reflects the last packet), a module-level dict `_accumulated[unit_uuid][packet_type]`
caches the last value of each sensor type so entities don't lose their value when a
different packet arrives.

**Candidate for library improvement:** The library should decode `SENSOR`-type controls
into typed sub-values (wind, rain, solar, PIR) rather than leaving them as raw bytes.
This would require knowledge of the Sensor Platform V4 BLE encoding, which is now
documented here.

---

### 2.5 DALI-2 Sensor{Presence,Daylight} (`dali2_sensor.py`)

**What it does:** Exposes a combined presence + daylight sensor as two HA entities:
- `binary_sensor.dali2_presence` — motion/presence (`device_class: motion`)
- `sensor.dali2_lux` — illuminance in lux (`device_class: illuminance`)

**Detection:** `unit.unitType.mode.startswith("DALI Sensor")`

**BLE state format (reverse-engineered from live traffic, 2026-03-13):**
The unit state is a 16-bit little-endian value:
```
bits  0– 1  (2 bits)  → presence  (0 = absent, non-zero = present)
bits  2–13  (12 bits) → daylight in lux  (0–4095)
bit  14     (1 bit)   → reserved / unknown flag
```

**Library bypass:** The library cannot decode DALI-2 sensor state (unknown control
types). It stores the decoded bit fields in `unit.state._unknown_controls`, a **private**
attribute — a list of `(bit_offset, bit_size, value)` tuples in bit order.
Access: `unit.state._unknown_controls[0][2]` → presence, `[1][2]` → lux.

This is the most fragile bypass in the codebase — it accesses a private implementation
detail of the library that could change without notice.

**Candidate for library improvement (high priority):** Add DALI-2 sensor type decoding
to `casambi-bt`. The library should expose `unit.state.presence` and
`unit.state.daylight_lux` (or similar) for DALI Sensor units, derived from the
already-decoded `_unknown_controls` bit fields.

---

### 2.6 Switch sensor improvements (`switch_sensor.py`, `switch_config_sensor.py`)

**What it does:** Detects EnOcean PTM215B kinetic switches and exposes button events
as HA events (`casambi_bt_switch_event`).

**Discriminator — `_is_switch_unit(unit)`:**
```python
"Kinetic" in mode  → True   (EnOcean kinetic switch)
mode == "Sensor"   → False  (BT repeater, explicitly excluded)
model name / manufacturer keywords → fallback
```
The `mode == "Sensor"` exclusion was added to prevent Winsol BT repeaters (which have
only UNKNOWN controls) from being misclassified as switches.

**Switch event filtering revert:** An earlier version filtered BLE events to only
those matching known button indices. This was reverted (`97b4b8c`) — all BLE events
are now passed unconditionally to allow the library to handle deduplication.

**Library usage:** Uses `casa.registerUnitChangedHandler`. No bypass — the library
delivers switch state changes correctly for kinetic switches.

---

### 2.7 Light platform discriminator fix (`light.py`)

**What it does:** Prevents EXT/1ch/Dim luminaires (Occhio Mito) from being excluded
from the light platform.

**Fix:** Changed from `mode.startswith("EXT/1ch/Dim")` (mode-only check, excludes all
EXT/1ch/Dim units including luminaires) to `_is_cover_unit(u)` (same discriminator as
`cover.py`, which also checks for light-specific controls). Luminaires with TEMPERATURE
or VERTICAL are now correctly kept on the light platform.

---

## 3. Library Bypass Summary

| Feature | Bypass type | Private API used | Library improvement needed |
|---------|-------------|-----------------|---------------------------|
| White Color Balance | Raw byte r/w | `unit.state.raw_state` (byte array) | `setWhiteColorBalance(unit, value)` |
| Sensor Platform V4 | Raw byte decode | `unit.state.raw_state` | Decode SENSOR control type into typed sub-values |
| DALI-2 presence + lux | Private attribute | `unit.state._unknown_controls` | Add DALI Sensor state decoding with typed fields |

All three bypasses access `unit.state` internals. The DALI-2 one is highest risk
because it uses a name-mangled private attribute (`_unknown_controls`).

---

## 4. Casambi Library Version Notes

- **Our fork uses:** `casambi-bt-revamped==0.4.2.dev5` (rankjie's fork of the library)
- **lkempf:dev uses:** `casambi-bt==0.4.0b2` (lkempf's upstream library)

These are **different forks** of the same library. Before rebasing on lkempf, the
library version and API compatibility must be checked for all features above.
Key question: does lkempf's `0.4.0b2` expose `_unknown_controls` in the same structure
as `0.4.2.dev5`?

---

## 5. Unit Type Mode Reference

Quick reference for discriminating devices by `unit.unitType.mode`:

| Mode pattern | Device type | Action |
|--------------|-------------|--------|
| `EXT/1ch/Dim` + DIMMER, no light controls | Motor-driven blind | → `cover` |
| `EXT/1ch/Dim` + DIMMER + TEMPERATURE/VERTICAL | Luminaire (Occhio) | → `light` |
| `EXT/Elements{...}` + SENSOR, no DIMMER | Sensor Platform V4 | → `sensor`/`binary_sensor` |
| `DALI Sensor` | DALI-2 combined sensor | → `sensor`/`binary_sensor` |
| `Kinetic Switch` | EnOcean PTM215B | → switch event sensor |
| `Sensor` (exact) | BT Repeater | → ignored |
| `PWM/*` | Standard luminaire | → `light` |
