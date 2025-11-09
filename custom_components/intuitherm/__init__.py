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
    DATA_COORDINATOR,
    DATA_UNSUB,
    DEFAULT_UPDATE_INTERVAL,
    VERSION,
)
from .coordinator import IntuiThermCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the IntuiTherm component from yaml configuration."""
    # This integration only supports config flow setup
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IntuiTherm from a config entry."""
    # Merge entry.data and entry.options (options take precedence)
    config = {**entry.data, **entry.options}

    _LOGGER.info(
        "Setting up IntuiTherm integration v%s for service at %s",
        VERSION,
        config[CONF_SERVICE_URL]
    )

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
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
        DATA_UNSUB: [],
    }

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

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Remove config entry from domain
        entry_data = hass.data[DOMAIN].pop(entry.entry_id)

        # Cancel any subscriptions
        for unsub in entry_data[DATA_UNSUB]:
            unsub()

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
