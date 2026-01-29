# Changelog

All notable changes to the intuiHEMS Home Assistant integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
