"""Home Assistant adapter for the self-use guard: reads entities, runs guard_logic, writes the inverter."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any, Callable

from homeassistant.const import (
    EVENT_HOMEASSISTANT_STARTED,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CoreState, Event, HomeAssistant, State, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BATTERY_MAX_POWER,
    CONF_BATTERY_SOC_ENTITY,
    CONF_DETECTED_ENTITIES,
    CONF_DRY_RUN_MODE,
    CONF_GUARD_BATTERY_POWER_ENTITY,
    CONF_GUARD_FORCE_DISCHARGE_POWER_ENTITY,
    CONF_GUARD_GRID_CT_ENTITIES,
    CONF_GUARD_LOAD_RUNNING_ENTITY,
    CONF_GUARD_MIN_SOC_ENTITY,
    CONF_GUARD_PV_POWER_ENTITY,
    CONF_GUARD_SOC_THRESHOLD,
    CONF_GUARD_Z2_EXPORT_ENTITY,
    CONF_GUARD_Z2_IMPORT_ENTITY,
    CONF_MODE_FORCE_DISCHARGE,
    DEFAULT_BATTERY_MAX_POWER,
    DEFAULT_GUARD_SOC_THRESHOLD,
    GUARD_CRASH_FALLBACK_MODES,
    GUARD_EVAL_INTERVAL_S,
    GUARD_POLL_INTERVAL_S,
    GUARD_REQUIRED_FIELDS,
)
from .guard_logic import Action, Decision, GuardController, GuardState, Snapshot

if TYPE_CHECKING:
    from .battery_control import BatteryControlExecutor

_LOGGER = logging.getLogger(__name__)


def _float_state(state: State | None) -> float | None:
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


def _power_kw(state: State | None) -> float | None:
    value = _float_state(state)
    if value is None:
        return None
    unit = (state.attributes.get("unit_of_measurement") or "").lower()
    if unit == "w":
        return value / 1000
    if unit == "mw":
        return value * 1000
    return value


def _sum_power_kw(states: list[State | None]) -> float | None:
    """Sum of per-phase powers; None if any phase is unavailable (a partial sum would mislead)."""
    values = [_power_kw(state) for state in states]
    if not values or any(v is None for v in values):
        return None
    return sum(values)


class SelfUseGuard:
    """Keeps battery energy out of a controllable load metered on its own contract."""

    def __init__(
        self,
        hass: HomeAssistant,
        executor: BatteryControlExecutor,
        detected: dict[str, Any],
        battery_max_kw: float,
    ) -> None:
        self.hass = hass
        self._executor = executor
        self._z2_import = detected[CONF_GUARD_Z2_IMPORT_ENTITY]
        self._z2_export = detected[CONF_GUARD_Z2_EXPORT_ENTITY]
        self._grid_ct: list[str] = list(detected[CONF_GUARD_GRID_CT_ENTITIES])
        self._battery_power = detected[CONF_GUARD_BATTERY_POWER_ENTITY]
        self._pv_power = detected[CONF_GUARD_PV_POWER_ENTITY]
        self._load_running = detected.get(CONF_GUARD_LOAD_RUNNING_ENTITY) or None
        self._min_soc = detected[CONF_GUARD_MIN_SOC_ENTITY]
        self._soc = detected[CONF_BATTERY_SOC_ENTITY]
        self._setpoint_entity = detected[CONF_GUARD_FORCE_DISCHARGE_POWER_ENTITY]
        self._mode_force_discharge = detected[CONF_MODE_FORCE_DISCHARGE]
        self._dry_run = bool(detected.get(CONF_DRY_RUN_MODE, False))
        self._ctrl = GuardController(
            soc_threshold=float(detected.get(CONF_GUARD_SOC_THRESHOLD, DEFAULT_GUARD_SOC_THRESHOLD)),
            battery_max_kw=battery_max_kw,
            settle_s=GUARD_POLL_INTERVAL_S + 3,
        )
        self._lock = asyncio.Lock()
        self._unsubs: list[Callable[[], None]] = []
        self._listeners: list[Callable[[], None]] = []
        self.running = False

    @classmethod
    def from_config(
        cls, hass: HomeAssistant, executor: BatteryControlExecutor, config: dict[str, Any]
    ) -> SelfUseGuard | None:
        detected = config.get(CONF_DETECTED_ENTITIES, {})
        if not detected.get(CONF_GUARD_Z2_IMPORT_ENTITY):
            return None
        missing = [key for key in (*GUARD_REQUIRED_FIELDS, CONF_BATTERY_SOC_ENTITY) if not detected.get(key)]
        if not executor.battery_mode_select:
            missing.append("battery_mode_select")
        if missing:
            _LOGGER.warning("Self-use guard is configured but inactive; missing: %s", ", ".join(missing))
            return None
        battery_max_kw = float(config.get(CONF_BATTERY_MAX_POWER, DEFAULT_BATTERY_MAX_POWER))
        return cls(hass, executor, detected, battery_max_kw)

    # Lifecycle

    @callback
    def async_start(self) -> None:
        if self.running:
            return
        self.running = True
        self._ctrl.reset("started")
        self._unsubs = [
            async_track_state_change_event(
                self.hass, [self._z2_import, self._z2_export], self._on_z2_change
            ),
            async_track_time_interval(
                self.hass, self._on_timer, timedelta(seconds=GUARD_EVAL_INTERVAL_S)
            ),
        ]
        _LOGGER.info("Self-use guard started (watching %s / %s)", self._z2_import, self._z2_export)
        self._notify()

    async def async_stop(self, restore_self_use: bool) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []
        async with self._lock:
            was_guarding = self._ctrl.state is GuardState.GUARDING
            self.running = False
            self._ctrl.reset("stopped")
            if was_guarding and restore_self_use:
                await self._write_mode(self._executor.mode_self_use, "stop")
        _LOGGER.info("Self-use guard stopped (was_guarding=%s)", was_guarding)
        self._notify()

    @callback
    def async_schedule_startup_reset(self) -> None:
        """After a crash the inverter is left in Force Discharge or foxess_modbus's fallback mode."""
        if self.hass.state is CoreState.running:
            self.hass.async_create_task(self._async_startup_reset())
        else:
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, self._on_ha_started)

    @callback
    def _on_ha_started(self, _event: Event) -> None:
        self.hass.async_create_task(self._async_startup_reset())

    async def _async_startup_reset(self) -> None:
        state = self.hass.states.get(self._executor.battery_mode_select)
        if state is None or state.state not in (self._mode_force_discharge, *GUARD_CRASH_FALLBACK_MODES):
            return
        _LOGGER.warning(
            "Inverter work mode is '%s' at startup (left over from a stopped guard); restoring Self Use",
            state.state,
        )
        await self._write_mode(self._executor.mode_self_use, "startup reset")

    # Inputs

    @callback
    def _on_z2_change(self, event: Event) -> None:
        import_kw = _power_kw(self.hass.states.get(self._z2_import))
        export_kw = _power_kw(self.hass.states.get(self._z2_export))
        if import_kw is None or export_kw is None:
            return
        self._ctrl.on_z2(dt_util.utcnow().timestamp(), import_kw, export_kw)

    @callback
    def _on_timer(self, _now: Any) -> None:
        self.hass.async_create_task(self._async_evaluate())

    def _snapshot(self) -> Snapshot:
        grid_ct = _sum_power_kw([self.hass.states.get(entity_id) for entity_id in self._grid_ct])
        running, changed = None, None
        if self._load_running:
            state = self.hass.states.get(self._load_running)
            if state is not None and state.state in (STATE_ON, STATE_OFF):
                running = state.state == STATE_ON
                changed = state.last_changed.timestamp()
        return Snapshot(
            grid_import_kw=None if grid_ct is None else -grid_ct,
            battery_discharge_kw=_power_kw(self.hass.states.get(self._battery_power)),
            pv_kw=_power_kw(self.hass.states.get(self._pv_power)),
            soc=_float_state(self.hass.states.get(self._soc)),
            min_soc=_float_state(self.hass.states.get(self._min_soc)),
            load_running=running,
            load_changed_ts=changed,
        )

    async def _async_evaluate(self) -> None:
        if self._lock.locked():
            return
        async with self._lock:
            if not self.running:
                return
            now = dt_util.utcnow().timestamp()
            decision = self._ctrl.on_poll(now, self._snapshot())
            if decision.action is not Action.NONE:
                await self._apply(decision)
        self._notify()

    # Outputs

    async def _apply(self, decision: Decision) -> None:
        if decision.action is Action.ENTER:
            _LOGGER.info("Self-use guard: entering Force Discharge at %.2f kW (%s)", decision.setpoint_kw, decision.reason)
            ok = await self._write_setpoint(decision.setpoint_kw)
            ok = ok and await self._write_mode(self._mode_force_discharge, "enter")
            if not ok:
                self._ctrl.reset("enter_failed")
                await self._write_mode(self._executor.mode_self_use, "enter failed")
        elif decision.action is Action.SET:
            _LOGGER.debug("Self-use guard: setpoint %.2f kW", decision.setpoint_kw)
            await self._write_setpoint(decision.setpoint_kw)
        elif decision.action is Action.EXIT:
            _LOGGER.info("Self-use guard: back to Self Use (%s)", decision.reason)
            await self._write_mode(self._executor.mode_self_use, decision.reason)

    async def _write_setpoint(self, kw: float) -> bool:
        state = self.hass.states.get(self._setpoint_entity)
        unit = ((state.attributes.get("unit_of_measurement") if state else None) or "kW").lower()
        value = round(kw * 1000) if unit == "w" else round(kw, 2)
        if state is not None:
            low, high = state.attributes.get("min"), state.attributes.get("max")
            if high is not None:
                value = min(value, high)
            if low is not None:
                value = max(value, low)
        if self._dry_run:
            _LOGGER.info("🎮 Demo mode: guard would set %s to %s", self._setpoint_entity, value)
            return True
        return await self._executor._call_service_resilient(
            "number", "set_value",
            {"entity_id": self._setpoint_entity, "value": value},
            verify_entity=self._setpoint_entity,
            verify_value=value,
            description=f"Guard setpoint {value}",
        )

    async def _write_mode(self, option: str, reason: str) -> bool:
        if self._dry_run:
            _LOGGER.info("🎮 Demo mode: guard would set work mode to %s (%s)", option, reason)
            return True
        select = self._executor.battery_mode_select
        return await self._executor._call_service_resilient(
            "select", "select_option",
            {"entity_id": select, "option": option},
            verify_entity=select,
            verify_value=option,
            description=f"Guard work mode {option} ({reason})",
        )

    # Observability

    @property
    def is_guarding(self) -> bool:
        return self.running and self._ctrl.state is GuardState.GUARDING

    @property
    def status(self) -> str:
        return self._ctrl.state.value if self.running else "off"

    @property
    def diagnostics(self) -> dict[str, Any]:
        ctrl = self._ctrl
        return {
            "setpoint_kw": ctrl.setpoint_kw,
            "setpoint_min_kw": ctrl.a_min,
            "z2_net_import_kw": ctrl.last_n_mean,
            "controllable_load_estimate_kw": ctrl.last_load_estimate,
            "pv_surplus_to_load": ctrl.surplus_to_load,
            "soc_threshold": ctrl.soc_threshold,
            "last_reason": ctrl.last_reason,
            "demo_mode": self._dry_run,
        }

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()
