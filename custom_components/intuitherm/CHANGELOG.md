# Changelog

All notable changes to the intuiHEMS Home Assistant integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2026.02.06.1] - 2026-02-06

### Changed
- **SolarEdge Power Conversion Precision**
  - New helper function `kw_to_watts_rounded100()` ensures power values are always rounded to nearest 100W
  - SolarEdge inverters require power limits in 100W increments - improves control accuracy
  - Applied consistently across all SolarEdge control commands (force_charge, self_use, backup)
  - Enhanced logging with detailed power values in Watts for better troubleshooting

### Added
- **Battery Power Sensor Configuration**
  - New config field `battery_power_entity` for real-time battery power monitoring
  - Auto-detection during setup searches device registry for battery power sensors
  - Used for execution feedback telemetry to backend
  - Improves closed-loop optimization accuracy
  
- **User-Configured Mode Names for SolarEdge**
  - SolarEdge command mode now uses user-configured mode mappings from setup
  - Respects custom mode names instead of hardcoded English strings
  - Example: Users can map to localized mode names like "Maximaler Eigenverbrauch"
  
- **Enhanced SolarEdge Logging**
  - Integration startup logs SolarEdge system detection
  - Control execution logs include command mode names and power values in Watts
  - Better visibility into what commands are sent to inverter

### Fixed
- **Generic Battery Control Power Clamping**
  - Removed arbitrary 50kW upper limit that could reject valid MPC power setpoints
  - Now properly validates against configured battery max power
  - Safety: Still enforces 0kW minimum

### Technical Details
- Power conversion formula: `int((abs(power_kw) * 1000 + 50) // 100 * 100)` rounds to nearest 100W
- Battery power sensor fallback: `sensor.battery_power` if not configured
- SolarEdge mode mapping: Uses `mode_self_use`, `mode_backup`, `mode_force_charge` from config
- Files modified: `battery_control.py` (+45, -23), `config_flow.py` (+28, -1), `const.py` (+1), `__init__.py` (+4)

## [2026.02.05.2] - 2026-02-05

### Added
- **SolarEdge Battery Control Support**
  - Auto-detects SolarEdge systems via multi-modbus command mode selector
  - Added `CONF_SOLAREDGE_COMMAND_MODE` constant for SolarEdge command mode selector entity

### Technical Details
- Detection: Looks for `select.command_mode` or similar entities during config flow
- Control mappings added to `DEVICE_CONTROL_MAPPINGS` in const.py
- Command modes: "Maximize Self Consumption" and "Charge from Solar Power and Grid"
- Power control: Uses number entities for charge/discharge limits (in Watts)
- Integrates seamlessly with existing MPC optimization system

## [2026.02.05.1] - 2026-02-05

### Changed
- **Config Flow & Options UI Improvements**
  - Fixed sensor labels: Changed "Solar Power (kW)" to "Solar Energy Total (kWh)" - these are cumulative energy sensors, not instantaneous power
  - Updated all translation files (EN, DE) and strings.json with consistent terminology
  - Added clear descriptions for all configuration fields

### Removed
- **Grid Export Price Field from UI**
  - Removed from configuration flow to avoid user confusion
  - Constant kept in const.py for future use
  - Currently unused by backend optimization

### Technical Details
- The integration uses cumulative energy sensors (kWh, total_increasing) for solar and house load
- Backend automatically calculates instantaneous power from energy readings
- Battery Max Power (kW) label remains correct as it represents charge/discharge rate

## [2026.01.30.1] - 2026-01-30

### Added
- **Display User ID in Options Screen**
  - Shows user ID prominently in the configuration options dialog
  - Format: "Your User ID: `{user_id}`" with info icon for saving

## [2026.01.29.4] - 2026-01-29

### Added
- **Automatic migration for existing Huawei installations**
  - Detects if ha_device_id is missing on startup (installations from before v2026.01.28.2)
  - Fixes: "No Huawei battery device ID found - cannot call forcible_charge service"

### Technical Details
- Migration runs in __init__.py during async_setup_entry
- Checks: is_huawei AND ha_device_id missing
- Looks up grid_charge_switch entity to find owning device
- Calls hass.config_entries.async_update_entry to persist ha_device_id
- No user action required - automatic on next HA restart or integration reload

## [2026.01.29.3] - 2026-01-29

### Fixed
- **CRITICAL: Fix KeyError 'device_id' in Huawei backup and self_use modes**
  - In v2026.01.28.2, renamed `device_id` key to `ha_device_id` for Huawei battery device
  - Error appeared as: "Error applying control backup: 'device_id'" at line 479/483

## [2026.01.29.2] - 2026-01-29

### Fixed
- **CRITICAL: Battery Control Executor Not Starting for Huawei Systems**
  - Root cause: Executor required `battery_charge_power` entity which Huawei systems don't have
  - **This was why battery didn't charge - the executor never started!**
- **Huawei Battery Charge Power: Use MPC-Calculated Optimal Power**
  - Now uses MPC-calculated `control.power_kw` (optimal power per 15-min period)
  - Example: MPC calculates 2.0kW → service receives "2000" watts
- **Improved Huawei Logging**: Changed critical logs from DEBUG to INFO level
  - Added try/except with exc_info for service call failures
  - Log device_id being used in forcible_charge call

### Technical Details
- `__init__.py` line 95: Changed startup check from `all([mode_select, charge_power])` to smart detection
- Now checks: `has_mode_select AND (is_huawei OR has_charge_power)`
- Huawei detection: Presence of `grid_charge_switch` entity
- Battery charge power: Uses `abs(power_kw) * 1000` from MPC control, clamped to 1-50kW
- Service call: `{"device_id": str, "duration": 16, "power": str(watts)}`
