"""Control logic for the self-use guard (separate metering contract, Messkonzept 8.3).

Kept free of Home Assistant imports so it can be unit-tested with plain pytest.
All powers are in kW. See docs/PRD_HEATPUMP_SEPARATE_METERING_SELFUSE.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

GAIN_UP = 0.5
GAIN_DOWN = 1.0
DEADBAND_KW = 0.1
MIN_SETPOINT_CHANGE_KW = 0.01
ENTRY_OUTBOUND_KW = 0.1
ENTRY_DISCHARGE_KW = 0.1
ENTRY_CONFIRM_READINGS = 2
EXIT_CONFIRM_S = 30.0
Z2_STALE_S = 30.0
Z1_EXPORT_EXIT_KW = 0.1
LOAD_RUNNING_KW = 0.2
# After entry, an indicator still reporting "off" is trusted once this has passed
# (longer than one IDM refresh; covers runs too short for IDM to ever report "on").
LOAD_OFF_TRUST_S = 180.0
SOC_HYSTERESIS_PCT = 3.0
# foxess_modbus applies a new setpoint at its next poll; Z2 readings before that would be
# corrected twice. Default = 10 s poll + 3 s for Tibber to report the effect.
DEFAULT_SETTLE_S = 13.0
# Increases are capped at the lowest household load implied over this window. An appliance
# switching faster than the ~30 s control loop then takes its on-phases from the grid,
# instead of the battery pushing power to the controllable load in its off-phases.
BASE_LOAD_WINDOW_S = 60.0
# Physics: Z1 import = Z2 import + controllable load >= Z2 import. Grid CT sensors that
# violate this most of the time while Z2 imports have the wrong sign or are import-only.
PLAUSIBILITY_MIN_Z2_KW = 0.3
PLAUSIBILITY_TOLERANCE_KW = 0.3
# Only steady moments count: with fast-switching loads, Tibber and FoxESS readings taken at
# different instants contradict each other even when the sensors are right.
PLAUSIBILITY_STEADY_KW = 0.2
PLAUSIBILITY_MIN_SAMPLES = 30
PLAUSIBILITY_BAD_RATIO = 0.8


class GuardState(str, Enum):
    WATCHING = "watching"
    GUARDING = "guarding"


class Action(str, Enum):
    NONE = "none"
    ENTER = "enter"
    SET = "set"
    EXIT = "exit"


@dataclass
class Snapshot:
    """Inverter-side values from one FoxESS poll. None = unavailable."""

    grid_import_kw: float | None  # G at Z1, import positive
    battery_discharge_kw: float | None  # D, discharge positive
    pv_kw: float | None
    soc: float | None
    min_soc: float | None
    load_running: bool | None = None  # binary indicator; None = not configured/unavailable
    load_changed_ts: float | None = None
    load_kw: float | None = None  # measured load power; None = no power sensor/unavailable


@dataclass
class Decision:
    action: Action
    setpoint_kw: float | None = None
    reason: str = ""


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class GuardController:
    """State machine + integral controller on the Z2 net flow."""

    def __init__(
        self, soc_threshold: float, battery_max_kw: float, settle_s: float = DEFAULT_SETTLE_S
    ) -> None:
        self.soc_threshold = soc_threshold
        self.battery_max_kw = battery_max_kw
        self.settle_s = settle_s
        self._settle_until = float("-inf")
        self.state = GuardState.WATCHING
        self.setpoint_kw: float | None = None
        self.surplus_to_load: bool | None = None
        self.last_reason = ""
        self.last_n_mean: float | None = None
        self.last_load_kw: float | None = None
        self.load_source: str | None = None
        self.grid_ct_implausible = False
        self._plaus_samples = 0
        self._plaus_bad = 0
        self._prev_plaus_n: float | None = None
        self._implied_load: list[tuple[float, float]] = []
        self.a_min: float | None = None
        self._z2_buffer: list[float] = []
        self._last_z2_ts: float | None = None
        self._last_z2_net: float | None = None
        self._outbound_streak = 0
        self._entered_ts: float | None = None
        self._exit_since: float | None = None

    def on_z2(self, ts: float, import_kw: float, outbound_kw: float) -> None:
        if ts == self._last_z2_ts:
            return  # same report seen again
        net = import_kw - outbound_kw
        if ts >= self._settle_until:
            self._z2_buffer.append(net)
        self._last_z2_ts = ts
        self._last_z2_net = net
        self._outbound_streak = self._outbound_streak + 1 if outbound_kw > ENTRY_OUTBOUND_KW else 0

    def reset(self, reason: str = "") -> None:
        self.state = GuardState.WATCHING
        self.setpoint_kw = None
        self.a_min = None
        self._settle_until = float("-inf")
        self._z2_buffer = []
        self._implied_load = []
        self._entered_ts = None
        self._exit_since = None
        self._outbound_streak = 0
        if reason:
            self.last_reason = reason

    def on_poll(self, now: float, snap: Snapshot) -> Decision:
        if self._last_z2_ts is None or now - self._last_z2_ts > Z2_STALE_S:
            return self._safety_exit("z2_stale")
        required = (snap.grid_import_kw, snap.battery_discharge_kw, snap.pv_kw, snap.soc, snap.min_soc)
        if any(v is None for v in required):
            return self._safety_exit("inverter_data_unavailable")
        if snap.soc <= snap.min_soc:
            return self._safety_exit("soc_at_min")

        self._update_routing(snap.soc)
        n_fresh = self._consume_z2()
        n_mean = n_fresh if n_fresh is not None else self._last_z2_net
        self.last_n_mean = n_mean
        self._check_plausibility(snap.grid_import_kw, n_fresh)
        if snap.load_kw is not None:
            self.last_load_kw, self.load_source = snap.load_kw, "power_sensor"
        else:
            self.last_load_kw, self.load_source = snap.grid_import_kw - n_mean, "z1_minus_z2"
        a_min = snap.pv_kw if self.surplus_to_load else 0.0
        a_max = max(a_min, snap.pv_kw + self.battery_max_kw)
        self.a_min = a_min

        if self.state is GuardState.WATCHING:
            return self._maybe_enter(now, snap, n_mean, a_min, a_max)
        return self._regulate(now, snap, n_fresh, a_min, a_max)

    def _consume_z2(self) -> float | None:
        if not self._z2_buffer:
            return None
        n_mean = sum(self._z2_buffer) / len(self._z2_buffer)
        self._z2_buffer = []
        return n_mean

    def _check_plausibility(self, grid_import_kw: float, n_fresh: float | None) -> None:
        if n_fresh is None:
            return
        prev, self._prev_plaus_n = self._prev_plaus_n, n_fresh
        if prev is None or abs(n_fresh - prev) >= PLAUSIBILITY_STEADY_KW:
            return
        # Only while Z2 imports: then Z1 must import at least as much, while import-only
        # sensors read with the wrong sign show <= 0 every time.
        if n_fresh < PLAUSIBILITY_MIN_Z2_KW:
            return
        self._plaus_samples += 1
        self._plaus_bad += grid_import_kw < n_fresh - PLAUSIBILITY_TOLERANCE_KW
        if self._plaus_samples >= PLAUSIBILITY_MIN_SAMPLES:
            self.grid_ct_implausible = self._plaus_bad / self._plaus_samples >= PLAUSIBILITY_BAD_RATIO

    def _update_routing(self, soc: float) -> None:
        if self.surplus_to_load is None:
            self.surplus_to_load = soc >= self.soc_threshold
        elif soc >= self.soc_threshold:
            self.surplus_to_load = True
        elif soc < self.soc_threshold - SOC_HYSTERESIS_PCT:
            self.surplus_to_load = False

    def _safety_exit(self, reason: str) -> Decision:
        if self.state is GuardState.GUARDING:
            self.reset(reason)
            return Decision(Action.EXIT, reason=reason)
        self.last_reason = reason
        return Decision(Action.NONE, reason=reason)

    def _maybe_enter(
        self, now: float, snap: Snapshot, n_mean: float, a_min: float, a_max: float
    ) -> Decision:
        # Never enter where an exit condition already holds: the load must draw power
        # (measured, else Z1 - Z2; the binary indicator lags too much) and Z1 must not export.
        if (
            snap.battery_discharge_kw > ENTRY_DISCHARGE_KW
            and self._outbound_streak >= ENTRY_CONFIRM_READINGS
            and self.last_load_kw >= LOAD_RUNNING_KW
            and snap.grid_import_kw >= -Z1_EXPORT_EXIT_KW
        ):
            household_kw = snap.pv_kw + snap.battery_discharge_kw + n_mean
            self.setpoint_kw = round(clamp(household_kw, a_min, a_max), 2)
            self.state = GuardState.GUARDING
            self._entered_ts = now
            self._settle_until = now + self.settle_s
            self._z2_buffer = []
            self._implied_load = [(now, household_kw)]
            self._exit_since = None
            self.last_reason = "battery_feeding_controllable_load"
            return Decision(Action.ENTER, self.setpoint_kw, self.last_reason)
        return Decision(Action.NONE)

    def _load_off(self, now: float, snap: Snapshot) -> bool:
        if snap.load_kw is not None:
            return snap.load_kw < LOAD_RUNNING_KW
        if snap.load_running is None:
            return self.last_load_kw < LOAD_RUNNING_KW
        if snap.load_running:
            return False
        if snap.load_changed_ts is None:
            return True
        # An "off" carried over from before entry is IDM lag at start-up, not a stop.
        return snap.load_changed_ts > self._entered_ts or now - self._entered_ts >= LOAD_OFF_TRUST_S

    def _regulate(
        self, now: float, snap: Snapshot, n_fresh: float | None, a_min: float, a_max: float
    ) -> Decision:
        z1_exporting = snap.grid_import_kw < -Z1_EXPORT_EXIT_KW
        if z1_exporting or self._load_off(now, snap):
            if self._exit_since is None:
                self._exit_since = now
            elif now - self._exit_since >= EXIT_CONFIRM_S:
                reason = "z1_exporting" if z1_exporting else "controllable_load_off"
                self.reset(reason)
                return Decision(Action.EXIT, reason=reason)
        else:
            self._exit_since = None

        current = self.setpoint_kw if self.setpoint_kw is not None else a_min
        settled = now >= self._settle_until and n_fresh is not None
        if settled:
            self._implied_load.append((now, current + n_fresh))
        self._implied_load = [(t, v) for t, v in self._implied_load if now - t <= BASE_LOAD_WINDOW_S]
        target = current
        if settled and abs(n_fresh) >= DEADBAND_KW:
            if n_fresh > 0:
                base_load = min(v for _, v in self._implied_load)
                target = min(current + GAIN_UP * n_fresh, max(base_load, current))
            else:
                target = current + GAIN_DOWN * n_fresh
        target = round(clamp(target, a_min, a_max), 2)
        if abs(target - current) < MIN_SETPOINT_CHANGE_KW:
            return Decision(Action.NONE)
        self.setpoint_kw = target
        self._settle_until = now + self.settle_s
        self._z2_buffer = []
        return Decision(Action.SET, target)
