"""Resolve the sidecar's product ids: what each list ships and, for processes, takes."""

from dataclasses import replace

from .agents import (
    ROLE_CONSUMER,
    ROLE_FEED_MANUFACTURER,
    ROLE_LAND_TRANSPORT,
    ROLE_PROCESSOR,
    ROLE_SEA_TRANSPORT,
)

_TRANSPORTS = {ROLE_LAND_TRANSPORT, ROLE_SEA_TRANSPORT}
_PROCESSES = {ROLE_PROCESSOR, ROLE_FEED_MANUFACTURER}


def _ids(value, name, role):
    if isinstance(value, str):
        value = {"ships": value}
    if not isinstance(value, dict) or "ships" not in value or value.keys() - {"ships", "takes"}:
        raise ValueError(f"products {name}: expected an id or {{ships, takes}}")
    if "takes" in value and role not in _PROCESSES:
        raise ValueError(f"products {name}: only processes take a product")
    for key, product in value.items():
        if not isinstance(product, str) or not product:
            raise ValueError(f"products {name}: {key} must be a non-empty id")
    ids = {"product": value["ships"]}
    if "takes" in value:
        ids["input_product"] = value["takes"]
    return ids


def resolve_products(roster, raw_products):
    """Return fresh roster entries carrying product ids. Without the section, products are unused."""
    if not raw_products:
        return roster
    if not isinstance(raw_products, dict):
        raise ValueError("products section must be a mapping")  # noqa: TRY004 -- configuration error
    roles = {entry.archetype.name: entry.archetype.role for entry in roster}
    unknown = sorted(raw_products.keys() - roles.keys())
    if unknown:
        raise ValueError(f"products contains unknown roster targets: {unknown}")
    listed = sorted(name for name in raw_products if roles[name] in _TRANSPORTS)
    if listed:
        raise ValueError(f"products: transports carry their sources' product, remove {listed}")
    missing = sorted(name for name, role in roles.items()
                     if role not in _TRANSPORTS | {ROLE_CONSUMER} and name not in raw_products)
    if missing:
        raise ValueError(f"products: no product for {missing}")
    resolved = []
    for entry in roster:
        arc = entry.archetype
        if arc.name in raw_products:
            params = dict(arc.params)
            params["attrs"] = {**params.get("attrs", {}),
                               **_ids(raw_products[arc.name], arc.name, arc.role)}
            entry = replace(entry, archetype=replace(arc, params=params))
        resolved.append(entry)
    return resolved
