# intuiHEMS Release Notes

## v2026.02.06.1 - Battery Power Monitoring & SolarEdge Refinements

**Released:** February 6, 2026

### What's New

#### 🔋 Battery Power Sensor Support
You can now configure a battery power sensor for real-time monitoring. The integration will:
- Auto-detect battery power sensors during setup
- Use the sensor for execution feedback to improve optimization accuracy
- Fall back to `sensor.battery_power` if not explicitly configured

**How to configure:** Go to Settings → Devices & Services → intuiHEMS → Configure, then select your battery power sensor from the dropdown.

#### ⚡ Improved SolarEdge Control Precision
SolarEdge inverters require power limits in 100W increments. This release ensures all power commands are properly rounded:
- New conversion function rounds to nearest 100W
- More accurate battery charge/discharge control
- Better logging shows exact Watt values sent to inverter

#### 🌐 Localized SolarEdge Mode Names
SolarEdge users with non-English HA installations can now use localized mode names:
- Integration respects your configured mode names from setup
- Example: Use "Maximaler Eigenverbrauch" instead of "Maximize Self Consumption"
- No more mode name conflicts!

### Bug Fixes
- Removed arbitrary 50kW power limit in generic battery control that could reject valid commands
- Now properly validates against your configured battery max power

### Upgrade Instructions
1. Update the integration via HACS or manually replace files
2. Restart Home Assistant
3. *(Optional)* Reconfigure to add battery power sensor: Settings → Devices & Services → intuiHEMS → Configure

### Technical Changes
- Added `CONF_BATTERY_POWER_ENTITY` configuration key
- New `kw_to_watts_rounded100()` helper function for SolarEdge
- Enhanced logging with `is_solaredge` detection and Watts display
- 4 files modified: `battery_control.py`, `config_flow.py`, `const.py`, `__init__.py`

---

## v2025.12.22.3

## 🐛 Critical Fix: 15-Minute Execution Timing Bug

This release fixes a critical timing issue where battery controls were executing 15 minutes late, causing missed optimization opportunities and higher energy costs.

### The Problem

- **Battery charged at wrong times**: If MPC calculated optimal charge at 10:45, battery would charge at 11:00 instead
- **Root cause**: MPC ran at quarter hours (10:45) and generated controls starting at 10:45, but by the time executor fetched them, 10:45 had passed
- **Result**: Executor would skip to next control (11:00), missing the optimal window

### The Fix

Three coordinated changes across backend and Home Assistant integration:

1. **Backend MPC Scheduler** (energy-management-service):
   - Now runs **3 minutes BEFORE** quarter hours (:42, :57, :12, :27)
   - Generates controls for the NEXT quarter hour (not current)
   - Example: MPC at 10:42 generates controls starting at 10:45

2. **Backend API** (control plan endpoint):
   - Includes controls from last 5 minutes (not just future)
   - Handles network latency and clock sync differences
   - Executor can now find controls even if fetched slightly after quarter hour

3. **HA Integration Executor**:
   - Triggers on-demand coordinator refresh before execution
   - Ensures fresh control plan data at execution time
   - Improved logging (DEBUG → INFO) for better visibility

### Impact

✅ Battery now charges/discharges at **exact optimal times** calculated by MPC  
✅ No more 15-minute delays that caused missed cheap electricity windows  
✅ Controls execute within 1 second of target time (:00, :15, :30, :45)

## 🚀 Major Feature: Automatic Battery Control

The integration now **automatically controls your battery** based on MPC optimization:

### Battery Control Executor

- Executes control decisions every 15 minutes (:00, :15, :30, :45)
- Supports three battery modes:
  - **Self Use**: Battery charges from solar, powers house loads
  - **Backup**: Battery reserved for backup power (no grid charging)
  - **Force Charge**: Active grid charging at specified power level
- Sends execution feedback to backend for closed-loop optimization
- Configurable mode mappings for different inverter brands

### Setup Configuration

Enhanced configuration flow with:
- **Battery control entity selection**: Choose work mode and charge current entities
- **Mode mapping**: Map MPC control actions to your inverter's mode names
- **Auto-detection**: Automatically finds FoxESS, SolarEdge, and other inverter entities
- **Validation**: Ensures all required entities are selected and valid

### Safety Features

- Respects battery SOC limits (min/max configured in backend)
- Allows operation even when battery is below minimum (prevents infeasibility)
- Proper unit handling: kW power setpoints converted to Amperes for FoxESS
- Only executes controls from the latest MPC run (prevents stale controls)

