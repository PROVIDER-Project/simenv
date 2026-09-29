"""
PostgreSQL table and view definitions

The shape of the tables tick_writer.py writes and export_bundle.py reads.
Written out as explicit DDL rather than left to pandas type inference, so the
column types are what this file says instead of what the first batch of rows
happened to imply.

Storage is four tables: sim_run (one row per invocation), sim_agent (one
row per recorded agent per run), sim_metric (one row per kind of measurement,
shared by all runs) and sim_tick (one row per measured value, keys and
numbers only). A PDL declaring other entities adds rows, never tables,
columns or views.

Reading goes through views generated here from the fixed role and metric
lists: sim_tick_readable joins the keys back to names, and one
sim_<role>_view per role pivots metrics into columns. Every name embedded in
view SQL comes from a constant in this codebase and is checked to be a plain
identifier.

Every table statement is CREATE TABLE IF NOT EXISTS and every view statement
is CREATE OR REPLACE VIEW; nothing in this codebase drops a table or a view.
docs/postgres-schema.md documents the columns, their units, and which of them
an external consumer may rely on.
"""

import re
from typing import NamedTuple

from .data_collector import _PROPS_BY_ROLE, ENVIRONMENT_PROPS

# The environment is recorded as one agent per run, under these sentinels.
ENVIRONMENT_ENTITY_ID = "environment"
ENVIRONMENT_ROLE = "environment"
ENVIRONMENT_AGENT_ID = 0

SIM_RUN_TABLE = "sim_run"
SIM_AGENT_TABLE = "sim_agent"
SIM_METRIC_TABLE = "sim_metric"
SIM_TICK_TABLE = "sim_tick"
SIM_TICK_READABLE_VIEW = "sim_tick_readable"


class Metric(NamedTuple):
    name: str
    unit: str
    description: str
    # stored as 1.0 / 0.0, read back as boolean in the role views
    flag: bool = False


# A unit is never changed in place: a changed unit needs a new metric name.
METRICS = (
    Metric(
        "quantity_available", "output units per period",
        "How much of its output good the agent has ready this period.",
    ),
    Metric(
        "unit_price", "currency per output unit",
        "The agent's asking price this period; 0.0 when it has nothing "
        "to sell.",
    ),
    Metric(
        "storage_utilization", "ratio, 0.0-1.0",
        "Stock divided by storage capacity.",
    ),
    Metric(
        "feed_received", "feed units per period",
        "Feed collected from upstream traders, split evenly across active "
        "consumers.",
    ),
    Metric(
        "livestock_output", "output units per period",
        "Livestock produced, proportional to feed_received.",
    ),
    Metric(
        "active", "flag, 1.0 or 0.0",
        "Whether the agent is still in the market.",
        flag=True,
    ),
    Metric(
        "soy_price", "currency per unit",
        "Weighted average price across active wholesalers.",
    ),
    Metric(
        "feed_price", "currency per unit",
        "Weighted average price across active feed traders.",
    ),
    Metric(
        "shock_scale", "multiplier",
        "Largest active shock multiplier this period; 0.0 when nothing is "
        "shocked.",
    ),
    Metric(
        "drought_severity", "ratio, 0.0-1.0",
        "Largest active drought severity this period.",
    ),
    Metric(
        "total_soy_supply", "output units",
        "Sum of quantity_available across the PDL's producer regions.",
    ),
    Metric(
        "transport_utilisation", "ratio, 0.0-1.0",
        "Average utilisation across transport agents.",
    ),
    Metric(
        "current_step", "day",
        "The period index; redundant with period.",
    ),
)

METRICS_BY_NAME = {m.name: m for m in METRICS}

DDL = (
    """
    CREATE TABLE IF NOT EXISTS sim_run (
        run_id       text        PRIMARY KEY,
        started_at   timestamptz NOT NULL,
        finished_at  timestamptz,
        status       text        NOT NULL
                     CHECK (status IN ('running', 'completed', 'failed')),
        pdl          text,
        pdl_sha256   text,
        scenario_ids integer[]   NOT NULL,
        period_num   integer     NOT NULL,
        git_sha      text,
        label        text
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sim_agent (
        agent_key integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        run_id    text    NOT NULL REFERENCES sim_run (run_id),
        entity_id text    NOT NULL,
        role      text    NOT NULL,
        agent_id  integer NOT NULL,
        UNIQUE (run_id, entity_id, agent_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sim_metric (
        metric_id   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        name        text    NOT NULL UNIQUE,
        unit        text    NOT NULL,
        description text    NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sim_tick (
        agent_key   integer          NOT NULL
                    REFERENCES sim_agent (agent_key),
        id_scenario integer          NOT NULL,
        metric_id   integer          NOT NULL
                    REFERENCES sim_metric (metric_id),
        period      integer          NOT NULL,
        value       double precision NOT NULL,
        PRIMARY KEY (agent_key, id_scenario, metric_id, period)
    )
    """,
)

_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*")


def _identifier(name: str) -> str:
    """name unchanged, or ValueError if not a plain lowercase identifier."""
    if not _IDENTIFIER.fullmatch(name):
        raise ValueError(f"not a plain SQL identifier: {name!r}")
    return name


def role_view_name(role: str) -> str:
    """``feed_trader`` -> ``sim_feed_trader_view``."""
    return f"sim_{_identifier(role)}_view"


def _metric_column(name: str) -> str:
    column = _identifier(name)
    pivot = f"max(t.value) FILTER (WHERE m.name = '{column}')"
    if METRICS_BY_NAME[name].flag:
        return f"{pivot} <> 0 AS {column}"
    return f"{pivot} AS {column}"


def _role_view(
    role: str, metrics: tuple[str, ...], keys: tuple[str, ...],
) -> str:
    columns = ",\n           ".join(
        [*keys, *(_metric_column(name) for name in metrics)]
    )
    return f"""
    CREATE OR REPLACE VIEW {role_view_name(role)} AS
    SELECT {columns}
    FROM sim_tick t
    JOIN sim_agent  a ON a.agent_key = t.agent_key
    JOIN sim_metric m ON m.metric_id = t.metric_id
    WHERE a.role = '{_identifier(role)}'
    GROUP BY {", ".join(keys)}
    """


_AGENT_KEYS = (
    "a.run_id", "t.id_scenario", "t.period", "a.entity_id", "a.agent_id",
)
_ENVIRONMENT_KEYS = ("a.run_id", "t.id_scenario", "t.period")

VIEW_DDL = (
    """
    CREATE OR REPLACE VIEW sim_tick_readable AS
    SELECT a.run_id, t.id_scenario, t.period,
           a.entity_id, a.role, a.agent_id,
           m.name AS metric, m.unit, t.value
    FROM sim_tick t
    JOIN sim_agent  a ON a.agent_key = t.agent_key
    JOIN sim_metric m ON m.metric_id = t.metric_id
    """,
    *(
        _role_view(role, metrics, _AGENT_KEYS)
        for role, metrics in _PROPS_BY_ROLE.items()
    ),
    _role_view(ENVIRONMENT_ROLE, ENVIRONMENT_PROPS, _ENVIRONMENT_KEYS),
)
