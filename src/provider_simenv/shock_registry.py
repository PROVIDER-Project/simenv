"""
Single source of truth for the shock-parameter registry.

To expose a new (entity, impact) to the model: add one row to BINDING.
"""
from __future__ import annotations


# (PDL entity id, impact field "supply"|"price") -> SupplyChainScenario / model param name.
BINDING: dict[tuple[str, str], str] = {
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

# Binding key whose supply degradation defines drought severity.
_DROUGHT_KEY: tuple[str, str] = ("brazil_farms", "supply")


def param_for(entity: str, impact_field: str) -> str | None:
    """
    Resolve a (PDL entity, impact field) pair to a model param name, or None if unbound.
    """
    return BINDING.get((entity, impact_field))


def param_names() -> set[str]:
    """
    All model params the registry can bind. Drives the environment's shock_scales keys.
    """
    return set(BINDING.values())


def drought_param() -> str:
    """
    Param tracked by the drought-severity indicator. Derived from BINDING.
    """
    return BINDING[_DROUGHT_KEY]

def aggregate(impact_field: str, values: list[float]) -> float:
    """
    The single aggregation rule, a function of the impact fields:
        supply -> min()     (worst-case capacity degradation)
        price -> max()      (worst-case price spike)
    """
    return min(values) if impact_field == "supply" else max(values)