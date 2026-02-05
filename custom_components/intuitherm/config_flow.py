"""Config flow for IntuiTherm integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from datetime import timezone as dt_timezone
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, device_registry as dr, selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_SERVICE_URL,
    CONF_API_KEY,
    CONF_UPDATE_INTERVAL,
    CONF_DETECTED_ENTITIES,
    CONF_BATTERY_SOC_ENTITY,
    CONF_SOLAR_POWER_ENTITY,
    CONF_HOUSE_LOAD_ENTITY,
    CONF_SOLAR_SENSORS,
    CONF_BATTERY_DISCHARGE_SENSORS,
    CONF_BATTERY_CHARGE_SENSORS,
    CONF_GRID_IMPORT_SENSORS,
    CONF_GRID_EXPORT_SENSORS,
    CONF_BATTERY_MODE_SELECT,
    CONF_BATTERY_CHARGE_POWER,
    CONF_BATTERY_DISCHARGE_POWER,
    CONF_SOLAREDGE_COMMAND_MODE,
    CONF_MODE_SELF_USE,
    CONF_MODE_BACKUP,
    CONF_MODE_FORCE_CHARGE,
    BATTERY_MODE_NAMES,
    BATTERY_MODE_SELF_USE,
    BATTERY_MODE_BACKUP,
    BATTERY_MODE_FORCE_CHARGE,
    CONF_BATTERY_CAPACITY,
    CONF_BATTERY_MAX_POWER,
    CONF_BATTERY_CHARGE_MAX_POWER,
    CONF_HOUSE_LOAD_CALC_MODE,
    CONF_EPEX_MARKUP,
    CONF_GRID_EXPORT_PRICE,
    CONF_DRY_RUN_MODE,
    CONF_INSTANCE_ID,
    CONF_USER_ID,
    CONF_USER_EMAIL,
    CONF_MARKETING_CONSENT,
    CONF_SAVINGS_REPORT_CONSENT,
    CONF_REGISTERED_AT,
    DEFAULT_SERVICE_URL,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_BATTERY_MAX_POWER,
    DEFAULT_BATTERY_CHARGE_MAX_POWER,
    DEFAULT_EPEX_MARKUP,
    DEFAULT_GRID_EXPORT_PRICE,
    ENDPOINT_UPDATE_CONFIG,
    ENDPOINT_AUTH_STATUS,
    ENDPOINT_AUTH_REGISTER,
    ENDPOINT_HEALTH,
    DEVICE_CONTROL_MAPPINGS,
)
from .device_learning import async_setup_device_learning

_LOGGER = logging.getLogger(__name__)


class IntuiThermConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IntuiTherm."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return IntuiThermOptionsFlowHandler()

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._service_url: str | None = None
        self._api_key: str | None = None
        self._update_interval: int = DEFAULT_UPDATE_INTERVAL
        self._detected_entities: dict[str, Any] = {}
        self._device_info: dict[str, Any] | None = None  # Track device for learning
        self._device_learning_store = None  # Will be initialized when needed
        self._user_name: str | None = None  # HA user's display name for personalization
        self._user_email: str | None = None  # Optional user email
        self._marketing_consent: bool = False  # Consent for product updates
        self._savings_report_consent: bool = False  # Consent for savings reports
        
        # Multi-device and multi-sensor support
        self._discovered_devices: list[dict[str, Any]] = []  # All found devices
        self._all_solar_sensors: list[dict[str, Any]] = []  # All solar sensors found
        self._all_batteries: list[dict[str, Any]] = []  # All battery devices found
        self._selected_solar_sensors: list[str] = []  # User-selected solar sensors
        self._selected_battery_idx: int = 0  # Index of selected battery (if multiple)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step - welcome screen with email opt-in."""
        from .const import VERSION
        
        if user_input is not None:
            # Store user inputs
            self._user_email = user_input.get("user_email", "").strip() or None
            self._marketing_consent = user_input.get("marketing_consent", False)
            self._savings_report_consent = user_input.get("savings_report_consent", False)
            
            # Set service URL (production only, no user config)
            self._service_url = DEFAULT_SERVICE_URL
            self._update_interval = DEFAULT_UPDATE_INTERVAL
            
            _LOGGER.info("=" * 60)
            _LOGGER.info("IntuiHEMS Setup Flow Started")
            _LOGGER.info("Version: %s", VERSION)
            _LOGGER.info("Service URL: %s", self._service_url)
            _LOGGER.info("Update Interval: %d seconds", self._update_interval)
            if self._user_email:
                _LOGGER.info("User Email: %s (marketing: %s, savings: %s)", self._user_email, self._marketing_consent, self._savings_report_consent)
            _LOGGER.info("=" * 60)
            
            # Auto-register with backend to get API key
            return await self.async_step_register()

        # Get current HA user's display name for personalization
        user_name = "there"  # Fallback
        try:
            if self.context.get("user_id"):
                user = await self.hass.auth.async_get_user(self.context["user_id"])
                if user and user.name:
                    user_name = user.name
                    self._user_name = user_name
                    _LOGGER.info("Detected HA user: %s", user_name)
        except Exception as e:
            _LOGGER.debug("Could not get HA user name: %s", e)
        
        # Show welcome screen with version and personalized greeting
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Optional("user_email", default=""): str,
                vol.Optional("marketing_consent", default=False): bool,
                vol.Optional("savings_report_consent", default=False): bool,
            }),
            description_placeholders={
                "version": VERSION,
                "user_name": user_name,
            },
        )

    async def async_step_register(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Auto-register with backend to get API key."""
        from homeassistant.helpers import instance_id
        
        errors: dict[str, str] = {}
        
        # This step is automatic - no user input
        if user_input is None:
            _LOGGER.info("")
            _LOGGER.info("STEP: Auto-Registration with Backend")
            _LOGGER.info("-" * 60)
            
            try:
                # Get HA instance details
                ha_instance_id = await instance_id.async_get(self.hass)
                latitude = self.hass.config.latitude
                longitude = self.hass.config.longitude
                elevation = self.hass.config.elevation
                timezone = str(self.hass.config.time_zone)
                location_name = self.hass.config.location_name
                
                # Get HA version safely
                try:
                    from homeassistant.const import __version__ as ha_version
                except ImportError:
                    ha_version = None
                
                _LOGGER.info("HA Instance ID: %s", ha_instance_id)
                _LOGGER.info("Location: (%s, %s, %sm)", latitude, longitude, elevation)
                _LOGGER.info("Timezone: %s", timezone)
                _LOGGER.info("Location Name: %s", location_name)
                _LOGGER.info("HA Version: %s", ha_version)
                
                # Check service status first (alpha limit)
                _LOGGER.info("Checking service availability...")
                session = async_get_clientsession(self.hass)
                
                async with asyncio.timeout(10):
                    async with session.get(
                        f"{self._service_url}{ENDPOINT_AUTH_STATUS}"
                    ) as resp:
                        if resp.status == 200:
                            status_data = await resp.json()
                            _LOGGER.info(
                                "Service status: %s (users: %d/%s)",
                                status_data.get("phase"),
                                status_data.get("registered_users", 0),
                                status_data.get("max_users", "unlimited")
                            )
                            
                            if not status_data.get("accepting_registrations", True):
                                waitlist_url = status_data.get("waitlist_url", "https://intuihems.io/waitlist")
                                _LOGGER.warning("Service not accepting registrations - alpha limit reached")
                                errors["base"] = "alpha_limit_reached"
                                return self.async_show_form(
                                    step_id="register",
                                    data_schema=vol.Schema({}),
                                    errors=errors,
                                    description_placeholders={"waitlist_url": waitlist_url},
                                )
                        else:
                            _LOGGER.warning("Could not check service status (status=%d), proceeding anyway", resp.status)
                
                # Register with backend
                _LOGGER.info("Registering with backend...")
                registration_data = {
                    "installation_id": ha_instance_id,
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                }
                
                # Add optional fields only if they have valid values
                if elevation is not None and elevation > 0:
                    registration_data["elevation"] = float(elevation)
                if timezone:
                    registration_data["timezone"] = timezone
                if location_name:
                    registration_data["installation_name"] = location_name
                if ha_version:
                    registration_data["ha_version"] = ha_version
                if self._user_email:
                    registration_data["user_email"] = self._user_email
                if self._marketing_consent:
                    registration_data["marketing_consent"] = self._marketing_consent
                if self._savings_report_consent:
                    registration_data["savings_report_consent"] = self._savings_report_consent
                
                _LOGGER.info("Registration payload:")
                for key, value in registration_data.items():
                    if key == "installation_id":
                        _LOGGER.info("  %s: %s", key, value[:8] + "..." if len(value) > 8 else value)
                    elif key == "user_email":
                        # Mask email for privacy in logs
                        email_parts = value.split("@") if "@" in value else [value]
                        masked = f"{email_parts[0][:2]}...@{email_parts[1]}" if len(email_parts) == 2 else "***"
                        _LOGGER.info("  %s: %s", key, masked)
                    else:
                        _LOGGER.info("  %s: %s", key, value)
                
                async with asyncio.timeout(15):
                    async with session.post(
                        f"{self._service_url}{ENDPOINT_AUTH_REGISTER}",
                        json=registration_data,
                    ) as resp:
                        response_text = await resp.text()
                        
                        if resp.status == 201:
                            # Success - new registration
                            response_data = await resp.json()
                            self._api_key = response_data["api_key"]
                            user_id = response_data["user_id"]
                            
                            _LOGGER.info("✅ Registration successful!")
                            _LOGGER.info("User ID: %s", user_id)
                            _LOGGER.info("API key received (length: %d chars)", len(self._api_key))
                            _LOGGER.info("Setup required: %s", response_data.get("setup_required", True))
                            
                            # Store for later
                            self._detected_entities[CONF_INSTANCE_ID] = ha_instance_id
                            self._detected_entities[CONF_USER_ID] = user_id
                            self._detected_entities[CONF_REGISTERED_AT] = datetime.now(dt_timezone.utc).isoformat()
                            
                            # Show user ID to user before continuing
                            return self.async_show_form(
                                step_id="show_user_id",
                                data_schema=vol.Schema({}),
                                description_placeholders={"user_id": user_id},
                            )
                            
                        elif resp.status == 409:
                            # Already registered - backend will deactivate old user and allow re-registration
                            # This shouldn't happen anymore with the new backend logic, but handle it gracefully
                            _LOGGER.warning("Installation already registered (unexpected 409), retrying registration")
                            try:
                                error_data = await resp.json()
                                _LOGGER.info("Registration conflict details: %s", error_data)
                            except:
                                pass
                            errors["base"] = "registration_failed"
                            
                        elif resp.status == 503:
                            # Service unavailable (alpha limit)
                            _LOGGER.warning("Service unavailable - alpha limit reached")
                            errors["base"] = "alpha_limit_reached"
                            
                        else:
                            # Other error - log full details
                            _LOGGER.error("Registration failed with status %d: %s", resp.status, response_text)
                            try:
                                error_json = await resp.json()
                                _LOGGER.error("Error details: %s", error_json)
                            except:
                                pass
                            errors["base"] = "registration_failed"
                
            except asyncio.TimeoutError:
                _LOGGER.error("Registration timeout")
                errors["base"] = "timeout_connect"
            except Exception as err:
                _LOGGER.exception("Registration error: %s", err)
                errors["base"] = "registration_failed"
        
        # Show error form if registration failed (but not for 409, which redirects)
        return self.async_show_form(
            step_id="register",
            data_schema=vol.Schema({}),
            errors=errors,
        )

    async def async_step_show_user_id(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Show user ID after registration."""
        if user_input is not None:
            # User clicked continue, proceed to auto-detection
            return await self.async_step_auto_detect()
        
        # This should never happen since user_id is set during registration
        # but provide fallback just in case
        user_id = self._detected_entities.get(CONF_USER_ID, "Unknown")
        
        return self.async_show_form(
            step_id="show_user_id",
            data_schema=vol.Schema({}),
            description_placeholders={"user_id": user_id},
        )

    async def async_step_auto_detect(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Auto-detect entities from Home Assistant Energy Dashboard."""
        if user_input is not None:
            if user_input.get("skip"):
                # User chose to skip auto-detection
                return await self.async_step_review()

        # Run auto-detection
        _LOGGER.info("")
        _LOGGER.info("STEP 1: Starting Entity Auto-Detection")
        _LOGGER.info("-" * 60)

        try:
            # Phase 1: Extract ALL Energy Dashboard sensors with availability
            all_energy_sensors = await self._get_all_energy_sensors()
            _LOGGER.info("Energy Dashboard Sensors Extracted:")
            for category, sensor_list in all_energy_sensors.items():
                available_count = sum(1 for s in sensor_list if s["available"])
                _LOGGER.info(
                    "  %s: %d total (%d available)",
                    category,
                    len(sensor_list),
                    available_count
                )
                for sensor in sensor_list:
                    # Classify sensor type
                    sensor_info = self._classify_sensor(sensor["entity_id"])
                    status = "✅" if sensor["available"] else "❌"
                    _LOGGER.info(
                        "    %s %s [%s, %s] value=%s",
                        status,
                        sensor["entity_id"],
                        sensor_info.get("type", "unknown"),
                        sensor["unit"],
                        sensor["state"]
                    )

            # Query Energy Dashboard configuration
            _LOGGER.info("")
            _LOGGER.info("STEP 2: Querying Energy Dashboard Configuration")
            _LOGGER.info("-" * 60)
            energy_prefs = await self._get_energy_prefs()

            if not energy_prefs:
                _LOGGER.warning("⚠️  Energy Dashboard not configured")
                _LOGGER.info("Skipping Energy Dashboard detection, will use pattern matching")
            else:
                _LOGGER.info("✅ Energy Dashboard configured")
                source_counts = {}
                for source in energy_prefs.get("energy_sources", []):
                    source_type = source.get("type")
                    source_counts[source_type] = source_counts.get(source_type, 0) + 1
                for source_type, count in source_counts.items():
                    _LOGGER.info("  - %s sources: %d", source_type, count)

            # Discover devices from energy entities
            _LOGGER.info("")
            _LOGGER.info("STEP 3: Discovering Devices from Energy Dashboard")
            _LOGGER.info("-" * 60)
            devices = await self._discover_devices(energy_prefs) if energy_prefs else {}
            _LOGGER.info("Discovered %d device(s)", len(devices))

            # Find relevant power sensors on devices
            _LOGGER.info("")
            _LOGGER.info("STEP 4: Scanning Device Sensors")
            _LOGGER.info("-" * 60)
            for device_id, device_info in devices.items():
                _LOGGER.info("Scanning device: %s", device_info["name"])
                sensors = await self._find_power_sensors(device_id)
                if sensors:
                    # Store complete device information with sensors
                    device_entry = {
                        "device_id": device_id,
                        "name": device_info["name"],
                        "manufacturer": device_info.get("manufacturer"),
                        "model": device_info.get("model"),
                        "platform": device_info.get("platform"),
                        "sensors": sensors,
                    }
                    self._discovered_devices.append(device_entry)
                    
                    # Store device info for potential learning
                    if sensors.get("device_info") and not self._device_info:
                        self._device_info = sensors["device_info"]
                    
                    # Store best single matches (for backward compatibility)
                    if sensors.get("battery_soc") and not self._detected_entities.get(
                        CONF_BATTERY_SOC_ENTITY
                    ):
                        self._detected_entities[CONF_BATTERY_SOC_ENTITY] = sensors[
                            "battery_soc"
                        ]["entity_id"]

                    if sensors.get("solar_power") and not self._detected_entities.get(
                        CONF_SOLAR_POWER_ENTITY
                    ):
                        self._detected_entities[CONF_SOLAR_POWER_ENTITY] = sensors[
                            "solar_power"
                        ]["entity_id"]

                    if sensors.get("house_load") and not self._detected_entities.get(
                        CONF_HOUSE_LOAD_ENTITY
                    ):
                        self._detected_entities[CONF_HOUSE_LOAD_ENTITY] = sensors[
                            "house_load"
                        ]["entity_id"]
                    
                    # NEW: Collect ALL multi-sensors
                    if sensors.get("all_pv_sensors"):
                        self._all_solar_sensors.extend(sensors["all_pv_sensors"])
                    if sensors.get("all_battery_charge_sensors"):
                        for sensor in sensors["all_battery_charge_sensors"]:
                            if sensor not in self._detected_entities.get(CONF_BATTERY_CHARGE_SENSORS, []):
                                self._detected_entities.setdefault(CONF_BATTERY_CHARGE_SENSORS, []).append(sensor["entity_id"])
                    if sensors.get("all_battery_discharge_sensors"):
                        for sensor in sensors["all_battery_discharge_sensors"]:
                            if sensor not in self._detected_entities.get(CONF_BATTERY_DISCHARGE_SENSORS, []):
                                self._detected_entities.setdefault(CONF_BATTERY_DISCHARGE_SENSORS, []).append(sensor["entity_id"])
                    if sensors.get("all_grid_consumption_sensors"):
                        for sensor in sensors["all_grid_consumption_sensors"]:
                            if sensor not in self._detected_entities.get(CONF_GRID_IMPORT_SENSORS, []):
                                self._detected_entities.setdefault(CONF_GRID_IMPORT_SENSORS, []).append(sensor["entity_id"])
                    if sensors.get("all_grid_feedin_sensors"):
                        for sensor in sensors["all_grid_feedin_sensors"]:
                            if sensor not in self._detected_entities.get(CONF_GRID_EXPORT_SENSORS, []):
                                self._detected_entities.setdefault(CONF_GRID_EXPORT_SENSORS, []).append(sensor["entity_id"])
                    
                    # Store detected battery control entities
                    if sensors.get("control_entities"):
                        control_entities = sensors["control_entities"]
                        if control_entities.get(CONF_BATTERY_MODE_SELECT):
                            self._detected_entities[CONF_BATTERY_MODE_SELECT] = control_entities[
                                CONF_BATTERY_MODE_SELECT
                            ]
                        if control_entities.get(CONF_BATTERY_CHARGE_POWER):
                            self._detected_entities[CONF_BATTERY_CHARGE_POWER] = control_entities[
                                CONF_BATTERY_CHARGE_POWER
                            ]
                        if control_entities.get(CONF_BATTERY_DISCHARGE_POWER):
                            self._detected_entities[CONF_BATTERY_DISCHARGE_POWER] = control_entities[
                                CONF_BATTERY_DISCHARGE_POWER
                            ]
                        # Optional Huawei-specific entities
                        if control_entities.get("grid_charge_switch"):
                            self._detected_entities["grid_charge_switch"] = control_entities[
                                "grid_charge_switch"
                            ]
                        if control_entities.get("device_id"):
                            self._detected_entities["device_id"] = control_entities[
                                "device_id"
                            ]
                    
                    # Log what we found on this device
                    _LOGGER.info("  Found on device:")
                    if sensors.get("all_pv_sensors"):
                        _LOGGER.info("    PV sensors: %d", len(sensors["all_pv_sensors"]))
                        for pv in sensors["all_pv_sensors"]:
                            _LOGGER.info("      - %s [%s]", pv["entity_id"], "cumulative ⭐" if pv["is_cumulative"] else "instantaneous")
                    if sensors.get("battery_soc"):
                        _LOGGER.info("    Battery SoC: %s", sensors["battery_soc"]["entity_id"])
                    if sensors.get("all_battery_charge_sensors"):
                        _LOGGER.info("    Battery Charge: %d sensor(s)", len(sensors["all_battery_charge_sensors"]))
                        for bc in sensors["all_battery_charge_sensors"]:
                            _LOGGER.info("      - %s [%s]", bc["entity_id"], "cumulative ⭐" if bc["is_cumulative"] else "instantaneous")
                    if sensors.get("all_battery_discharge_sensors"):
                        _LOGGER.info("    Battery Discharge: %d sensor(s)", len(sensors["all_battery_discharge_sensors"]))
                        for bd in sensors["all_battery_discharge_sensors"]:
                            _LOGGER.info("      - %s [%s]", bd["entity_id"], "cumulative ⭐" if bd["is_cumulative"] else "instantaneous")
                    if sensors.get("all_grid_consumption_sensors"):
                        _LOGGER.info("    Grid Consumption: %d sensor(s)", len(sensors["all_grid_consumption_sensors"]))
                        for gc in sensors["all_grid_consumption_sensors"]:
                            _LOGGER.info("      - %s [%s]", gc["entity_id"], "cumulative ⭐" if gc["is_cumulative"] else "instantaneous")
                    if sensors.get("all_grid_feedin_sensors"):
                        _LOGGER.info("    Grid Feed-in: %d sensor(s)", len(sensors["all_grid_feedin_sensors"]))
                        for gf in sensors["all_grid_feedin_sensors"]:
                            _LOGGER.info("      - %s [%s]", gf["entity_id"], "cumulative ⭐" if gf["is_cumulative"] else "instantaneous")
            
            # Check for learned patterns if no control entities detected
            if self._device_info and not self._detected_entities.get(CONF_BATTERY_MODE_SELECT):
                await self._check_learned_patterns()

            # Convert collected solar sensors to CONF_SOLAR_SENSORS list
            if self._all_solar_sensors:
                solar_sensor_ids = [s["entity_id"] for s in self._all_solar_sensors]
                self._detected_entities[CONF_SOLAR_SENSORS] = solar_sensor_ids
                _LOGGER.info("")
                _LOGGER.info("Collected %d PV sensor(s) total", len(solar_sensor_ids))

            # Priority 1: Try Energy Dashboard cumulative sensors first (best source of truth)
            # These are kWh sensors that the backend will convert to kW via derivatives
            _LOGGER.info("")
            _LOGGER.info("STEP 5: Prioritizing Cumulative Energy Sensors")
            _LOGGER.info("-" * 60)
            dashboard_sensors = await self._find_energy_dashboard_sensors()

            if dashboard_sensors.get("solar_power"):
                # Prefer Energy Dashboard cumulative sensors over device-based detection
                entity_id = dashboard_sensors["solar_power"]["entity_id"]
                self._detected_entities[CONF_SOLAR_POWER_ENTITY] = entity_id
                is_cumulative = dashboard_sensors["solar_power"].get("is_cumulative", False)
                sensor_info = self._classify_sensor(entity_id)
                
                _LOGGER.info(
                    "✅ Solar sensor from Energy Dashboard: %s",
                    entity_id
                )
                _LOGGER.info(
                    "   Type: %s | Unit: %s | Confidence: High",
                    sensor_info.get("type", "unknown"),
                    sensor_info.get("unit", "unknown")
                )
                if is_cumulative:
                    _LOGGER.info("   ⭐ Cumulative sensor - backend will compute power derivative")

            # Fallback: If no/few sensors detected, try pattern-based search
            detected_count = len([v for v in self._detected_entities.values() if v])
            if detected_count < 2:
                _LOGGER.info("")
                _LOGGER.info("STEP 6: Pattern-Based Fallback Detection")
                _LOGGER.info("-" * 60)
                _LOGGER.info("Only %d sensor(s) detected so far, trying pattern matching", detected_count)
                fallback_sensors = await self._find_sensors_by_pattern()

                if fallback_sensors.get("battery_soc") and not self._detected_entities.get(
                    CONF_BATTERY_SOC_ENTITY
                ):
                    entity_id = fallback_sensors["battery_soc"]["entity_id"]
                    self._detected_entities[CONF_BATTERY_SOC_ENTITY] = entity_id
                    sensor_info = self._classify_sensor(entity_id)
                    _LOGGER.info(
                        "⚠️  Pattern-detected battery SOC: %s [%s, %s]",
                        entity_id,
                        sensor_info.get("type", "unknown"),
                        sensor_info.get("unit", "unknown")
                    )

                if fallback_sensors.get("solar_power") and not self._detected_entities.get(
                    CONF_SOLAR_POWER_ENTITY
                ):
                    entity_id = fallback_sensors["solar_power"]["entity_id"]
                    self._detected_entities[CONF_SOLAR_POWER_ENTITY] = entity_id
                    sensor_info = self._classify_sensor(entity_id)
                    _LOGGER.info(
                        "⚠️  Pattern-detected solar: %s [%s, %s]",
                        entity_id,
                        sensor_info.get("type", "unknown"),
                        sensor_info.get("unit", "unknown")
                    )

                if fallback_sensors.get("house_load") and not self._detected_entities.get(
                    CONF_HOUSE_LOAD_ENTITY
                ):
                    entity_id = fallback_sensors["house_load"]["entity_id"]
                    self._detected_entities[CONF_HOUSE_LOAD_ENTITY] = entity_id
                    sensor_info = self._classify_sensor(entity_id)
                    _LOGGER.info(
                        "⚠️  Pattern-detected house load: %s [%s, %s]",
                        entity_id,
                        sensor_info.get("type", "unknown"),
                        sensor_info.get("unit", "unknown")
                    )

            # Validate detected sensors
            _LOGGER.info("")
            _LOGGER.info("STEP 7: Validating Detected Sensors")
            _LOGGER.info("-" * 60)
            await self._validate_detected_sensors()

            # Summary
            _LOGGER.info("")
            _LOGGER.info("DETECTION SUMMARY")
            _LOGGER.info("=" * 60)
            
            # Single sensors
            detected_count = len([v for v in self._detected_entities.values() if v and isinstance(v, str)])
            _LOGGER.info("Single sensors detected: %d", detected_count)
            for key, value in self._detected_entities.items():
                if value and isinstance(value, str):  # Skip lists for now
                    sensor_info = self._classify_sensor(value)
                    _LOGGER.info(
                        "  %s: %s [%s]",
                        key,
                        value,
                        sensor_info.get("type", "unknown")
                    )
            
            # Multi-sensor lists
            _LOGGER.info("")
            _LOGGER.info("Multi-sensor lists:")
            if self._detected_entities.get(CONF_SOLAR_SENSORS):
                _LOGGER.info("  Solar sensors: %d", len(self._detected_entities[CONF_SOLAR_SENSORS]))
                for sensor_id in self._detected_entities[CONF_SOLAR_SENSORS]:
                    sensor_info = self._classify_sensor(sensor_id)
                    _LOGGER.info("    - %s [%s]", sensor_id, sensor_info.get("type", "unknown"))
            
            if self._detected_entities.get(CONF_BATTERY_CHARGE_SENSORS):
                _LOGGER.info("  Battery Charge sensors: %d", len(self._detected_entities[CONF_BATTERY_CHARGE_SENSORS]))
                for sensor_id in self._detected_entities[CONF_BATTERY_CHARGE_SENSORS]:
                    sensor_info = self._classify_sensor(sensor_id)
                    _LOGGER.info("    - %s [%s]", sensor_id, sensor_info.get("type", "unknown"))
            
            if self._detected_entities.get(CONF_BATTERY_DISCHARGE_SENSORS):
                _LOGGER.info("  Battery Discharge sensors: %d", len(self._detected_entities[CONF_BATTERY_DISCHARGE_SENSORS]))
                for sensor_id in self._detected_entities[CONF_BATTERY_DISCHARGE_SENSORS]:
                    sensor_info = self._classify_sensor(sensor_id)
                    _LOGGER.info("    - %s [%s]", sensor_id, sensor_info.get("type", "unknown"))
            
            if self._detected_entities.get(CONF_GRID_IMPORT_SENSORS):
                _LOGGER.info("  Grid Import sensors: %d", len(self._detected_entities[CONF_GRID_IMPORT_SENSORS]))
                for sensor_id in self._detected_entities[CONF_GRID_IMPORT_SENSORS]:
                    sensor_info = self._classify_sensor(sensor_id)
                    _LOGGER.info("    - %s [%s]", sensor_id, sensor_info.get("type", "unknown"))
            
            if self._detected_entities.get(CONF_GRID_EXPORT_SENSORS):
                _LOGGER.info("  Grid Export sensors: %d", len(self._detected_entities[CONF_GRID_EXPORT_SENSORS]))
                for sensor_id in self._detected_entities[CONF_GRID_EXPORT_SENSORS]:
                    sensor_info = self._classify_sensor(sensor_id)
                    _LOGGER.info("    - %s [%s]", sensor_id, sensor_info.get("type", "unknown"))
            
            _LOGGER.info("=" * 60)

        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Auto-detection failed")

        # Move to device discovery step to show found devices
        return await self.async_step_device_discovery()

    async def async_step_device_discovery(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Show discovered devices and their sensors."""
        if user_input is not None:
            # User clicked Next, proceed to review
            return await self.async_step_review()
        
        # Build personalized greeting
        greeting = f"Hi {self._user_name or 'there'}, "
        
        # Check if we have known devices
        known_device_msg = ""
        if self._discovered_devices:
            first_device = self._discovered_devices[0]
            manufacturer = first_device.get("manufacturer", "")
            model = first_device.get("model", "Unknown Model")
            
            if manufacturer and model:
                known_device_msg = f"we discovered your **{manufacturer} {model}**. Good news: we know this device and can prefill most of your configuration!"
            elif manufacturer:
                known_device_msg = f"we discovered your **{manufacturer}** device. Good news: we can auto-detect most settings!"
            else:
                known_device_msg = f"we discovered your energy system!"
        
        # Build description with discovered devices
        description_parts = []
        if known_device_msg:
            description_parts.append(greeting + known_device_msg + "\n")
        
        description_parts.append(f"Discovered {len(self._discovered_devices)} device(s):\n")
        
        for device in self._discovered_devices:
            device_name = device["name"]
            manufacturer = device.get("manufacturer", "Unknown")
            model = device.get("model", "Unknown Model")
            sensors = device.get("sensors", {})
            
            description_parts.append(f"\n**{device_name}**")
            description_parts.append(f"└─ Manufacturer: {manufacturer}")
            description_parts.append(f"└─ Model: {model}")
            
            # Show sensor counts
            pv_count = len(sensors.get("all_pv_sensors", []))
            if pv_count > 0:
                description_parts.append(f"└─ PV Sensors: {pv_count}")
                # Show preference for cumulative
                cumulative_count = sum(1 for s in sensors.get("all_pv_sensors", []) if s.get("is_cumulative"))
                if cumulative_count > 0:
                    description_parts.append(f"   ├─ {cumulative_count} cumulative (kWh) ⭐")
                if pv_count - cumulative_count > 0:
                    description_parts.append(f"   └─ {pv_count - cumulative_count} instantaneous (kW)")
            
            if sensors.get("battery_soc"):
                description_parts.append(f"└─ Battery SoC: {sensors['battery_soc']['entity_id']}")
            
            bat_charge_count = len(sensors.get("all_battery_charge_sensors", []))
            if bat_charge_count > 0:
                description_parts.append(f"└─ Battery Charge Sensors: {bat_charge_count}")
            
            bat_discharge_count = len(sensors.get("all_battery_discharge_sensors", []))
            if bat_discharge_count > 0:
                description_parts.append(f"└─ Battery Discharge Sensors: {bat_discharge_count}")
            
            grid_cons_count = len(sensors.get("all_grid_consumption_sensors", []))
            if grid_cons_count > 0:
                description_parts.append(f"└─ Grid Consumption Sensors: {grid_cons_count}")
            
            grid_feed_count = len(sensors.get("all_grid_feedin_sensors", []))
            if grid_feed_count > 0:
                description_parts.append(f"└─ Grid Feed-in Sensors: {grid_feed_count}")
            
            # Show control entities if found
            control_ents = sensors.get("control_entities", {})
            if control_ents:
                description_parts.append(f"└─ Battery Control Entities:")
                if control_ents.get(CONF_BATTERY_MODE_SELECT):
                    description_parts.append(f"   ├─ Mode Select: ✅")
                if control_ents.get(CONF_BATTERY_CHARGE_POWER):
                    description_parts.append(f"   ├─ Charge Power: ✅")
                if control_ents.get(CONF_BATTERY_DISCHARGE_POWER):
                    description_parts.append(f"   └─ Discharge Power: ✅")
        
        description = "\n".join(description_parts)
        
        return self.async_show_form(
            step_id="device_discovery",
            data_schema=vol.Schema({}),
            description_placeholders={
                "device_count": str(len(self._discovered_devices)),
                "device_details": description,
            },
        )

    async def async_step_review(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Review and confirm detected entities."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Get the 3 required sensor selections
            solar_production = user_input.get("solar_production", "").strip()
            battery_soc = user_input.get("battery_soc", "").strip()
            house_load = user_input.get("house_load", "").strip()
            
            # Validate all required sensors are provided
            if not solar_production:
                errors["solar_production"] = "Solar production sensor is required"
            if not battery_soc:
                errors["battery_soc"] = "Battery SoC sensor is required"
            if not house_load:
                errors["house_load"] = "House load sensor is required"
            
            # Validate entities exist
            if not errors:
                for sensor_id, field_name in [
                    (solar_production, "solar_production"),
                    (battery_soc, "battery_soc"),
                    (house_load, "house_load"),
                ]:
                    if not self.hass.states.get(sensor_id):
                        errors[field_name] = f"Entity '{sensor_id}' not found in Home Assistant"
            
            if not errors:
                # Store the final selected sensors (simplified - only 3 required sensors)
                self._detected_entities[CONF_SOLAR_POWER_ENTITY] = solar_production
                self._detected_entities[CONF_BATTERY_SOC_ENTITY] = battery_soc
                self._detected_entities[CONF_HOUSE_LOAD_ENTITY] = house_load
                
                # Store empty lists for optional sensors (for coordinator compatibility)
                self._detected_entities[CONF_BATTERY_CHARGE_SENSORS] = []
                self._detected_entities[CONF_BATTERY_DISCHARGE_SENSORS] = []
                self._detected_entities[CONF_GRID_IMPORT_SENSORS] = []
                self._detected_entities[CONF_GRID_EXPORT_SENSORS] = []
                
                _LOGGER.info("Sensors configured: solar=%s, battery_soc=%s, house_load=%s",
                             solar_production, battery_soc, house_load)
                
                # Proceed to battery control configuration
                return await self.async_step_battery_control()
        
        # If no user input yet, show the review form with available sensors
        return await self._show_review_form()
    
    async def async_step_battery_control(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Configure battery control entities (optional, skip if no battery or demo mode)."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            # Extract control entities
            battery_mode_select = user_input.get(CONF_BATTERY_MODE_SELECT)
            battery_charge_power = user_input.get(CONF_BATTERY_CHARGE_POWER)
            battery_discharge_power = user_input.get(CONF_BATTERY_DISCHARGE_POWER)
            
            # Store control entities (can be None/empty if skipped)
            if battery_mode_select:
                self._detected_entities[CONF_BATTERY_MODE_SELECT] = battery_mode_select
            if battery_charge_power:
                self._detected_entities[CONF_BATTERY_CHARGE_POWER] = battery_charge_power
            if battery_discharge_power:
                self._detected_entities[CONF_BATTERY_DISCHARGE_POWER] = battery_discharge_power
            
            _LOGGER.info("Battery control configured: mode=%s, charge_power=%s, discharge_power=%s",
                         battery_mode_select or "none", battery_charge_power or "none", 
                         battery_discharge_power or "none")
            
            # If mode select is configured, go to mode mapping step
            if battery_mode_select:
                return await self.async_step_mode_mapping()
            
            # Otherwise proceed directly to pricing
            return await self.async_step_pricing()
        
        # Auto-detect battery control entities
        return await self._show_battery_control_form()
    
    async def async_step_mode_mapping(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Map battery mode select options to standard modes (self_use, backup, force_charge)."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            # Store mode mappings
            self._detected_entities[CONF_MODE_SELF_USE] = user_input.get(CONF_MODE_SELF_USE)
            self._detected_entities[CONF_MODE_BACKUP] = user_input.get(CONF_MODE_BACKUP)
            self._detected_entities[CONF_MODE_FORCE_CHARGE] = user_input.get(CONF_MODE_FORCE_CHARGE)
            
            _LOGGER.info("Mode mapping configured: self_use=%s, backup=%s, force_charge=%s",
                         user_input.get(CONF_MODE_SELF_USE),
                         user_input.get(CONF_MODE_BACKUP),
                         user_input.get(CONF_MODE_FORCE_CHARGE))
            
            # Proceed to pricing configuration
            return await self.async_step_pricing()
        
        # Get the mode select entity and fetch its available options
        mode_select_entity = self._detected_entities.get(CONF_BATTERY_MODE_SELECT)
        available_options = []
        
        if mode_select_entity:
            # Try to get available options from the entity's state
            state = self.hass.states.get(mode_select_entity)
            if state and state.attributes:
                available_options = state.attributes.get("options", [])
                _LOGGER.info("Mode select entity %s has options: %s", mode_select_entity, available_options)
        
        # Try to auto-detect FoxESS default mappings
        default_self_use = ""
        default_backup = ""
        default_force_charge = ""
        
        if available_options:
            # Common FoxESS H3 mode names
            for option in available_options:
                option_lower = option.lower()
                if "self" in option_lower and "use" in option_lower:
                    default_self_use = option
                elif "backup" in option_lower:
                    default_backup = option
                elif "force" in option_lower and "charge" in option_lower:
                    default_force_charge = option
        
        from homeassistant.helpers import selector
        
        # Build schema with dropdowns if options are available
        if available_options:
            schema = {
                vol.Required(
                    CONF_MODE_SELF_USE,
                    default=default_self_use,
                    description=f"Select the mode option for '{BATTERY_MODE_NAMES['self_use']}'",
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=available_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
                vol.Required(
                    CONF_MODE_BACKUP,
                    default=default_backup,
                    description=f"Select the mode option for '{BATTERY_MODE_NAMES['backup']}'",
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=available_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
                vol.Required(
                    CONF_MODE_FORCE_CHARGE,
                    default=default_force_charge,
                    description=f"Select the mode option for '{BATTERY_MODE_NAMES['force_charge']}'",
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=available_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
            }
        else:
            # Fallback to text inputs if we can't fetch options
            schema = {
                vol.Required(
                    CONF_MODE_SELF_USE,
                    default="Self Use",
                    description=f"Enter the exact option value for '{BATTERY_MODE_NAMES['self_use']}'",
                ): str,
                vol.Required(
                    CONF_MODE_BACKUP,
                    default="Backup",
                    description=f"Enter the exact option value for '{BATTERY_MODE_NAMES['backup']}'",
                ): str,
                vol.Required(
                    CONF_MODE_FORCE_CHARGE,
                    default="Force Charge",
                    description=f"Enter the exact option value for '{BATTERY_MODE_NAMES['force_charge']}'",
                ): str,
            }
        
        return self.async_show_form(
            step_id="mode_mapping",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={
                "entity": mode_select_entity or "Unknown",
                "options": ", ".join(available_options) if available_options else "Could not detect options",
            },
        )
    
    async def async_step_pricing(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Configure dynamic pricing, battery specs, and control mode."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            # Validate pricing inputs
            epex_markup = user_input.get(CONF_EPEX_MARKUP, DEFAULT_EPEX_MARKUP)
            dry_run_mode = user_input.get(CONF_DRY_RUN_MODE, False)
            battery_capacity = user_input.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)
            battery_max_power = user_input.get(CONF_BATTERY_MAX_POWER, DEFAULT_BATTERY_MAX_POWER)
            
            try:
                epex_markup = float(epex_markup)
                if epex_markup < 0 or epex_markup > 1:
                    errors[CONF_EPEX_MARKUP] = "Markup must be between 0 and 1 €/kWh"
            except (ValueError, TypeError):
                errors[CONF_EPEX_MARKUP] = "Invalid number format"
            
            try:
                battery_capacity = float(battery_capacity)
                if battery_capacity < 1 or battery_capacity > 100:
                    errors[CONF_BATTERY_CAPACITY] = "Battery capacity must be between 1 and 100 kWh"
            except (ValueError, TypeError):
                errors[CONF_BATTERY_CAPACITY] = "Invalid number format"
            
            try:
                battery_max_power = float(battery_max_power)
                if battery_max_power < 0.5 or battery_max_power > 20:
                    errors[CONF_BATTERY_MAX_POWER] = "Battery max power must be between 0.5 and 20 kW"
            except (ValueError, TypeError):
                errors[CONF_BATTERY_MAX_POWER] = "Invalid number format"
            
            if not errors:
                # Store pricing, battery specs, and control mode configuration
                self._detected_entities[CONF_EPEX_MARKUP] = epex_markup
                self._detected_entities[CONF_DRY_RUN_MODE] = dry_run_mode
                self._detected_entities[CONF_BATTERY_CAPACITY] = battery_capacity
                self._detected_entities[CONF_BATTERY_MAX_POWER] = battery_max_power
                
                _LOGGER.info(
                    "Pricing configured: markup=%.3f€/kWh, dry_run=%s",
                    epex_markup, dry_run_mode
                )
                _LOGGER.info(
                    "Battery configured: capacity=%.1fkWh, max_power=%.2fkW",
                    battery_capacity, battery_max_power
                )
                
                # Create config entry (historic data backfill will happen on first run)
                return self.async_create_entry(
                    title="intuiHEMS",
                    data={
                        CONF_SERVICE_URL: self._service_url,
                        CONF_API_KEY: self._api_key,
                        CONF_UPDATE_INTERVAL: self._update_interval,
                        CONF_DETECTED_ENTITIES: self._detected_entities,
                        CONF_USER_EMAIL: self._user_email,
                        CONF_MARKETING_CONSENT: self._marketing_consent,
                        CONF_SAVINGS_REPORT_CONSENT: self._savings_report_consent,
                    },
                )
        
        return self.async_show_form(
            step_id="pricing",
            data_schema=vol.Schema({
                vol.Required(CONF_BATTERY_CAPACITY, default=DEFAULT_BATTERY_CAPACITY, description="Total usable battery capacity in kWh. This is the energy your battery can store and use. Example: 10 for a 10 kWh battery."): vol.All(vol.Coerce(float), vol.Range(min=1.0, max=100.0)),
                vol.Required(CONF_BATTERY_MAX_POWER, default=DEFAULT_BATTERY_MAX_POWER, description="Maximum charging/discharging rate in kW. Limits how fast the battery can charge or discharge. Example: 3 for a 3 kW inverter."): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=20.0)),
                vol.Required(CONF_EPEX_MARKUP, default=DEFAULT_EPEX_MARKUP, description="Additional cost on top of EPEX spot price in €/kWh (taxes, fees, supplier margin). Example: 0.15 if you pay 15 cents above spot price."): vol.Coerce(float),
                vol.Optional(CONF_DRY_RUN_MODE, default=False, description="Enable to see optimization recommendations without controlling your battery. Perfect for testing the system safely."): bool,
            }),
            errors=errors,
            description_placeholders={
                "dry_run_info": "Enable dry run mode to see optimization recommendations without controlling your battery. Perfect for testing!"
            },
        )

    async def _save_learned_device(self, control_entities: dict[str, str]) -> None:
        """Save learned device configuration.
        
        Args:
            control_entities: User-selected control entities
        """
        if not self._device_info:
            return
        
        # Initialize learning store if needed
        if not self._device_learning_store:
            try:
                self._device_learning_store = await async_setup_device_learning(self.hass)
            except Exception as err:
                _LOGGER.error("Could not initialize device learning: %s", err)
                return
        
        # Check if this is a new device (not in built-in mappings)
        platform = self._device_info.get("platform", "").lower()
        manufacturer = self._device_info.get("manufacturer", "").lower()
        model = self._device_info.get("model", "").lower()
        
        is_unknown_device = True
        for (map_platform, map_manufacturer, map_model), _ in DEVICE_CONTROL_MAPPINGS.items():
            if platform == map_platform.lower():
                if map_manufacturer and map_manufacturer.lower() in manufacturer:
                    if not map_model or map_model.lower() in model:
                        is_unknown_device = False
                        break
        
        if is_unknown_device and control_entities:
            _LOGGER.info(
                "Saving learned configuration for unknown device: %s %s",
                self._device_info.get("manufacturer"),
                self._device_info.get("model"),
            )
            
            # Save the configuration (with opt-in for community sharing)
            await self._device_learning_store.async_save_device_config(
                device_info=self._device_info,
                control_entities=control_entities,
                user_notes=f"Configured via IntuiTherm setup on {self.hass.config.location_name}",
                share_with_community=True,  # User can opt-out in settings later
            )

    def _is_cumulative_sensor(self, entity_id: str) -> bool:
        """Check if sensor is cumulative (kWh, total_increasing)."""
        state = self.hass.states.get(entity_id)
        if not state:
            return False
        
        attrs = state.attributes
        unit = attrs.get("unit_of_measurement", "").lower()
        device_class = attrs.get("device_class")
        state_class = attrs.get("state_class")
        
        return (
            device_class == "energy" or
            state_class == "total_increasing" or
            unit in ["kwh", "wh", "mwh"] or
            "total" in entity_id.lower()
        )
    
    async def _show_review_form(self) -> config_entries.FlowResult:
        """Show the review & select form with recommended sensors (CUMULATIVE ONLY)."""
        entity_registry = er.async_get(self.hass)
        
        # Get all detected sensors for dropdowns
        solar_sensors = self._detected_entities.get(CONF_SOLAR_SENSORS, [])
        battery_charge = self._detected_entities.get(CONF_BATTERY_CHARGE_SENSORS, [])
        battery_discharge = self._detected_entities.get(CONF_BATTERY_DISCHARGE_SENSORS, [])
        grid_import = self._detected_entities.get(CONF_GRID_IMPORT_SENSORS, [])
        grid_export = self._detected_entities.get(CONF_GRID_EXPORT_SENSORS, [])
        battery_soc = self._detected_entities.get(CONF_BATTERY_SOC_ENTITY)
        
        # Debug logging to help diagnose empty form issues
        _LOGGER.info("Review form - detected entities summary:")
        _LOGGER.info("  Solar sensors: %d", len(solar_sensors))
        _LOGGER.info("  Battery SoC: %s", battery_soc)
        _LOGGER.info("  Battery charge sensors: %d", len(battery_charge))
        _LOGGER.info("  Battery discharge sensors: %d", len(battery_discharge))
        _LOGGER.info("  Grid import sensors: %d", len(grid_import))
        _LOGGER.info("  Grid export sensors: %d", len(grid_export))
        
        # Pick recommended sensors (first cumulative one of each type)
        # We calculate them but don't use them for defaults anymore (per user request)
        recommended_solar = None
        if solar_sensors:
            # Prefer solar_energy_total, then other _total sensors
            for sensor in solar_sensors:
                if "solar_energy_total" in sensor.lower():
                    recommended_solar = sensor
                    break
            # Fallback to any _total sensor
            if not recommended_solar:
                for sensor in solar_sensors:
                    if "total" in sensor.lower() and "today" not in sensor.lower():
                        recommended_solar = sensor
                        break
            if not recommended_solar:
                recommended_solar = solar_sensors[0]
        
        # Build list of options for selector (just entity IDs)
        def build_selector_options(sensor_list):
            """Build options list for selector."""
            return [sensor_id for sensor_id in sensor_list]
        
        # Import selector
        from homeassistant.helpers import selector
        
        # Build the schema using selectors that allow custom values
        schema = {}
        
        # Solar production (required) - Scan ALL cumulative kWh sensors
        all_cumulative_energy = []
        for entry in entity_registry.entities.values():
            if entry.domain != "sensor" or entry.disabled_by:
                continue
            state = self.hass.states.get(entry.entity_id)
            if not state:
                continue
            
            attrs = state.attributes
            unit = attrs.get("unit_of_measurement", "").lower()
            device_class = attrs.get("device_class")
            state_class = attrs.get("state_class")
            
            # Check if cumulative energy sensor
            is_cumulative = (
                device_class == "energy" or
                state_class == "total_increasing" or
                unit in ["kwh", "wh"]
            )
            
            if is_cumulative:
                all_cumulative_energy.append(entry.entity_id)
        
        # Always show dropdown with all cumulative energy sensors for solar
        _LOGGER.info("Found %d total cumulative energy sensors for solar selection", len(all_cumulative_energy))
        schema[vol.Required(
            "solar_production",
            description="Required: Cumulative solar energy sensor (kWh, total_increasing)"
        )] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=build_selector_options(all_cumulative_energy) if all_cumulative_energy else [],
                mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        )
        
        # Battery SoC (required) - Scan ALL % sensors
        all_soc_sensors = []
        for entry in entity_registry.entities.values():
            if entry.domain != "sensor" or entry.disabled_by:
                continue
            state = self.hass.states.get(entry.entity_id)
            if not state:
                continue
            
            attrs = state.attributes
            unit = attrs.get("unit_of_measurement", "").lower()
            device_class = attrs.get("device_class")
            
            # Check if battery/SoC sensor (% unit)
            is_soc = (
                device_class == "battery" or
                unit == "%" or
                "soc" in entry.entity_id.lower() or
                "battery" in entry.entity_id.lower()
            )
            
            if is_soc and unit == "%":  # Require % unit for SoC
                all_soc_sensors.append(entry.entity_id)
        
        # Always show dropdown with all % sensors for battery SoC
        _LOGGER.info("Found %d total battery SoC sensors (%%)", len(all_soc_sensors))
        schema[vol.Required(
            "battery_soc",
            description="Required: Battery State of Charge sensor (%)"
        )] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=all_soc_sensors if all_soc_sensors else [],
                mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        )
        
        # House load (required) - Use same cumulative energy list as solar
        # (user can select any cumulative kWh sensor for house load)
        _LOGGER.info("Offering %d cumulative energy sensors for house load selection", len(all_cumulative_energy))
        schema[vol.Required(
            "house_load",
            description="Required: Cumulative house energy sensor (kWh, total_increasing)"
        )] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=build_selector_options(all_cumulative_energy) if all_cumulative_energy else [],
                mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        )
        
        return self.async_show_form(
            step_id="review",
            data_schema=vol.Schema(schema),
            errors={},
        )

    async def _show_battery_control_form(self) -> config_entries.FlowResult:
        """Show battery control entity selection form (optional, can be skipped)."""
        entity_registry = er.async_get(self.hass)
        device_registry = dr.async_get(self.hass)
        
        # Get battery SoC entity to find associated device
        battery_soc_entity = self._detected_entities.get(CONF_BATTERY_SOC_ENTITY)
        
        # Auto-detect battery control entities from device registry
        detected_mode_select = None
        detected_charge_power = None
        detected_discharge_power = None
        
        if battery_soc_entity:
            # Get device ID from battery SoC sensor
            soc_entry = entity_registry.entities.get(battery_soc_entity)
            if soc_entry and soc_entry.device_id:
                device_id = soc_entry.device_id
                device = device_registry.async_get(device_id)
                
                if device:
                    _LOGGER.info("Found battery device: %s (%s)", 
                                 device.name or device.name_by_user, device.manufacturer)
                    
                    # Scan all entities on this device
                    for entry in entity_registry.entities.values():
                        if entry.device_id != device_id or entry.disabled_by:
                            continue
                        
                        entity_id = entry.entity_id
                        entity_id_lower = entity_id.lower()
                        
                        # Look for mode select entity
                        if entry.domain == "select" and not detected_mode_select:
                            if any(keyword in entity_id_lower for keyword in ["mode", "work_mode", "battery_mode"]):
                                detected_mode_select = entity_id
                                _LOGGER.info("Detected battery mode select: %s", entity_id)
                        
                        # Look for charge power control
                        if entry.domain == "number" and not detected_charge_power:
                            if any(keyword in entity_id_lower for keyword in ["charge_power", "charge_limit", "max_charge"]):
                                detected_charge_power = entity_id
                                _LOGGER.info("Detected charge power control: %s", entity_id)
                        
                        # Look for discharge power control
                        if entry.domain == "number" and not detected_discharge_power:
                            if any(keyword in entity_id_lower for keyword in ["discharge_power", "discharge_limit", "max_discharge"]):
                                detected_discharge_power = entity_id
                                _LOGGER.info("Detected discharge power control: %s", entity_id)
        
        # Build selector options for each control type
        from homeassistant.helpers import selector
        
        # Get all select entities (for mode selector)
        all_select_entities = []
        for entry in entity_registry.entities.values():
            if entry.domain == "select" and not entry.disabled_by:
                all_select_entities.append(entry.entity_id)
        
        # Get all number entities (for power controls)
        all_number_entities = []
        for entry in entity_registry.entities.values():
            if entry.domain == "number" and not entry.disabled_by:
                all_number_entities.append(entry.entity_id)
        
        # Build schema
        schema = {}
        
        schema[vol.Optional(
            CONF_BATTERY_MODE_SELECT,
            default=detected_mode_select or "",
            description="Battery mode select entity (e.g., select.battery_mode, select.work_mode). Leave empty to skip control."
        )] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=all_select_entities if all_select_entities else [],
                mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        )
        
        schema[vol.Optional(
            CONF_BATTERY_CHARGE_POWER,
            default=detected_charge_power or "",
            description="Battery charge power control entity (e.g., number.battery_charge_power). Leave empty to skip."
        )] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=all_number_entities if all_number_entities else [],
                mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        )
        
        schema[vol.Optional(
            CONF_BATTERY_DISCHARGE_POWER,
            default=detected_discharge_power or "",
            description="Battery discharge power control entity (e.g., number.battery_discharge_power). Leave empty to skip."
        )] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=all_number_entities if all_number_entities else [],
                mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        )
        
        return self.async_show_form(
            step_id="battery_control",
            data_schema=vol.Schema(schema),
            errors={},
            description_placeholders={
                "info": "Configure battery control entities. These are optional - leave empty if you don't have battery control or want demo mode only."
            },
        )

    async def _get_energy_prefs(self) -> dict[str, Any] | None:
        """Get Home Assistant Energy Dashboard preferences."""
        try:
            _LOGGER.debug("Checking for Energy Dashboard data...")
            
            # Try energy_manager first (modern HA)
            if "energy_manager" in self.hass.data:
                energy_manager = self.hass.data["energy_manager"]
                _LOGGER.debug("Found energy_manager: %s", type(energy_manager))
                _LOGGER.debug("energy_manager methods: %s", dir(energy_manager))
                
                # Try async_get_prefs method
                if hasattr(energy_manager, "async_get_prefs"):
                    prefs = await energy_manager.async_get_prefs()
                    _LOGGER.debug("Got energy preferences from energy_manager.async_get_prefs(): %s", prefs is not None)
                    return prefs
                # Try data property
                elif hasattr(energy_manager, "data"):
                    prefs = energy_manager.data
                    _LOGGER.debug("Got energy preferences from energy_manager.data: %s", prefs is not None)
                    return prefs
                else:
                    _LOGGER.debug("energy_manager has no async_get_prefs or data")
            
            # Fallback to energy key (older HA or dict storage)
            if "energy" in self.hass.data:
                energy_data = self.hass.data["energy"]
                _LOGGER.debug("Found energy: %s", type(energy_data))
                if isinstance(energy_data, dict):
                    _LOGGER.debug("Energy is a dict, returning directly")
                    return energy_data
                elif hasattr(energy_data, "async_get_prefs"):
                    prefs = await energy_data.async_get_prefs()
                    _LOGGER.debug("Got energy preferences from energy.async_get_prefs(): %s", prefs is not None)
                    return prefs
            
            _LOGGER.debug("No usable energy data found in hass.data")
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Failed to get energy preferences")

        return None

    async def _discover_devices(
        self, energy_prefs: dict[str, Any]
    ) -> dict[str, Any]:
        """Discover devices from energy entities."""
        entity_registry = er.async_get(self.hass)
        device_registry = dr.async_get(self.hass)

        devices = {}
        energy_entities = []

        # Extract entity IDs from energy sources
        for source in energy_prefs.get("energy_sources", []):
            if source.get("type") == "solar":
                entity_id = source.get("stat_energy_from")
                if entity_id:
                    energy_entities.append(entity_id)

            elif source.get("type") == "battery":
                entity_id = source.get("stat_energy_to")
                if entity_id:
                    energy_entities.append(entity_id)
                entity_id = source.get("stat_energy_from")
                if entity_id:
                    energy_entities.append(entity_id)

            elif source.get("type") == "grid":
                for flow in source.get("flow_from", []):
                    entity_id = flow.get("stat_energy_from")
                    if entity_id:
                        energy_entities.append(entity_id)
                for flow in source.get("flow_to", []):
                    entity_id = flow.get("stat_energy_to")
                    if entity_id:
                        energy_entities.append(entity_id)

        # Get devices for these entities
        for entity_id in energy_entities:
            entry = entity_registry.async_get(entity_id)
            if entry and entry.device_id:
                device = device_registry.async_get(entry.device_id)
                if device and entry.device_id not in devices:
                    devices[entry.device_id] = {
                        "name": device.name_by_user or device.name,
                        "manufacturer": device.manufacturer,
                        "model": device.model,
                        "platform": entry.platform,
                    }

        return devices

    async def _find_power_sensors(self, device_id: str) -> dict[str, Any]:
        """Find relevant power/energy sensors and control entities on a device.
        
        Priority: Cumulative energy sensors (_total, total_increasing) over instantaneous power.
        Collects ALL sensors of each type for multi-sensor support.
        """
        entity_registry = er.async_get(self.hass)
        device_registry = dr.async_get(self.hass)

        # Get device info to check for known inverter brands
        device = device_registry.async_get(device_id)
        device_info = None
        control_entities = {}
        
        if device:
            device_info = {
                "name": device.name_by_user or device.name,
                "manufacturer": device.manufacturer,
                "model": device.model,
            }
            _LOGGER.info(
                "Checking device: %s (manufacturer=%s, model=%s)",
                device_info["name"],
                device_info["manufacturer"],
                device_info["model"],
            )

        device_entities = er.async_entries_for_device(
            entity_registry, device_id, include_disabled_entities=False
        )

        # Collect ALL sensors (not just first match)
        pv_sensors = []  # All PV/solar sensors
        battery_charge_sensors = []  # Battery charge energy
        battery_discharge_sensors = []  # Battery discharge energy
        grid_consumption_sensors = []  # Grid import
        grid_feedin_sensors = []  # Grid export
        battery_soc_sensor = None  # Only one SoC needed
        house_load_sensor = None  # House consumption

        for entry in device_entities:
            if entry.domain != "sensor":
                continue

            state = self.hass.states.get(entry.entity_id)
            if not state or state.state in ["unavailable", "unknown"]:
                continue

            attrs = state.attributes
            entity_lower = entry.entity_id.lower()
            unit = attrs.get("unit_of_measurement", "").lower()
            device_class = attrs.get("device_class")
            state_class = attrs.get("state_class")
            
            # Determine if cumulative (prefer these)
            is_cumulative = (
                device_class == "energy" or
                state_class == "total_increasing" or
                unit in ["kwh", "wh"] or
                "total" in entity_lower
            )
            
            sensor_info = {
                "entity_id": entry.entity_id,
                "name": attrs.get("friendly_name", entry.entity_id),
                "unit": unit,
                "is_cumulative": is_cumulative,
                "device_class": device_class,
                "state_class": state_class,
            }

            # Battery SOC (%) - only need one
            if (device_class == "battery" or "soc" in entity_lower) and unit == "%":
                if not battery_soc_sensor:
                    battery_soc_sensor = sensor_info
                    _LOGGER.debug("   Found Battery SoC: %s", entry.entity_id)

            # PV/Solar sensors - collect ALL (pv1, pv2, etc.)
            elif any(x in entity_lower for x in ["pv", "solar"]) and not any(x in entity_lower for x in ["battery", "grid"]):
                # Prefer cumulative (_total, _energy_total)
                if is_cumulative or device_class in ["energy", "power"]:
                    pv_sensors.append(sensor_info)
                    _LOGGER.debug("   Found PV sensor: %s [%s]", entry.entity_id, "cumulative" if is_cumulative else "instantaneous")

            # Battery charge sensors
            elif any(x in entity_lower for x in ["battery_charge", "bat_charge"]) and "discharge" not in entity_lower:
                if is_cumulative or device_class in ["energy", "power"]:
                    battery_charge_sensors.append(sensor_info)
                    _LOGGER.debug("   Found Battery Charge: %s [%s]", entry.entity_id, "cumulative" if is_cumulative else "instantaneous")

            # Battery discharge sensors
            elif any(x in entity_lower for x in ["battery_discharge", "bat_discharge"]):
                if is_cumulative or device_class in ["energy", "power"]:
                    battery_discharge_sensors.append(sensor_info)
                    _LOGGER.debug("   Found Battery Discharge: %s [%s]", entry.entity_id, "cumulative" if is_cumulative else "instantaneous")

            # Grid consumption (import from grid)
            elif any(x in entity_lower for x in ["grid_consumption", "meter_consumption", "import"]) and "export" not in entity_lower:
                if is_cumulative or device_class in ["energy", "power"]:
                    grid_consumption_sensors.append(sensor_info)
                    _LOGGER.debug("   Found Grid Consumption: %s [%s]", entry.entity_id, "cumulative" if is_cumulative else "instantaneous")

            # Grid feed-in (export to grid)
            elif any(x in entity_lower for x in ["feed_in", "feedin", "grid_export", "export"]):
                if is_cumulative or device_class in ["energy", "power"]:
                    grid_feedin_sensors.append(sensor_info)
                    _LOGGER.debug("   Found Grid Feed-in: %s [%s]", entry.entity_id, "cumulative" if is_cumulative else "instantaneous")

            # House load/consumption
            elif any(x in entity_lower for x in ["house", "load", "home"]) and "grid" not in entity_lower:
                if device_class in ["energy", "power"] and not house_load_sensor:
                    house_load_sensor = sensor_info
                    _LOGGER.debug("   Found House Load: %s [%s]", entry.entity_id, "cumulative" if is_cumulative else "instantaneous")

        # Sort each list to prefer cumulative sensors
        pv_sensors.sort(key=lambda x: (not x["is_cumulative"], x["entity_id"]))
        battery_charge_sensors.sort(key=lambda x: (not x["is_cumulative"], x["entity_id"]))
        battery_discharge_sensors.sort(key=lambda x: (not x["is_cumulative"], x["entity_id"]))
        grid_consumption_sensors.sort(key=lambda x: (not x["is_cumulative"], x["entity_id"]))
        grid_feedin_sensors.sort(key=lambda x: (not x["is_cumulative"], x["entity_id"]))

        candidates = {
            "solar_power": pv_sensors[0] if pv_sensors else None,  # First (best) PV sensor for backward compat
            "battery_soc": battery_soc_sensor,
            "house_load": house_load_sensor,
            "device_info": device_info,
            "control_entities": control_entities,
            # NEW: Multi-sensor support
            "all_pv_sensors": pv_sensors,
            "all_battery_charge_sensors": battery_charge_sensors,
            "all_battery_discharge_sensors": battery_discharge_sensors,
            "all_grid_consumption_sensors": grid_consumption_sensors,
            "all_grid_feedin_sensors": grid_feedin_sensors,
        }

        # If we have device info, try to detect battery control entities
        if device and device_info:
            control_entities = self._detect_battery_control_entities(
                device, device_entities, entity_registry
            )
            candidates["control_entities"] = control_entities
            
            if control_entities:
                _LOGGER.info(
                    "Detected battery control entities on %s: %s",
                    device_info["name"],
                    control_entities,
                )

        return candidates

    async def _find_sensors_by_pattern(self) -> dict[str, Any]:
        """Fallback: Find sensors by pattern matching across all entities."""
        entity_registry = er.async_get(self.hass)

        candidates = {
            "solar_power": None,
            "battery_soc": None,
            "house_load": None,
        }

        for entry in entity_registry.entities.values():
            if entry.domain != "sensor" or entry.disabled_by:
                continue

            state = self.hass.states.get(entry.entity_id)
            if not state or state.state in ["unavailable", "unknown"]:
                continue

            attrs = state.attributes
            entity_lower = entry.entity_id.lower()

            # Battery SOC - look for % unit and common keywords
            if not candidates["battery_soc"]:
                if attrs.get("unit_of_measurement") == "%":
                    if any(x in entity_lower for x in ["battery", "bat", "soc"]):
                        candidates["battery_soc"] = {
                            "entity_id": entry.entity_id,
                            "name": attrs.get("friendly_name", entry.entity_id),
                            "confidence": "medium",
                        }

            # Solar power - look for kW/W and PV/solar keywords
            if not candidates["solar_power"]:
                unit = attrs.get("unit_of_measurement", "").lower()
                if unit in ["kw", "w"]:
                    if any(x in entity_lower for x in ["pv", "solar", "photovoltaic"]):
                        # Prefer combined sensors over individual strings
                        if "power" in entity_lower and "_1" not in entity_lower and "_2" not in entity_lower:
                            candidates["solar_power"] = {
                                "entity_id": entry.entity_id,
                                "name": attrs.get("friendly_name", entry.entity_id),
                                "confidence": "high",
                            }
                        elif not candidates.get("solar_power"):
                            candidates["solar_power"] = {
                                "entity_id": entry.entity_id,
                                "name": attrs.get("friendly_name", entry.entity_id),
                                "confidence": "medium",
                            }

            # House load - look for kW/W and house/load keywords
            if not candidates["house_load"]:
                unit = attrs.get("unit_of_measurement", "").lower()
                if unit in ["kw", "w"]:
                    if any(x in entity_lower for x in ["house", "load", "consumption", "home"]):
                        # Skip utility meter totals, but allow daily/hourly if they're power sensors
                        if unit in ["kw", "w"] or not any(x in entity_lower for x in ["total", "sum"]):
                            candidates["house_load"] = {
                                "entity_id": entry.entity_id,
                                "name": attrs.get("friendly_name", entry.entity_id),
                                "confidence": "medium",
                            }

        return candidates

    def _classify_sensor(self, entity_id: str) -> dict[str, Any]:
        """Classify sensor as cumulative or instantaneous.
        
        Args:
            entity_id: Entity ID to classify
            
        Returns:
            Dictionary with sensor classification:
                - type: "cumulative" or "instantaneous" or "unknown"
                - unit: Unit of measurement
                - device_class: Device class
                - state_class: State class
                - confidence: "high" or "medium" or "low"
                - note: Human-readable description
        """
        state = self.hass.states.get(entity_id)
        if not state:
            return {
                "type": "unknown",
                "unit": None,
                "device_class": None,
                "state_class": None,
                "confidence": "low",
                "note": "Entity not found"
            }
        
        unit = state.attributes.get("unit_of_measurement", "").lower()
        device_class = state.attributes.get("device_class")
        state_class = state.attributes.get("state_class")
        
        # Cumulative (preferred for reliability)
        is_cumulative = (
            unit in ["kwh", "wh", "mwh"] or
            device_class == "energy" or
            state_class == "total_increasing"
        )
        
        # Instantaneous (acceptable)
        is_instantaneous = (
            unit in ["kw", "w", "mw"] or
            device_class == "power" or
            state_class == "measurement"
        )
        
        if is_cumulative:
            return {
                "type": "cumulative",
                "unit": unit,
                "device_class": device_class,
                "state_class": state_class,
                "confidence": "high",
                "note": "Cumulative energy - backend will compute power derivative"
            }
        elif is_instantaneous:
            return {
                "type": "instantaneous",
                "unit": unit,
                "device_class": device_class,
                "state_class": state_class,
                "confidence": "medium",
                "note": "Instantaneous power reading"
            }
        else:
            return {
                "type": "unknown",
                "unit": unit,
                "device_class": device_class,
                "state_class": state_class,
                "confidence": "low",
                "note": f"Unknown sensor type (unit={unit})"
            }

    async def _validate_sensor(self, entity_id: str) -> dict[str, Any]:
        """Validate sensor has valid, recent data.
        
        Args:
            entity_id: Entity ID to validate
            
        Returns:
            Dictionary with validation results:
                - valid: True if sensor is valid
                - issue: Description of issue if not valid
                - current_value: Current sensor value
                - unit: Unit of measurement
                - last_updated: Last update timestamp
                - age_seconds: Age of last update in seconds
        """
        from homeassistant.util import dt as dt_util
        
        state = self.hass.states.get(entity_id)
        
        # Check 1: Entity exists
        if not state:
            return {"valid": False, "issue": "entity_not_found"}
        
        # Check 2: Available
        if state.state in ["unavailable", "unknown"]:
            return {"valid": False, "issue": "currently_unavailable", "state": state.state}
        
        # Check 3: Numeric value
        try:
            value = float(state.state)
        except (ValueError, TypeError):
            return {"valid": False, "issue": "non_numeric_state", "state": state.state}
        
        # Check 4: Recent data (< 10 min old)
        now = dt_util.utcnow()
        age_seconds = (now - state.last_updated).total_seconds()
        if age_seconds > 600:
            return {
                "valid": False,
                "issue": "stale_data",
                "age_minutes": int(age_seconds / 60),
                "last_updated": state.last_updated
            }
        
        # Check 5: Unit of measurement exists
        unit = state.attributes.get("unit_of_measurement")
        if not unit:
            return {"valid": False, "issue": "no_unit"}
        
        return {
            "valid": True,
            "current_value": value,
            "unit": unit,
            "last_updated": state.last_updated,
            "age_seconds": int(age_seconds),
        }

    async def _validate_detected_sensors(self) -> None:
        """Validate all detected sensors and log results."""
        # Non-entity configuration keys to skip
        non_entity_keys = {CONF_INSTANCE_ID, CONF_USER_ID, CONF_REGISTERED_AT}
        
        for key, value in self._detected_entities.items():
            if not value:
                continue
            
            # Skip non-entity configuration keys (instance_id, user_id, etc.)
            if key in non_entity_keys:
                continue
            
            # Skip list values (multi-sensor lists)
            if isinstance(value, list):
                continue
            
            # Validate single entity_id
            if isinstance(value, str):
                validation = await self._validate_sensor(value)
                if validation["valid"]:
                    _LOGGER.info(
                        "  ✅ %s: Valid (value=%.2f %s, age=%ds)",
                        key,
                        validation["current_value"],
                        validation["unit"],
                        validation["age_seconds"]
                    )
                else:
                    _LOGGER.warning(
                        "  ⚠️  %s: %s",
                        key,
                        validation["issue"]
                    )

    def _detect_battery_control_entities(
        self,
        device: dr.DeviceEntry,
        device_entities: list[er.RegistryEntry],
        entity_registry: er.EntityRegistry,
    ) -> dict[str, str]:
        """Detect battery control entities based on device manufacturer/model.
        
        Args:
            device: Device registry entry
            device_entities: List of entities for this device
            entity_registry: Entity registry
            
        Returns:
            Dictionary with detected control entities:
                - battery_mode_select: select entity for battery work mode
                - battery_charge_power: number entity for charge power
                - battery_discharge_power: number entity for discharge power
        """
        control_entities = {}
        
        # Find matching device mapping
        platform = None
        for entry in device_entities:
            if entry.platform:
                platform = entry.platform
                break
        
        if not platform:
            _LOGGER.debug("No platform found for device %s", device.name)
            return control_entities
        
        # Check if this device matches any known control mappings
        mapping = None
        manufacturer_lower = (device.manufacturer or "").lower()
        model_lower = (device.model or "").lower()
        
        for (map_platform, map_manufacturer, map_model), patterns in DEVICE_CONTROL_MAPPINGS.items():
            # Check platform match
            if platform.lower() != map_platform.lower():
                continue
            
            # Check manufacturer match (case-insensitive partial match)
            if map_manufacturer and map_manufacturer.lower() not in manufacturer_lower:
                continue
            
            # Check model match if specified (case-insensitive partial match)
            if map_model and map_model.lower() not in model_lower:
                continue
            
            # Found a match!
            mapping = patterns
            _LOGGER.info(
                "Found control mapping for %s %s (platform=%s)",
                device.manufacturer,
                device.model,
                platform,
            )
            break
        
        if not mapping:
            _LOGGER.debug(
                "No control mapping found for platform=%s, manufacturer=%s, model=%s",
                platform,
                device.manufacturer,
                device.model,
            )
            return control_entities
        
        # Search device entities for control entities using patterns
        for entry in device_entities:
            entity_lower = entry.entity_id.lower()
            
            # Look for mode select entity
            if entry.domain == "select" and not control_entities.get(CONF_BATTERY_MODE_SELECT):
                for pattern in mapping.get("mode_select_patterns", []):
                    if pattern.lower() in entity_lower:
                        control_entities[CONF_BATTERY_MODE_SELECT] = entry.entity_id
                        _LOGGER.info(
                            "Detected battery mode select: %s (pattern=%s)",
                            entry.entity_id,
                            pattern,
                        )
                        break
            
            # Look for charge power entity
            if entry.domain == "number" and not control_entities.get(CONF_BATTERY_CHARGE_POWER):
                for pattern in mapping.get("charge_power_patterns", []):
                    if pattern.lower() in entity_lower:
                        control_entities[CONF_BATTERY_CHARGE_POWER] = entry.entity_id
                        _LOGGER.info(
                            "Detected battery charge power: %s (pattern=%s)",
                            entry.entity_id,
                            pattern,
                        )
                        break
            
            # Look for discharge power entity
            if entry.domain == "number" and not control_entities.get(CONF_BATTERY_DISCHARGE_POWER):
                for pattern in mapping.get("discharge_power_patterns", []):
                    if pattern.lower() in entity_lower:
                        control_entities[CONF_BATTERY_DISCHARGE_POWER] = entry.entity_id
                        _LOGGER.info(
                            "Detected battery discharge power: %s (pattern=%s)",
                            entry.entity_id,
                            pattern,
                        )
                        break
            
            # Look for SolarEdge command mode
            if entry.domain == "select" and not control_entities.get(CONF_SOLAREDGE_COMMAND_MODE):
                for pattern in mapping.get("command_mode_patterns", []):
                    if pattern.lower() in entity_lower:
                        control_entities[CONF_SOLAREDGE_COMMAND_MODE] = entry.entity_id
                        _LOGGER.info(
                            "Detected SolarEdge command mode: %s (pattern=%s)",
                            entry.entity_id,
                            pattern,
                        )
                        break
            
            # Look for grid charge switch (Huawei specific)
            if entry.domain == "switch" and not control_entities.get("grid_charge_switch"):
                for pattern in mapping.get("grid_charge_switch_patterns", []):
                    if pattern.lower() in entity_lower:
                        control_entities["grid_charge_switch"] = entry.entity_id
                        _LOGGER.info(
                            "Detected grid charge switch: %s (pattern=%s)",
                            entry.entity_id,
                            pattern,
                        )
                        break
        
        # For Huawei: explicitly find the battery device ID by looking up which device
        # owns the grid_charge_switch entity (battery-specific entity)
        if platform.lower() == "huawei_solar" and control_entities.get("grid_charge_switch"):
            grid_switch_entity_id = control_entities["grid_charge_switch"]
            grid_switch_entry = entity_registry.entities.get(grid_switch_entity_id)
            
            if grid_switch_entry and grid_switch_entry.device_id:
                # Get the battery device from the entity registry
                from homeassistant.helpers import device_registry as dr
                device_registry = dr.async_get(entity_registry.hass)
                battery_device = device_registry.async_get(grid_switch_entry.device_id)
                
                if battery_device:
                    control_entities["ha_device_id"] = battery_device.id
                    _LOGGER.info(
                        "Stored Huawei battery device ID: %s (device: %s)",
                        battery_device.id,
                        battery_device.name_by_user or battery_device.name
                    )
        
        return control_entities

    async def _check_learned_patterns(self) -> None:
        """Check if we have learned patterns for this device."""
        if not self._device_info:
            return
        
        # Initialize learning store if needed
        if not self._device_learning_store:
            try:
                self._device_learning_store = await async_setup_device_learning(self.hass)
            except Exception as err:
                _LOGGER.debug("Could not initialize device learning: %s", err)
                return
        
        # Look for learned patterns
        learned_patterns = self._device_learning_store.get_learned_patterns(self._device_info)
        if learned_patterns:
            _LOGGER.info(
                "Found learned control patterns for %s %s",
                self._device_info.get("manufacturer"),
                self._device_info.get("model"),
            )
            # Apply learned patterns
            if learned_patterns.get(CONF_BATTERY_MODE_SELECT):
                self._detected_entities[CONF_BATTERY_MODE_SELECT] = learned_patterns[
                    CONF_BATTERY_MODE_SELECT
                ]
            if learned_patterns.get(CONF_BATTERY_CHARGE_POWER):
                self._detected_entities[CONF_BATTERY_CHARGE_POWER] = learned_patterns[
                    CONF_BATTERY_CHARGE_POWER
                ]
            if learned_patterns.get(CONF_BATTERY_DISCHARGE_POWER):
                self._detected_entities[CONF_BATTERY_DISCHARGE_POWER] = learned_patterns[
                    CONF_BATTERY_DISCHARGE_POWER
                ]

    async def _get_all_energy_sensors(self) -> dict[str, list[dict[str, Any]]]:
        """Extract ALL sensors from Energy Dashboard with availability status.
        
        Returns dict with lists of sensors grouped by type:
        - solar: all solar production sensors
        - battery_discharge: battery discharge sensors
        - battery_charge: battery charge sensors  
        - grid_import: grid consumption sensors
        - grid_export: grid feed-in sensors
        """
        sensors = {
            "solar": [],
            "battery_discharge": [],
            "battery_charge": [],
            "grid_import": [],
            "grid_export": [],
        }

        try:
            energy_prefs = await self._get_energy_prefs()
            if not energy_prefs:
                _LOGGER.debug("Energy Dashboard not configured")
                return sensors

            # Extract all sensors from Energy Dashboard
            for source in energy_prefs.get("energy_sources", []):
                source_type = source.get("type")
                
                if source_type == "solar":
                    # Solar production sensors
                    entity_id = source.get("stat_energy_from")
                    if entity_id:
                        state = self.hass.states.get(entity_id)
                        sensors["solar"].append({
                            "entity_id": entity_id,
                            "name": state.attributes.get("friendly_name", entity_id) if state else entity_id,
                            "available": state is not None and state.state not in ["unavailable", "unknown"],
                            "unit": state.attributes.get("unit_of_measurement", "") if state else "",
                            "state": state.state if state else None,
                        })
                
                elif source_type == "battery":
                    # Battery discharge (stat_energy_from)
                    entity_id = source.get("stat_energy_from")
                    if entity_id:
                        state = self.hass.states.get(entity_id)
                        sensors["battery_discharge"].append({
                            "entity_id": entity_id,
                            "name": state.attributes.get("friendly_name", entity_id) if state else entity_id,
                            "available": state is not None and state.state not in ["unavailable", "unknown"],
                            "unit": state.attributes.get("unit_of_measurement", "") if state else "",
                            "state": state.state if state else None,
                        })
                    
                    # Battery charge (stat_energy_to)
                    entity_id = source.get("stat_energy_to")
                    if entity_id:
                        state = self.hass.states.get(entity_id)
                        sensors["battery_charge"].append({
                            "entity_id": entity_id,
                            "name": state.attributes.get("friendly_name", entity_id) if state else entity_id,
                            "available": state is not None and state.state not in ["unavailable", "unknown"],
                            "unit": state.attributes.get("unit_of_measurement", "") if state else "",
                            "state": state.state if state else None,
                        })
                
                elif source_type == "grid":
                    # Grid import (flow_from)
                    for flow in source.get("flow_from", []):
                        entity_id = flow.get("stat_energy_from")
                        if entity_id:
                            state = self.hass.states.get(entity_id)
                            sensors["grid_import"].append({
                                "entity_id": entity_id,
                                "name": state.attributes.get("friendly_name", entity_id) if state else entity_id,
                                "available": state is not None and state.state not in ["unavailable", "unknown"],
                                "unit": state.attributes.get("unit_of_measurement", "") if state else "",
                                "state": state.state if state else None,
                            })
                    
                    # Grid export (flow_to)
                    for flow in source.get("flow_to", []):
                        entity_id = flow.get("stat_energy_to")
                        if entity_id:
                            state = self.hass.states.get(entity_id)
                            sensors["grid_export"].append({
                                "entity_id": entity_id,
                                "name": state.attributes.get("friendly_name", entity_id) if state else entity_id,
                                "available": state is not None and state.state not in ["unavailable", "unknown"],
                                "unit": state.attributes.get("unit_of_measurement", "") if state else "",
                                "state": state.state if state else None,
                            })

            # Log summary
            _LOGGER.info(
                "Energy Dashboard sensors: solar=%d, battery_discharge=%d, battery_charge=%d, grid_import=%d, grid_export=%d",
                len(sensors["solar"]),
                len(sensors["battery_discharge"]),
                len(sensors["battery_charge"]),
                len(sensors["grid_import"]),
                len(sensors["grid_export"]),
            )

        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Failed to extract Energy Dashboard sensors")

        return sensors

    async def _find_energy_dashboard_sensors(self) -> dict[str, Any]:
        """Find cumulative energy sensors from Energy Dashboard configuration.
        
        Returns cumulative sensors (kWh) which the backend will convert to power (kW)
        via derivatives. These are preferred over instantaneous power sensors.
        """
        candidates = {
            "solar_power": None,
            "battery_soc": None,
            "house_load": None,
        }

        try:
            energy_prefs = await self._get_energy_prefs()
            if not energy_prefs:
                _LOGGER.debug("Energy Dashboard not configured")
                return candidates

            # Extract cumulative energy sensors from Energy Dashboard
            for source in energy_prefs.get("energy_sources", []):
                if source.get("type") == "solar":
                    # stat_energy_from is the cumulative solar energy sensor (kWh)
                    entity_id = source.get("stat_energy_from")
                    if entity_id and not candidates["solar_power"]:
                        state = self.hass.states.get(entity_id)
                        if state and state.state not in ["unavailable", "unknown"]:
                            unit = state.attributes.get("unit_of_measurement", "")
                            candidates["solar_power"] = {
                                "entity_id": entity_id,
                                "name": state.attributes.get("friendly_name", entity_id),
                                "confidence": "high",
                                "unit": unit,
                                "is_cumulative": unit.lower() in ["kwh", "wh"],
                            }
                            _LOGGER.info(
                                "✅ Energy Dashboard solar sensor: %s (%s, cumulative=%s)",
                                entity_id,
                                unit,
                                candidates["solar_power"]["is_cumulative"],
                            )

                elif source.get("type") == "battery":
                    # For battery, we might find discharge energy sensor
                    # But we still need battery SOC (%) which isn't in Energy Dashboard
                    pass

                elif source.get("type") == "grid":
                    # Could use grid consumption for house load calculation
                    # But this is complex - better to let user select house load sensor
                    pass

        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Failed to find Energy Dashboard sensors")

        return candidates


class IntuiThermOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for IntuiTherm integration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Get current configuration
            current_config = {**self.config_entry.data, **self.config_entry.options}
            
            if not errors:
                # Update detected_entities with any changed sensors
                detected_entities = current_config.get(CONF_DETECTED_ENTITIES, {}).copy()
                
                # Update sensor selections if provided
                if user_input.get(CONF_BATTERY_SOC_ENTITY):
                    detected_entities[CONF_BATTERY_SOC_ENTITY] = user_input[CONF_BATTERY_SOC_ENTITY]
                if user_input.get(CONF_SOLAR_POWER_ENTITY):
                    detected_entities[CONF_SOLAR_POWER_ENTITY] = user_input[CONF_SOLAR_POWER_ENTITY]
                if user_input.get(CONF_HOUSE_LOAD_ENTITY):
                    detected_entities[CONF_HOUSE_LOAD_ENTITY] = user_input[CONF_HOUSE_LOAD_ENTITY]
                
                # Update battery control entities
                if user_input.get(CONF_BATTERY_MODE_SELECT):
                    detected_entities[CONF_BATTERY_MODE_SELECT] = user_input[CONF_BATTERY_MODE_SELECT]
                if user_input.get(CONF_BATTERY_CHARGE_POWER):
                    detected_entities[CONF_BATTERY_CHARGE_POWER] = user_input[CONF_BATTERY_CHARGE_POWER]
                
                # Update mode mappings
                if user_input.get(CONF_MODE_SELF_USE):
                    detected_entities[CONF_MODE_SELF_USE] = user_input[CONF_MODE_SELF_USE]
                if user_input.get(CONF_MODE_BACKUP):
                    detected_entities[CONF_MODE_BACKUP] = user_input[CONF_MODE_BACKUP]
                if user_input.get(CONF_MODE_FORCE_CHARGE):
                    detected_entities[CONF_MODE_FORCE_CHARGE] = user_input[CONF_MODE_FORCE_CHARGE]
                
                # Build options dict with updated sensors and battery specs
                # Note: Service URL and API key are preserved from original config (not user-editable)
                options_data = {
                    CONF_DETECTED_ENTITIES: detected_entities,
                    CONF_BATTERY_CAPACITY: user_input.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY),
                    CONF_BATTERY_MAX_POWER: user_input.get(CONF_BATTERY_MAX_POWER, DEFAULT_BATTERY_MAX_POWER),
                }
                
                # Send battery configuration to backend
                try:
                    await self._update_battery_config(
                        current_config,
                        options_data[CONF_BATTERY_CAPACITY],
                        options_data[CONF_BATTERY_MAX_POWER]
                    )
                except Exception as err:
                    _LOGGER.warning("Failed to update battery config on backend: %s", err)
                
                # Trigger forecast and MPC regeneration after sensor reconfiguration
                try:
                    await self._trigger_forecast_and_mpc(current_config)
                except Exception as err:
                    _LOGGER.warning("Failed to trigger forecast/MPC regeneration: %s", err)
                
                # Save updated options
                return self.async_create_entry(title="", data=options_data)

        # Get current configuration (merge data and options)
        current_config = {**self.config_entry.data, **self.config_entry.options}
        
        # Get detected entities from config
        detected_entities = current_config.get(CONF_DETECTED_ENTITIES, {})

        # Get entity lists
        entity_registry = er.async_get(self.hass)

        # SOC sensors (%)
        soc_entities = {
            entry.entity_id: f"{entry.entity_id} ({entry.original_name or entry.entity_id})"
            for entry in entity_registry.entities.values()
            if entry.domain == "sensor"
            and not entry.disabled_by
            and (
                (entry.device_class == "battery" or "soc" in entry.entity_id.lower())
                and self.hass.states.get(entry.entity_id)
            )
        }

        # Power/Energy sensors (device_class=power OR energy, units kW/W/kWh/Wh)
        # Include both instantaneous power (kW) and cumulative energy (kWh) sensors
        power_entities = {}
        for entry in entity_registry.entities.values():
            if entry.domain != "sensor" or entry.disabled_by:
                continue
            state = self.hass.states.get(entry.entity_id)
            if not state:
                continue
            # Include power sensors (kW/W) and energy sensors (kWh/Wh)
            unit = state.attributes.get("unit_of_measurement", "").lower()
            device_class = entry.device_class
            if device_class in ["power", "energy"] or unit in ["kw", "w", "kwh", "wh"]:
                # Add unit indicator to help users distinguish
                unit_display = state.attributes.get("unit_of_measurement", "")
                power_entities[entry.entity_id] = (
                    f"{entry.entity_id} [{unit_display}] ({entry.original_name or entry.entity_id})"
                )

        # Build schema with current values as defaults
        # Note: Service URL and API key are not user-configurable (registered during setup)
        schema = {
            vol.Required(
                CONF_BATTERY_CAPACITY,
                default=current_config.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY),
                description="Total usable battery capacity in kilowatt-hours (kWh). This is the amount of energy your battery can store and use. Example: 10 for a 10 kWh battery."
            ): vol.All(vol.Coerce(float), vol.Range(min=1.0, max=100.0)),
            vol.Required(
                CONF_BATTERY_MAX_POWER,
                default=current_config.get(CONF_BATTERY_MAX_POWER, DEFAULT_BATTERY_MAX_POWER),
                description="Maximum charging/discharging rate in kilowatts (kW). Limits how fast the battery can charge or discharge. Example: 3 for a 3 kW inverter."
            ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=20.0)),
        }
        
        # Auto-detect battery control entities from battery device
        battery_soc_entity = detected_entities.get(CONF_BATTERY_SOC_ENTITY)
        detected_mode_select = None
        detected_charge_power = None
        
        if battery_soc_entity:
            # Get device ID from battery SoC sensor
            soc_entry = entity_registry.entities.get(battery_soc_entity)
            if soc_entry and soc_entry.device_id:
                device_id = soc_entry.device_id
                device_registry = dr.async_get(self.hass)
                device = device_registry.async_get(device_id)
                
                if device:
                    # Scan all entities on this device
                    for entry in entity_registry.entities.values():
                        if entry.device_id != device_id or entry.disabled_by:
                            continue
                        
                        entity_id_lower = entry.entity_id.lower()
                        
                        # Look for mode select entity
                        if entry.domain == "select" and not detected_mode_select:
                            if any(keyword in entity_id_lower for keyword in ["mode", "work_mode", "battery_mode"]):
                                detected_mode_select = entry.entity_id
                        
                        # Look for charge power control
                        if entry.domain == "number" and not detected_charge_power:
                            if any(keyword in entity_id_lower for keyword in ["charge_power", "charge_limit", "max_charge"]):
                                detected_charge_power = entry.entity_id
        
        # Get all select and number entities for dropdowns
        all_select_entities = [
            entry.entity_id for entry in entity_registry.entities.values()
            if entry.domain == "select" and not entry.disabled_by
        ]
        all_number_entities = [
            entry.entity_id for entry in entity_registry.entities.values()
            if entry.domain == "number" and not entry.disabled_by
        ]
        
        # Add entity selectors with values from detected_entities
        # Always show fields even if no entities detected (allow custom input)
        
        # Battery SOC
        current_soc = detected_entities.get(CONF_BATTERY_SOC_ENTITY)
        if soc_entities:
            # Ensure the current value is in the list, otherwise add it
            if current_soc and current_soc not in soc_entities:
                soc_entities[current_soc] = f"{current_soc} (configured)"
            if current_soc:
                schema[vol.Optional(
                    CONF_BATTERY_SOC_ENTITY,
                    default=current_soc,
                    description="Sensor showing battery charge percentage (0-100%). Tracks how full your battery currently is. Used to optimize charging decisions."
                )] = selector.SelectSelector(
                    selector.SelectSelectorConfig(options=list(soc_entities.keys()), custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN)
                )
            else:
                schema[vol.Optional(
                    CONF_BATTERY_SOC_ENTITY,
                    description="Sensor showing battery charge percentage (0-100%). Tracks how full your battery currently is. Used to optimize charging decisions."
                )] = selector.SelectSelector(
                    selector.SelectSelectorConfig(options=list(soc_entities.keys()), custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN)
                )
        else:
            # No SOC entities found, show text input
            schema[vol.Optional(
                CONF_BATTERY_SOC_ENTITY,
                default=current_soc or "",
                description="Sensor showing battery charge percentage (0-100%). Tracks how full your battery currently is. Used to optimize charging decisions."
            )] = str

        # Power/Energy sensors
        if power_entities:
            # Solar Power
            current_solar = detected_entities.get(CONF_SOLAR_POWER_ENTITY)
            if current_solar and current_solar not in power_entities:
                power_entities[current_solar] = f"{current_solar} (configured)"
            if current_solar:
                schema[vol.Optional(
                    CONF_SOLAR_POWER_ENTITY,
                    default=current_solar,
                    description="Cumulative solar energy production sensor (kWh, total_increasing). Tracks total energy generated by your solar panels. The system calculates power from these readings."
                )] = selector.SelectSelector(
                    selector.SelectSelectorConfig(options=list(power_entities.keys()), custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN)
                )
            else:
                schema[vol.Optional(
                    CONF_SOLAR_POWER_ENTITY,
                    description="Cumulative solar energy production sensor (kWh, total_increasing). Tracks total energy generated by your solar panels. The system calculates power from these readings."
                )] = selector.SelectSelector(
                    selector.SelectSelectorConfig(options=list(power_entities.keys()), custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN)
                )

            # House Load
            current_load = detected_entities.get(CONF_HOUSE_LOAD_ENTITY)
            if current_load and current_load not in power_entities:
                power_entities[current_load] = f"{current_load} (configured)"
            if current_load:
                schema[vol.Optional(
                    CONF_HOUSE_LOAD_ENTITY,
                    default=current_load,
                    description="Cumulative house energy consumption sensor (kWh, total_increasing). Tracks total energy used by your home. Used to predict consumption patterns."
                )] = selector.SelectSelector(
                    selector.SelectSelectorConfig(options=list(power_entities.keys()), custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN)
                )
            else:
                schema[vol.Optional(
                    CONF_HOUSE_LOAD_ENTITY,
                    description="Cumulative house energy consumption sensor (kWh, total_increasing). Tracks total energy used by your home. Used to predict consumption patterns."
                )] = selector.SelectSelector(
                    selector.SelectSelectorConfig(options=list(power_entities.keys()), custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN)
                )
        else:
            # No power entities found, show text inputs
            current_solar = detected_entities.get(CONF_SOLAR_POWER_ENTITY)
            current_load = detected_entities.get(CONF_HOUSE_LOAD_ENTITY)
            
            schema[vol.Optional(
                CONF_SOLAR_POWER_ENTITY,
                default=current_solar or "",
                description="Cumulative solar energy production sensor (kWh, total_increasing). Tracks total energy generated by your solar panels."
            )] = str
            schema[vol.Optional(
                CONF_HOUSE_LOAD_ENTITY,
                default=current_load or "",
                description="Cumulative house energy consumption sensor (kWh, total_increasing). Tracks total energy used by your home."
            )] = str

        # Use detected or current values for battery control entities
        current_mode_select = detected_entities.get(CONF_BATTERY_MODE_SELECT) or detected_mode_select or ""
        current_charge_power = detected_entities.get(CONF_BATTERY_CHARGE_POWER) or detected_charge_power or ""
        
        # Add battery control entity selectors (optional - for actual battery control)
        schema[vol.Optional(
            CONF_BATTERY_MODE_SELECT,
            default=current_mode_select,
            description="Select entity that controls battery operating mode (e.g., select.work_mode). Enables automatic switching between Self Use, Backup, and Force Charge modes. Leave empty for monitoring-only."
        )] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=all_select_entities if all_select_entities else [],
                mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        )
        
        schema[vol.Optional(
            CONF_BATTERY_CHARGE_POWER,
            default=current_charge_power,
            description="Number entity to control battery charging power (e.g., number.force_charge_power). Controls how fast the battery charges during force charge periods. Leave empty if not available."
        )] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=all_number_entities if all_number_entities else [],
                mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        )
        
        # Add mode mapping fields if battery mode select entity is configured
        mode_select_entity = detected_entities.get(CONF_BATTERY_MODE_SELECT)
        if mode_select_entity:
            # Get available mode options from the entity
            available_options = []
            state = self.hass.states.get(mode_select_entity)
            if state and state.attributes:
                available_options = state.attributes.get("options", [])
            
            # Get current mode mappings
            current_self_use = detected_entities.get(CONF_MODE_SELF_USE, "")
            current_backup = detected_entities.get(CONF_MODE_BACKUP, "")
            current_force_charge = detected_entities.get(CONF_MODE_FORCE_CHARGE, "")
            
            # Auto-detect defaults if not already configured
            if not current_self_use and available_options:
                for option in available_options:
                    option_lower = option.lower()
                    if "self" in option_lower and "use" in option_lower:
                        current_self_use = option
                        break
            
            if not current_backup and available_options:
                for option in available_options:
                    if "backup" in option.lower():
                        current_backup = option
                        break
            
            if not current_force_charge and available_options:
                for option in available_options:
                    option_lower = option.lower()
                    if "force" in option_lower and "charge" in option_lower:
                        current_force_charge = option
                        break
            
            # Add mode mapping fields
            if available_options:
                schema[vol.Required(
                    CONF_MODE_SELF_USE,
                    default=current_self_use or "",
                    description=f"Select the mode option for '{BATTERY_MODE_NAMES[BATTERY_MODE_SELF_USE]}'"
                )] = selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=available_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                )
                
                schema[vol.Required(
                    CONF_MODE_BACKUP,
                    default=current_backup or "",
                    description=f"Select the mode option for '{BATTERY_MODE_NAMES[BATTERY_MODE_BACKUP]}'"
                )] = selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=available_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                )
                
                schema[vol.Required(
                    CONF_MODE_FORCE_CHARGE,
                    default=current_force_charge or "",
                    description=f"Select the mode option for '{BATTERY_MODE_NAMES[BATTERY_MODE_FORCE_CHARGE]}'"
                )] = selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=available_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                )
            else:
                # Fallback to text inputs if options can't be fetched
                schema[vol.Required(
                    CONF_MODE_SELF_USE,
                    default=current_self_use or "Self Use",
                    description=f"Enter the exact option value for '{BATTERY_MODE_NAMES[BATTERY_MODE_SELF_USE]}'"
                )] = str
                
                schema[vol.Required(
                    CONF_MODE_BACKUP,
                    default=current_backup or "Backup",
                    description=f"Enter the exact option value for '{BATTERY_MODE_NAMES[BATTERY_MODE_BACKUP]}'"
                )] = str
                
                schema[vol.Required(
                    CONF_MODE_FORCE_CHARGE,
                    default=current_force_charge or "Force Charge",
                    description=f"Enter the exact option value for '{BATTERY_MODE_NAMES[BATTERY_MODE_FORCE_CHARGE]}'"
                )] = str


        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={
                "user_id": current_config.get(CONF_USER_ID, "not-set")
            },
        )
    
    async def _update_battery_config(self, config: dict, capacity_kwh: float, max_power_kw: float) -> None:
        """Update battery configuration on the backend."""
        service_url = config.get(CONF_SERVICE_URL, DEFAULT_SERVICE_URL)
        api_key = config.get(CONF_API_KEY)
        
        if not api_key:
            raise ValueError("No API key available")
        
        session = async_get_clientsession(self.hass)
        headers = {"Authorization": f"Bearer {api_key}"}
        url = f"{service_url}{ENDPOINT_UPDATE_CONFIG}"
        
        payload = {
            "battery_capacity_kwh": capacity_kwh,
            "battery_max_power_kw": max_power_kw
        }
        
        # Include battery control entities if configured (stored as device presets)
        detected_entities = config.get(CONF_DETECTED_ENTITIES, {})
        if battery_mode := detected_entities.get(CONF_BATTERY_MODE_SELECT):
            payload["ha_battery_mode_entity_id"] = battery_mode
        if charge_power := detected_entities.get(CONF_BATTERY_CHARGE_POWER):
            payload["ha_battery_charge_power_entity_id"] = charge_power
        if discharge_power := detected_entities.get(CONF_BATTERY_DISCHARGE_POWER):
            payload["ha_battery_discharge_power_entity_id"] = discharge_power
        
        async with session.post(url, json=payload, headers=headers) as response:
            if response.status not in [200, 201]:
                error_text = await response.text()
                raise Exception(f"Backend returned {response.status}: {error_text}")
            
        _LOGGER.info("Updated battery config on backend: %.1f kWh @ %.2f kW", capacity_kwh, max_power_kw)
    
    async def _trigger_forecast_and_mpc(self, config: dict) -> None:
        """Trigger forecast regeneration and MPC optimization after sensor reconfiguration."""
        service_url = config.get(CONF_SERVICE_URL, DEFAULT_SERVICE_URL)
        api_key = config.get(CONF_API_KEY)
        
        if not api_key:
            raise ValueError("No API key available")
        
        session = async_get_clientsession(self.hass)
        headers = {"Authorization": f"Bearer {api_key}"}
        
        # Trigger forecast regeneration
        forecast_url = f"{service_url}/api/v1/forecasts/trigger"
        async with session.post(forecast_url, headers=headers) as response:
            if response.status == 200:
                result = await response.json()
                _LOGGER.info("Triggered forecast regeneration: %s forecasts generated", 
                           result.get("forecasts_generated", 0))
            else:
                error_text = await response.text()
                _LOGGER.warning("Failed to trigger forecast: %s - %s", response.status, error_text)
        
        # Trigger MPC optimization
        mpc_url = f"{service_url}/api/v1/mpc/trigger"
        async with session.post(mpc_url, headers=headers) as response:
            if response.status == 200:
                result = await response.json()
                _LOGGER.info("Triggered MPC optimization: %s", 
                           "successful" if result.get("mpc_run_successful") else "failed")
            else:
                error_text = await response.text()
                _LOGGER.warning("Failed to trigger MPC: %s - %s", response.status, error_text)
