"""Immutable value objects returned across the DataSource seam.

These are the ONLY data shapes the view layer (map, timeline, HUD) ever sees.
No pandas DataFrame, no CSV row, no SQL cursor ever crosses this boundary — so a
future PostgresDataSource is a drop-in swap with zero view changes.

Field names mirror the real CSV columns in Result_Simulator_*.csv; nothing here
is invented. See NOTES.md for the CSV-now / Postgres-later rationale.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnvState:
    """One row of Result_Simulator_Environment.csv for a (scenario, period)."""
    scenario: int
    period: int
    soja_price: float
    feed_price: float
    shock_scale: float          # 0.0 .. 1.0  (drives corridor/node shock tint)
    drought_severity: float     # 0.0 .. 1.0
    total_soja_supply: float
    transport_utilisation: float  # GLOBAL utilisation — no per-port breakdown exists
    current_step: int


@dataclass(frozen=True)
class NodeThroughput:
    """Per-period state of one agent within an entity group.

    `active` is only meaningful for farmers (their CSV has an `active` column);
    other groups always report active=True. `quantity` drives node size/color;
    farmers gray-out when active is False.

    `quantity` is whichever throughput column the group exposes (soja
    quantity_available for most; livestock_output for EuFarmers, who are
    consumers, not producers). `unit_price` is None for groups that have no
    price (EuFarmers) — the view renders that as "—". The exact column each
    group maps to is declared in csv_source._GROUP_COLUMNS.
    """
    group: str                  # e.g. "BraFarmers", "Wholesalers", "Processors"
    id: int
    quantity: float
    unit_price: float | None
    active: bool


@dataclass(frozen=True)
class OriginFlows:
    """Wholesaler export volumes by origin, summed over all wholesalers.

    These are the only flow magnitudes in the data. There is NO per-port lane
    flow — ports are visual waypoints (see NOTES.md). Drives line width/opacity
    and (Phase 3) the number of moving ship icons per corridor.
    """
    scenario: int
    period: int
    bra_volume: float
    arg_volume: float
    usa_volume: float
