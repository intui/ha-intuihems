# IntuiTherm Home Assistant Integration - Implementation Guide

## Overview

This guide documents the implementation of the IntuiTherm Home Assistant custom integration that connects to the production energy-management-service running on Hetzner.

**Service URL**: `http://128.140.44.143:80`
**Authentication**: Bearer token (API key)
**Integration Type**: Local polling with API key authentication

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Home Assistant (Nabu Casa Cloud)                   │
│  ┌───────────────────────────────────────────────┐  │
│  │  custom_components/intuitherm/                │  │
│  │  ├── Config Flow (auto-detect entities)      │  │
│  │  ├── Coordinator (poll every 60s)            │  │
│  │  ├── Sensors (health, MPC, control status)   │  │
│  │  ├── Switches (enable/disable auto control)  │  │
│  │  └── Services (manual override)              │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
                        │
                        │ HTTPS (Bearer token)
                        │ Polling: 60s interval
                        ↓
┌─────────────────────────────────────────────────────┐
│  Hetzner CX23 (128.140.44.143:80)                   │
│  ┌───────────────────────────────────────────────┐  │
│  │  Energy Management Service (Docker)           │  │
│  │  ├── /api/v1/health         (GET)            │  │
│  │  ├── /api/v1/control/status (GET)            │  │
│  │  ├── /api/v1/metrics        (GET)            │  │
│  │  ├── /api/v1/control/override (POST)         │  │
│  │  ├── /api/v1/control/enable   (POST)         │  │
│  │  └── /api/v1/control/disable  (POST)         │  │
│  └───────────────────────────────────────────────┘  │
│                                                      │
│  Service continues to:                               │
│  - Poll HA sensors (battery SOC, solar, load)       │
│  - Run MPC optimization every 15 min                 │
│  - Execute battery control commands                  │
└──────────────────────────────────────────────────────┘
```

**Key Point**: The HA integration provides **monitoring and manual control**. The service continues to run autonomously (polling HA, running MPC, controlling battery).

---

## Phase 0: Service Authentication Setup

### Status: ✅ COMPLETED

**Files Modified:**
1. `app/api/dependencies.py` (NEW)
2. `app/core/config.py` (MODIFIED)
3. `docker-compose.yml` (MODIFIED)

### Deployment Steps for Hetzner:

1. **Add API key to `.env` file** on Hetzner server:
   ```bash
   ssh root@128.140.44.143
   cd /path/to/energy-management-service
   nano .env

   # Add this line:
   API_KEY=A6SJ7InZ0cjMMNEP7FS2YOqfr6JMvxZVwbKfPC-dYsk
   ```

2. **Rebuild and redeploy** Docker container:
   ```bash
   docker-compose down
   docker-compose build
   docker-compose up -d
   ```

3. **Verify authentication** works:
   ```bash
   # Without API key (should fail with 401)
   curl http://128.140.44.143:80/api/v1/health

   # With API key (should succeed)
   curl -H "Authorization: Bearer A6SJ7InZ0cjMMNEP7FS2YOqfr6JMvxZVwbKfPC-dYsk" \
        http://128.140.44.143:80/api/v1/health
   ```

4. **Optional: Add authentication to control endpoints**

   Currently control endpoints (`/api/v1/control/*`) are NOT protected. To secure them:

   **Edit `app/api/control.py`:**
   ```python
   from app.api.dependencies import verify_api_key
   from fastapi import Depends

   # Add to each endpoint:
   @router.post("/control/override")
   async def manual_override(
       request: ManualControlRequest,
       db: Session = Depends(get_db),
       authorized: bool = Depends(verify_api_key)  # ADD THIS LINE
   ):
       # ... rest of function
   ```

   **Endpoints to protect:**
   - `/api/v1/control/override`
   - `/api/v1/control/enable`
   - `/api/v1/control/disable`

---

## Phase 1: HA Integration Scaffolding

### Status: ✅ COMPLETED

**Files Created:**
1. `custom_components/intuitherm/manifest.json`
2. `custom_components/intuitherm/const.py`
3. `custom_components/intuitherm/__init__.py`

**Location**: `/home/wirsam/intui/intuitherm/custom_components/intuitherm/`

---

## Phase 2: Data Coordinator

### Status: 🔄 IN PROGRESS

**File to Create**: `coordinator.py` (~200 lines)

**Purpose**: Poll the Hetzner service every 60 seconds and fetch:
- Service health status
- Control system status
- MPC metrics

**Key Implementation Details:**

```python
class IntuiThermCoordinator(DataUpdateCoordinator):
    """Coordinate data fetching from IntuiTherm service."""

    def __init__(self, hass, session, service_url, api_key, update_interval):
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval)
        self.service_url = service_url.rstrip('/')
        self.api_key = api_key
        self.session = session
        self.headers = {"Authorization": f"Bearer {api_key}"}

    async def _async_update_data(self):
        """Fetch data from service."""
        try:
            async with asyncio.timeout(10):
                # Fetch all endpoints in parallel
                health, status, metrics = await asyncio.gather(
                    self._fetch_json("/api/v1/health"),
                    self._fetch_json("/api/v1/control/status"),
                    self._fetch_json("/api/v1/metrics?period_hours=1"),
                    return_exceptions=True
                )

            return {
                "health": health if not isinstance(health, Exception) else None,
                "control": status if not isinstance(status, Exception) else None,
                "metrics": metrics if not isinstance(metrics, Exception) else None,
                "last_update": datetime.now(timezone.utc)
            }
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}")
```

**Methods to Implement:**
- `_async_update_data()` - Main update loop
- `_fetch_json(endpoint)` - HTTP GET with auth
- `async_manual_override(action, power_kw, duration)` - POST to override endpoint
- `async_enable_auto_control()` - POST to enable endpoint
- `async_disable_auto_control()` - POST to disable endpoint

---

## Phase 3: Config Flow with Auto-Detection

### Status: 📋 TODO

**File to Create**: `config_flow.py` (~400 lines)

**Flow Steps:**

1. **Step: User (Connection)**
   - Input: Service URL (default: http://128.140.44.143:80)
   - Input: API Key
   - Input: Update Interval (default: 60s)
   - Validation: Test connection to `/api/v1/health` with Bearer token
   - On success: → Step 2 (Auto-detect)

2. **Step: Auto-detect (Entity Discovery)**
   - Query HA Energy Dashboard: `hass.data["energy"].async_get_prefs()`
   - Get device IDs from energy entities via entity registry
   - Find power sensors on devices (battery SOC, solar, house load)
   - Store detected entities in `self.detected_entities`
   - On success: → Step 3 (Review)

3. **Step: Review (Confirm Entities)**
   - Display detected entities with dropdowns (pre-selected)
   - User can override selections
   - Show current values for validation
   - On submit: → Create config entry

**Config Entry Data Structure:**
```python
{
    "service_url": "http://128.140.44.143:80",
    "api_key": "A6SJ7InZ0cjMMNEP7FS2YOqfr6JMvxZVwbKfPC-dYsk",
    "update_interval": 60,
    "detected_entities": {
        "battery_soc": "sensor.battery_soc_2",
        "solar_power": "sensor.pv_power",
        "house_load": "sensor.house_energy_load"
    }
}
```

**Auto-Detection Algorithm** (reuse POC logic):
```python
async def _discover_entities(self):
    """Auto-detect entities from Energy Dashboard."""
    # Get energy prefs
    energy_prefs = await self.hass.data["energy"].async_get_prefs()

    # Get entity and device registries
    entity_reg = er.async_get(self.hass)
    device_reg = dr.async_get(self.hass)

    # Find devices from energy entities
    devices = {}
    for source in energy_prefs.get("energy_sources", []):
        entity_id = source.get("stat_energy_from") or source.get("stat_energy_to")
        if entity_id:
            entry = entity_reg.async_get(entity_id)
            if entry and entry.device_id:
                device = device_reg.async_get(entry.device_id)
                devices[entry.device_id] = device

    # Find power sensors on devices
    for device_id, device in devices.items():
        entities = er.async_entries_for_device(entity_reg, device_id)
        # Pattern match for battery_soc, solar_power, house_load
        # (See POC script for full logic)
```

---

## Phase 4: Sensor Entities

### Status: 📋 TODO

**File to Create**: `sensor.py` (~300 lines)

**Sensors to Implement:**

| Sensor | State | Attributes | Icon |
|--------|-------|------------|------|
| **Service Health** | healthy/degraded/unhealthy | db_status, mpc_status, last_check | mdi:server |
| **Optimization Status** | enabled/disabled | manual_override, last_mpc_run | mdi:auto-fix |
| **Control Mode** | Force Charge/Self Use/Back-up | power_kw, reason, next_review | mdi:battery-charging |
| **MPC Success Rate** | 95.5 (%) | runs_last_hour, successful_runs | mdi:chart-line |
| **MPC Solve Time** | 145 (ms) | avg over last hour | mdi:timer |
| **MPC Runs (24h)** | 96 (count) | total optimizations | mdi:counter |

**Base Class:**
```python
class IntuiThermSensor(CoordinatorEntity, SensorEntity):
    """Base class for IntuiTherm sensors."""

    def __init__(self, coordinator, entry, sensor_type):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{sensor_type}"
        self._sensor_type = sensor_type
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="IntuiTherm Battery Optimizer",
            manufacturer="IntuiTherm",
            model="Energy Management Service",
            sw_version="1.0.0",
            configuration_url=entry.data[CONF_SERVICE_URL]
        )
```

**Example Sensor:**
```python
class ServiceHealthSensor(IntuiThermSensor):
    """Service health status sensor."""

    _attr_name = "Service Health"
    _attr_icon = "mdi:server"

    @property
    def native_value(self):
        """Return health status."""
        health = self.coordinator.data.get("health")
        if health:
            return health.get("status", "unknown")
        return "unavailable"

    @property
    def extra_state_attributes(self):
        """Return health details."""
        health = self.coordinator.data.get("health")
        if not health:
            return {}

        components = health.get("components", {})
        return {
            "database_status": components.get("database", {}).get("status"),
            "mpc_status": components.get("mpc", {}).get("status"),
            "last_check": health.get("timestamp")
        }
```

---

## Phase 5: Switch Entities

### Status: 📋 TODO

**File to Create**: `switch.py` (~150 lines)

**Switch to Implement:**

**Automatic Control Switch**
- **Turn On**: Call `coordinator.async_enable_auto_control()` → POST `/api/v1/control/enable`
- **Turn Off**: Call `coordinator.async_disable_auto_control()` → POST `/api/v1/control/disable`
- **State**: Read from `coordinator.data["control"]["automatic_control_enabled"]`
- **Icon**: mdi:auto-fix
- **Entity ID**: `switch.intuitherm_automatic_control`

**Implementation:**
```python
class AutomaticControlSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable/disable automatic battery control."""

    _attr_name = "Automatic Control"
    _attr_icon = "mdi:auto-fix"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_automatic_control"

    @property
    def is_on(self):
        """Return true if automatic control is enabled."""
        control = self.coordinator.data.get("control")
        if control:
            return control.get("automatic_control_enabled", False)
        return False

    async def async_turn_on(self, **kwargs):
        """Enable automatic control."""
        result = await self.coordinator.async_enable_auto_control()
        if result.get("status") == "success":
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Disable automatic control."""
        result = await self.coordinator.async_disable_auto_control()
        if result.get("status") == "success":
            await self.coordinator.async_request_refresh()
```

---

## Phase 6: Services

### Status: ✅ COMPLETED (in __init__.py)

**Service Registered**: `intuitherm.manual_override`

**Parameters:**
- `action` (required): "charge" | "discharge" | "idle" | "auto"
- `power_kw` (optional): 0.0 - 3.0
- `duration_minutes` (optional): 1 - 1440

**Usage Example:**
```yaml
# automation.yaml
- alias: "Charge battery when cheap electricity"
  trigger:
    - platform: numeric_state
      entity_id: sensor.electricity_price
      below: 0.10
  action:
    - service: intuitherm.manual_override
      data:
        action: "charge"
        power_kw: 3.0
        duration_minutes: 60
```

---

## Phase 7: Translations

### Status: 📋 TODO

**Files to Create:**
1. `strings.json` - Default strings (English)
2. `translations/en.json` - English translations

**Content Structure:**
```json
{
  "config": {
    "step": {
      "user": {
        "title": "Connect to IntuiTherm Service",
        "description": "Enter your IntuiTherm service URL and API key.",
        "data": {
          "service_url": "Service URL",
          "api_key": "API Key",
          "update_interval": "Update Interval (seconds)"
        }
      },
      "auto_detect": {
        "title": "Auto-Detect Entities",
        "description": "Detecting battery and solar entities from Energy Dashboard..."
      },
      "review": {
        "title": "Review Detected Entities",
        "description": "Confirm or adjust the auto-detected entities.",
        "data": {
          "battery_soc_entity": "Battery SOC Sensor",
          "solar_power_entity": "Solar Power Sensor",
          "house_load_entity": "House Load Sensor"
        }
      }
    },
    "error": {
      "cannot_connect": "Failed to connect to service",
      "invalid_api_key": "Invalid API key",
      "energy_dashboard_not_configured": "Energy Dashboard not configured"
    }
  }
}
```

---

## Testing Checklist

### Pre-Deployment (on Hetzner):

- [ ] API key added to `.env`
- [ ] Docker container rebuilt with port 80
- [ ] Service accessible: `curl -H "Authorization: Bearer KEY" http://128.140.44.143:80/api/v1/health`
- [ ] Control endpoints working with API key

### HA Integration Testing:

- [ ] Copy integration to HA: `/config/custom_components/intuitherm/`
- [ ] Restart Home Assistant
- [ ] No errors in logs: Check Configuration → Logs
- [ ] Add integration via UI: Configuration → Integrations → Add Integration → "IntuiTherm"
- [ ] Config flow completes successfully
- [ ] Auto-detection finds correct entities
- [ ] Integration creates sensors and switches
- [ ] Sensors show correct values
- [ ] Sensors update every 60 seconds
- [ ] Switch controls work (turn on/off automatic control)
- [ ] Service works: Developer Tools → Services → intuitherm.manual_override
- [ ] Graceful error handling when service offline

---

## Troubleshooting

### Issue: "Failed to connect to service"

**Diagnosis:**
```bash
# From HA machine, test connectivity
curl -v http://128.140.44.143:80/api/v1/health

# Check Hetzner firewall
ssh root@128.140.44.143
iptables -L -n | grep 80

# Check Docker port mapping
docker ps | grep energy-management
```

**Solution:**
- Ensure port 80 is open on Hetzner firewall
- Verify Docker is running and port mapped correctly

### Issue: "Invalid API key"

**Diagnosis:**
```bash
# Check API key in Hetzner .env
ssh root@128.140.44.143
cat /path/to/energy-management-service/.env | grep API_KEY

# Test with curl
curl -H "Authorization: Bearer YOUR_KEY" http://128.140.44.143:80/api/v1/health
```

**Solution:**
- Ensure API key in HA config matches `.env` on Hetzner
- Re-enter API key in HA integration config

### Issue: "Energy Dashboard not configured"

**Solution:**
- Configure Energy Dashboard in HA first: Settings → Dashboards → Energy
- Add solar, battery, and grid entities
- Retry integration setup (will auto-detect from dashboard)

### Issue: "Sensors show unavailable"

**Diagnosis:**
Check HA logs for errors:
```
Configuration → Logs → Filter: "intuitherm"
```

**Common Causes:**
- Service unreachable from HA
- API key expired or changed
- Service returned error response

**Solution:**
- Check service health manually
- Reload integration: Configuration → Integrations → IntuiTherm → ... → Reload

---

## API Key Regeneration

If you need to regenerate the API key:

1. **Generate new key:**
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Update Hetzner `.env`:**
   ```bash
   ssh root@128.140.44.143
   nano /path/to/energy-management-service/.env
   # Update API_KEY=new_key
   docker-compose restart
   ```

3. **Update HA integration:**
   - Configuration → Integrations → IntuiTherm
   - Click "Configure"
   - Enter new API key
   - Save

---

## Security Recommendations

1. **API Key Storage:**
   - ✅ API key is stored in HA config (encrypted)
   - ✅ API key not logged or displayed
   - ✅ API key transmitted over HTTPS when HA accesses service

2. **Network Security:**
   - ⚠️ Service currently uses HTTP (port 80)
   - 🔒 **Recommended**: Add HTTPS/SSL with Let's Encrypt
   - 🔒 **Recommended**: Restrict Hetzner firewall to HA's public IP

3. **API Key Strength:**
   - ✅ Generated with `secrets.token_urlsafe(32)` = 43 characters
   - ✅ Cryptographically secure random

4. **Endpoint Protection:**
   - ⚠️ Currently only tested endpoints are protected
   - 🔒 **Recommended**: Add `Depends(verify_api_key)` to all control endpoints

---

## Future Enhancements

1. **HTTPS Support**: Add nginx reverse proxy with Let's Encrypt
2. **Binary Sensors**: Add alert sensors (forecast error, sensor offline, etc.)
3. **More Metrics**: Battery cycle count, cost savings, solar yield
4. **Lovelace Dashboard**: Auto-create dashboard on setup
5. **HACS Integration**: Submit to HACS for easy installation
6. **Multi-User Support**: Evolve to Phase 1A (multi-tenant cloud service)

---

## File Structure Summary

```
custom_components/intuitherm/
├── __init__.py              ✅ DONE (150 lines)
├── manifest.json            ✅ DONE (30 lines)
├── const.py                 ✅ DONE (70 lines)
├── config_flow.py           📋 TODO (400 lines)
├── coordinator.py           📋 TODO (200 lines)
├── sensor.py                📋 TODO (300 lines)
├── switch.py                📋 TODO (150 lines)
├── strings.json             📋 TODO (100 lines)
├── translations/
│   └── en.json              📋 TODO (100 lines)
└── IMPLEMENTATION_GUIDE.md  ✅ DONE (this file)

Total: ~1,500 lines remaining
```

---

## Contact & Support

**Repository**: https://github.com/yourusername/intuitherm
**Issues**: https://github.com/yourusername/intuitherm/issues
**Service URL**: http://128.140.44.143:80
**API Key**: A6SJ7InZ0cjMMNEP7FS2YOqfr6JMvxZVwbKfPC-dYsk (keep secure!)

---

**Document Version**: 1.0
**Last Updated**: October 31, 2025
**Status**: Implementation in progress - Phase 1 complete
