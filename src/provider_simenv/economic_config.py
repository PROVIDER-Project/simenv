"""Resolve the sidecar's typed economic settings without embedding entities."""

from copy import deepcopy
from dataclasses import replace

from provider_agents.offis_agents.economics import (
    nonnegative,
    validate_cost_shares,
)

_COMMON = {"fixed_costs", "input_cost_shares"}
_PARAMETERS = {
    "producer": _COMMON | {"margin", "base_yield"},
    "consumer": _COMMON,
    "wholesaler": _COMMON | {"margin", "storage_capacity"},
    "feed_trader": _COMMON | {"margin"},
    "processor": _COMMON | {
        "margin", "conversion_ratio", "throughput_capacity",
    },
    "feed_manufacturer": _COMMON | {
        "margin", "conversion_ratio", "throughput_capacity",
    },
    "land_transport": _COMMON | {"margin", "capacity", "transit_steps"},
    "sea_transport": _COMMON | {"margin", "capacity", "transit_steps"},
}


def _mapping(value, context):
    if not isinstance(value, dict):
        raise ValueError(  # noqa: TRY004 -- configuration errors use ValueError
            f"economics {context} must be a mapping",
        )
    return value


def _parameters(raw, role):
    values = _mapping(raw, "parameters")
    unknown = values.keys() - _PARAMETERS[role]
    if unknown:
        raise ValueError(f"economics unsupported {role} parameters: {unknown}")
    result = deepcopy(values)
    for name, value in values.items():
        if name == "input_cost_shares":
            validate_cost_shares(value)
        elif name == "throughput_capacity" and value is None:
            continue
        else:
            nonnegative(value, name)
            if name == "conversion_ratio" and value == 0:
                raise ValueError("economics conversion_ratio must be positive")
            if name == "transit_steps" and not isinstance(value, int):
                raise ValueError("economics transit_steps must be an integer")
    if "margin" in result and role in ("land_transport", "sea_transport"):
        result["margin_transport"] = result.pop("margin")
    return result


def _bindings(raw, entity_ids):
    result = {}
    for slot, target in _mapping(raw, "bindings").items():
        if (not isinstance(slot, str) or not slot or slot == "capacity"
                or not isinstance(target, (tuple, list)) or len(target) != 2
                or not all(isinstance(item, str) for item in target)
                or target[0] not in entity_ids
                or target[1] not in ("price", "supply")):
            raise ValueError(f"economics invalid binding {slot!r}: {target!r}")
        result[slot] = tuple(target)
    return result


def resolve_economics(roster, raw_economics, entity_ids):
    """Return fresh roster entries; explicit settings win over defaults."""
    economics = _mapping(raw_economics, "section")
    names = {entry.archetype.name for entry in roster}
    if economics.keys() - names:
        raise ValueError("economics contains unknown roster targets")
    resolved = []
    for entry in roster:
        arc = entry.archetype
        config = _mapping(economics.get(arc.name, {}), arc.name)
        if config.keys() - {"parameters", "bindings"}:
            raise ValueError(f"economics {arc.name}: unknown settings")
        try:
            attrs = _parameters(config.get("parameters", {}), arc.role)
            bindings = {
                **arc.params.get("bindings", {}),
                **_bindings(config.get("bindings", {}), entity_ids),
            }
            defaults = arc.agent_class.agent_type.defaults
            shares = attrs.get("input_cost_shares", arc.params.get(
                "attrs", {},
            ).get("input_cost_shares", defaults["input_cost_shares"]))
            for slot, share in shares.items():
                if not share:
                    continue
                if slot not in bindings:
                    if "input_cost_shares" in attrs:
                        raise ValueError(f"unbound price exposure {slot!r}")
                    continue  # unbound compatibility defaults remain neutral
                entity, impact = bindings[slot]
                if entity not in entity_ids or impact != "price":
                    raise ValueError(f"invalid price exposure {slot!r}")
        except ValueError as exc:
            raise ValueError(f"economics {arc.name}: {exc}") from exc
        params = deepcopy(dict(arc.params))
        if attrs:
            params["attrs"] = {**params.get("attrs", {}), **attrs}
        if bindings:
            params["bindings"] = bindings
        params["scenario_attrs"] = {
            attr: source for attr, source
            in params.get("scenario_attrs", {}).items() if attr not in attrs
        }
        resolved.append(replace(entry, archetype=replace(arc, params=params)))
    return resolved
