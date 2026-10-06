"""Home Assistant adapter: report household load without the controllable load (heat pump).

Wraps household_load_logic with persistence and unit handling. The coordinator passes the
house load through `async_live` (every send) and `backfill` (historic readings at HA start).
"""
from __future__ import annotations

import asyncio
from datetime import datetime
import logging
from typing import Any

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import CONF_GUARD_LOAD_ENERGY_ENTITY, CONF_GUARD_LOAD_RUNNING_ENTITY, DOMAIN
from .household_load_logic import HouseholdLoadSubtractor, SubtractionState
from .remote_control import float_state, power_kw

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
_ENERGY_FACTOR = {"wh": 0.001, "kwh": 1.0, "mwh": 1000.0}


def _energy_factor(state: State | None) -> float | None:
    """kWh per unit of an energy sensor; None if the unit isn't an energy unit."""
    unit = ((state.attributes.get("unit_of_measurement") if state else None) or "").lower()
    return _ENERGY_FACTOR.get(unit)


def is_cumulative(state: State) -> bool:
    """Same classification as the data upload (coordinator / config_flow._classify_sensor)."""
    attributes = state.attributes
    unit = attributes.get("unit_of_measurement")
    return (
        (unit and unit.lower() in ["kwh", "wh", "mwh"])
        or attributes.get("device_class") == "energy"
        or attributes.get("state_class") == "total_increasing"
    )


class HouseholdLoad:
    """Subtracts the controllable load from the reported house load (separate metering)."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.household_load.{entry_id}")
        self._sub = HouseholdLoadSubtractor()
        self._hp_entity: str | None = None
        self._power_entity: str | None = None
        self._loaded = False
        self._lock = asyncio.Lock()  # backfill and the first send configure concurrently at startup

    async def async_configure(self, detected: dict[str, Any]) -> None:
        """Load persisted state once, then apply the current options."""
        async with self._lock:
            await self._async_configure(detected)

    async def _async_configure(self, detected: dict[str, Any]) -> None:
        if not self._loaded:
            self._sub = HouseholdLoadSubtractor(SubtractionState.from_dict(await self._store.async_load()))
            self._loaded = True
        self._hp_entity = detected.get(CONF_GUARD_LOAD_ENERGY_ENTITY) or None
        power = detected.get(CONF_GUARD_LOAD_RUNNING_ENTITY)
        self._power_entity = power if power and power.startswith("sensor.") else None
        if self._sub.set_active(self._hp_entity is not None, self._hp_entity, dt_util.utcnow().timestamp()):
            _LOGGER.info(
                "Household load reporting: heat pump subtraction %s",
                f"on ({self._hp_entity})" if self._hp_entity else "off",
            )
            await self._store.async_save(self._sub.state.as_dict())

    @property
    def subtracted_kwh(self) -> float:
        return round(self._sub.state.subtracted, 3)

    async def async_live(self, load_entity: str, load_state: State, value: float) -> float:
        """Value to send for the house load entity."""
        if not is_cumulative(load_state):
            return self._live_power(load_state, value)
        if self._sub.state.since is None:
            return value  # never enabled: nothing to do, nothing to persist
        hp_kwh = None
        if self._hp_entity:
            hp_state = self.hass.states.get(self._hp_entity)
            hp_factor = _energy_factor(hp_state)
            hp_value = float_state(hp_state)
            if hp_factor is not None and hp_value is not None:
                hp_kwh = hp_value * hp_factor
        load_factor = _energy_factor(load_state) or 1.0
        hp_in_load_unit = None if hp_kwh is None else hp_kwh / load_factor
        reported = self._sub.live(load_entity, value, hp_in_load_unit)
        await self._store.async_save(self._sub.state.as_dict())
        if reported != value:
            _LOGGER.debug(
                "House load %.3f − heat pump %.3f (since enabled) → reported %.3f",
                value, self._sub.state.subtracted, reported,
            )
        return reported

    def _live_power(self, load_state: State, value: float) -> float:
        """Power-type house load: subtract the controllable load's current power."""
        if not self._hp_entity or not self._power_entity:
            return value
        hp_kw = power_kw(self.hass.states.get(self._power_entity))
        if hp_kw is None:
            return value
        unit = (load_state.attributes.get("unit_of_measurement") or "kW").lower()
        hp_in_load_unit = hp_kw * 1000 if unit == "w" else hp_kw
        return max(0.0, value - hp_in_load_unit)

    @property
    def backfill_entity(self) -> str | None:
        """Meter whose history the backfill needs (only while the subtraction is on)."""
        return self._hp_entity if self._sub.state.active else None

    def backfill(
        self, load_state: State | None, readings: list[dict[str, Any]], hp_states: list[State]
    ) -> list[dict[str, Any]]:
        """Transform historic house load readings [{"timestamp", "value"}] like the live path."""
        if self._sub.state.since is None:
            return readings
        if load_state is None or not is_cumulative(load_state):
            return []  # historic power can't be corrected; raw values would include the heat pump
        load_factor = _energy_factor(load_state) or 1.0
        hp_points = []
        for state in hp_states:
            factor, value = _energy_factor(state) or _energy_factor(self.hass.states.get(state.entity_id)), float_state(state)
            if factor is not None and value is not None:
                hp_points.append((state.last_changed.timestamp(), value * factor / load_factor))
        points = [(datetime.fromisoformat(r["timestamp"]).timestamp(), r["value"]) for r in readings]
        out = self._sub.backfill(points, hp_points)
        return [
            {"timestamp": datetime.fromtimestamp(t, tz=dt_util.UTC).isoformat(), "value": v} for t, v in out
        ]
