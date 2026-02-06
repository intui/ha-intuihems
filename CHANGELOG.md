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
  - Implements three battery control modes for SolarEdge inverters:
    - **Force Charge**: Uses "Charge from Solar Power and Grid" mode with configurable charge limit (in Watts)
    - **Self Use**: Uses "Maximize Self Consumption" mode with peak shaving configuration
    - **Backup**: Uses backup/reserve mode to preserve battery for emergencies
  - Automatically configures charge/discharge power limits based on battery specifications
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
  - Fixed sensor labels: Changed "House Load (kW)" to "House Energy Consumption (kWh)" - same reason
  - Removed unused "Grid Export Price" field from pricing configuration (not currently used, was confusing)
  - Added comprehensive field descriptions explaining the purpose of each configuration option
  - Updated all translation files (EN, DE) and strings.json with consistent terminology

### Technical Details
- The integration uses cumulative energy sensors (kWh, total_increasing) for solar and house load
- Backend automatically calculates instantaneous power from energy readings
- Battery Max Power (kW) label remains correct as it represents charge/discharge rate
- Grid export price constant kept in const.py for future use but removed from UI

## [2026.01.30.1] - 2026-01-30

### Added
- **Display User ID in Options Screen**
  - Shows user ID prominently in the configuration options dialog
  - Helps users identify their ID for troubleshooting and support
  - Added to both English and German translations
  - Format: "Your User ID: `{user_id}`" with info icon for saving

## [2026.01.29.4] - 2026-01-29

### Added
- **Automatic migration for existing Huawei installations**
  - Detects if ha_device_id is missing on startup (installations from before v2026.01.28.2)
  - Automatically queries entity/device registry to find battery device ID
  - Updates config entry with ha_device_id without requiring reconfiguration
  - Logs migration success/failure for debugging
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
  - Updated force_charge mode but forgot to update backup and self_use modes
  - Both modes were still looking for old `device_id` key causing KeyError crash
  - Now all three modes (force_charge, self_use, backup) use `ha_device_id` consistently
  - Error appeared as: "Error applying control backup: 'device_id'" at line 479/483

## [2026.01.29.2] - 2026-01-29

### Fixed
- **CRITICAL: Battery Control Executor Not Starting for Huawei Systems**
  - Root cause: Executor required `battery_charge_power` entity which Huawei systems don't have
  - Huawei uses `forcible_charge` service instead of a charge power entity
  - Made `battery_charge_power` optional for Huawei (detected via `grid_charge_switch` presence)
  - Executor now starts for Huawei systems with only `battery_mode_select`
  - **This was why battery didn't charge - the executor never started!**
- **Huawei Battery Charge Power: Use MPC-Calculated Optimal Power**
  - Now uses MPC-calculated `control.power_kw` (optimal power per 15-min period)
  - Previously read from `battery_charge_power` entity (configured max power)
  - MPC dynamically optimizes power between 0 and configured max for each period
  - Power converted to watts and passed as string to `forcible_charge` service
  - Example: MPC calculates 2.0kW → service receives "2000" watts
- **Improved Huawei Logging**: Changed critical logs from DEBUG to INFO level
  - Added try/except with exc_info for service call failures
  - Added ✓/✗ indicators for success/failure visibility
  - Log device_id being used in forcible_charge call

### Technical Details
- `__init__.py` line 95: Changed startup check from `all([mode_select, charge_power])` to smart detection
- Now checks: `has_mode_select AND (is_huawei OR has_charge_power)`
- Huawei detection: Presence of `grid_charge_switch` entity
- Battery charge power: Uses `abs(power_kw) * 1000` from MPC control, clamped to 1-50kW
- Service call: `{"device_id": str, "duration": 16, "power": str(watts)}`

## [2026.01.29.1] - 2026-01-29

### Fixed
- **Huawei Battery Control Logging**: Changed forcible_charge service call logging from DEBUG to INFO level
  - Added explicit success/failure logging with ✓/✗ indicators
  - Added error handling with exc_info for better debugging
  - Log now shows device_id being used for forcible_charge service
  - This helps diagnose battery control issues when HA logs cannot be accessed

