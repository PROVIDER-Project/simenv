"""
PostgreSQL table definitions

The shape of the tables tick_writer.py writes and export_bundle.py reads.
Written out as explicit DDL rather than left to pandas type inference, so the
column types are what this file says instead of what the first batch of rows
happened to imply.

sim_run holds one row per simulation invocation; sim_tick holds one row per
measured value, so a PDL declaring other entities adds rows rather than tables
or columns. The wide Result_Simulator_* tables are still created by pandas on
first write and are deliberately not defined here - they are convenience for
ad-hoc queries, not the interface.

Every statement here is CREATE TABLE IF NOT EXISTS and nothing in this codebase
drops a table. docs/postgres-schema.md documents the columns, their units, and
which of them an external consumer may rely on.
"""

# no table map here: every tracked list comes from the PDL roster,
# and its table name derives from the entity id via result_table_name(),
# so the Postgres tables carry the same names as the Melodie CSVs.
ENVIRONMENT_TABLE = "Result_Simulator_Environment"

# Environment rows live in sim_tick alongside the agents, under these sentinels.
ENVIRONMENT_ENTITY_ID = "environment"
ENVIRONMENT_ROLE = "environment"

SIM_RUN_TABLE = "sim_run"
SIM_TICK_TABLE = "sim_tick"

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
    CREATE TABLE IF NOT EXISTS sim_tick (
        run_id      text             NOT NULL REFERENCES sim_run (run_id),
        id_scenario integer          NOT NULL,
        entity_id   text             NOT NULL,
        role        text             NOT NULL,
        agent_id    integer          NOT NULL,
        metric      text             NOT NULL,
        period      integer          NOT NULL,
        value       double precision NOT NULL,
        PRIMARY KEY (run_id, id_scenario, entity_id, agent_id, metric, period)
    )
    """,
)
