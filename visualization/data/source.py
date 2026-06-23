"""The DataSource seam — the single boundary the view layer depends on.

The map, timeline, and HUD import ONLY from this module (and `models`). They
never touch pandas, CSV, or SQL. Today the concrete implementation is
`CsvDataSource`; the target is a `PostgresDataSource` reading per-tick rows from
`tick_writer.py`. Because both satisfy this Protocol and return the frozen value
objects from `models.py`, swapping sources requires zero view changes.

This is a structural (runtime-checkable) Protocol: a class is a DataSource if it
has these methods — no explicit subclassing required.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import EnvState, NodeThroughput, OriginFlows


@runtime_checkable
class DataSource(Protocol):
    """Read-only access to recorded simulation output, keyed by scenario/period.

    All methods are pure reads. Implementations should be cheap to call once per
    timeline tick (the view calls environment_at / node_throughput / origin_flows
    on every period change), so implementations are expected to cache as needed.
    """

    def scenarios(self) -> list[int]:
        """All id_scenario values present in the output, ascending."""
        ...

    def periods(self, scenario: int) -> list[int]:
        """All period values for one scenario, ascending (e.g. 0..364)."""
        ...

    def environment_at(self, scenario: int, period: int) -> EnvState:
        """Environment row for one (scenario, period): prices, shock, transport."""
        ...

    def node_throughput(self, scenario: int, period: int) -> list[NodeThroughput]:
        """Every agent's state at one (scenario, period), across all groups.

        One NodeThroughput per (group, id). The view indexes these by group+id
        to size/color each node; farmers carry their real `active` flag.
        """
        ...

    def origin_flows(self, scenario: int, period: int) -> OriginFlows:
        """Wholesaler bra/arg/usa export volumes summed for one (scenario, period)."""
        ...

    def reload(self) -> None:
        """Invalidate any cached state so the next read reflects fresh output.

        Called after the app runs the simulation. CsvDataSource drops its cached
        DataFrames; a streaming source (e.g. Postgres) may treat this as a no-op.
        """
        ...