### Technical Details
- The Huawei forcible_charge service call was using `_LOGGER.debug()` which prevented visibility into execution
- Now uses `_LOGGER.info()` with try/except blocks to catch and log service call failures
- Critical for diagnosing why battery didn't charge overnight despite MPC generating force_charge controls

## [2026.01.28.2] - 2026-01-28

### Fixed
- **Huawei battery device ID detection**: Now correctly identifies battery device by looking up which device owns the `grid_charge_switch` entity, instead of using the inverter device ID. This fixes the "Not a valid 'Connected Energy Storage' device" error when calling `forcible_charge` service.
- **Config flow logging**: Changed false ERROR level logs to INFO during setup entry initialization
- **German translation**: Added missing `{user_name}` placeholder to welcome message title

### Changed
- Device ID detection now explicitly queries entity registry to find the actual battery device, ensuring correct device is passed to Huawei Solar `forcible_charge` service

## [Unreleased]

### Planned
- Advanced ML forecasting with weather data integration
- Multi-battery support per installation
- Local compute mode (optional offline operation)
- Email notifications for important events

## [2026.01.28.1] - 2026-01-28

### Fixed
- **Huawei Battery Control**: Implemented proper forcible charge procedure for Huawei Luna2000 batteries
  - Now uses `huawei_solar.forcible_charge` service instead of direct entity control
  - Follows 3-step procedure: service call → mode select → grid charge switch
  - Fixes issue where Huawei batteries received commands but didn't physically charge
  - Based on community-validated procedure from Huawei Solar users
  - 5-second delays between steps for reliable operation

### Changed
- **Battery Control Detection**: Enhanced entity detection for Huawei-specific controls
  - Auto-detects `grid_charge_switch` entity (Huawei only)
  - Auto-detects `device_id` for Huawei service calls
  - Detection is optional and backward compatible

### Compatibility
- ✅ **Fully backward compatible** - No impact on existing FoxESS, Solis, SolarEdge, or Growatt systems
- ✅ **Automatic detection** - Huawei systems identified by presence of grid charge switch
- ✅ **Dual-mode operation** - Huawei uses service calls, other brands use direct control

## [2026.01.13.1] - 2026-01-13

### Changed
- **Polling Interval**: Increased update interval from 5 minutes to 15 minutes
  - Reduces API calls and backend load
  - Better aligns with MPC optimization cycle
- **Time Alignment**: Updates now aligned to quarter-hour marks (:00, :15, :30, :45)
  - Ensures consistent timing across all installations
  - Improves data quality for time-series analysis
  - First update after restart aligns to next quarter-hour mark

## [2025.11.13.4] - 2025-11-13

### Added
- **Battery SOC Forecast Sensor**: New sensor showing predicted battery state of charge over 24 hours
  - 96 data points (15-minute intervals)
  - Shows mean forecast as state
  - Full forecast array in attributes
  - Now have 3 forecast sensors total: Consumption, Solar, Battery SOC

## [2025.11.13.3] - 2025-11-13

### Changed
- **Cleaner UI**: Removed "IntuiHEMS" prefix from all sensor and switch names
  - Sensors now show as "Battery SOC Forecast", "Solar Forecast", etc.
  - Already grouped under IntuiHEMS device, so prefix was redundant

## [2025.11.13.2] - 2025-11-13

### Changed
- **Branding Update**: Renamed all user-facing names from "IntuiTherm" to "IntuiHEMS"
  - Master Switch: "IntuiHEMS Master Switch"
  - All sensors now show "IntuiHEMS" prefix
  - Device name: "IntuiHEMS Battery Optimizer"

## [2025.11.13.1] - 2025-11-13

### Added
- **5 New Forecast Sensors**: Real-time visualization of 24-hour predictions
  - `sensor.intuihems_consumption_forecast` - House consumption forecast (kW)
  - `sensor.intuihems_solar_forecast` - Solar production forecast (kW)
  - `sensor.intuihems_battery_soc_forecast` - Battery state of charge forecast (%)
  - `sensor.intuihems_grid_import_forecast` - Predicted grid imports (kW)
  - `sensor.intuihems_grid_export_forecast` - Predicted grid exports (kW)
  - Each sensor provides 96 data points (15-min intervals, 24 hours)
  - Compatible with ApexCharts card for rich dashboard visualizations

