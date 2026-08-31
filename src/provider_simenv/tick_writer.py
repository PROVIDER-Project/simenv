"""
Per-tick PostgreSQL writer

Writes agent and environment state to the database after every simulation step.
    - palaestrAI can query live data mid-run

Run lifecycle:
    1. TickWriter.__init__ -> drops and recreates all tables
    2. write_tick() once per step -> append one tick's row per call
    3. End of run        -> tables are complete, identical to batch import

Failure handling:
    If Postgres is unreachable or sqlalchemy/psycopg2 is missing,
    TickWriter silently disables itself. The simulation continues normally.
    CSV and SQLite outputs are unaffected.
"""

from __future__ import annotations
import logging

import pandas as pd

from .data_collector import _PROPS_BY_ROLE, result_table_name

logger = logging.getLogger(__name__)

# no table map here: every tracked list comes from the PDL roster,
# and its table name derives from the entity id via result_table_name(),
# so the Postgres tables carry the same names as the Melodie CSVs.
ENVIRONMENT_TABLE = "Result_Simulator_Environment"
ENVIRONMENT_PROPS = [
    "soja_price", "feed_price", "shock_scale", "drought_severity",
    "total_soja_supply", "transport_utilisation", "current_step",
]

class TickWriter:
    """
    Writes one simulation tick to Postgres per call to write_tick()

    Instantiate once per simulation run - the first write_tick() drops the
    roster's tick tables so each run starts clean.
    """

    def __init__(self, engine, reset: bool = True) -> None:
        self.engine = engine
        self.enabled = True
        self._pending_reset = reset

    @classmethod
    def from_config(cls, cfg, *, reset: bool = True) -> "TickWriter":
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
            return cls(engine, reset=reset)
        except ImportError:
            logger.warning("sqlalchemy or psycopg2 not installed")
        except Exception as exc:
            logger.warning("could not connect to Postgres: %s", exc)
        writer = object.__new__(cls)
        writer.engine = None
        writer.enabled = False
        writer._pending_reset = False
        return writer


    def write_tick(self, model, id_scenario: int, id_run: int, t: int) -> None:
        """
        Write the current agent + environment state for step t to Postgres.

        Call this once per tick, after _do_step(t) has run.
        """
        if not self.enabled:
            return
        try:
            if self._pending_reset:
                self._reset_tables(model)
                self._pending_reset = False
            self._write_agents(model, id_scenario, id_run, t)
            self._write_environment(model.environment, id_scenario, id_run, t)
        except Exception as exc:
            logger.error("error at step %d: %s - disabling tick writes for remainder of this run.", t, exc)
            self.enabled = False

    def _reset_tables(self, model) -> None:
        """
        Drop the tick tables this run writes.
        Derived from the PDL roster, so stale data from the previous run doesn't pollute queries.
        """
        try:
            from sqlalchemy import text
            tables = [
                result_table_name(entry.archetype.name)
                for entry in model._roster
                if _PROPS_BY_ROLE.get(entry.archetype.role) is not None
            ] + [ENVIRONMENT_TABLE]
            with self.engine.connect() as conn:
                for table in tables:
                    conn.execute(text(f'DROP TABLE IF EXISTS "{table}"'))
                conn.commit()
        except Exception as exc:
            logger.warning("could not reset tick tables: %s", exc)


    def _write_agents(self, model, id_scenario: int, id_run: int, t: int) -> None:
        """
        Write one row per active agent for every roster list with tracked props.
        The table name derives from the PDL entity ID, so a PDL declaring other
        entities writes the matching tables without a code change.
        """
        for entry in model._roster:
            props = _PROPS_BY_ROLE.get(entry.archetype.role)
            if props is None:
                continue

            node_id = entry.archetype.name
            agent_list = getattr(model, node_id, None)
            if agent_list is None:
                logger.warning("[SKIPPED] roster entry %r has no model list", node_id)
                continue

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
                df.to_sql(
                    result_table_name(node_id),
                    self.engine,
                    if_exists="append",
                    index=False,
                )


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
