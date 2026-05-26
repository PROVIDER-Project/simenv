"""
Event state tracker for conditional PDL events.

Cascade timing system precomputes static onset/end windows per param.
The event tracker does dynamic condition evaluation: events only activate when
their cascade day is reached and the pdl condition is satisfied.("brazil_drought.active")
"""

from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class EventDef:
    """
    Single PDL event definition, pre-mapped to simenv params.
    Events without a simenv param (param: None) are also tracked.
    Other events may depend on them.
    """
    id: str
    param: str | None       # simenv param name, None if unmapped
    value: float | None     # converted impact value
    duration: int           # duration (days)
    condition: str          # condition string, "" = unconditional
    impact_field: str       # supply || price


@dataclass(frozen=True)
class TimelineEntry:
    """
    One cascade timeline trigger point.
    """
    at_day: int
    event_id: str


@dataclass
class ActiveEvent:
    """
    Runtime state for a currently active event.
    """
    activated_at: int
    event_def: EventDef


# --- Aggregation constants ---
_CAPACITY_PARAMS = {
    "farm_capacity_bra", "farm_capacity_arg",
    "port_capacity_santos", "port_capacity_paranagua",
    "port_capacity_rotterdam", "port_capacity_hamburg",
    "oil_mill_capacity", "feed_mill_capacity",
}
_PRICE_PARAMS = {"energy_price_factor", "fertilizer_price_factor"}


# --- Event tracker ---
class EventTracker:
    """
    Tracks PDL event activation state and derives per-parameter shock values.

    Rules:
        1. Event becomes eligible when its cascade timeline is reached.
        2. Eligible event activates on the first step where its condition is satisfied.
           Unconditional events activate immediately.
        3. Active event expires after its duration elapses. Events with duration = 0 never expire (permanent).
        4. Once expired, an event does not reactivate.
    """

    def __init__(self, events: list[dict], timeline: list[dict]) -> None:
        # event definition indexed by id
        self._events: dict[str, EventDef] = {}
        for e in events:
            self._events[e["id"]] = EventDef(
                id=e["id"],
                param=e.get("param"),
                value=e.get("value"),
                duration=e.get("duration", 0),
                condition=e.get("condition", ""),
                impact_field=e.get("impact_field", "supply"),
            )

        # timeline sorted by day
        self._timeline: list[TimelineEntry] = sorted(
            [TimelineEntry(at_day=t["at_day"], event_id=t["event_id"]) for t in timeline],
            key=lambda e: e.at_day,
        )

        self._eligible: set[str] = set()            # cascade day reached
        self._active: dict[str, ActiveEvent] = {}   # currently firing
        self._expired: set[str] = set()             # fired and finished

        self._current_day: int = -1

        # derived shock state (re-calc every step)
        self._shock_scales: dict[str, float] = {}
        self._param_values: dict[str, float] = {}


    def step(self, day: int) -> None:
        """
        Advance tracker to the given simulation day.

        Order:
            mark eligible -> expire -> activate -> recompute scales
        """
        self._current_day = day

        # mark newly eligible events
        for entry in self._timeline:
            if entry.at_day <= day:
                eid = entry.event_id
                if eid not in self._eligible and eid not in self._expired:
                    self._eligible.add(eid)

        # expire active events, which have past their duration
        newly_expired: list[str] = []
        for eid, active in self._active.items():
            dur = active.event_def.duration
            if dur > 0 and day >= active.activated_at + dur:
                newly_expired.append(eid)
        for eid in newly_expired:
            del self._active[eid]
            self._expired.add(eid)

        # activate eligible events, which have their condition met
        # unconditional first, then conditional
        pending = []
        for eid in list(self._eligible):
            if eid in self._active or eid in self._expired:
                continue
            edef = self._events.get(eid)
            if edef is None:
                continue
            if not edef.condition:
                self._active[eid] = ActiveEvent(
                    activated_at=day, event_def=edef,
                )
            else:
                pending.append(eid)

        for eid in pending:
            if eid in self._active or eid in self._expired:
                continue
            edef = self._events.get(eid)
            if edef is None:
                continue
            if self._evaluate_condition(edef.condition, day):
                self._active[eid] = ActiveEvent(
                    activated_at=day, event_def=edef,
                )

        self._recompute_scales()


    def get_shock_scale(self, param: str) -> float:
        """
        1.0 if param has any active shock, 0.0 otherwise.
        """
        return self._shock_scales.get(param, 0.0)


    def get_param_value(self, param: str) -> float:
        """
        Aggregated shock value from active events targeting this param.
        Returns 1.0 if no active events targeting this param.
        """
        return self._param_values.get(param, 1.0)


    def is_event_active(self, event_id: str) -> int:
        """
        Days the event has been continuously active. 0 if inactive.
        """
        active = self._active.get(event_id)
        if active is None:
            return 0
        return self._current_day - active.activated_at


    def get_active_event_ids(self) -> set[str]:
        """
        Set of currently active event IDs.
        """
        return set(self._active.keys())


    # --- Condition Evaluator ---
    def _evaluate_condition(self, condition: str, day: int) -> bool:
        """
        Evaluate a PDL condition string against current tracker state.
        """
        condition = condition.strip()
        if not condition:
            return True

        # OR
        if " OR " in condition:
            return any(
                self._evaluate_condition(p, day) for p in condition.split(" OR ")
            )

        # AND
        if " AND " in condition:
            return all(
                self._evaluate_condition(p, day) for p in condition.split(" AND ")
            )

        # "event_id.duration > Xd"
        if ".duration" in condition and ">" in condition:
            event_id = condition.split(".duration")[0].strip()
            threshold_str = condition.split(">")[1].strip().rstrip("d").strip()
            try:
                threshold = int(threshold_str)
            except ValueError:
                return False
            return self.is_event_active(event_id) > threshold

        # "event_id.active"
        if condition.endswith(".active"):
            event_id = condition[:-7]   # len(".active") == 7
            return self.is_event_active(event_id)

        # Unknown format
        return False


    # --- shock scale computation ---
    def _recompute_scales(self) -> None:
        """
        Derive per param shock scales and values from active events.

        Multiple active events on the same param:
            capacity params -> min(values)
            price params -> max(values)
        """
        candidates: dict[str, list[float]] = {}

        for active in self._active.values():
            edef = active.event_def
            if edef.param is not None and edef.value is not None:
                candidates.setdefault(edef.param, []).append(edef.value)

        self._shock_scales.clear()
        self._param_values.clear()

        for param, values in candidates.items():
            self._shock_scales[param] = 1.0
            if param in _CAPACITY_PARAMS:
                self._param_values[param] = min(values)
            elif param in _PRICE_PARAMS:
                self._param_values[param] = max(values)
            else:
                self._param_values[param] = values[0]