- **Battery Charge/Discharge Sensors**: Added to setup flow
  - Battery charge sensor (energy going INTO battery)
  - Battery discharge sensor (energy coming OUT of battery)
  - Critical for accurate house load calculation
  - See `docs/HOUSE_LOAD_CALCULATION.md` for details

- **Documentation**:
  - `HOUSE_LOAD_CALCULATION.md` - Explains power balance equation and sensor requirements
  - Dashboard YAML examples for forecast visualization

### Changed
- **HTTPS Domain**: Default service URL changed from IP to `https://api.intuihems.de`
  - SSL/TLS encryption for all API communication
  - More reliable (survives server IP changes)
  - Professional domain with Let's Encrypt certificates

- **Improved Sensor Selection**: All sensors now use dropdown selectors
  - Consistent UX across all sensor selections
  - Battery charge/discharge now included in review screen
  - Custom entity ID entry option for all sensors

### Technical
- Backend deployed with Traefik reverse proxy
- SSL certificates auto-renewed via Let's Encrypt
- GitHub redirects configured (www.intuihems.de → repository)
- Migration chain fixed for production database

## [0.1.1] - 2025-11-06

### Added
- **Enhanced Energy Dashboard Integration**: Comprehensive sensor extraction during setup
  - Auto-detects ALL sensors from Energy Dashboard with availability status
  - Groups sensors by type: solar, battery discharge/charge, grid import/export
  - Detailed logging shows sensor status (✅ available / ❌ unavailable)
  - Foundation for upcoming multi-sensor support (multiple PV strings, batteries)

### Improved
- Better visibility during config flow setup process
- More detailed debug logging for troubleshooting

## [0.1.0-alpha] - 2025-11-06

### Added - Initial Alpha Release

#### Core Features
- **Automatic Registration**: Zero-click API key generation during setup
- **Multi-Tenant Cloud Service**: Secure, isolated data per user
- **Pull-Based Control Architecture**: Works behind NAT/firewall with local execution
- **Model Predictive Control (MPC)**: 24-hour optimization planning
- **ML Forecasting**: Consumption and solar production prediction
- **Multi-Source Pricing**:
  - Tibber API integration
  - EPEX Spot prices via ENTSO-E (8 European bidding zones)
- **GDPR Compliance**: Full data export and deletion capabilities

#### Home Assistant Integration
- **Config Flow**: 5-step wizard for easy setup
  - Automatic cloud registration
  - Entity selection for sensors (SOC, load, solar)
  - Battery configuration (capacity, power, SOC limits)
  - Pricing setup (Tibber or EPEX Spot)
  - Control entity mapping

- **Entities Created**:
  - 9 sensor entities (SOC, next action, costs, savings, forecasts)
  - 1 switch entity (optimization enable/disable)
  - 2 services (refresh data, run optimization)

- **Coordinator System**:
  - Sensor data coordinator (uploads to cloud every 15 min)
  - Control decision coordinator (fetches 24h plan)
  - Metrics coordinator (historical data and forecasts)

#### Cloud Backend
- **Multi-Tenancy**:
  - Isolated user data with `user_id` scoping
  - SHA-256 hashed API keys
  - Automatic user creation during registration
  - Alpha limit: 100 users max

- **API Endpoints**:
  - `POST /api/v1/auth/register` - User registration
  - `POST /api/v1/sensors/data` - Sensor data ingestion
  - `GET /api/v1/control/plan` - Fetch 24h control plan
  - `POST /api/v1/control/execution_feedback` - Report execution
  - `GET /api/v1/forecast/{type}` - Consumption/solar forecasts
  - `GET /api/v1/metrics` - Historical data and savings
  - `GET /api/v1/gdpr/export` - Data export (GDPR Article 20)
  - `POST /api/v1/gdpr/delete` - Account deletion (GDPR Article 17)
  - `GET /api/v1/gdpr/privacy` - Privacy policy

