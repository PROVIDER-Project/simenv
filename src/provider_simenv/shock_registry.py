"""
Single source of truth for the shock-parameter registry.

To expose a new (entity, impact) to the model: add one row to BINDING.
"""
from __future__ import annotations



# The (entity, impact_field) key, whose supply degradation defines drought severity.
DROUGHT_KEY: tuple[str, str] = ("brazil_farms", "supply")

def aggregate(impact_field: str, values: list[float]) -> float:
    """
    The single aggregation rule, a function of the impact fields:
        supply -> min()     (worst-case capacity degradation)
        price -> max()      (worst-case price spike)
    """
    return min(values) if impact_field == "supply" else max(values)