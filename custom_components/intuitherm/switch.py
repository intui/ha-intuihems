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
        IntuiThermDemoModeSwitch(coordinator, entry),
    ]

    async_add_entities(switches)
    _LOGGER.info("IntuiTherm switches added")


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
        
        # Update config entry options. IMPORTANT: build a fresh copy of
        # detected_entities rather than mutating it in place - the dict
        # returned by config.get() may be the SAME object as
        # self._entry.data[CONF_DETECTED_ENTITIES] (or a previous options
        # dict). Mutating it in place before calling async_update_entry()
        # makes HA's old-vs-new equality check see "no change", so the
        # write is silently skipped and never persisted to disk - the
        # toggle appears to work until the next HA restart, when it
        # reverts to the last value that was actually saved.
        config = {**self._entry.data, **self._entry.options}
        detected_entities = dict(config.get(CONF_DETECTED_ENTITIES, {}))
        detected_entities[CONF_DRY_RUN_MODE] = True
        
        # Update entry options
        new_options = {**self._entry.options, CONF_DETECTED_ENTITIES: detected_entities}
        
        self.hass.config_entries.async_update_entry(
            self._entry,
            options=new_options
        )
        
        _LOGGER.info("Demo mode enabled - battery control disabled")
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable demo mode."""
        _LOGGER.info("Disabling demo mode - enabling battery control")
        
        # Update config entry options (see async_turn_on for why we copy
        # detected_entities instead of mutating it in place).
        config = {**self._entry.data, **self._entry.options}
        detected_entities = dict(config.get(CONF_DETECTED_ENTITIES, {}))
        detected_entities[CONF_DRY_RUN_MODE] = False
        
        # Update entry options
        new_options = {**self._entry.options, CONF_DETECTED_ENTITIES: detected_entities}
        
        self.hass.config_entries.async_update_entry(
            self._entry,
            options=new_options
        )
        
        _LOGGER.info("Demo mode disabled - battery control enabled")
        await self.coordinator.async_request_refresh()