## 🔧 Major Improvements

### MPC Optimization

- **Grid export disabled**: Prevents unbounded optimization solutions
- **DCP-compliant constraints**: Ensures convex optimization problem
- **Solar opportunity cost**: Penalizes grid charging during solar surplus hours
- **Better handling of edge cases**: Works when battery SOC is below minimum

### Configuration UI

- **Simplified setup flow**: Removed confusing fields (update_interval, battery_discharge_power)
- **Better field descriptions**: Clear explanations for each configuration option
- **Reordered fields**: Energy sensors grouped together, battery control grouped together
- **Dropdown selectors**: All entity selections use consistent dropdown UI
- **Options flow**: Full reconfiguration without deleting/re-adding integration

### Sensor Data Collection

- **Fixed cumulative sensor handling**: Solar energy totals properly converted to power
- **Category-based queries**: Sensors queried by category instead of hardcoded IDs
- **Unit conversions**: Automatic W → kW conversion where needed
- **Outlier filtering**: Removes spurious solar spikes from data

### Timezone Handling

- **All displays in local time**: Next Control sensor shows local time (not UTC)
- **Proper timezone conversions**: Backend uses UTC, HA displays in local timezone
- **Aligned execution times**: Controls execute at exact quarter hours in user's timezone

## 📚 Documentation Updates

- **README_HA_INTEGRATION.md**: Complete installation and setup guide
- **English README.md**: HACS-ready documentation
- **Comprehensive field descriptions**: In-app help text for all configuration options
- **Architecture documentation**: System design and optimization details

## 🔐 Security & Privacy

- **Personalized setup flow**: Optional email opt-in for updates
- **Consent tracking**: Privacy preferences stored and respected
- **HTTPS by default**: All API communication encrypted
- **Bearer token authentication**: Secure API key handling

## 🐛 Bug Fixes

- Fixed duplicate control execution from multiple MPC runs
- Fixed control timestamp alignment (quarter-hour boundaries)
- Fixed database migration conflicts in production
- Fixed sensor validation warnings for non-entity config keys
- Fixed setup flow showing no fields when auto-detection fails
- Fixed spurious PV spike data corruption
- Fixed forecast queries missing user_id filter

## 📊 Technical Details

### Version History
- **v2025.12.22.3**: Control plan API 5-minute lookback fix
- **v2025.12.22.2**: Executor logging improvements
- **v2025.12.22.1**: MPC 3-minute lead time implementation
- **v2025.12.05.3**: Battery mode mapping in options flow
- **v2025.12.05.2**: Configuration UI improvements
- **v2025.12.05.1**: Battery control entity storage

### Backend Changes
- MPC runner: Configurable lead time (3 minutes before quarter hour)
- Control plan API: Time window includes last 5 minutes
- Database: Proper cascade deletes for control plans
- Forecast generation: Improved solar data handling

### Integration Changes
- Battery control executor: On-demand coordinator refresh
- Coordinator: 5-minute polling interval (was 1 minute)
- Config flow: Comprehensive validation and auto-detection
- Sensors: Better state handling and timezone display

## 🚀 Upgrade Instructions

### For Existing Installations

1. **Update integration** via HACS or manual git pull
2. **Restart Home Assistant**
3. **Battery control setup** (if not already configured):
   - Go to Settings → Devices & Services → intuiHEMS
   - Click "Configure"
   - Select battery control entities (work mode, charge current)
   - Map control modes to your inverter's mode names
   - Complete the flow

4. **Verify execution** (check logs):
   ```
   Settings → System → Logs → Filter: "intuitherm"
   Look for: "Successfully executed control: X"
   ```

### For New Installations

Just add the integration - all new features are enabled by default!

## ⚠️ Breaking Changes

None - all changes are backward compatible. Existing configurations will continue to work.

## 🎯 What's Next?

- **Adaptive MPC**: Learn from execution feedback to improve forecasts
- **Price forecasting**: Integrate dynamic electricity price predictions
- **Multi-battery support**: Optimize multiple battery systems
- **Advanced visualizations**: Real-time optimization dashboard

---

**Questions or Issues?**
- Documentation: https://github.com/intui/intuiHEMS
- Report bugs: https://github.com/intui/intuiHEMS/issues
- Discussion: https://github.com/intui/intuiHEMS/discussions

---

# Release Notes - v2025.11.13.1

## 🎉 Major Feature: Live Forecast Dashboard

