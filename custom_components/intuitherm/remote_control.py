"""Shared helpers for steering the inverter via foxess_modbus remote control.

Used by the self-use guard and the Force Charge tracker: sensor reading with unit conversion,
Modbus-resilient writes of setpoints and work modes, and detection of the foxess_modbus entities.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

if TYPE_CHECKING:
    from .battery_control import BatteryControlExecutor

_LOGGER = logging.getLogger(__name__)

FOXESS_MODBUS_PLATFORM = "foxess_modbus"
# foxess_modbus leaves the inverter in this mode when remote control times out (HA crash)
CRASH_FALLBACK_MODES = ("Feed-in First",)


def float_state(state: State | None) -> float | None:
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


def power_kw(state: State | None) -> float | None:
    value = float_state(state)
    if value is None:
        return None
    unit = (state.attributes.get("unit_of_measurement") or "").lower()
    if unit == "w":
        return value / 1000
    if unit == "mw":
        return value * 1000
    return value


def sum_power_kw(states: list[State | None]) -> float | None:
    """Sum of per-phase powers; None if any phase is unavailable (a partial sum would mislead)."""
    values = [power_kw(state) for state in states]
    if not values or any(v is None for v in values):
        return None
    return sum(values)


async def async_write_number(
    hass: HomeAssistant, executor: BatteryControlExecutor, entity_id: str, kw: float, dry_run: bool, label: str
) -> bool:
    """Write a power setpoint in the entity's own unit, clamped to its min/max."""
    state = hass.states.get(entity_id)
    unit = ((state.attributes.get("unit_of_measurement") if state else None) or "kW").lower()
    value = round(kw * 1000) if unit == "w" else round(kw, 2)
    if state is not None:
        low, high = state.attributes.get("min"), state.attributes.get("max")
        if high is not None:
            value = min(value, high)
        if low is not None:
            value = max(value, low)
    if dry_run:
        _LOGGER.info("🎮 Demo mode: %s would set %s to %s", label, entity_id, value)
        return True
    return await executor._call_service_resilient(
        "number", "set_value",
        {"entity_id": entity_id, "value": value},
        verify_entity=entity_id,
        verify_value=value,
        description=f"{label} setpoint {value}",
    )


async def async_write_mode(executor: BatteryControlExecutor, option: str, dry_run: bool, label: str) -> bool:
    if dry_run:
        _LOGGER.info("🎮 Demo mode: %s would set work mode to %s", label, option)
        return True
    select = executor.battery_mode_select
    return await executor._call_service_resilient(
        "select", "select_option",
        {"entity_id": select, "option": option},
        verify_entity=select,
        verify_value=option,
        description=f"{label} work mode {option}",
    )


def is_foxess_modbus(hass: HomeAssistant, mode_select: str | None) -> bool:
    entry = er.async_get(hass).async_get(mode_select) if mode_select else None
    return entry is not None and entry.platform == FOXESS_MODBUS_PLATFORM


async def async_reset_leftover(
    hass: HomeAssistant, executor: BatteryControlExecutor, force_discharge_option: str | None, dry_run: bool
) -> None:
    """After a crash the inverter is left in Force Discharge or foxess_modbus's fallback mode."""
    state = hass.states.get(executor.battery_mode_select)
    leftovers = {*CRASH_FALLBACK_MODES, *([force_discharge_option] if force_discharge_option else [])}
    if state is None or state.state not in leftovers:
        return
    _LOGGER.warning("Inverter work mode is '%s' at startup (left over from remote control); restoring Self Use", state.state)
    await async_write_mode(executor, executor.mode_self_use, dry_run, "startup reset")


@dataclass
class FoxessEntities:
    """foxess_modbus entities needed to steer the inverter's AC power via remote control."""

    pv_power: str
    battery_power: str  # signed, discharge positive
    grid_ct: list[str]  # signed, feed-in positive; one per phase on three-phase inverters
    force_charge_power: str
    force_discharge_power: str
    mode_force_discharge: str


def _match(entries: list[er.RegistryEntry], domain: str, key: str) -> str | None:
    key = key.lower()
    for entry in entries:
        uid = str(entry.unique_id).lower()
        if entry.domain == domain and (uid == key or uid.endswith(f"_{key}")):
            return entry.entity_id
    return None


def detect_foxess_entities(hass: HomeAssistant, mode_select: str | None) -> FoxessEntities | None:
    """Find the remote-control entities on the foxess_modbus device that owns the work mode select.

    Matches on unique_id (`[prefix_]key`), so renamed entities are still found. Returns None
    unless every entity is present, so callers keep their previous behaviour.
    """
    if not mode_select:
        return None
    registry = er.async_get(hass)
    select_entry = registry.async_get(mode_select)
    if select_entry is None or select_entry.platform != FOXESS_MODBUS_PLATFORM or not select_entry.device_id:
        return None
    entries = [
        e for e in er.async_entries_for_device(registry, select_entry.device_id)
        if e.platform == FOXESS_MODBUS_PLATFORM and not e.disabled_by
    ]
    grid_single = _match(entries, "sensor", "grid_ct")
    grid_phases = [_match(entries, "sensor", f"grid_ct_{p}") for p in "rst"]
    grid_ct = [grid_single] if grid_single else ([p for p in grid_phases if p] if all(grid_phases) else [])

    select_state = hass.states.get(mode_select)
    options = list((select_state.attributes.get("options") or []) if select_state else [])
    mode_force_discharge = next(
        (o for o in options if "force" in o.lower() and "discharge" in o.lower()), None
    )
    found = dict(
        pv_power=_match(entries, "sensor", "pv_power_now"),
        battery_power=_match(entries, "sensor", "invbatpower"),
        force_charge_power=_match(entries, "number", "force_charge_power"),
        force_discharge_power=_match(entries, "number", "force_discharge_power"),
        mode_force_discharge=mode_force_discharge,
    )
    missing = [k for k, v in found.items() if not v] + ([] if grid_ct else ["grid_ct"])
    if missing:
        _LOGGER.info("foxess_modbus remote-control entities incomplete, missing: %s", ", ".join(missing))
        return None
    return FoxessEntities(grid_ct=grid_ct, **found)
