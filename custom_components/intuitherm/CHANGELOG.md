# Changelog

All notable changes to the intuiHEMS Home Assistant integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2026.10.07.2] - 2026-10-07

### Changed
- Options: the "Separate metering" section is now labelled with the general term **cascaded meters** (German: **Zählerkaskade**) instead of "Messkonzept 8.3", which is the name used by one grid operator only

## [2026.10.07.1] - 2026-10-07

### Fixed
- **Self-Use Guard and Force Charge tracker didn't resume after a restart or options save**
  - After a Home Assistant restart, an integration reload or saving the options during a quarter hour, the guard (or tracker) stayed off until the next quarter hour, because the freshly fetched plan no longer contained the current one
  - The integration now remembers the plan entry it is executing and resumes it immediately

## [2026.10.06.3] - 2026-10-06

### Added
- **Separate metering: house load reported without the heat pump**
  - New optional field "Controllable load: energy counter" in the "Separate metering" options section (e.g. the Shelly's total energy)
  - When set, the house load sent to intuiHEMS excludes the heat pump, so the optimiser plans the battery for the household only
  - No jump when switching on or off; heat pump energy is kept across restarts and meter outages; the 7-day backfill at startup is corrected the same way
  - Diagnostic attribute `household_load_subtracted_kwh` on the Self-Use Guard sensor

## [2026.10.06.2] - 2026-10-06

### Fixed
- **FoxESS (foxess_modbus): Force Charge charged with all PV on top of the planned power**
  - foxess_modbus treats the Force Charge power as grid import and puts all PV into the battery on top, while the house and an EV are supplied from the grid
  - During a planned Force Charge the battery now charges at the planned power: the integration steers the inverter's output via foxess_modbus remote control (Force Charge when PV is below the plan, Force Discharge with the PV surplus otherwise)
  - PV beyond the plan covers the house first, then the battery; nothing is exported while the battery can charge. Above the configured maximum battery power, surplus is exported rather than curtailed
  - With a full battery (SoC ≥ 99 %), native Self Use takes over for the rest of the quarter hour
  - The required FoxESS entities are detected automatically; if one is missing, Force Charge works as before

### Added
- Diagnostic sensor "Force Charge Tracker" (FoxESS via foxess_modbus)

## [2026.10.06.1] - 2026-10-06

### Fixed
- **Self-Use Guard and fast-switching household appliances**
  - An appliance switching on and off faster than the guard's ~30 s control loop (e.g. a hob cycling about once a minute) made the battery push power to the heat pump in the appliance's off-phases, and could end Force Discharge via `z1_exporting`
  - Setpoint increases are now capped at the household base load of the last 60 s; reductions stay immediate. Sustained load increases are followed after about 60 s
- **False grid CT plausibility warning** with fast-switching loads: the check now only counts steady moments

## [2026.10.05.1] - 2026-10-05

### Fixed
- **Self-Use Guard entered Force Discharge without a running heat pump**
  - At full battery with PV surplus, or after a short overshoot at heat pump standby, the guard could enter and leave Force Discharge repeatedly (in one field test, 19 of 32 entries)
  - Entry now also requires the controllable load to draw at least 0.2 kW and the main meter (Z1) not to export
- **Self-Use Guard left Force Discharge while the household meter was balanced at 0 W**
  - Unchanged real-time meter values were mistaken for stale data
  - Freshness is now judged by when the sensor was last reported, not when its value last changed

### Added
- **Power sensor as controllable-load signal:** the "controllable load" field now also accepts a power sensor (e.g. a Shelly meter on the heat pump); running means at least 0.2 kW. Faster exits than with a binary indicator.
- **Immediate resume:** after a restart or reload, the guard starts right away when the current plan is Self Use
- **Grid CT plausibility check:** a warning in the log and `grid_ct_plausible: false` on the diagnostic sensor when the selected grid CT sensors can't be right (e.g. import-only "Grid Consumption" sensors)

## [2026.10.03.1] - 2026-10-03

### Added
- **Self-Use Guard (experimental)** for a controllable load such as a heat pump that is metered on its own electricity contract (German Messkonzept 8.3: household meter Z2 behind the main meter Z1, heat pump in between)
  - While the plan is Self Use, the battery covers only the household, never the heat pump
  - Steers the household meter Z2 (real-time readout, e.g. Tibber Pulse) to zero by switching the inverter to Force Discharge and adjusting its setpoint; returns to native Self Use when the heat pump is off, the house exports, SoC reaches min SoC, or data is unavailable
  - PV surplus goes to the heat pump at or above a configurable SoC (default 66 %) and charges the battery below it
  - Configured in a new collapsed options section "Separate metering contract (Messkonzept 8.3)"; off unless the Z2 import sensor is set
  - New diagnostic sensor "Self-Use Guard" (state: off / watching / guarding)
  - Requires a FoxESS inverter via foxess_modbus; three-phase grid CT sensors are summed
  - Respects Demo Mode: logs what it would do without writing

### Changed
- **Minimum Home Assistant version is now 2024.7** (needed for collapsible options sections)

## [2026.09.24.2] - 2026-09-24

### Fixed
- **Options Flow Showed "Your User ID: unknown"**
  - `CONF_USER_ID` is stored nested inside `entry.data[CONF_DETECTED_ENTITIES]`, never as a top-level key
  - The options flow read it off the flat merged `current_config` dict, which never has a top-level `CONF_USER_ID`, so it always fell back to `"unknown"`
  - Fixed to read from the already-available `detected_entities` dict instead

### Added
- **Installed Version shown in options flow**, below the user ID, sourced from `manifest.json` via `const.VERSION` — makes it easy to confirm an update actually landed on a given HA instance

## [2026.09.24.1] - 2026-09-24

### Fixed
- **Demo Mode Switch Not Persisting Across HA Restarts**
  - `IntuiThermDemoModeSwitch` pulled `detected_entities` out of the merged config without copying it, then mutated that dict in place before calling `async_update_entry()`
  - Since the dict was the same object already referenced by `entry.options`, HA's old-vs-new equality check saw no difference and never scheduled a save to `.storage/core.config_entries`
  - The switch looked correct in the UI (it reads live from the same mutated dict) but reverted to its last saved value on every HA restart
  - Fix: build a fresh copy of `detected_entities` before mutating it, so the change is actually persisted to disk

### Removed
- **Master Switch** (`switch.intuitherm_master_switch`)
  - Demo Mode is now the primary user-facing control from Home Assistant
  - Automatic control status remains visible read-only via `sensor.optimization_status`

## [2026.04.07.2] - 2026-04-07

### Added
- **Savings Sensor Tooltip Descriptions**
  - All three savings sensors now expose a `description` attribute explaining the formula and limitations
  - `sensor.savings_today`: description + live pool breakdown notes showing current kWh, % split, and avg grid cost
  - `sensor.pv_savings_today`: explains feed-in price subtraction and battery-only limitation (direct solar-to-load not counted)
  - `sensor.arbitrage_savings_today`: explains buy-cheap-use-expensive logic and that negative spreads are clamped to zero

### Fixed
- **Savings Not Accumulating — actual_power Always None**
  - FoxESS inverters expose separate `sensor.battery_charge` and `sensor.battery_discharge` sensors (kW) but no combined net power sensor
  - `battery_control.py` was reading `sensor.battery_power` (unavailable on FoxESS), resulting in `actual_power=None` on every feedback call
  - Fix: derive net power as `charge_kW − discharge_kW` when the net sensor is unavailable (positive = charging, negative = discharging)
  - Fix: savings state is always created and SOC recalibration always runs even when power reading is missing (removed premature early return)

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
