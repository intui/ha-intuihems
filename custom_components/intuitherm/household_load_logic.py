"""Household load without the controllable load (heat pump on a separate metering contract).

The house load counter (e.g. FoxESS load_power_total, measured at Z1) includes the heat pump.
With separate metering the backend should see only the household, so the integration reports
`house load − S` under the same entity, where S is the heat pump energy subtracted since the
feature was enabled. See docs/PRD_HOUSEHOLD_LOAD_WITHOUT_CONTROLLABLE_LOAD.md.

Pure logic, no Home Assistant imports. Energies in the house load counter's unit.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import asdict, dataclass
from typing import Any

# A fall of the reported counter below this is quantisation (house counter in 0.1 kWh steps)
# and is held back; a larger fall is a real reset or a different counter and passes through.
MAX_HELD_DROP = 0.5


@dataclass
class SubtractionState:
    subtracted: float = 0.0  # S: controllable load energy subtracted so far
    active: bool = False
    since: float | None = None  # timestamp of the last switch on/off; None = never enabled
    subtracted_at_since: float = 0.0
    hp_entity: str | None = None
    hp_last: float | None = None
    load_entity: str | None = None
    last_sent: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SubtractionState:
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in (data or {}).items() if k in fields})

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class HouseholdLoadSubtractor:
    """Running subtraction of the controllable load's energy from a cumulative house load counter."""

    def __init__(self, state: SubtractionState | None = None) -> None:
        self.state = state or SubtractionState()

    def set_active(self, active: bool, hp_entity: str | None, now: float) -> bool:
        """Apply the configured on/off state. Returns True if the state changed."""
        s = self.state
        changed = False
        if active != s.active:
            s.active, s.since, s.subtracted_at_since, changed = active, now, s.subtracted, True
        if active and (changed or hp_entity != s.hp_entity):
            # Switched on, or a different meter: count from its next reading, not the off period
            s.hp_entity, s.hp_last, changed = hp_entity, None, True
        return changed

    def live(self, load_entity: str, load_total: float, hp_total: float | None) -> float:
        """Value to report for the house load counter now."""
        s = self.state
        if s.active and hp_total is not None:
            if s.hp_last is not None and hp_total >= s.hp_last:
                s.subtracted += hp_total - s.hp_last
            # First reading, or counter reset / meter swap (Δ < 0): rebaseline, S unchanged
            s.hp_last = hp_total
        if load_entity != s.load_entity:
            s.load_entity, s.last_sent = load_entity, None
        reported = load_total - s.subtracted
        if s.last_sent is not None and s.last_sent - MAX_HELD_DROP < reported < s.last_sent:
            reported = s.last_sent
        s.last_sent = reported
        return reported

    def backfill(
        self, load_points: list[tuple[float, float]], hp_points: list[tuple[float, float]]
    ) -> list[tuple[float, float]]:
        """Transform historic house load readings [(timestamp, value)] the same way as live().

        S(t) = S − (hp_last − hp(t)): the current S minus the meter energy after t. Readings
        before the last switch on/off are dropped: the backend already holds them, and it
        skips timestamps it has, using the rest only as its delta baseline.
        """
        s = self.state
        if s.since is None:
            return list(load_points)
        hp_times = [t for t, _ in hp_points]
        out: list[tuple[float, float]] = []
        for t, load in load_points:
            if t < s.since:
                continue
            subtracted = s.subtracted
            if s.active and s.hp_last is not None:
                i = bisect_right(hp_times, t) - 1
                if i < 0 or hp_points[i][1] > s.hp_last:
                    continue  # no meter reading yet, or a reset in between: S(t) unknown
                subtracted = max(s.subtracted - (s.hp_last - hp_points[i][1]), s.subtracted_at_since)
            value = load - subtracted
            if out and out[-1][1] - MAX_HELD_DROP < value < out[-1][1]:
                value = out[-1][1]
            out.append((t, value))
        return out
