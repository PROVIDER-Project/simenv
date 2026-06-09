"""
Maps PDL YAML scenario files to SupplyChainScenario parameters.

PDL (Provider Domain Language) is a YAML-based DSL for supply chain disruption scenarios.


Conversion rules
----------------
    supply impact: capacity = 1.0 + pct / 100   e.g. "-40%" -> 0.60
    price impact: price_factor = 1.0 + pct / 100   e.g. "+200%" -> 3.0

Aggregation (when multiple events target the same entity)
----------------------------------------------------------
    capacity params -> take min()  # worst case supply degradation
    price params -> take max()  # worst case price spike

"""

from pathlib import Path

import yaml

try:
    from shock_registry import BINDING, aggregate
except ImportError:
    from .shock_registry import BINDING, aggregate



# -------
# Helpers
# -------

def _parse_percent(raw: str) -> float:
    """
    Convert a PDL impact string to a plain float

    examples:
        "-40%" -> -40.0
        "+200%" -> 200.0
        "+80%" -> 80.0
    """
    return float(raw.strip().rstrip("%").replace("+", ""))


def _parse_duration(raw: str) -> int:
    """
    Convert  PDL duration/offset string to plain integer days.

    examples:
        "0d" -> 0
        "14d" -> 14
        "90d" -> 90
    """
    return int(str(raw).strip().rstrip("d"))


# ------
# Loader
# ------

class PDLLoader:
    """
    Loads a PDL YAML scenario file and translates the events section into
    SupplyChainScenario parameter overrides.

    Parameters
    -----------
    path : str / Path
        Path to a *.pdl.yaml file, e.g. "scenarios/s1-soja.pdl.yaml".
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        with self.path.open("r", encoding="utf-8") as f:
            self._doc: dict = yaml.safe_load(f)
        self.label: str = self._doc.get("scenario", {}).get("name", self.path.stem)




    def _get_cascade(self, cascade_id: str | None) -> dict:
        """
        Return the cascade dict matching cascade_id, or the first one if None.
        """
        cascades = self._doc.get("cascades") or []
        if not cascades:
            raise ValueError(f"No cascade section found in '{self.path.name}'.")
        if cascade_id is None:
            return cascades[0]
        for c in cascades:
            if c.get("id") == cascade_id:
                return c
        raise ValueError(
            f"Cascase '{cascade_id}' not found in '{self.path.name}'.'"
            f"Available cascade IDs: {[c.get('id') for c in cascades]}."
        )


    def to_event_registry(self, cascade_id: str | None = None) -> dict:
        """
        Export event definitions and cascade timeline for the EventTracker.

        All PDL events are included, events without a simenv param mapping get param=None / value=None
        """
        events: list[dict] = []
        for event in (self._doc.get("events") or []):
            eid = event.get("id", "")
            trigger = event.get("trigger") or {}
            target = trigger.get("target", "")
            condition = trigger.get("condition", "")
            impact = event.get("impact") or {}

            duration_raw = impact.get("duration")
            duration = _parse_duration(duration_raw) if duration_raw else 0

            # find the first mapped (target, field)
            param = None
            value = None
            impact_field = "supply"

            for field in ("supply", "price"):
                raw = impact.get(field)
                if raw is None:
                    continue
                mapped = BINDING.get((target, field))
                if mapped is not None:
                    pct = _parse_percent(str(raw))
                    param = mapped
                    value = round(1.0 + pct / 100.0, 6)
                    impact_field = field
                    break               # one param per event

            events.append({
                "id": eid,
                "param": param,
                "value": value,
                "duration": duration,
                "condition": condition,
                "impact_field": impact_field,
            })

        # --- cascade timeline ---
        cascade = self._get_cascade(cascade_id)
        timeline: list[dict] = []
        for entry in (cascade.get("timeline") or []):
            timeline.append({
                "at_day": _parse_duration(entry.get("at", "0d")),
                "event_id": entry.get("event", ""),
            })

        return {"events": events, "timeline": timeline}


    def __repr__(self) -> str:
        return f"PDLLoader({self.path.name!r}, label={self.label!r})"
