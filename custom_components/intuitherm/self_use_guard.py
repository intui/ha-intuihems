"""Home Assistant adapter for the self-use guard: reads entities, runs guard_logic, writes the inverter."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any, Callable

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
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
    GUARD_EVAL_INTERVAL_S,
    GUARD_POLL_INTERVAL_S,
    GUARD_REQUIRED_FIELDS,
)
from .guard_logic import Action, Decision, GuardController, GuardState, Snapshot
from .remote_control import (
    async_reset_leftover,
    async_write_mode,
    async_write_number,
    float_state,
    power_kw,
    sum_power_kw,
)

if TYPE_CHECKING:
    from .battery_control import BatteryControlExecutor

_LOGGER = logging.getLogger(__name__)


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
        # Either a binary sensor (on = running) or a power sensor (running above 0.2 kW).
        self._load_entity = detected.get(CONF_GUARD_LOAD_RUNNING_ENTITY) or None
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
        self._warned_grid_ct = False
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

    async def async_startup_reset(self) -> None:
        await async_reset_leftover(self.hass, self._executor, self._mode_force_discharge, self._dry_run)

    # Inputs

    def _sample_z2(self) -> None:
        # Freshness comes from last_reported: an unchanged value (e.g. 0 W while the guard
        # balances Z2) fires no state change but is still reported.
        states = [self.hass.states.get(self._z2_import), self.hass.states.get(self._z2_export)]
        import_kw, export_kw = (power_kw(state) for state in states)
        if import_kw is None or export_kw is None:
            return
        reported = max(state.last_reported for state in states)
        self._ctrl.on_z2(reported.timestamp(), import_kw, export_kw)

    @callback
    def _on_timer(self, _now: Any) -> None:
        self.hass.async_create_task(self._async_evaluate())

    def _snapshot(self) -> Snapshot:
        grid_ct = sum_power_kw([self.hass.states.get(entity_id) for entity_id in self._grid_ct])
        running, changed, load_kw = None, None, None
        if self._load_entity:
            state = self.hass.states.get(self._load_entity)
            if self._load_entity.startswith("binary_sensor."):
                if state is not None and state.state in (STATE_ON, STATE_OFF):
                    running = state.state == STATE_ON
                    changed = state.last_changed.timestamp()
            else:
                load_kw = power_kw(state)
        return Snapshot(
            grid_import_kw=None if grid_ct is None else -grid_ct,
            battery_discharge_kw=power_kw(self.hass.states.get(self._battery_power)),
            pv_kw=power_kw(self.hass.states.get(self._pv_power)),
            soc=float_state(self.hass.states.get(self._soc)),
            min_soc=float_state(self.hass.states.get(self._min_soc)),
            load_running=running,
            load_changed_ts=changed,
            load_kw=load_kw,
        )

    async def _async_evaluate(self) -> None:
        if self._lock.locked():
            return
        async with self._lock:
            if not self.running:
                return
            self._sample_z2()
            now = dt_util.utcnow().timestamp()
            decision = self._ctrl.on_poll(now, self._snapshot())
            if decision.action is not Action.NONE:
                await self._apply(decision)
            if self._ctrl.grid_ct_implausible and not self._warned_grid_ct:
                self._warned_grid_ct = True
                _LOGGER.warning(
                    "Self-use guard: grid CT sensors %s look wrong. Z1 import is mostly below Z2 import, "
                    "which is physically impossible. Use the signed Grid CT sensors (feed-in positive), "
                    "not import-only ones such as 'Grid Consumption'",
                    ", ".join(self._grid_ct),
                )
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
        return await async_write_number(self.hass, self._executor, self._setpoint_entity, kw, self._dry_run, "Guard")

    async def _write_mode(self, option: str, reason: str) -> bool:
        return await async_write_mode(self._executor, option, self._dry_run, f"Guard ({reason})")

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
            "controllable_load_kw": ctrl.last_load_kw,
            "controllable_load_source": ctrl.load_source,
            "grid_ct_plausible": not ctrl.grid_ct_implausible,
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
