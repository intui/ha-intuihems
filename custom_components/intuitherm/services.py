"""Services for IntuiTherm integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .device_learning import async_setup_device_learning

_LOGGER = logging.getLogger(__name__)

# Service names
SERVICE_LIST_LEARNED_DEVICES = "list_learned_devices"
SERVICE_DELETE_LEARNED_DEVICE = "delete_learned_device"
SERVICE_EXPORT_LEARNED_DEVICES = "export_learned_devices"

# Service schemas
DELETE_LEARNED_DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required("device_index"): cv.positive_int,
    }
)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for IntuiTherm integration."""

    async def list_learned_devices(call: ServiceCall) -> dict[str, Any]:
        """List all learned device configurations."""
        store = await async_setup_device_learning(hass)
        devices = store.get_all_learned_devices()
        
        _LOGGER.info("Listing %d learned devices", len(devices))
        
        # Format for display
        formatted_devices = []
        for idx, device in enumerate(devices):
            formatted_devices.append({
                "index": idx,
                "platform": device.get("platform"),
                "manufacturer": device.get("manufacturer"),
                "model": device.get("model"),
                "control_entities": device.get("control_entities", {}),
                "times_used": device.get("times_used", 0),
                "success_rate": f"{device.get('success_rate', 0) * 100:.1f}%",
                "learned_at": device.get("learned_at"),
            })
        
        return {"devices": formatted_devices}

    async def delete_learned_device(call: ServiceCall) -> None:
        """Delete a learned device configuration."""
        device_index = call.data["device_index"]
        
        store = await async_setup_device_learning(hass)
        success = await store.delete_learned_device(device_index)
        
        if success:
            _LOGGER.info("Deleted learned device at index %d", device_index)
        else:
            _LOGGER.warning("Could not delete device at index %d (not found)", device_index)

    async def export_learned_devices(call: ServiceCall) -> dict[str, Any]:
        """Export all learned devices as JSON."""
        store = await async_setup_device_learning(hass)
        devices = store.get_all_learned_devices()
        
        _LOGGER.info("Exporting %d learned devices", len(devices))
        
        return {
            "version": "1.0",
            "exported_at": "now",
            "devices": devices,
        }

    # Register services
    hass.services.async_register(
        DOMAIN,
        SERVICE_LIST_LEARNED_DEVICES,
        list_learned_devices,
        supports_response=True,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_LEARNED_DEVICE,
        delete_learned_device,
        schema=DELETE_LEARNED_DEVICE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_EXPORT_LEARNED_DEVICES,
        export_learned_devices,
        supports_response=True,
    )

    _LOGGER.info("IntuiTherm services registered")


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload IntuiTherm services."""
    hass.services.async_remove(DOMAIN, SERVICE_LIST_LEARNED_DEVICES)
    hass.services.async_remove(DOMAIN, SERVICE_DELETE_LEARNED_DEVICE)
    hass.services.async_remove(DOMAIN, SERVICE_EXPORT_LEARNED_DEVICES)
    
    _LOGGER.info("IntuiTherm services unloaded")
