"""
Per-tick PostgreSQL writer

Writes agent and environment state to the database after every simulation step.
    - palaestrAI can query live data mid-run

Run lifecycle:
    1. TickWriter.__init__ -> drops and recreates all tables
    2. write_tick() * 52 -> append one tick's row per call
    3. End of run        -> tables are complete, identical to batch import

Failure handling:
    If Postgres is unreachable or sqlalchemy/psycopg2 is missing,
    TickWriter silently disables itself. The simulation continues normally.
    CSV and SQLite outputs are unaffected.
"""

from __future__ import annotations
import logging

import pandas as pd

from .agents import (
    ROLE_CONSUMER,
    ROLE_FEED_MANUFACTURER,
    ROLE_FEED_TRADER,
    ROLE_PROCESSOR,
    ROLE_PRODUCER,
    ROLE_WHOLESALER,
)
from .data_collector import _PROPS_BY_ROLE

logger = logging.getLogger(__name__)

AGENT_TABLES: dict[str, tuple[str, list[str]]] = {
    "Result_Simulator_BraFarmers":        ("brazil_farms",        list(_PROPS_BY_ROLE[ROLE_PRODUCER])),
    "Result_Simulator_ArgFarmers":        ("argentina_farms",     list(_PROPS_BY_ROLE[ROLE_PRODUCER])),
    "Result_Simulator_UsaFarmers":        ("us_farms",            list(_PROPS_BY_ROLE[ROLE_PRODUCER])),
    "Result_Simulator_Wholesalers":       ("wholesalers",         list(_PROPS_BY_ROLE[ROLE_WHOLESALER])),
    "Result_Simulator_Processors":        ("processors",          list(_PROPS_BY_ROLE[ROLE_PROCESSOR])),
    "Result_Simulator_FeedManufacturers": ("feed_manufacturers",  list(_PROPS_BY_ROLE[ROLE_FEED_MANUFACTURER])),
    "Result_Simulator_FeedTraders":       ("feed_traders",        list(_PROPS_BY_ROLE[ROLE_FEED_TRADER])),
    "Result_Simulator_EuFarmers":         ("eu_farmers",          list(_PROPS_BY_ROLE[ROLE_CONSUMER])),
}

ENVIRONMENT_TABLE = "Result_Simulator_Environment"
ENVIRONMENT_PROPS = [
    "soja_price", "feed_price", "shock_scale", "drought_severity",
    "total_soja_supply", "transport_utilisation", "current_step",
]

class TickWriter:
    """
    Writes one simulation tick to Postgres per call to write_tick()

    Instantiagte once per simulation run - the constructor truncates
    the tick tables so each run starts clean.
    """

    def __init__(self, engine) -> None:
        self.engine = engine
        self.enabled = True
        self._reset_tables()

    @classmethod
    def from_config(cls, cfg) -> "TickWriter":
        """
        Builds a TickWriter from PostgresDBConfig.
        Returns a disabled no-op writer if Postgres is unreachable.
        """
        try:
            from sqlalchemy import create_engine
            engine = create_engine(cfg.sqlalchemy_url())
            # connection test
            with engine.connect():
                pass
            return cls(engine)
        except ImportError:
            logger.warning("sqlalchemy or psycopg2 not installed")
        except Exception as exc:
            logger.warning("could not connect to Postgres: %s", exc)
        writer = object.__new__(cls)
        writer.engine = None
        writer.enabled = False
        return writer


    def write_tick(self, model, id_scenario: int, id_run: int, t: int) -> None:
        """
        Write the current agent + environment state for step t to Postgres.

        Call this once per tick, after _do_step(t) has run.
        """
        if not self.enabled:
            return
        try:
            self._write_agents(model, id_scenario, id_run, t)
            self._write_environment(model.environment, id_scenario, id_run, t)
        except Exception as exc:
            logger.error("error at step %d: %s - disabling tick writes for remainder of this run.", t, exc)
            self.enabled = False

    def _reset_tables(self) -> None:
        """
        Drop all tick tables at the start of a run so stale data
        from the previous run doesn't pollute queries.
        """
        try:
            from sqlalchemy import text
            tables = list(AGENT_TABLES.keys()) + [ENVIRONMENT_TABLE]
            with self.engine.connect() as conn:
                for table in tables:
                    conn.execute(text(f'DROP TABLE IF EXISTS "{table}"'))
                conn.commit()
        except Exception as exc:
            logger.warning("could not reset tick tables: %s", exc)


    def _write_agents(self, model, id_scenario: int, id_run: int, t: int) -> None:
        """Write one row per active agent for each tracked agent list."""
        for table_name, (list_attr, props) in AGENT_TABLES.items():
            agent_list = getattr(model, list_attr)
            rows = []
            for agent in agent_list.agents:
                row = {
                    "id_scenario": id_scenario,
                    "id_run": id_run,
                    "period": t,
                    "id": agent.id,
                }
                for prop in props:
                    row[prop] = getattr(agent, prop, None)
                rows.append(row)

            if rows:
                df = pd.DataFrame(rows)
                df.to_sql(table_name, self.engine, if_exists="append", index=False)


    def _write_environment(self, env, id_scenario: int, id_run: int, t: int) -> None:
        """Write one environment row for this step."""
        row = {
            "id_scenario": id_scenario,
            "id_run": id_run,
            "period": t,
        }
        for prop in ENVIRONMENT_PROPS:
            row[prop] = getattr(env, prop, None)

        df = pd.DataFrame([row])
        df.to_sql(ENVIRONMENT_TABLE, self.engine, if_exists="append", index=False)