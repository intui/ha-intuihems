# intuiHEMS Alpha Testing Guide

Thank you for participating in the intuiHEMS alpha testing program! This guide will help you get started and provide valuable feedback.

## Alpha Program Overview

**Status:** Alpha v0.1.0
**Duration:** November 2025 - January 2026
**User Limit:** 100 alpha testers
**Cost:** FREE during alpha phase

## What to Expect

### Alpha Status Means:
- ✅ **Core functionality working** - MPC optimization, forecasting, control
- ✅ **Cloud service operational** - Multi-tenant SaaS with GDPR compliance
- ✅ **Production-ready backend** - Phase 1A complete and tested
- ⚠️ **Early stage integration** - May have UI rough edges
- ⚠️ **Limited documentation** - Help us improve it!
- ⚠️ **Potential bugs** - Please report what you find!

### You'll Help Us:
1. **Test compatibility** with different inverters/batteries
2. **Validate setup process** - Is it easy enough?
3. **Find bugs** - Integration, UI, cloud service issues
4. **Measure performance** - Does it actually save money?
5. **Improve documentation** - What's confusing?

## Prerequisites

### Hardware Requirements
- ✅ Home Assistant 2024.4.0 or later (HA OS, Container, Core, or Supervised)
- ✅ Battery storage system with State of Charge (SOC) sensor
- ✅ Battery control entities (work mode select, charge/discharge power)
- ✅ House load power sensor (or components to calculate it)
- ✅ Optional: Solar power sensor

