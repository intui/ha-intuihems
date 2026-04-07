# Changelog

All notable changes to the intuiHEMS Home Assistant integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2026.04.07.1] - 2026-04-07

### Added
- **Battery Savings Tracking**
  - New two-pool cost-basis model tracks solar vs grid energy in the battery
  - On discharge, computes PV savings (free solar vs grid price) and arbitrage savings (bought cheap, used at peak) separately
  - Three new sensors:
    - `sensor.savings_today` — total estimated savings in EUR (PV + arbitrage)
    - `sensor.pv_savings_today` — savings from using stored solar energy instead of grid
    - `sensor.arbitrage_savings_today` — savings from smart charging timing
  - Main savings sensor exposes battery pool state as attributes (solar/grid kWh, avg grid cost)
  - Savings reset automatically at midnight UTC

### Backend (Cloud Service — no HA update required)
- **Savings Backend** *(deployed 2026-04-07)*
  - New `energy_savings_state` table: per-user cost-basis pools, daily savings accumulators
  - New `energy_savings_log` table: per-interval savings history for weekly/monthly roll-ups
  - Alembic migration 009
  - `update_savings()` service called from execution feedback handler every 15 min
  - API: `GET /api/v1/savings/today`, `GET /api/v1/savings/period?days=7`

### Technical Details
- HA files: `const.py`, `coordinator.py`, `sensor.py`, `manifest.json`
- Backend files: `models.py`, `savings_tracker.py` (new), `savings.py` (new), `control_plan.py`, `main.py`
- Backend migration: `alembic/versions/009_add_savings_tables.py`

## [2026.03.23.1] - 2026-03-23

### Added
- **Configurable Geo Location**
  - Installation latitude, longitude, and elevation are auto-detected from Home Assistant during initial setup
  - Location fields are editable in the options flow for manual correction
  - Location is synced to backend for weather-based solar forecasting accuracy
  - New constants: `CONF_LATITUDE`, `CONF_LONGITUDE`, `CONF_ELEVATION`

### Changed
- **Options Flow Simplified**
  - User ID removed from options screen (not user-facing information)
  - Options description updated with Location & Weather section

### Fixed
- **strings.json Invalid JSON**
  - Fixed mixed escaped/unescaped quotes throughout `strings.json` that made it unparseable
  - Fixed broken emoji character in options description

### Backend (Cloud Service — no HA update required)
- **Tibber API Resilience** *(deployed 2026-03-23)*
  - Increased Tibber API timeout from 10s to 30s to prevent `asyncio.TimeoutError`
  - Added retry logic on price fetch failure: retries at 5min, 10min, 20min, 40min intervals
    instead of sleeping 1h and waiting for next 13:00 CET cycle
  - Prevents 24h+ price data gaps from transient API failures
- **Location API**
  - `/api/v1/config` endpoint now accepts `latitude`, `longitude`, `elevation` fields
  - Updates active Installation record with new coordinates
  - Validation: lat [-90,90], lon [-180,180], elevation [0,9000]

### Technical Details
- Config flow stores location in entry data during `async_step_pricing`
- Options flow defaults to current config values, falls back to HA core location
- Files modified: `config_flow.py`, `const.py`, `strings.json`, `translations/en.json`, `translations/de.json`, `manifest.json`
- Backend files: `ha_integration.py` (+24), `tibber.py` (+1, -1), `epex_price_fetcher.py` (+14, -2)

## [2026.03.05.1] - 2026-03-05

### Fixed
- **Forecast sensor attributes exceeding HA Recorder 16 KB limit**
  - `sensor.consumption_forecast` and `sensor.solar_forecast` were embedding up to 3 days
    of historical readings (~11.5 KB each) in their state attributes on every coordinator
    poll, causing HA Recorder to refuse storing them and log repeated warnings.
  - Removed the `historical` key from both sensors' `extra_state_attributes`.
    HA already records the full state history natively — no duplication needed.
  - The `forecast` array (96 × 15-min steps, ~3.8 KB) is kept for ApexCharts dashboard cards.

### Backend (Cloud Service — no HA update required)
- **Cost-based MPC with grid export revenue** *(deployed 2026-03-02)*
  - Replaced the heuristic solar-penalty formulation with a proper cost-minimisation model.
  - Added `p_grid_export` decision variable and feed-in revenue term to the CVXPY objective:
    `minimize(import_cost − export_revenue + degradation)`
  - Equality power balance constraint: `solar + grid_import == load + p_bat + grid_export`
  - Feed-in price is now read per-user from `UserConfig.feed_in_price_eur_kwh` (default 0.082 EUR/kWh).
  - Improved mode derivation: `force_charge` only when grid imports exceed net house load.
  - Solver output now includes `import_cost`, `export_revenue`, `degradation_cost`,
    and full `grid_import`/`grid_export` profiles for diagnostics.

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
