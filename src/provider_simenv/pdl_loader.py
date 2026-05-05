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
    ("santos_port", "supply"): "port_capacity_sa",
    ("paranagua_port", "supply"): "port_capacity_sa",
    ("gas_supply", "price"): "energy_price_factor",
    ("fertilizer_supply", "price"): "fertilizer_price_factor",
    ("eu_oil_mills", "supply"): "oil_mill_capacity",
}

# params where lower = worse (capacity degradation) -> aggregate with min()
_CAPACITY_PARAMS = {"farm_capacity_bra", "port_capacity_sa", "oil_mill_capacity", "feed_mill_capacity"}

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


    def __repr__(self) -> str:
        return f"PDLLoader({self.path.name!r}, label={self.label!r})"