### Confirmed Compatible Inverters
- **FoxESS** H3, H1 series (via [foxess-modbus](https://github.com/nathanmarlor/foxess_modbus))

### Help Us Test These:
- **SolarEdge** (via SolarEdge integration)
- **Fronius** (via Fronius Solar integration)
- **SMA** (via SMA Solar integration)
- **Huawei** (via Huawei Solar integration)
- **Other brands** - If you have SOC and control entities, it should work!

### Pricing Requirements
- **Option 1 (Recommended):** Tibber account with API token
- **Option 2:** EPEX Spot prices (free, supports 8 EU zones: DE_LU, DE_AT_LU, NL, BE, FR, AT, NO, DK)

### Network Requirements
- Internet connection (cloud-based optimization)
- No special firewall rules (uses standard HTTPS, pull-based)

## Installation Steps

### 1. Check Alpha Capacity

Before installing, verify slots are available:

```bash
curl https://api.intuihems.io/api/v1/auth/status
```

Expected response:
```json
{
  "status": "accepting_users",
  "current_users": 45,
  "max_users": 100,
  "alpha_phase": true
}
```

If `current_users >= max_users`, alpha is full. Join the [waitlist](https://github.com/intui/intuitherm/discussions).

### 2. Install via HACS (Recommended)

1. Open **HACS** in Home Assistant
2. Go to **Integrations**
3. Click **⋮** (three dots) → **Custom repositories**
4. Add repository URL: `https://github.com/intui/intuitherm`
5. Select category: **Integration**
6. Click **Add**
7. Find **intuiHEMS Battery Optimizer** in HACS
8. Click **Download**
9. **Restart Home Assistant**

### 3. Alternative: Manual Installation

```bash
# SSH into your Home Assistant
cd /config
mkdir -p custom_components
cd custom_components

# Clone or download the repository
git clone https://github.com/intui/intuitherm.git
cp -r intuitherm/custom_components/intuitherm .

# Restart Home Assistant
ha core restart
```

### 4. Configure Integration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for **intuiHEMS**
4. Follow the 5-step wizard:

#### Step 1: API Connection
- **API URL:** `https://api.intuihems.io` (default)
- Click **Submit**
- **Automatic registration** will generate your API key

#### Step 2: Entity Selection
- **Battery SOC Entity:** Select your battery state of charge sensor (must be in %)
- **House Load Entity:** Select your house power consumption sensor (must be in kW or W)
- **Solar Power Entity (Optional):** Select your solar production sensor

**Tip:** If you don't have a house load sensor, you can create one using a template sensor:

```yaml
# configuration.yaml
template:
  - sensor:
      - name: "House Load Power"
        unit_of_measurement: "kW"
        device_class: power
        state: >
          {{ (states('sensor.pv_power')|float(0)
              + states('sensor.grid_power')|float(0)
              + states('sensor.battery_power')|float(0)) | round(2) }}
```

#### Step 3: Battery Configuration
- **Battery Capacity (kWh):** Your battery's total capacity (e.g., 10.0)
- **Max Charge/Discharge Power (kW):** Maximum power rating (e.g., 3.0)
- **Min SOC (%):** Minimum state of charge (default: 10%)
- **Max SOC (%):** Maximum state of charge (default: 100%)

#### Step 4: Pricing Configuration
- **Pricing Source:** Choose between Tibber or EPEX Spot
  - **Tibber:** Enter your Tibber API token and home ID
  - **EPEX Spot:** Set your electricity markup (EUR/kWh, default: 0.05)
- **Feed-in Tariff (EUR/kWh):** What you get paid for solar export (e.g., 0.082)

**Getting Tibber API Token:**
1. Go to https://developer.tibber.com/
2. Sign in with your Tibber account
3. Create a token
4. Copy and paste into HA config flow

#### Step 5: Control Entities
- **Battery Mode Entity:** Select entity (usually `select.battery_mode` or similar)
- **Charge Power Entity:** Select entity that controls charge power
- **Discharge Power Entity (Optional):** Select if separate from charge power

### 5. Verify Installation

After completing setup:

1. **Check Integration:**
   - Settings → Devices & Services → intuiHEMS
   - Should show "Configured"

2. **Check Entities:**
   ```
   sensor.intuihems_battery_soc
   sensor.intuihems_next_action
   sensor.intuihems_next_action_reason
   sensor.intuihems_daily_cost
   sensor.intuihems_daily_savings
   sensor.intuihems_monthly_savings
   sensor.intuihems_consumption_forecast
   sensor.intuihems_solar_forecast
   sensor.intuihems_price_forecast
   switch.intuihems_optimization_enabled
   ```

3. **Check Logs:**
   - Settings → System → Logs
   - Filter by `intuihems`
   - Should see: "Sensor data uploaded successfully" every 15 minutes

4. **Check Cloud Service:**
   - Wait 15 minutes for first data upload
   - Check diagnostics: Settings → Devices & Services → intuiHEMS → Diagnostics

## What to Test

### Phase 1: Installation (Week 1)
- [ ] Installation via HACS succeeds
- [ ] Configuration wizard completes without errors
- [ ] All entities appear in Home Assistant
- [ ] No error logs related to intuiHEMS
- [ ] Sensor data uploads to cloud (check logs after 15 min)

### Phase 2: Data Collection (Week 1-2)
- [ ] Battery SOC sensor updates correctly
- [ ] House load sensor shows reasonable values
- [ ] Solar power sensor updates (if applicable)
- [ ] Sensor values appear in cloud diagnostics
- [ ] No authentication errors in logs

### Phase 3: Optimization (Week 2-3)
- [ ] First MPC run completes (after 24h of data)
- [ ] `sensor.intuihems_next_action` shows meaningful actions
- [ ] Battery mode changes automatically
- [ ] Charge/discharge power setpoints adjust
- [ ] Actions make sense given current prices

### Phase 4: Long-Term Testing (Week 3-4)
- [ ] System runs reliably for 1-2 weeks
- [ ] Savings estimate seems accurate
- [ ] Battery behavior is safe (respects SOC limits)
- [ ] No unexpected control actions
- [ ] Dashboard shows meaningful data

## How to Report Issues

### Before Reporting
1. Check [existing issues](https://github.com/intui/intuitherm/issues)
2. Check Home Assistant logs for errors
3. Verify internet connection to cloud service
4. Try reloading the integration: Settings → Devices & Services → intuiHEMS → ⋮ → Reload

### Creating an Issue

Go to https://github.com/intui/intuitherm/issues/new and include:

**Required Information:**
- **Home Assistant Version:** (e.g., 2024.11.1)
- **Integration Version:** (e.g., 0.1.0-alpha)
- **Installation Method:** HACS or Manual
- **Inverter/Battery Brand/Model:** (e.g., FoxESS H3-10.0-E)
- **Pricing Source:** Tibber or EPEX Spot

**Issue Description:**
- Clear description of the problem
- Expected behavior vs. actual behavior
- Steps to reproduce
- Relevant log entries (Settings → System → Logs, filter by `intuihems`)
- Screenshots if UI-related

**Example Issue:**
```
**Title:** Battery not charging during low price period

**Environment:**
- HA Version: 2024.11.1
- Integration: 0.1.0-alpha
- Inverter: FoxESS H3-10.0-E (foxess-modbus)
- Pricing: Tibber

**Description:**
Next action shows "Force Charge" with reason "Low price period", but
battery mode remains in "Self Use" and doesn't switch to "Force Charge".

**Logs:**
[Paste relevant log entries]

**Screenshots:**
[Screenshot of sensor.intuihems_next_action state]
```

### Bug Severity Levels

**🔴 Critical (Report Immediately):**
- Data loss or corruption
- Integration crashes Home Assistant
- Battery safety issues (SOC limits violated)
- Security/privacy issues

**🟡 High (Report Within 24h):**
- Control actions not executing
- Optimization not running
- API authentication failures
- Incorrect cost/savings calculations

**🟢 Medium (Report Within Week):**
- UI display issues
- Missing/incorrect documentation
- Feature requests
- Performance issues

**⚪ Low (No Rush):**
- Cosmetic issues
- Documentation typos
- Nice-to-have features

## Providing Feedback

We want to hear from you! Share feedback via:

### GitHub Discussions
- **General Feedback:** https://github.com/intui/intuitherm/discussions/categories/general
- **Feature Requests:** https://github.com/intui/intuitherm/discussions/categories/ideas
- **Show & Tell:** https://github.com/intui/intuitherm/discussions/categories/show-and-tell
- **Q&A:** https://github.com/intui/intuitherm/discussions/categories/q-a

### What We Want to Know

**Setup Experience:**
- How long did setup take?
- Was anything confusing?
- Did auto-detection work? (coming in v0.2.0)
- What documentation is missing?

**Performance:**
- How much are you saving? (EUR/month)
- Does optimization make sense?
- Any unexpected battery behavior?
- How's the reliability?

**Compatibility:**
- What inverter/battery are you using?
- Did all entities work correctly?
- Any integration conflicts?

**Feature Requests:**
- What features are most important to you?
- What's missing that would improve usability?

## Alpha Tester Benefits

### During Alpha
- ✅ **Free access** to full cloud service (normally planned as paid service)
- ✅ **Priority support** - Direct feedback channel to developers
- ✅ **Early access** to new features
- ✅ **Influence roadmap** - Your feedback shapes development

### After Alpha
- 🎁 **Lifetime discount** for alpha testers (50% off when pricing introduced)
- 🎁 **Recognition** in project credits
- 🎁 **Beta access** guaranteed

## Frequently Asked Questions

### How long does alpha testing last?
**Estimated:** 2-3 months (November 2025 - January 2026)

### What happens to my data after alpha?
Your data remains yours. You can:
- Continue using the service (free or paid, TBD)
- Export all your data (GDPR right)
- Delete your account and data

### Will the service remain free?
- **During alpha:** 100% free
- **After alpha:** Pricing TBD, but:
  - Free tier likely (limited features or data retention)
  - Paid tier for advanced features (~5-10 EUR/month)
  - **Alpha testers:** 50% lifetime discount

### Is my data safe?
Yes:
- ✅ GDPR compliant (EU data protection regulations)
- ✅ TLS/HTTPS encryption
- ✅ SHA-256 API key hashing
- ✅ Data isolation (multi-tenant)
- ✅ No third-party data sharing
- ✅ Right to export and delete

### Can I use this commercially?
Not during alpha. Alpha is for:
- ✅ Personal home use
- ✅ Testing and evaluation
- ❌ Commercial deployment
- ❌ Resale or sub-licensing

### What if I find a critical security issue?
**Do NOT post publicly!** Email: security@intuihems.io

We follow responsible disclosure:
1. Report privately
2. We investigate within 48h
3. Fix deployed within 7 days
4. Public disclosure after fix

## Support Channels

### Primary Support
- **GitHub Issues:** https://github.com/intui/intuitherm/issues
- **GitHub Discussions:** https://github.com/intui/intuitherm/discussions

### Emergency Contact
- **Security Issues:** security@intuihems.io
- **Privacy/GDPR:** privacy@intuihems.io

### Community
- **Home Assistant Community Forum:** (coming soon)
- **Discord Server:** (coming soon)

## Uninstalling (If Needed)

### Remove Integration
1. Settings → Devices & Services → intuiHEMS
2. Click **⋮** → **Delete**
3. Confirm deletion

### Delete Cloud Data (GDPR)
1. Before uninstalling: Settings → Devices & Services → intuiHEMS → **Export Data**
2. Settings → Devices & Services → intuiHEMS → **Delete Account**
3. Account will be deleted after 30-day grace period
4. Or immediate deletion: contact privacy@intuihems.io

### Remove from HACS
1. HACS → Integrations → intuiHEMS
2. Click **⋮** → **Remove**

## Thank You!

Your participation helps make intuiHEMS better for the entire Home Assistant community. We appreciate your time and feedback!

**Questions?** Open a [discussion](https://github.com/intui/intuitherm/discussions)

**Found a bug?** Create an [issue](https://github.com/intui/intuitherm/issues)

**Happy with it?** Share your experience in [Show & Tell](https://github.com/intui/intuitherm/discussions/categories/show-and-tell)

---

**Last Updated:** 2025-11-06
**Alpha Version:** 0.1.0
**Alpha Testers:** 0 / 100
