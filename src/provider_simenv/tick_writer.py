"""
Per-tick PostgreSQL writer

Writes agent and environment state to the database after every simulation step.
    - palaestrAI can query live data mid-run

Run lifecycle:
    1. TickWriter.from_config() -> one writer per run, built from the
       connection config.
    2. open_run() -> create the tables if they are missing and commit this
       run's sim_run row, then create the views and register the metric
       catalogue in a second transaction.
    3. write_tick() once per step -> register agents not seen before in
       sim_agent, then insert one sim_tick row per measured value for all
       agents and the environment in one statement, and commit.
    4. close_run() -> patch the sim_run row to its final status and release
       the connection.

The run row and every agent row carry the run id minted in main.py, the same
string that names the run's output directory and keys runs.json. The writer
never mints an identity of its own, and nothing it does removes rows an
earlier run wrote.

One connection is held from open_run() to close_run(), and the insert
statements are built once per writer, so a step costs one round trip for its
values and one commit rather than a connection and a table lookup per list.

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

from .data_collector import _PROPS_BY_ROLE, ENVIRONMENT_PROPS
from .db_schema import (
    DDL,
    ENVIRONMENT_AGENT_ID,
    ENVIRONMENT_ENTITY_ID,
    ENVIRONMENT_ROLE,
    METRICS,
    SIM_AGENT_TABLE,
    SIM_TICK_TABLE,
    VIEW_DDL,
)

logger = logging.getLogger(__name__)


def _masked_url(cfg) -> str:
    """The connection URL with the password replaced, for error messages."""
    from sqlalchemy.engine import make_url
    return make_url(cfg.sqlalchemy_url()).render_as_string(hide_password=True)


class TickWriter:
    """
    Writes one simulation tick to Postgres per call to write_tick()

    Instantiate once per simulation run - every agent it registers carries
    the run id the caller passes to write_tick().
    """

    def __init__(self, engine) -> None:
        from sqlalchemy import column, insert, table
        self.engine = engine
        self._conn = None
        self._metric_ids: dict[str, int] = {}
        self._agent_keys: dict[tuple[str, str, int], int] = {}
        sim_agent = table(
            SIM_AGENT_TABLE,
            column("agent_key"), column("run_id"), column("entity_id"),
            column("role"), column("agent_id"),
        )
        sim_tick = table(
            SIM_TICK_TABLE,
            column("agent_key"), column("id_scenario"), column("metric_id"),
            column("period"), column("value"),
        )
        self._agent_insert = insert(sim_agent).returning(
            sim_agent.c.agent_key,
        )
        self._tick_insert = insert(sim_tick)

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
        Create the tables if they are missing and insert this run's sim_run
        row, then create the views and register the metric catalogue.

        Call once per invocation, before the first write_tick(). The record is
        run_registry.run_record(), the same one written to runs.json, so the
        two stores describe the run identically. The run row is committed on
        its own, so a run that fails while registering the catalogue still
        exists in sim_run for close_run() to mark failed.
        """
        from sqlalchemy import text
        self._conn = self.engine.connect()
        conn = self._conn
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

        for statement in VIEW_DDL:
            conn.execute(text(statement))
        self._metric_ids = self._register_metrics(conn)
        conn.commit()


    def _register_metrics(self, conn) -> dict[str, int]:
        """
        Upsert the metric catalogue and return metric_id by name. Only the
        description is updated in place: a stored unit that differs from the
        catalogue raises, because changing it would relabel every earlier
        run's values.
        """
        from sqlalchemy import text
        statement = text(
            "INSERT INTO sim_metric (name, unit, description)"
            " VALUES (:name, :unit, :description)"
            " ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description"
            " RETURNING metric_id, unit"
        )
        metric_ids = {}
        for metric in METRICS:
            metric_id, unit = conn.execute(
                statement,
                {
                    "name": metric.name,
                    "unit": metric.unit,
                    "description": metric.description,
                },
            ).one()
            if unit != metric.unit:
                raise RuntimeError(
                    f"metric {metric.name!r} is stored with unit {unit!r}, "
                    f"the code says {metric.unit!r} - a changed unit needs a "
                    "new metric name"
                )
            metric_ids[metric.name] = metric_id
        return metric_ids


    def close_run(self, run_id: str, *, status: str) -> None:
        """
        Patch this run's sim_run row to its final status and release the
        connection.

        Call once per invocation, after the last write_tick() or after a
        failure. A transaction the failure left open is rolled back first.
        """
        from sqlalchemy import text
        conn = self._conn if self._conn is not None else self.engine.connect()
        try:
            conn.rollback()
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
        finally:
            conn.close()
            self._conn = None
            self.engine.dispose()


    def write_tick(self, model, id_scenario: int, run_id: str, t: int) -> None:
        """
        Write the current agent + environment state for step t to Postgres.

        Call this once per tick, after _do_step(t) has run. A failure raises:
        the run fails rather than finishing with rows missing.
        """
        conn = self._conn
        if conn is None:
            raise RuntimeError(
                f"tick write at step {t} before open_run() - the caller must "
                "open the run first"
            )
        try:
            rows = self._agent_rows(conn, model, id_scenario, run_id, t)
            rows += self._environment_rows(
                conn, model.environment, id_scenario, run_id, t,
            )
            if rows:
                conn.execute(self._tick_insert, rows)
            conn.commit()
        except Exception as exc:
            raise RuntimeError(f"tick write failed at step {t}: {exc}") from exc


    def _agent_rows(
        self, conn, model, id_scenario: int, run_id: str, t: int,
    ) -> list[dict]:
        """
        sim_tick rows for every agent in every roster list with tracked props.
        Entities come from the PDL roster, so a PDL declaring other entities
        adds agents and rows without a code change.
        """
        rows = []
        for entry in model._roster:
            props = _PROPS_BY_ROLE.get(entry.archetype.role)
            if props is None:
                continue

            node_id = entry.archetype.name
            agent_list = getattr(model, node_id, None)
            if agent_list is None:
                logger.warning("[SKIPPED] roster entry %r has no model list", node_id)
                continue

            for agent in agent_list.agents:
                agent_key = self._agent_key(
                    conn, run_id, node_id, entry.archetype.role, agent.id,
                )
                rows.extend(
                    self._value_rows(agent, props, agent_key, id_scenario, t)
                )
        return rows


    def _environment_rows(
        self, conn, env, id_scenario: int, run_id: str, t: int,
    ) -> list[dict]:
        """sim_tick rows for the environment, recorded as one agent."""
        agent_key = self._agent_key(
            conn, run_id, ENVIRONMENT_ENTITY_ID, ENVIRONMENT_ROLE,
            ENVIRONMENT_AGENT_ID,
        )
        return self._value_rows(
            env, ENVIRONMENT_PROPS, agent_key, id_scenario, t,
        )


    def _value_rows(
        self,
        source,
        props: tuple[str, ...],
        agent_key: int,
        id_scenario: int,
        t: int,
    ) -> list[dict]:
        """
        One sim_tick row per prop the source carries. A metric the source
        does not carry produces no row, so no NULL value reaches the table.
        """
        rows = []
        for prop in props:
            value = getattr(source, prop, None)
            if value is None:
                continue
            rows.append({
                "agent_key": agent_key,
                "id_scenario": id_scenario,
                "metric_id": self._metric_ids[prop],
                "period": t,
                "value": float(value),
            })
        return rows


    def _agent_key(
        self, conn, run_id: str, entity_id: str, role: str, agent_id: int,
    ) -> int:
        """
        The agent's sim_agent key, registering it the first time it is seen
        in this run. The lookup includes the role and the insert has no
        ON CONFLICT, so two entities sharing an entity_id reach the unique
        constraint and fail the run instead of sharing a key.
        """
        key = (entity_id, role, agent_id)
        agent_key = self._agent_keys.get(key)
        if agent_key is None:
            agent_key = conn.execute(
                self._agent_insert,
                {
                    "run_id": run_id,
                    "entity_id": entity_id,
                    "role": role,
                    "agent_id": agent_id,
                },
            ).scalar_one()
            self._agent_keys[key] = agent_key
        return agent_key
