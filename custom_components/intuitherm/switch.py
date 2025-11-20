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
    SWITCH_TYPE_DEMO_MODE,
    CONF_DRY_RUN_MODE,
    CONF_DETECTED_ENTITIES,
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
        IntuiThermDemoModeSwitch(coordinator, entry),
    ]

    async_add_entities(switches)
    _LOGGER.info("IntuiTherm switches added")


class IntuiThermAutoControlSwitch(CoordinatorEntity, SwitchEntity):
    """Master switch to enable/disable the entire optimization system."""

    def __init__(
        self, coordinator: IntuiThermCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_name = "Master Switch"
        self._attr_icon = "mdi:power"
        self._attr_unique_id = f"{entry.entry_id}_{SWITCH_TYPE_AUTO_CONTROL}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Battery Optimizer",
            "manufacturer": "IntuiHEMS",
            "model": "Battery Optimization Service",
            "sw_version": "1.0",
        }
        self._attr_entity_category = None  # Show prominently in controls

    @property
    def is_on(self) -> bool:
        """Return true if automatic control is enabled."""
        if not self.coordinator.data or self.coordinator.data is None:
            return False

        control_data = self.coordinator.data.get("control") if isinstance(self.coordinator.data, dict) else None
        
        if not control_data or isinstance(control_data, Exception):
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
        """Turn on the master switch (enable optimization system)."""
        _LOGGER.info("Enabling IntuiHEMS master switch - optimization system ON")

        result = await self.coordinator.async_enable_auto_control()

        if result.get("status") != "success":
            _LOGGER.error(
                "Failed to enable master switch: %s", result.get("detail")
            )
            # Still refresh to show current state
            await self.coordinator.async_request_refresh()
            return

        _LOGGER.info("Optimization system enabled successfully")
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the master switch (disable optimization system)."""
        _LOGGER.info("Disabling IntuiHEMS master switch - optimization system OFF")

        result = await self.coordinator.async_disable_auto_control()

        if result.get("status") != "success":
            _LOGGER.error(
                "Failed to disable master switch: %s", result.get("detail")
            )
            # Still refresh to show current state
            await self.coordinator.async_request_refresh()
            return

        _LOGGER.info("Optimization system disabled successfully")
        await self.coordinator.async_request_refresh()

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self.coordinator.last_update_success:
            return False

        # Check if control data is available and not an exception
        control_data = self.coordinator.data.get("control", {})
        return not isinstance(control_data, Exception)


class IntuiThermDemoModeSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable/disable demo mode (MPC runs but doesn't control battery)."""

    def __init__(
        self, coordinator: IntuiThermCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Demo Mode"
        self._attr_icon = "mdi:flask"
        self._attr_unique_id = f"{entry.entry_id}_{SWITCH_TYPE_DEMO_MODE}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Battery Optimizer",
            "manufacturer": "IntuiHEMS",
            "model": "Battery Optimization Service",
            "sw_version": "1.0",
        }
        self._attr_entity_category = None  # Show in controls

    @property
    def is_on(self) -> bool:
        """Return true if demo mode is enabled."""
        config = {**self._entry.data, **self._entry.options}
        detected_entities = config.get(CONF_DETECTED_ENTITIES, {})
        return detected_entities.get(CONF_DRY_RUN_MODE, False)

    @property
    def icon(self) -> str:
        """Return dynamic icon based on state."""
        return "mdi:flask" if self.is_on else "mdi:flask-empty-off"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "description": "Demo mode - MPC runs but doesn't control battery" if self.is_on else "Normal mode - battery control enabled",
            "commands_executed": not self.is_on,
            "warning": "Battery is NOT being controlled - for testing only" if self.is_on else None,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable demo mode."""
        _LOGGER.info("Enabling demo mode - MPC will run but won't control battery")
        
        # Update config entry options
        config = {**self._entry.data, **self._entry.options}
        detected_entities = config.get(CONF_DETECTED_ENTITIES, {})
        detected_entities[CONF_DRY_RUN_MODE] = True
        
        # Update entry options
        new_options = {**self._entry.options}
        new_options[CONF_DETECTED_ENTITIES] = detected_entities
        
        self.hass.config_entries.async_update_entry(
            self._entry,
            options=new_options
        )
        
        _LOGGER.info("Demo mode enabled - battery control disabled")
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable demo mode."""
        _LOGGER.info("Disabling demo mode - enabling battery control")
        
        # Update config entry options
        config = {**self._entry.data, **self._entry.options}
        detected_entities = config.get(CONF_DETECTED_ENTITIES, {})
        detected_entities[CONF_DRY_RUN_MODE] = False
        
        # Update entry options
        new_options = {**self._entry.options}
        new_options[CONF_DETECTED_ENTITIES] = detected_entities
        
        self.hass.config_entries.async_update_entry(
            self._entry,
            options=new_options
        )
        
        _LOGGER.info("Demo mode disabled - battery control enabled")
        await self.coordinator.async_request_refresh()
