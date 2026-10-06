"""Control logic for planned Force Charge on FoxESS via foxess_modbus remote control.

The optimiser's Force Charge power is the total battery charging power p_bat. foxess_modbus
remote control sets the inverter's AC power instead (battery = PV + import, or PV - export),
so the tracker translates: inverter AC setpoint A = PV - p_bat, as Force Charge (import -A)
or Force Discharge (export A). PV beyond p_bat goes to the house first, then the battery;
nothing is exported while the battery can still charge.

Kept free of Home Assistant imports so it can be unit-tested with plain pytest. All powers in kW.
See docs/PRD_FOXESS_FORCE_CHARGE_BATTERY_POWER.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

DEADBAND_KW = 0.1
# A switch between Force Charge and Force Discharge writes the work mode; only switch once the
# direction has been stable this long, and hold the setpoint at 0 meanwhile.
SWITCH_STABLE_S = 60.0
TRIM_GAIN = 0.3
TRIM_LIMIT_KW = 0.5
# Trim and saturation checks need measurements taken after the inverter applied the last
# setpoint (next foxess_modbus poll) and are evaluated at most once per poll.
DEFAULT_SETTLE_S = 13.0
DEFAULT_POLL_S = 10.0
# In export direction the inverter outputs exactly A and the battery takes PV - A. If that hits
# the battery's charging limit, the inverter curtails PV, and the PV sensor then only shows the
# PV used, so available PV is invisible. While the battery charges at its limit, the output is
# raised step by step (never above measured PV); once it charges clearly below, it's lowered.
LIMIT_MARGIN_KW = 0.1
LIMIT_RELEASE_KW = 0.5
RAISE_STEP_KW = 0.3
# A full battery can't take PV, and curtailment can't be detected: hand over to native Self Use.
FULL_SOC_PCT = 99.0


class TrackerMode(str, Enum):
    CHARGE = "charge"  # Force Charge: inverter imports the setpoint
    DISCHARGE = "discharge"  # Force Discharge: inverter outputs the setpoint
    FALLBACK = "fallback"  # inputs unavailable: Force Charge with a fixed setpoint
    HANDOVER = "handover"  # battery full: native Self Use for the rest of the quarter hour


@dataclass
class TrackerInputs:
    pv_kw: float | None
    battery_discharge_kw: float | None  # discharge positive, charge negative
    grid_import_kw: float | None  # at the inverter's grid meter, import positive
    soc: float | None = None


@dataclass
class TrackerDecision:
    mode: TrackerMode | None  # mode to switch to; None = keep the current one
    setpoint_kw: float
    reason: str = ""


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class ChargeTrackerController:
    def __init__(
        self,
        p_bat_kw: float,
        battery_max_kw: float,
        settle_s: float = DEFAULT_SETTLE_S,
        poll_s: float = DEFAULT_POLL_S,
    ) -> None:
        self.p_bat = clamp(p_bat_kw, 0.0, battery_max_kw)
        self.battery_max = battery_max_kw
        self.settle_s = settle_s
        self.poll_s = poll_s
        self.mode: TrackerMode | None = None
        self.setpoint_kw: float | None = None
        self.trim_kw = 0.0
        self.raise_kw = 0.0
        self.last_reason = ""
        self.last_house_kw: float | None = None
        self._last_pv: float | None = None
        self._flip_since: float | None = None
        self._settle_until = float("-inf")
        self._last_measured = float("-inf")

    def on_poll(self, now: float, inp: TrackerInputs) -> TrackerDecision | None:
        if self.mode in (TrackerMode.FALLBACK, TrackerMode.HANDOVER):
            return None
        if inp.soc is not None and inp.soc >= FULL_SOC_PCT:
            self.mode, self.setpoint_kw, self.last_reason = TrackerMode.HANDOVER, 0.0, "battery_full"
            return TrackerDecision(TrackerMode.HANDOVER, 0.0, self.last_reason)
        if inp.pv_kw is None or inp.battery_discharge_kw is None or inp.grid_import_kw is None:
            return self._fallback()
        self._last_pv = inp.pv_kw
        house = inp.grid_import_kw + inp.pv_kw + inp.battery_discharge_kw
        self.last_house_kw = house
        a = inp.pv_kw - self.p_bat
        wanted = TrackerMode.DISCHARGE if a >= 0 else TrackerMode.CHARGE

        mode = self._choose_mode(now, wanted)
        measured = now >= self._settle_until and now - self._last_measured >= self.poll_s
        if measured:
            self._last_measured = now
        charge_kw = -inp.battery_discharge_kw

        if mode is TrackerMode.CHARGE:
            if measured and self.mode is TrackerMode.CHARGE and wanted is TrackerMode.CHARGE:
                self.trim_kw = clamp(self.trim_kw + TRIM_GAIN * (charge_kw - self.p_bat), -TRIM_LIMIT_KW, TRIM_LIMIT_KW)
            target = max(0.0, -a - self.trim_kw) if wanted is TrackerMode.CHARGE else 0.0
            reason = "charging_from_grid" if target > 0 else "pv_covers_plan"
        else:
            target = clamp(min(a, house), 0.0, max(a, 0.0)) if wanted is TrackerMode.DISCHARGE else 0.0
            reason = "pv_surplus_to_house"
            if measured and self.mode is TrackerMode.DISCHARGE:
                if charge_kw >= self.battery_max - LIMIT_MARGIN_KW:
                    self.raise_kw += RAISE_STEP_KW
                elif charge_kw < self.battery_max - LIMIT_RELEASE_KW:
                    self.raise_kw = max(0.0, self.raise_kw - RAISE_STEP_KW)
            if self.raise_kw > 0:
                target = min(target + self.raise_kw, inp.pv_kw)
                reason = "battery_at_limit"
        target = round(target, 2)

        if mode is self.mode and self.setpoint_kw is not None and abs(target - self.setpoint_kw) < DEADBAND_KW:
            return None
        switched = mode is not self.mode
        if switched:
            self.trim_kw, self.raise_kw = 0.0, 0.0
        self.mode, self.setpoint_kw, self.last_reason = mode, target, reason
        self._settle_until = now + self.settle_s
        return TrackerDecision(mode if switched else None, target, reason)

    def _choose_mode(self, now: float, wanted: TrackerMode) -> TrackerMode:
        if self.mode is None:
            return wanted
        if wanted is self.mode:
            self._flip_since = None
            return self.mode
        if self._flip_since is None:
            self._flip_since = now
        if now - self._flip_since >= SWITCH_STABLE_S:
            self._flip_since = None
            return wanted
        return self.mode

    def _fallback(self) -> TrackerDecision:
        target = round(max(0.0, self.p_bat - self._last_pv) if self._last_pv is not None else self.p_bat, 2)
        self.mode, self.setpoint_kw, self.last_reason = TrackerMode.FALLBACK, target, "inputs_unavailable"
        return TrackerDecision(TrackerMode.FALLBACK, target, self.last_reason)
