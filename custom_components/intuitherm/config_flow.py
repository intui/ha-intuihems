"""Config flow for IntuiTherm integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, device_registry as dr
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
    CONF_HOUSE_LOAD_CALC_MODE,
    DEFAULT_SERVICE_URL,
    DEFAULT_UPDATE_INTERVAL,
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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step - welcome screen."""
        from .const import VERSION
        
        if user_input is not None:
            # Use hard-coded development values
            self._service_url = DEFAULT_SERVICE_URL
            self._api_key = "A6SJ7InZ0cjMMNEP7FS2YOqfr6JMvxZVwbKfPC-dYsk"  # Development API key
            self._update_interval = DEFAULT_UPDATE_INTERVAL
            
            _LOGGER.info(
                "Starting intuiHEMS setup (version %s) with service at %s",
                VERSION,
                self._service_url,
            )
            # Move directly to auto-detection
            return await self.async_step_auto_detect()

        # Show welcome screen with version
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            description_placeholders={"version": VERSION},
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
        _LOGGER.info("Starting entity auto-detection")

        try:
            # Phase 1: Extract ALL Energy Dashboard sensors with availability
            all_energy_sensors = await self._get_all_energy_sensors()
            _LOGGER.info("Extracted Energy Dashboard sensors - Details:")
            for category, sensor_list in all_energy_sensors.items():
                available_count = sum(1 for s in sensor_list if s["available"])
                _LOGGER.info(
                    "  %s: %d total (%d available)",
                    category,
                    len(sensor_list),
                    available_count
                )
                for sensor in sensor_list:
                    status = "✅" if sensor["available"] else "❌"
                    _LOGGER.info(
                        "    %s %s [%s] state=%s",
                        status,
                        sensor["entity_id"],
                        sensor["unit"],
                        sensor["state"]
                    )

            # Query Energy Dashboard configuration
            energy_prefs = await self._get_energy_prefs()

            if not energy_prefs:
                _LOGGER.debug("Energy Dashboard not configured, skipping auto-detection")
                # Skip to manual review
                return await self.async_step_review()

            # Discover devices from energy entities
            devices = await self._discover_devices(energy_prefs)
            _LOGGER.info("Discovered %d devices", len(devices))

            # Find relevant power sensors on devices
            for device_id, device_info in devices.items():
                sensors = await self._find_power_sensors(device_id)
                if sensors:
                    # Store device info for potential learning
                    if sensors.get("device_info") and not self._device_info:
                        self._device_info = sensors["device_info"]
                    
                    # Store best matches
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
            
            # Check for learned patterns if no control entities detected
            if self._device_info and not self._detected_entities.get(CONF_BATTERY_MODE_SELECT):
                await self._check_learned_patterns()

            # Priority 1: Try Energy Dashboard cumulative sensors first (best source of truth)
            # These are kWh sensors that the backend will convert to kW via derivatives
            _LOGGER.info("Trying Energy Dashboard cumulative sensor detection")
            dashboard_sensors = await self._find_energy_dashboard_sensors()

            if dashboard_sensors.get("solar_power"):
                # Prefer Energy Dashboard cumulative sensors over device-based detection
                self._detected_entities[CONF_SOLAR_POWER_ENTITY] = dashboard_sensors[
                    "solar_power"
                ]["entity_id"]
                is_cumulative = dashboard_sensors["solar_power"].get("is_cumulative", False)
                _LOGGER.info(
                    "✅ Energy Dashboard solar: %s (cumulative=%s)",
                    dashboard_sensors["solar_power"]["entity_id"],
                    is_cumulative,
                )

            # Fallback: If no/few sensors detected, try pattern-based search
            if len([v for v in self._detected_entities.values() if v]) < 2:
                _LOGGER.info("Device-based detection found few sensors, trying pattern-based fallback")
                fallback_sensors = await self._find_sensors_by_pattern()

                if fallback_sensors.get("battery_soc") and not self._detected_entities.get(
                    CONF_BATTERY_SOC_ENTITY
                ):
                    self._detected_entities[CONF_BATTERY_SOC_ENTITY] = fallback_sensors[
                        "battery_soc"
                    ]["entity_id"]
                    _LOGGER.info("Pattern-detected battery SOC: %s", fallback_sensors["battery_soc"]["entity_id"])

                if fallback_sensors.get("solar_power") and not self._detected_entities.get(
                    CONF_SOLAR_POWER_ENTITY
                ):
                    self._detected_entities[CONF_SOLAR_POWER_ENTITY] = fallback_sensors[
                        "solar_power"
                    ]["entity_id"]
                    _LOGGER.info("Pattern-detected solar power: %s", fallback_sensors["solar_power"]["entity_id"])

                if fallback_sensors.get("house_load") and not self._detected_entities.get(
                    CONF_HOUSE_LOAD_ENTITY
                ):
                    self._detected_entities[CONF_HOUSE_LOAD_ENTITY] = fallback_sensors[
                        "house_load"
                    ]["entity_id"]
                    _LOGGER.info("Pattern-detected house load: %s", fallback_sensors["house_load"]["entity_id"])

            _LOGGER.info("Auto-detection complete: %s", self._detected_entities)

        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Auto-detection failed")

        # Move to review step
        return await self.async_step_review()

    async def async_step_review(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Review and confirm detected entities."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # User confirmed or adjusted entity selections
            self._detected_entities[CONF_BATTERY_SOC_ENTITY] = user_input.get(
                CONF_BATTERY_SOC_ENTITY
            )
            self._detected_entities[CONF_SOLAR_POWER_ENTITY] = user_input.get(
                CONF_SOLAR_POWER_ENTITY
            )
            self._detected_entities[CONF_HOUSE_LOAD_ENTITY] = user_input.get(
                CONF_HOUSE_LOAD_ENTITY
            )
            
            # Check if user selected control entities for an unknown device
            control_entities_selected = {}
            if user_input.get(CONF_BATTERY_MODE_SELECT):
                control_entities_selected[CONF_BATTERY_MODE_SELECT] = user_input[
                    CONF_BATTERY_MODE_SELECT
                ]
            if user_input.get(CONF_BATTERY_CHARGE_POWER):
                control_entities_selected[CONF_BATTERY_CHARGE_POWER] = user_input[
                    CONF_BATTERY_CHARGE_POWER
                ]
            if user_input.get(CONF_BATTERY_DISCHARGE_POWER):
                control_entities_selected[CONF_BATTERY_DISCHARGE_POWER] = user_input[
                    CONF_BATTERY_DISCHARGE_POWER
                ]
            
            # Save learned device configuration if entities were manually selected
            # TODO: Fix indentation issue in _save_learned_device method
            # if self._device_info and control_entities_selected:
            #     await self._save_learned_device(control_entities_selected)

            # Create config entry
            return self.async_create_entry(
                title="intuiHEMS",
                data={
                    CONF_SERVICE_URL: self._service_url,
                    CONF_API_KEY: self._api_key,
                    CONF_UPDATE_INTERVAL: self._update_interval,
                    CONF_DETECTED_ENTITIES: self._detected_entities,
                },
            )
        
        # If no user input yet, show the review form with available sensors
        return await self._show_review_form()

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

    async def _show_review_form(self) -> config_entries.FlowResult:
        """Show the review form with sensor selection."""
        entity_registry = er.async_get(self.hass)
        
        # Battery SOC sensors (device_class=battery, unit=%)
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
        power_entities = {}
        for entry in entity_registry.entities.values():
            if entry.domain != "sensor" or entry.disabled_by:
                continue
            state = self.hass.states.get(entry.entity_id)
            if not state:
                continue
            unit = state.attributes.get("unit_of_measurement", "").lower()
            device_class = entry.device_class
            if device_class in ["power", "energy"] or unit in ["kw", "w", "kwh", "wh"]:
                unit_display = state.attributes.get("unit_of_measurement", "")
                power_entities[entry.entity_id] = (
                    f"{entry.entity_id} [{unit_display}] ({entry.original_name or entry.entity_id})"
                )

        # Build schema with detected defaults
        schema = {}

        if soc_entities:
            default_soc = self._detected_entities.get(CONF_BATTERY_SOC_ENTITY)
            if default_soc and default_soc in soc_entities:
                schema[vol.Required(CONF_BATTERY_SOC_ENTITY, default=default_soc)] = vol.In(soc_entities)
            else:
                schema[vol.Optional(CONF_BATTERY_SOC_ENTITY)] = vol.In(soc_entities)

        if power_entities:
            default_solar = self._detected_entities.get(CONF_SOLAR_POWER_ENTITY)
            if default_solar and default_solar in power_entities:
                schema[vol.Optional(CONF_SOLAR_POWER_ENTITY, default=default_solar)] = vol.In(power_entities)
            else:
                schema[vol.Optional(CONF_SOLAR_POWER_ENTITY)] = vol.In(power_entities)

            default_load = self._detected_entities.get(CONF_HOUSE_LOAD_ENTITY)
            if default_load and default_load in power_entities:
                schema[vol.Optional(CONF_HOUSE_LOAD_ENTITY, default=default_load)] = vol.In(power_entities)
            else:
                schema[vol.Optional(CONF_HOUSE_LOAD_ENTITY)] = vol.In(power_entities)

        description_placeholders = {}
        if self._detected_entities:
            description_placeholders["detected_count"] = str(
                len([v for v in self._detected_entities.values() if v])
            )

        return self.async_show_form(
            step_id="review",
            data_schema=vol.Schema(schema),
            errors={},
            description_placeholders=description_placeholders,
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
        """Find relevant power sensors and control entities on a device."""
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

        candidates = {
            "solar_power": None,
            "battery_soc": None,
            "house_load": None,
            "device_info": device_info,
            "control_entities": control_entities,
        }

        for entry in device_entities:
            if entry.domain != "sensor":
                continue

            state = self.hass.states.get(entry.entity_id)
            if not state or state.state in ["unavailable", "unknown"]:
                continue

            attrs = state.attributes

            # Battery SOC (%)
            if (
                attrs.get("device_class") == "battery"
                or "soc" in entry.entity_id.lower()
            ) and attrs.get("unit_of_measurement") == "%":
                if not candidates["battery_soc"]:
                    candidates["battery_soc"] = {
                        "entity_id": entry.entity_id,
                        "name": attrs.get("friendly_name", entry.entity_id),
                        "confidence": "high",
                    }

            # Solar power (kW or W)
            elif attrs.get("device_class") == "power" and any(
                x in entry.entity_id.lower() for x in ["pv", "solar", "photovoltaic"]
            ):
                if not candidates["solar_power"]:
                    candidates["solar_power"] = {
                        "entity_id": entry.entity_id,
                        "name": attrs.get("friendly_name", entry.entity_id),
                        "confidence": "high",
                    }

            # House load (kW)
            elif attrs.get("device_class") == "power" and any(
                x in entry.entity_id.lower() for x in ["house", "load", "consumption"]
            ):
                if not candidates["house_load"]:
                    candidates["house_load"] = {
                        "entity_id": entry.entity_id,
                        "name": attrs.get("friendly_name", entry.entity_id),
                        "confidence": "medium",
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
            # Test connection if URL or API key changed
            current_config = {**self.config_entry.data, **self.config_entry.options}
            if (
                user_input.get(CONF_SERVICE_URL) != current_config.get(CONF_SERVICE_URL)
                or user_input.get(CONF_API_KEY) != current_config.get(CONF_API_KEY)
            ):
                # Validate connection with new credentials
                session = async_get_clientsession(self.hass)
                service_url = user_input[CONF_SERVICE_URL].rstrip("/")
                api_key = user_input[CONF_API_KEY]

                try:
                    async with asyncio.timeout(10):
                        headers = {"Authorization": f"Bearer {api_key}"}
                        async with session.get(
                            f"{service_url}{ENDPOINT_HEALTH}", headers=headers
                        ) as resp:
                            if resp.status == 401:
                                errors["base"] = "invalid_api_key"
                            elif resp.status != 200:
                                errors["base"] = "cannot_connect"
                except asyncio.TimeoutError:
                    errors["base"] = "timeout_connect"
                except Exception:  # pylint: disable=broad-except
                    _LOGGER.exception("Unexpected error connecting to service")
                    errors["base"] = "unknown"

            if not errors:
                # Save updated options
                return self.async_create_entry(title="", data=user_input)

        # Get current configuration (merge data and options)
        current_config = {**self.config_entry.data, **self.config_entry.options}

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
        schema = {
            vol.Required(
                CONF_SERVICE_URL,
                default=current_config.get(CONF_SERVICE_URL, DEFAULT_SERVICE_URL)
            ): str,
            vol.Required(
                CONF_API_KEY,
                default=current_config.get(CONF_API_KEY, "")
            ): str,
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=current_config.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
            ): vol.All(vol.Coerce(int), vol.Range(min=30, max=300)),
        }

        # Add entity selectors if entities available
        if soc_entities:
            current_soc = current_config.get(CONF_BATTERY_SOC_ENTITY)
            if current_soc and current_soc in soc_entities:
                schema[vol.Optional(CONF_BATTERY_SOC_ENTITY, default=current_soc)] = vol.In(soc_entities)
            else:
                schema[vol.Optional(CONF_BATTERY_SOC_ENTITY)] = vol.In(soc_entities)

        if power_entities:
            current_solar = current_config.get(CONF_SOLAR_POWER_ENTITY)
            if current_solar and current_solar in power_entities:
                schema[vol.Optional(CONF_SOLAR_POWER_ENTITY, default=current_solar)] = vol.In(power_entities)
            else:
                schema[vol.Optional(CONF_SOLAR_POWER_ENTITY)] = vol.In(power_entities)

            current_load = current_config.get(CONF_HOUSE_LOAD_ENTITY)
            if current_load and current_load in power_entities:
                schema[vol.Optional(CONF_HOUSE_LOAD_ENTITY, default=current_load)] = vol.In(power_entities)
            else:
                schema[vol.Optional(CONF_HOUSE_LOAD_ENTITY)] = vol.In(power_entities)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            errors=errors,
        )
