"""The IntuiTherm Battery Optimizer integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_SERVICE_URL,
    CONF_API_KEY,
    CONF_UPDATE_INTERVAL,
    CONF_DETECTED_ENTITIES,
    CONF_BATTERY_MODE_SELECT,
    CONF_BATTERY_CHARGE_POWER,
    CONF_BATTERY_DISCHARGE_POWER,
    CONF_SOLAREDGE_COMMAND_MODE,
    DATA_COORDINATOR,
    DATA_BATTERY_CONTROL,
    DATA_UNSUB,
    DEFAULT_UPDATE_INTERVAL,
    VERSION,
)
from .coordinator import IntuiThermCoordinator
from .battery_control import BatteryControlExecutor

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the IntuiTherm component from yaml configuration."""
    # This integration only supports config flow setup
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IntuiTherm from a config entry."""
    try:
        _LOGGER.info("=" * 80)
        _LOGGER.info("🚀 INTUITHERM ASYNC_SETUP_ENTRY CALLED")
        _LOGGER.info("Entry ID: %s", entry.entry_id)
        _LOGGER.info("Entry data keys: %s", list(entry.data.keys()))
        _LOGGER.info("=" * 80)
        
        # Merge entry.data and entry.options (options take precedence)
        config = {**entry.data, **entry.options}

        _LOGGER.info(
            "Setting up IntuiTherm integration v%s for service at %s",
            VERSION,
            config.get(CONF_SERVICE_URL, "MISSING")
        )
    except Exception as e:
        _LOGGER.error("❌ CRITICAL ERROR in async_setup_entry start: %s", e, exc_info=True)
        return False

    # Get aiohttp session
    session = async_get_clientsession(hass)

    # Create data coordinator
    coordinator = IntuiThermCoordinator(
        hass=hass,
        session=session,
        service_url=config[CONF_SERVICE_URL],
        api_key=config[CONF_API_KEY],
        update_interval=timedelta(
            seconds=config.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        ),
        entry=entry,
    )

    # Fetch initial data
    _LOGGER.info("🚀 Starting first coordinator refresh (will trigger sensor registration and backfill)...")
    try:
        await coordinator.async_config_entry_first_refresh()
        _LOGGER.info("✅ First coordinator refresh complete")
    except Exception as err:
        _LOGGER.error("❌ First coordinator refresh failed: %s", err, exc_info=True)
        # Don't fail setup - coordinator will retry
        _LOGGER.warning("Continuing setup despite coordinator error (will retry automatically)")

    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
        DATA_UNSUB: [],
    }

    # Migrate existing Huawei installations to add ha_device_id if missing
    detected_entities = config.get(CONF_DETECTED_ENTITIES, {})
    is_huawei = detected_entities.get("grid_charge_switch") is not None
    
    if is_huawei and not detected_entities.get("ha_device_id"):
        _LOGGER.warning("Huawei system detected but ha_device_id missing - attempting migration")
        
        from homeassistant.helpers import entity_registry as er, device_registry as dr
        entity_registry = er.async_get(hass)
        device_registry = dr.async_get(hass)
        
        grid_switch_entity_id = detected_entities.get("grid_charge_switch")
        if grid_switch_entity_id:
            grid_switch_entry = entity_registry.entities.get(grid_switch_entity_id)
            
            if grid_switch_entry and grid_switch_entry.device_id:
                battery_device = device_registry.async_get(grid_switch_entry.device_id)
                
                if battery_device:
                    detected_entities["ha_device_id"] = battery_device.id
                    
                    # Update the config entry with the new ha_device_id
                    new_data = {**entry.data}
                    if CONF_DETECTED_ENTITIES in new_data:
                        new_data[CONF_DETECTED_ENTITIES]["ha_device_id"] = battery_device.id
                    
                    hass.config_entries.async_update_entry(entry, data=new_data)
                    
                    _LOGGER.info(
                        "✅ Migration successful: Added ha_device_id=%s (device: %s)",
                        battery_device.id,
                        battery_device.name
                    )
                else:
                    _LOGGER.error("❌ Migration failed: Could not find battery device")
            else:
                _LOGGER.error("❌ Migration failed: grid_charge_switch entity not found in registry")
        else:
            _LOGGER.error("❌ Migration failed: No grid_charge_switch entity configured")

    # Initialize battery control executor if battery entities are configured
    battery_executor = None
    
    # Check if we have minimum required entities
    # For Huawei: battery_mode_select is required, battery_charge_power is optional (uses forcible_charge service)
    # For other brands: both battery_mode_select and battery_charge_power are required
    is_huawei = detected_entities.get("grid_charge_switch") is not None
    is_solaredge = detected_entities.get(CONF_SOLAREDGE_COMMAND_MODE) is not None
    has_mode_select = detected_entities.get(CONF_BATTERY_MODE_SELECT) is not None
    has_charge_power = detected_entities.get(CONF_BATTERY_CHARGE_POWER) is not None
    
    can_start_executor = has_mode_select and (is_huawei or has_charge_power)
    
    if can_start_executor:
        _LOGGER.info(
            f"Battery control entities configured, initializing executor "
            f"(is_huawei={is_huawei}, is_solaredge={is_solaredge}, has_charge_power={has_charge_power})"
        )
        battery_executor = BatteryControlExecutor(
            hass=hass,
            coordinator=coordinator,
            config=config,
        )
        hass.data[DOMAIN][entry.entry_id][DATA_BATTERY_CONTROL] = battery_executor
        
        # Start the executor
        battery_executor.start()
        _LOGGER.info("Battery control executor started")
    else:
        missing = []
        if not has_mode_select:
            missing.append("battery_mode_select")
        if not is_huawei and not has_charge_power:
            missing.append("battery_charge_power (required for non-Huawei)")
        _LOGGER.info(
            f"Battery control executor disabled - missing entities: {', '.join(missing)}"
        )

    # Forward entry setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services (manual override + device learning)
    await async_setup_services(hass, entry)
    
    # Register device learning services (only once for all entries)
    if not hass.services.has_service(DOMAIN, "list_learned_devices"):
        from .services import async_setup_services as setup_device_services
        await setup_device_services(hass)

    # Register options update listener
    entry.async_on_unload(entry.add_update_listener(update_listener))

    _LOGGER.info("IntuiTherm integration setup complete")

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading IntuiTherm integration")

    # Stop battery control executor if running
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    battery_executor = entry_data.get(DATA_BATTERY_CONTROL)
    if battery_executor:
        _LOGGER.info("Stopping battery control executor")
        battery_executor.stop()

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Remove config entry from domain
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    _LOGGER.info("IntuiTherm configuration updated, reloading integration")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up services for IntuiTherm integration."""
    from homeassistant.helpers import config_validation as cv
    import voluptuous as vol

    from .const import (
        SERVICE_MANUAL_OVERRIDE,
        ATTR_ACTION,
        ATTR_POWER_KW,
        ATTR_DURATION_MINUTES,
    )

    async def handle_manual_override(call):
        """Handle the manual_override service call."""
        coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

        action = call.data.get(ATTR_ACTION)
        power_kw = call.data.get(ATTR_POWER_KW)
        duration_minutes = call.data.get(ATTR_DURATION_MINUTES)

        result = await coordinator.manual_override(
            action=action,
            power_kw=power_kw,
            duration_minutes=duration_minutes
        )

        if result.get("status") != "success":
            _LOGGER.error("Manual override failed: %s", result.get("detail"))
        else:
            _LOGGER.info("Manual override successful: %s", action)

    # Register service
    hass.services.async_register(
        DOMAIN,
        SERVICE_MANUAL_OVERRIDE,
        handle_manual_override,
        schema=vol.Schema({
            vol.Required(ATTR_ACTION): cv.string,
            vol.Optional(ATTR_POWER_KW): vol.All(
                vol.Coerce(float), vol.Range(min=0, max=3.0)
            ),
            vol.Optional(ATTR_DURATION_MINUTES): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=1440)
            ),
        }),
    )

    _LOGGER.info("IntuiTherm services registered")
