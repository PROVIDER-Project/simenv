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

import warnings
from pathlib import Path
from traceback import format_exc

import yaml


# mapping table
# ---------------------------------------------------------------------------
# Key : (PDL entity id, impact field) - "supply" or "price"
# Value : SupplyChainScenario field name
#
# Only 5 parameters the current simenv model can consume are listed.
# Both santos_port and paranagua_port map to the same param (port_capacity_sa)
# when both appear the min() is taken
#----------------------------------------------------------------------------

_PDL_MAPPING: dict[tuple[str, str], str] = {
    ("brazil_farms", "supply"): "farm_capacity_bra",
    ("argentina_farms", "supply"): "farm_capacity_arg",
    ("santos_port", "supply"): "port_capacity_santos",
    ("paranagua_port", "supply"): "port_capacity_paranagua",
    ("rotterdam_port", "supply"): "port_capacity_rotterdam",
    ("hamburg_port", "supply"): "port_capacity_hamburg",
    ("gas_supply", "price"): "energy_price_factor",
    ("fertilizer_supply", "price"): "fertilizer_price_factor",
    ("eu_oil_mills", "supply"): "oil_mill_capacity",
}

# params where lower = worse (capacity degradation) -> aggregate with min()
_CAPACITY_PARAMS = {"farm_capacity_bra", "farm_capacity_arg",
                    "port_capacity_santos", "port_capacity_paranagua",
                    "port_capacity_rotterdam", "port_capacity_hamburg",
                    "oil_mill_capacity", "feed_mill_capacity"}

# params where higher = worse (price spikes) -> aggregate with max()
_PRICE_PARAMS = {"energy_price_factor", "fertilizer_price_factor"}


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


    def to_scenario_overrides(self) -> dict[str, float]:
        """
        Scan PDL events and return scenario parameters overrides.

        Only the 5 parameters th current simenv model can consume are populated.
        All other PDL events are silently skipped on the current version.

        Returns
        --------
        dict[str, float]
            e.g. {"farm_capacity_bra": 0.60, "port_capacity_sa": 0.80, ...}
        """

        # collect all candidate values per scenario param name
        candidates: dict[str, list[float]] = {}

        events: list[dict] = self._doc.get("events") or []

        for event in events:
            target: str = (event.get("trigger") or {}).get("target", "")
            impact: dict = event.get("impact") or {}

            for field in ("supply", "price"):
                raw = impact.get(field)
                if raw is None:
                    continue

                param = _PDL_MAPPING.get((target, field))
                if param is None:
                    continue    # not a mapped combination, skip silently

                pct = _parse_percent(str(raw))
                value = round(1.0 + pct / 100.0, 6)
                candidates.setdefault(param, []).append(value)

        # reduce candidates to a single value per param
        overrides: dict[str, float] = {}
        for param, values in candidates.items():
            if param in _CAPACITY_PARAMS:
                overrides[param] = min(values)  # worst-case supply
            elif param in _PRICE_PARAMS:
                overrides[param] = max(values)  # worst-case price
            else:
                overrides[param] = values[0]

        if not overrides:
            warnings.warn(
                f"PDLLoader: no mappable events found in '{self.path.name}'."
                "Check that entity IDs match the expected PDL mapping.",
                stacklevel=2,
            )

        return overrides


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


    def _build_event_index(self) -> dict[str, dict]:
        """
        Return a dict mapping event id -> event dict for fast lookup.
        """
        return {e["id"]: e for e in (self._doc.get("events") or [])}


    def to_cascade_schedule(self, cascade_id: str | None = None) -> dict[str, dict[str, int]]:
        """
        Parse a cascade timeline and return per-parameter shock schedule.

        For each scenario parameter the current model can consume,
        returns the onset day (when the shock starts) and end day (when it ends).
        Onset comes from the cascade timeline's 'at:' field.
        End is onset + the matching event's 'impact.duration'.

        When multiple timeline entries map to the same scenario parameter:
            onset = min(all onset days) -> shock starts at earliest trigger
            end = max(all end days) -> shock lasts until latest event expires

            e.g.
            - {at: 14d, event: soy_export_reduction} -> santos_port -> port_capacity_santos
            - {at: 21d, event: port_congestion} -> santos_port -> port_capacity_santos

        :param cascade_id:
            cascade_id: str | None
            ID of the cascade to read (e.g. "soy_crisis_cascade")
            If None, the first cascae in the file is used.

        :return:
            dict[str, dict[str, int]]
            e.g.
            {
                "farm_capacity_bra": {"onset": 0, "end": 90},
                "port_capacity_santos": {"onset": 14, "end": 134},
            }
        """
        cascade = self._get_cascade(cascade_id)
        event_index = self._build_event_index()
        timeline = cascade.get("timeline") or []

        candidates: dict[str, list[tuple[int, int]]] = {}

        for entry in timeline:
            onset_day = _parse_duration(entry.get("at", "0d"))
            event_id = entry.get("event", "")
            event = event_index.get(event_id)
            if event is None:
                continue

            target = (event.get("trigger") or {}).get("target", "")
            impact = event.get("impact") or {}
            duration_raw = impact.get("duration")
            duration_days = _parse_duration(duration_raw) if duration_raw else 0
            end_day = onset_day + duration_days

            for field in ("supply", "price"):
                if impact.get(field) is None:
                    continue
                param = _PDL_MAPPING.get((target, field))
                if param is None:
                    continue
                candidates.setdefault(param, []).append((onset_day, end_day))

        # earliest onset, latest end
        return {
            param: {
                "onset": min(p[0] for p in pairs),
                "end": max(p[1] for p in pairs),
            }
            for param, pairs in candidates.items()
        }


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
                mapped = _PDL_MAPPING.get((target, field))
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
