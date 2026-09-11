"""
Single source of truth for the shock-parameter registry.

To expose a new (entity, impact) to the model: add one row to BINDING.
"""
from __future__ import annotations



# The impact_field whose degradation defines drought severity. Which entities it
# applies to come from the PDL roster (every producer), not from this module.
DROUGHT_IMPACT_FIELD: str = "supply"

def aggregate(impact_field: str, values: list[float]) -> float:
    """
    The single aggregation rule, a function of the impact fields:
        supply -> min()     (worst-case capacity degradation)
        price -> max()      (worst-case price spike)
    """
    return min(values) if impact_field == "supply" else max(values)
