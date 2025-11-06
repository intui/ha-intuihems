# intuiHEMS Battery Optimizer for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub Release](https://img.shields.io/github/release/intui/intuitherm.svg)](https://github.com/intui/intuitherm/releases)
[![License](https://img.shields.io/github/license/intui/intuitherm.svg)](LICENSE)

**Intelligent home battery optimization using Model Predictive Control (MPC) and machine learning forecasting.**

## Features

- 🧠 **AI-Powered Optimization** - Model Predictive Control with ML-based consumption and solar forecasting
- 💰 **Maximize Savings** - Optimizes battery charging/discharging based on dynamic electricity prices
- ☁️ **Cloud-Based Compute** - Works on any Home Assistant hardware (even Raspberry Pi Zero)
- 🔒 **Privacy-First** - GDPR compliant with data export and deletion capabilities
- 🆓 **Alpha Testing** - Free during alpha phase (up to 100 users)
- ⚡ **Pull-Based Control** - Works behind NAT/firewall with local execution
- 🌍 **Multi-Source Pricing** - Supports Tibber API or EPEX Spot prices (8 European zones)

## What is intuiHEMS?

intuiHEMS (Intelligent Home Energy Management System) is a Home Assistant integration that automatically optimizes your battery storage system to minimize electricity costs. It uses:

1. **Model Predictive Control (MPC)** - Optimization algorithm that plans 24 hours ahead
2. **Machine Learning Forecasts** - Predicts household consumption and solar production
3. **Dynamic Pricing** - Integrates with Tibber or EPEX Spot day-ahead prices
4. **Cloud Processing** - Heavy computation runs in the cloud, HA executes locally

## How It Works

```
┌─────────────────────────────────────────────────────────┐
│  Home Assistant                                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │ intuiHEMS Integration                             │  │
│  │ • Reads: Battery SOC, House Load, Solar Power     │  │
│  │ • Sends data to cloud every 15 minutes            │  │
│  │ • Fetches 24h control plan from cloud             │  │
│  │ • Executes: Battery mode changes (Force Charge,   │  │
│  │            Self Use, etc.)                         │  │
│  └───────────────────────────────────────────────────┘  │
│         ▲                                  │             │
│         │ reads                            │ controls    │
│         │                                  ▼             │
│  ┌──────────────┐              ┌──────────────────┐     │
│  │ Battery SOC  │              │ Battery Control  │     │
│  │ House Load   │              │ (FoxESS, etc.)   │     │
│  │ Solar Power  │              │                  │     │
│  └──────────────┘              └──────────────────┘     │
└─────────────────────────────────────────────────────────┘
                    │ HTTPS (15 min)
                    ▼
         ┌──────────────────────────┐
         │ intuiHEMS Cloud Service  │
         │ • MPC Optimization       │
         │ • ML Forecasting         │
         │ • Price Fetching         │
         │ • Multi-Tenant SaaS      │
         └──────────────────────────┘
```

## Requirements

### Hardware
- Home Assistant 2024.4.0 or later
- Battery storage system with:
  - State of Charge (SOC) sensor (%)
  - Control entities (battery mode, charge/discharge power)
  - Supported inverters: FoxESS, SolarEdge, Fronius, etc.

### Pricing
- **Option 1:** Tibber account with API token (recommended)
- **Option 2:** EPEX Spot prices via ENTSO-E (free, supports 8 EU zones)

### Network
- Internet connection required (cloud-based optimization)
- Works behind NAT/firewall (pull-based control)

## Installation

### Via HACS (Recommended)

1. Open **HACS** in Home Assistant
2. Go to **Integrations**
3. Click the **⋮** menu → **Custom repositories**
4. Add repository: `https://github.com/intui/intuitherm`
5. Category: **Integration**
6. Click **Add**
7. Search for **intuiHEMS Battery Optimizer**
8. Click **Download**
9. **Restart Home Assistant**

### Manual Installation

1. Copy the `custom_components/intuitherm` directory to your Home Assistant `config/custom_components/` folder
2. Restart Home Assistant

## Configuration

### Step 1: Add Integration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for **intuiHEMS**
4. Follow the configuration wizard

### Step 2: Configuration Wizard

The integration uses automatic registration - no manual API key needed!

**Part 1: Connection Setup**
- API URL: `https://api.intuihems.io` (default)
- Registration happens automatically

**Part 2: Battery Sensors**
- Select your battery SOC sensor
- Select house load sensor (power in kW)
- Optional: Solar power sensor

**Part 3: Battery Configuration**
- Battery capacity (kWh)
- Maximum charge/discharge power (kW)
- Minimum/Maximum SOC limits (%)

**Part 4: Pricing Configuration**
- Choose pricing source:
  - **Tibber**: Enter your Tibber API token
  - **EPEX Spot**: Set your electricity markup (default 5 cents/kWh)
- Set feed-in tariff (EUR/kWh)

**Part 5: Control Entities**
- Select battery mode entity (e.g., `select.battery_mode`)
- Select charge/discharge power entities

### Step 3: Verification

After setup, you should see:
- ✅ Sensors: `sensor.intuihems_*` (battery SOC, next action, daily savings, etc.)
- ✅ Switch: `switch.intuihems_optimization_enabled`
- ✅ Data flowing to cloud every 15 minutes
- ✅ First control decision within 24 hours (after first MPC run)

## Entities Created

### Sensors (Read-Only)

| Entity | Description | Unit |
|--------|-------------|------|
| `sensor.intuihems_battery_soc` | Current battery state of charge | % |
| `sensor.intuihems_next_action` | Next battery control action | - |
| `sensor.intuihems_next_action_reason` | Explanation for next action | - |
| `sensor.intuihems_daily_cost` | Today's electricity cost | EUR |
| `sensor.intuihems_daily_savings` | Today's savings vs. baseline | EUR |
| `sensor.intuihems_monthly_savings` | Monthly savings estimate | EUR |
| `sensor.intuihems_consumption_forecast` | 24h consumption forecast | - |
| `sensor.intuihems_solar_forecast` | 24h solar forecast | - |
| `sensor.intuihems_price_forecast` | 24h price forecast | - |

### Controls

| Entity | Description |
|--------|-------------|
| `switch.intuihems_optimization_enabled` | Enable/disable automatic optimization |

### Services

| Service | Description |
|---------|-------------|
| `intuihems.refresh_data` | Force immediate data sync with cloud |
| `intuihems.run_optimization` | Manually trigger MPC optimization |

## Alpha Testing Program

### What to Expect

**Status:** Alpha (v0.1.0)
- ✅ Core functionality working
- ✅ Automated registration and setup
- ⚠️ Limited to 100 alpha testers
- ⚠️ May have bugs - please report!

### How to Report Issues

1. Check existing [GitHub Issues](https://github.com/intui/intuitherm/issues)
2. Create new issue with:
   - Home Assistant version
   - Integration version
   - Battery/inverter model
   - Detailed description of problem
   - Relevant logs from `Settings → System → Logs`

### Alpha User Limit

The cloud service currently supports **100 alpha users**. To check availability:

```bash
curl https://api.intuihems.io/api/v1/auth/status
```

Response:
```json
{
  "status": "accepting_users",
  "current_users": 45,
  "max_users": 100,
  "alpha_phase": true
}
```

## Privacy & GDPR

### Data Collection

intuiHEMS collects:
- Battery state of charge (every 15 minutes)
- House energy consumption
- Solar power production
- Battery control actions executed
- Electricity prices (from Tibber or EPEX Spot)

### Data Usage

Your data is used for:
- MPC optimization (battery charge/discharge planning)
- ML forecasting (consumption and solar prediction)
- Historical analytics and savings calculation

### Your Rights (GDPR)

| Right | How to Exercise |
|-------|-----------------|
| **Access** (Article 15) | Settings → intuiHEMS → Export Data |
| **Rectification** (Article 16) | Settings → intuiHEMS → Update Configuration |
| **Erasure** (Article 17) | Settings → intuiHEMS → Delete Account |
| **Data Portability** (Article 20) | Settings → intuiHEMS → Export Data (JSON) |

Data is **never shared** with third parties. Data retention: 30 days (configurable).

### Privacy Policy

Full privacy policy: https://api.intuihems.io/api/v1/gdpr/privacy

## Troubleshooting

### Integration Not Appearing

1. Check HACS logs: `Settings → System → Logs`
2. Verify `custom_components/intuitherm` exists
3. Restart Home Assistant

### API Connection Failed

1. Check internet connection
2. Verify cloud service status: https://api.intuihems.io/health
3. Check Home Assistant logs for authentication errors

### No Control Actions

1. Wait 24 hours for first MPC run
2. Check cloud service received data:
   - Settings → intuiHEMS → Diagnostics
3. Verify battery configuration is complete
4. Check optimization is enabled: `switch.intuihems_optimization_enabled`

### Battery Not Responding

1. Verify control entities are correct:
   - Settings → Devices & Services → intuiHEMS → Configure
2. Check entity states in Developer Tools
3. Test manual control via Home Assistant UI

## Supported Inverters

intuiHEMS has been tested with:
- ✅ FoxESS (H3, H1 series) via [foxess-modbus](https://github.com/nathanmarlor/foxess_modbus)
- 🔄 SolarEdge (community testing)
- 🔄 Fronius (community testing)
- 🔄 Other inverters with standard HA entities

**Note:** Any battery system with SOC sensor and control entities should work. Please report compatibility!

## Technical Details

### Architecture

- **Cloud Service:** FastAPI (Python), TimescaleDB, Docker
- **MPC Solver:** CVXPY with OSQP backend
- **Forecasting:** Scikit-learn (historical average + weather-enhanced hybrid)
- **Pricing:** Tibber API or ENTSO-E EPEX Spot
- **Communication:** HTTPS REST API (pull-based control)

### Update Frequency

| Task | Frequency |
|------|-----------|
| Sensor data upload | Every 15 minutes |
| Price fetching | Every hour |
| Consumption/solar forecasts | Every 2 hours |
| MPC optimization | Every 15 minutes |
| Control plan fetch | Daily at 00:05 |
| Control execution | :00, :15, :30, :45 minutes |

### Data Storage

- **Local:** Configuration only (API key, entity IDs)
- **Cloud:** Sensor readings (30 days), forecasts, MPC results

## Development

### Local Development

```bash
# Clone repository
git clone https://github.com/intui/intuitherm.git
cd intuitherm

# Create development environment
python3 -m venv venv
source venv/bin/activate
pip install -e .

# Run tests
pytest tests/
```

### Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create feature branch
3. Add tests
4. Submit pull request

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## Roadmap

### v0.2.0 (Beta)
- [ ] Increased user limit (1,000 users)
- [ ] Advanced ML forecasting (weather integration)
- [ ] Multi-battery support
- [ ] Email notifications

### v1.0.0 (Stable)
- [ ] Local compute mode (optional offline operation)
- [ ] Fleet optimization (cross-user insights)
- [ ] Mobile app
- [ ] Subscription plans

### v2.0.0 (Future)
- [ ] Energy community trading
- [ ] Vehicle-to-Grid (V2G) support
- [ ] Commercial deployment features

## Support the Project

intuiHEMS is **free during alpha testing**. If it saves you money, please consider donating to support development:

- [GitHub Sponsors](https://github.com/sponsors/intui)
- Bitcoin: `bc1q...` (coming soon)

**Suggested donation:** 20% of monthly electricity savings

## License

This project is licensed under the BSD-3-Clause License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- Based on research by TNO (Netherlands Organization for Applied Scientific Research)
- Built with [Neuromancer](https://github.com/pnnl/neuromancer) framework (PNNL)
- Inspired by Model Predictive Control research in building energy management

## Links

- **Documentation:** https://github.com/intui/intuitherm
- **Issues:** https://github.com/intui/intuitherm/issues
- **Discussions:** https://github.com/intui/intuitherm/discussions
- **Cloud Service:** https://api.intuihems.io
- **Privacy Policy:** https://api.intuihems.io/api/v1/gdpr/privacy

---

**Made with ❤️ for the Home Assistant community**