This release adds **5 new forecast sensors** that enable real-time visualization of your system's next 24 hours!

### New Sensors

Each sensor provides 96 data points (15-minute intervals over 24 hours):

1. **Consumption Forecast** (`sensor.intuihems_consumption_forecast`)
   - Predicted house consumption in kW
   - Learn your daily patterns
   - See upcoming high-load periods

2. **Solar Forecast** (`sensor.intuihems_solar_forecast`)
   - Predicted solar production in kW
   - Based on historical patterns
   - Plan around solar availability

3. **Battery SoC Forecast** (`sensor.intuihems_battery_soc_forecast`)
   - Predicted battery charge level (%)
   - See when battery will charge/discharge
   - Understand MPC optimization strategy

4. **Grid Import Forecast** (`sensor.intuihems_grid_import_forecast`)
   - Predicted grid consumption in kW
   - See when you'll pull from grid
   - Correlate with price forecasts

5. **Grid Export Forecast** (`sensor.intuihems_grid_export_forecast`)
   - Predicted solar export to grid in kW
   - Understand surplus solar periods
   - Optimize feed-in revenue

### Dashboard Integration

Perfect for **ApexCharts card** - create stunning visualizations:

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: 24-Hour Energy Forecast
graph_span: 24h
now:
  show: true
  label: Now
series:
  - entity: sensor.intuihems_consumption_forecast
    name: House Load
    type: area
    color: '#E74C3C'
  - entity: sensor.intuihems_solar_forecast
    name: Solar
    type: area
    color: '#F39C12'
  - entity: sensor.intuihems_battery_soc_forecast
    name: Battery SoC
    type: line
    color: '#3498DB'
    yaxis_id: percentage
yaxis:
  - id: power
    decimals: 1
    apex_config:
      title:
        text: Power (kW)
  - id: percentage
    opposite: true
    decimals: 0
    apex_config:
      title:
        text: Battery (%)
```

See `docs/DASHBOARD_FORECAST_EXAMPLES.md` for more examples!

## 🔧 Setup Flow Improvements

### Battery Sensors Added

The sensor selection screen now includes:
- ✅ **Battery Charge** (energy going INTO battery)
- ✅ **Battery Discharge** (energy coming OUT of battery)

**Why this matters**: These sensors are essential for calculating your actual house consumption using the power balance equation:

```
House Load = Solar + Battery Discharge + Grid Import - Battery Charge - Grid Export
```

### All Dropdowns

All sensor selections now use consistent dropdown selectors for better UX.

## 🔐 HTTPS by Default

Service URL updated to `https://api.intuihems.de`:
- ✅ SSL/TLS encryption
- ✅ Professional domain
- ✅ Auto-renewed Let's Encrypt certificates
- ✅ Works even if server IP changes

## 📚 New Documentation

- **`HOUSE_LOAD_CALCULATION.md`**: Explains the power balance equation and why we need all 6 sensors
- Dashboard YAML examples with ApexCharts

## 🚀 Upgrade Instructions

### For New Installations

Just add the integration - it will use the new defaults automatically!

### For Existing Installations

1. **Re-configure to add battery sensors** (optional but recommended):
   - Go to Settings → Devices & Services → intuiHEMS
   - Click "Configure"
   - On "Review & Select Sensors", add:
     - Battery Charge sensor
     - Battery Discharge sensor
   - Complete the flow

2. **New forecast sensors appear automatically** - no action needed!

3. **Install ApexCharts card** (for dashboard visualizations):
   - Go to HACS → Frontend
   - Search for "ApexCharts Card"
   - Install and restart Home Assistant

4. **Add forecast dashboard**:
   - Copy YAML from `docs/DASHBOARD_FORECAST_EXAMPLES.md`
   - Create new dashboard view or add cards to existing

## 🐛 Fixes

- Production database migration chain repaired
- Traefik reverse proxy configured with SSL
- Service endpoints now use HTTPS domain

## 📊 What's Next?

The forecast sensors lay the groundwork for:
- **Real-time optimization feedback**: See how MPC adapts to changing conditions
- **Historical comparison**: Compare forecasts vs. actuals
- **Advanced analytics**: Track forecast accuracy over time
- **Smart notifications**: Alert when forecasts predict issues

---

**Questions or Issues?**
- Documentation: https://github.com/intui/intuiHEMS
- Report bugs: https://github.com/intui/intuiHEMS/issues
- Discussion: https://github.com/intui/intuiHEMS/discussions

# Release automation
