"""Switch platform for IntuiTherm integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    DATA_COORDINATOR,
    SWITCH_TYPE_AUTO_CONTROL,
)
from .coordinator import IntuiThermCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IntuiTherm switches based on a config entry."""
    coordinator: IntuiThermCoordinator = hass.data[DOMAIN][entry.entry_id][
        DATA_COORDINATOR
    ]

    switches = [
        IntuiThermAutoControlSwitch(coordinator, entry),
    ]

    async_add_entities(switches)
    _LOGGER.info("IntuiTherm switches added")


class IntuiThermAutoControlSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable/disable automatic battery control."""

    def __init__(
        self, coordinator: IntuiThermCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_name = "IntuiTherm Automatic Control"
        self._attr_icon = "mdi:robot"
        self._attr_unique_id = f"{entry.entry_id}_{SWITCH_TYPE_AUTO_CONTROL}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "IntuiTherm Battery Optimizer",
            "manufacturer": "IntuiHEMS",
            "model": "Battery Optimization Service",
            "sw_version": "1.0",
        }

    @property
    def is_on(self) -> bool:
        """Return true if automatic control is enabled."""
        if not self.coordinator.data:
            return False

        control_data = self.coordinator.data.get("control", {})

        if isinstance(control_data, Exception):
            return False

        return control_data.get("automatic_control_enabled", False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return {}

        control_data = self.coordinator.data.get("control", {})

        if isinstance(control_data, Exception):
            return {"error": str(control_data)}

        attrs = {}

        # Add current mode
        if "current_mode" in control_data:
            attrs["current_mode"] = control_data["current_mode"]

        # Add next review time
        if "next_review_at" in control_data:
            attrs["next_review"] = control_data["next_review_at"]

        # Add last MPC run
        if "last_mpc_run_at" in control_data:
            attrs["last_mpc_run"] = control_data["last_mpc_run_at"]

        # Add override status
        if control_data.get("override_active"):
            attrs["override_active"] = True
            if "override_until" in control_data:
                attrs["override_until"] = control_data["override_until"]

        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on automatic control."""
        _LOGGER.info("Enabling IntuiTherm automatic control")

        result = await self.coordinator.async_enable_auto_control()

        if result.get("status") != "success":
            _LOGGER.error(
                "Failed to enable automatic control: %s", result.get("detail")
            )
            # Still refresh to show current state
            await self.coordinator.async_request_refresh()
            return

        _LOGGER.info("Automatic control enabled successfully")
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off automatic control."""
        _LOGGER.info("Disabling IntuiTherm automatic control")

        result = await self.coordinator.async_disable_auto_control()

        if result.get("status") != "success":
            _LOGGER.error(
                "Failed to disable automatic control: %s", result.get("detail")
            )
            # Still refresh to show current state
            await self.coordinator.async_request_refresh()
            return

        _LOGGER.info("Automatic control disabled successfully")
        await self.coordinator.async_request_refresh()

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self.coordinator.last_update_success:
            return False

        # Check if control data is available and not an exception
        control_data = self.coordinator.data.get("control", {})
        return not isinstance(control_data, Exception)
