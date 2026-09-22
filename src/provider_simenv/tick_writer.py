"""
Per-tick PostgreSQL writer

Writes agent and environment state to the database after every simulation step.
    - palaestrAI can query live data mid-run

Run lifecycle:
    1. TickWriter.from_config() -> one writer per run, built from the
       connection config.
    2. open_run() -> create the tables if they are missing and insert this
       run's sim_run row.
    3. write_tick() once per step -> append one row per agent plus one
       environment row to the wide tables, and one row per measured value
       to sim_tick.
    4. close_run() -> patch the sim_run row to its final status.

Every row carries the run id minted in main.py, the same string that names the
run's output directory and keys runs.json. The writer never mints an identity
of its own, and nothing it does removes rows an earlier run wrote.

Failure handling:
    A writer that cannot reach Postgres raises rather than disabling itself,
    and a failed write raises rather than skipping the rest of the run: a run
    that cannot record its results must not report success. Running without a
    database is an explicit choice - under --no-postgres main.py builds no
    writer at all, and the model's write call finds nothing and skips.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone

import pandas as pd

from .data_collector import _PROPS_BY_ROLE, result_table_name
from .db_schema import (
    DDL,
    ENVIRONMENT_ENTITY_ID,
    ENVIRONMENT_ROLE,
    ENVIRONMENT_TABLE,
    SIM_TICK_TABLE,
)

logger = logging.getLogger(__name__)


def _masked_url(cfg) -> str:
    """The connection URL with the password replaced, for error messages."""
    from sqlalchemy.engine import make_url
    return make_url(cfg.sqlalchemy_url()).render_as_string(hide_password=True)


ENVIRONMENT_PROPS = [
    "soy_price", "feed_price", "shock_scale", "drought_severity",
    "total_soy_supply", "transport_utilisation", "current_step",
]

class TickWriter:
    """
    Writes one simulation tick to Postgres per call to write_tick()

    Instantiate once per simulation run - every row carries the run id the
    caller passes to write_tick().
    """

    def __init__(self, engine) -> None:
        self.engine = engine

    @classmethod
    def from_config(cls, cfg) -> "TickWriter":
        """
        Builds a TickWriter from PostgresDBConfig.
        Raises if Postgres is unreachable: a run that cannot write its
        results must not report success.
        """
        try:
            from sqlalchemy import create_engine
        except ImportError as exc:
            raise RuntimeError(
                "sqlalchemy or psycopg2 is not installed - install them, or "
                "run with --no-postgres"
            ) from exc
        engine = create_engine(cfg.sqlalchemy_url())
        try:
            with engine.connect():
                pass
        except Exception as exc:
            raise RuntimeError(
                f"could not connect to Postgres at {_masked_url(cfg)}: {exc} - "
                "start the database, or run with --no-postgres"
            ) from exc
        return cls(engine)


    def open_run(self, record: dict) -> None:
        """
        Create the tables if they are missing and insert this run's sim_run row.

        Call once per invocation, before the first write_tick(). The record is
        run_registry.run_record(), the same one written to runs.json, so the
        two stores describe the run identically.
        """
        from sqlalchemy import text
        with self.engine.connect() as conn:
            for statement in DDL:
                conn.execute(text(statement))
            conn.execute(
                text(
                    "INSERT INTO sim_run (run_id, started_at, finished_at, status,"
                    " pdl, pdl_sha256, scenario_ids, period_num, git_sha, label)"
                    " VALUES (:run_id, :started_at, :finished_at, :status,"
                    " :pdl, :pdl_sha256, :scenario_ids, :period_num, :git_sha, :label)"
                ),
                record,
            )
            conn.commit()


    def close_run(self, run_id: str, *, status: str) -> None:
        """
        Patch this run's sim_run row to its final status.

        Call once per invocation, after the last write_tick().
        """
        from sqlalchemy import text
        with self.engine.connect() as conn:
            conn.execute(
                text(
                    "UPDATE sim_run SET status = :status, finished_at = :finished_at"
                    " WHERE run_id = :run_id"
                ),
                {
                    "status": status,
                    "finished_at": datetime.now(timezone.utc),
                    "run_id": run_id,
                },
            )
            conn.commit()


    def write_tick(self, model, id_scenario: int, run_id: str, t: int) -> None:
        """
        Write the current agent + environment state for step t to Postgres.

        Call this once per tick, after _do_step(t) has run. A failure raises:
        the run fails rather than finishing with rows missing.
        """
        try:
            self._write_agents(model, id_scenario, run_id, t)
            self._write_environment(model.environment, id_scenario, run_id, t)
        except Exception as exc:
            raise RuntimeError(f"tick write failed at step {t}: {exc}") from exc


    def _write_agents(self, model, id_scenario: int, run_id: str, t: int) -> None:
        """
        Write one row per active agent for every roster list with tracked props.
        The table name derives from the PDL entity ID, so a PDL declaring other
        entities writes the matching tables without a code change.
        """
        long_rows = []
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
                    "run_id": run_id,
                    "period": t,
                    "id": agent.id,
                }
                for prop in props:
                    value = getattr(agent, prop, None)
                    row[prop] = value
                    if value is not None:
                        long_rows.append({
                            "run_id": run_id,
                            "id_scenario": id_scenario,
                            "entity_id": node_id,
                            "role": entry.archetype.role,
                            "agent_id": agent.id,
                            "metric": prop,
                            "period": t,
                            "value": float(value),
                        })
                rows.append(row)

            if rows:
                df = pd.DataFrame(rows)
                df.to_sql(
                    result_table_name(node_id),
                    self.engine,
                    if_exists="append",
                    index=False,
                )

        self._write_long(long_rows)


    def _write_environment(self, env, id_scenario: int, run_id: str, t: int) -> None:
        """Write one environment row for this step."""
        row = {
            "id_scenario": id_scenario,
            "run_id": run_id,
            "period": t,
        }
        long_rows = []
        for prop in ENVIRONMENT_PROPS:
            value = getattr(env, prop, None)
            row[prop] = value
            if value is not None:
                long_rows.append({
                    "run_id": run_id,
                    "id_scenario": id_scenario,
                    "entity_id": ENVIRONMENT_ENTITY_ID,
                    "role": ENVIRONMENT_ROLE,
                    "agent_id": 0,
                    "metric": prop,
                    "period": t,
                    "value": float(value),
                })

        df = pd.DataFrame([row])
        df.to_sql(ENVIRONMENT_TABLE, self.engine, if_exists="append", index=False)
        self._write_long(long_rows)


    def _write_long(self, rows: list[dict]) -> None:
        """
        Append rows to sim_tick. A metric an agent does not carry is absent
        from rows entirely, so no NULL value reaches the table.
        """
        if not rows:
            return
        pd.DataFrame(rows).to_sql(
            SIM_TICK_TABLE,
            self.engine,
            if_exists="append",
            index=False,
        )
