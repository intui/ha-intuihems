"""Home Assistant adapter for the Force Charge tracker: reads FoxESS entities, runs charge_tracker_logic,
writes the inverter via foxess_modbus remote control."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .charge_tracker_logic import ChargeTrackerController, TrackerDecision, TrackerInputs, TrackerMode
from .const import GUARD_EVAL_INTERVAL_S, GUARD_POLL_INTERVAL_S
from .remote_control import (
    async_reset_leftover,
    FoxessEntities,
    async_write_mode,
    detect_foxess_entities,
    async_write_number,
    float_state,
    power_kw,
    sum_power_kw,
)

if TYPE_CHECKING:
    from .battery_control import BatteryControlExecutor

_LOGGER = logging.getLogger(__name__)


class ForceChargeTracker:
    """Charges the battery at the planned power during Force Charge (FoxESS via foxess_modbus)."""

    def __init__(
        self,
        hass: HomeAssistant,
        executor: BatteryControlExecutor,
        soc_entity: str | None,
        battery_max_kw: float,
        dry_run: bool,
    ) -> None:
        self.hass = hass
        self._executor = executor
        # Resolved at first use: at HA startup foxess_modbus may not have published its states yet.
        self._entities: FoxessEntities | None = None
        self._soc_entity = soc_entity
        self._battery_max_kw = battery_max_kw
        self._dry_run = dry_run
        self._ctrl: ChargeTrackerController | None = None
        self._lock = asyncio.Lock()
        self._unsub: Callable[[], None] | None = None
        self._listeners: list[Callable[[], None]] = []
        self.running = False

    # Lifecycle

    @callback
    def async_start(self, p_bat_kw: float) -> bool:
        """(Re)start for a new Force Charge quarter hour. False if the FoxESS entities aren't all there."""
        if self._entities is None:
            self._entities = detect_foxess_entities(self.hass, self._executor.battery_mode_select)
            if self._entities is None:
                return False
        self._ctrl = ChargeTrackerController(
            p_bat_kw, battery_max_kw=self._battery_max_kw, settle_s=GUARD_POLL_INTERVAL_S + 3,
            poll_s=GUARD_POLL_INTERVAL_S,
        )
        if not self.running:
            self.running = True
            self._unsub = async_track_time_interval(
                self.hass, self._on_timer, timedelta(seconds=GUARD_EVAL_INTERVAL_S)
            )
        _LOGGER.info("Force Charge tracker started: planned battery power %.2f kW", self._ctrl.p_bat)
        self.hass.async_create_task(self._async_evaluate())
        self._notify()
        return True

    async def async_startup_reset(self) -> None:
        if self._entities is None:
            self._entities = detect_foxess_entities(self.hass, self._executor.battery_mode_select)
        option = self._entities.mode_force_discharge if self._entities else None
        await async_reset_leftover(self.hass, self._executor, option, self._dry_run)

    async def async_stop(self, restore_self_use: bool) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        async with self._lock:
            was_active = self.running and self._ctrl is not None and self._ctrl.mode is not None
            self.running = False
            if was_active and restore_self_use:
                await async_write_mode(self._executor, self._executor.mode_self_use, self._dry_run, "Force Charge tracker (stop)")
        if was_active:
            _LOGGER.info("Force Charge tracker stopped")
        self._notify()

    # Inputs

    @callback
    def _on_timer(self, _now: Any) -> None:
        self.hass.async_create_task(self._async_evaluate())

    def _inputs(self) -> TrackerInputs:
        grid_ct = sum_power_kw([self.hass.states.get(e) for e in self._entities.grid_ct])
        return TrackerInputs(
            pv_kw=power_kw(self.hass.states.get(self._entities.pv_power)),
            battery_discharge_kw=power_kw(self.hass.states.get(self._entities.battery_power)),
            grid_import_kw=None if grid_ct is None else -grid_ct,
            soc=float_state(self.hass.states.get(self._soc_entity)) if self._soc_entity else None,
        )

    async def _async_evaluate(self) -> None:
        if self._lock.locked():
            return
        async with self._lock:
            if not self.running or self._ctrl is None:
                return
            decision = self._ctrl.on_poll(dt_util.utcnow().timestamp(), self._inputs())
            if decision is not None:
                await self._apply(decision)
        self._notify()

    # Outputs

    async def _apply(self, decision: TrackerDecision) -> None:
        e, label = self._entities, "Force Charge tracker"
        if decision.mode is TrackerMode.HANDOVER:
            _LOGGER.info("%s: battery full, handing over to Self Use", label)
            await async_write_mode(self._executor, self._executor.mode_self_use, self._dry_run, label)
            return
        charging = self._ctrl.mode in (TrackerMode.CHARGE, TrackerMode.FALLBACK)
        number = e.force_charge_power if charging else e.force_discharge_power
        await async_write_number(self.hass, self._executor, number, decision.setpoint_kw, self._dry_run, label)
        if decision.mode is not None:
            option = self._executor.mode_force_charge if charging else e.mode_force_discharge
            _LOGGER.info("%s: %s at %.2f kW (%s)", label, option, decision.setpoint_kw, decision.reason)
            await async_write_mode(self._executor, option, self._dry_run, label)

    # Observability

    @property
    def status(self) -> str:
        if not self.running or self._ctrl is None or self._ctrl.mode is None:
            return "off"
        return {
            TrackerMode.CHARGE: "charging_from_grid",
            TrackerMode.DISCHARGE: "pv_surplus_to_house",
            TrackerMode.FALLBACK: "fallback",
            TrackerMode.HANDOVER: "battery_full",
        }[self._ctrl.mode]

    @property
    def diagnostics(self) -> dict[str, Any]:
        ctrl = self._ctrl
        if ctrl is None:
            return {"demo_mode": self._dry_run}
        return {
            "planned_battery_kw": ctrl.p_bat,
            "inverter_setpoint_kw": ctrl.setpoint_kw,
            "house_load_kw": ctrl.last_house_kw,
            "trim_kw": ctrl.trim_kw,
            "raise_kw": ctrl.raise_kw,
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