- **Background Tasks**:
  - Price fetcher: Runs every hour (Tibber or EPEX Spot)
  - Forecaster: Runs every 2 hours (per user)
  - MPC runner: Runs every 15 minutes (per user)

- **Database**:
  - TimescaleDB for time-series data
  - 30-day data retention (configurable per user)
  - Automatic data cleanup tasks
  - Multi-tenant schema with user isolation

#### Control System
- **Pull-Based Architecture**:
  - HA fetches 24h control plan daily at 00:05
  - Local execution at :00, :15, :30, :45 minutes
  - No incoming connections required (NAT-friendly)
  - 24-hour autonomy if cloud unavailable

- **Battery Actions**:
  - Force Charge (during low prices)
  - Self Use (normal operation)
  - Force Discharge (during high prices, if enabled)
  - Intelligent power setpoints

- **Safety Features**:
  - Respects min/max SOC limits
  - Validates battery capacity and power limits
  - Manual override capability
  - Optimization enable/disable switch

#### Testing & Quality
- Automated multi-tenancy isolation tests (100% passing)
- API authentication and data scoping verified
- GDPR export/delete functionality validated
- Staging environment with real HA instance tested
- FoxESS inverter compatibility confirmed

#### Documentation
- Comprehensive setup guide
- API documentation (FastAPI auto-generated)
- Privacy policy (GDPR-compliant)
- Pull-based control architecture guide
- HA instance tracking documentation
- Phase 1A implementation complete document

### Technical Details

#### Dependencies
- `aiohttp>=3.9.0` - HTTP client for cloud API
- Home Assistant 2024.4.0+ required

#### Supported Inverters (Confirmed)
- FoxESS H3, H1 series (via foxess-modbus integration)

#### Supported Inverters (Community Testing)
- SolarEdge
- Fronius
- Any inverter with standard HA entities (SOC, power sensors)

#### Known Limitations
- Internet connection required (cloud-based)
- Alpha user limit: 100 concurrent users
- Initial optimization requires 24h of data
- No local compute mode yet
- Single battery per installation

### Security
- SHA-256 API key hashing
- TLS/HTTPS encryption in transit
- Database encryption at rest
- Per-user data isolation
- GDPR-compliant data handling
- 30-day account deletion grace period

### Infrastructure
- Cloud service: FastAPI + TimescaleDB
- Deployment: Docker on Hetzner
- Database: PostgreSQL with TimescaleDB extension
- Authentication: Bearer token (SHA-256 hashed)
- Monitoring: Health checks and metrics endpoints

### Performance
- API response time: <2s (p95)
- MPC solve time: <30s per user
- Update frequency: 15 minutes
- Data retention: 30 days (configurable)

## Alpha Testing Notes

### What Works
✅ Automatic registration and API key generation
✅ Multi-tenant cloud service with data isolation
✅ Sensor data upload to cloud
✅ MPC optimization (24h planning)
✅ Control plan fetching and execution
✅ Tibber and EPEX Spot price integration
✅ GDPR data export and deletion
✅ Works behind NAT/firewall

### Known Issues
⚠️ First optimization requires 24h of data collection
⚠️ Limited to 100 alpha testers
⚠️ No email notifications yet
⚠️ Single battery per installation only
⚠️ Manual entity selection (auto-detection planned for v0.2.0)

### Help Wanted
- Testing on different inverter brands (SolarEdge, Fronius, etc.)
- Testing with different pricing providers
- Feedback on setup process
- Bug reports and feature requests

## [0.0.1] - 2025-11-05

### Development
- Initial repository setup
- Integration scaffolding created
- Basic entity structure implemented

---

## Versioning Scheme

- **Major.Minor.Patch** (e.g., 1.2.3)
- **Alpha releases**: `0.x.x-alpha`
- **Beta releases**: `0.x.x-beta`
- **Release candidates**: `x.x.x-rc.N`
- **Stable releases**: `x.x.x`

## Links

- [GitHub Repository](https://github.com/intui/intuitherm)
- [Issue Tracker](https://github.com/intui/intuitherm/issues)
- [Cloud Service](https://api.intuihems.io)
- [Privacy Policy](https://api.intuihems.io/api/v1/gdpr/privacy)
# Trigger workflow
