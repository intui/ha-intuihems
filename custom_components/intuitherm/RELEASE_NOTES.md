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

