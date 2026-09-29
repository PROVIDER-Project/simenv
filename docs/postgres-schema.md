# PROVIDER simenv — PostgreSQL schema

**Status:** contract, agreed 2026-09-22, normalized 2026-09-29. Implemented by #43.
**Audience:** anyone joining this database to another schema, including the customer-side
Schnittstelle, plus the simenv maintainers.
**Companion:** `docs/pdl-derived-architecture.md` explains why the shape is PDL-independent.

---

## 1 · What this database holds

One PROVIDER simulation invocation produces one **run**. A run executes every scenario row in
`SimulatorScenarios.csv` — today a baseline (`id_scenario = 0`) and a PDL-shocked variant
(`id_scenario = 1`) — over a fixed number of daily periods, and records the state of every
agent and of the environment after each period.

A run is identified by its **run id**: `20260922T115943Z-f3c11976`, a UTC timestamp and eight
hex characters. The same string names the run's CSV directory under `data/output/`, keys its
entry in `runs.json`, and keys every row this database holds. There is exactly one identity;
nothing here mints a second one.

Storage is four tables. Reading is meant to go through views, which store nothing:

| Object | Kind | One row means |
|---|---|---|
| `sim_run` | table | One simulation invocation. |
| `sim_agent` | table | One recorded agent within one run. |
| `sim_metric` | table | One kind of measurement, shared by all runs. |
| `sim_tick` | table | One measured value: one agent, one scenario, one metric, one period. |
| `sim_tick_readable` | view | `sim_tick` with the keys resolved to names. |
| `sim_<role>_view` | view | One agent at the end of one period, metrics as columns. |

The database is append-only in practice. No run deletes or overwrites another run's rows, and
nothing in the code drops a table. Retention is not solved and not attempted.

---

## 2 · `sim_run` — one row per simulation invocation

One row means: this run started at this time, against this PDL, over these scenarios, and
ended in this state.

```sql
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
);
```

| Column | Type | Meaning |
|---|---|---|
| `run_id` | `text` | The run identity. Sorts chronologically as plain text. |
| `started_at` | `timestamptz` | UTC, written before the simulation starts. |
| `finished_at` | `timestamptz` | UTC, written when the run ends. `NULL` while running, and on a run that died without recording an end. |
| `status` | `text` | `running`, `completed` or `failed`. A row stuck at `running` is a crashed run. |
| `pdl` | `text` | PDL filename, basename only. `NULL` for a run without `--pdl`. |
| `pdl_sha256` | `text` | SHA-256 of the PDL file as read. The exact provenance of the input. |
| `scenario_ids` | `integer[]` | The scenario ids this run executed, e.g. `{0,1}`. |
| `period_num` | `integer` | Periods per scenario. All scenarios in one run share it. |
| `git_sha` | `text` | What `HEAD` pointed at. Not proof the working tree matched it. |
| `label` | `text` | Free text from `--label`. `NULL` when not given. |

Every column mirrors a field of the same name in `runs.json`. That is deliberate: the JSON
index and this table are two views of one record, and a difference between them is a bug.

---

## 3 · `sim_agent` — one row per recorded agent per run

One row means: **in this run, this entity had an agent with this index, playing this role.**

```sql
CREATE TABLE IF NOT EXISTS sim_agent (
    agent_key integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id    text    NOT NULL REFERENCES sim_run (run_id),
    entity_id text    NOT NULL,
    role      text    NOT NULL,
    agent_id  integer NOT NULL,
    UNIQUE (run_id, entity_id, agent_id)
);
```

| Column | Type | Meaning |
|---|---|---|
| `agent_key` | `integer` | Surrogate key, assigned by the database. Only `sim_tick` refers to it. |
| `run_id` | `text` | The run this agent belongs to. References `sim_run`. |
| `entity_id` | `text` | PDL entity id, e.g. `brazil_farms`. `environment` for the environment row. |
| `role` | `text` | `producer`, `consumer`, `wholesaler`, `processor`, `feed_manufacturer`, `feed_trader`, or `environment`. |
| `agent_id` | `integer` | Index of the agent within its own entity list, zero-based. **Unique only within `entity_id`**, never globally. `0` for the environment. |

**What identifies an agent is `(run_id, entity_id, agent_id)`.** `agent_key` is a shorthand for
that triple so each `sim_tick` row does not repeat it. Its values are specific to one database
and mean nothing outside it.

**An agent spans all scenarios of its run.** Scenario 0 and scenario 1 run the same roster, so
one `sim_agent` row carries the values of both; `id_scenario` lives on `sim_tick`.

**Roles are defined in code, not by the PDL.** A PDL chooses which of the fixed roles an entity
takes; an unknown role is rejected when the roster is built. The set above is therefore closed,
and so is the set of role views in section 7.

**The environment is an agent.** Each run has one row with `entity_id = 'environment'`,
`role = 'environment'`, `agent_id = 0`. Its values live in `sim_tick` like everyone else's.

**`environment` is a reserved `entity_id`.** A PDL declaring an entity by that name would
collide with the environment's own row. The unique constraint surfaces that as an error rather
than merging them silently, but no PDL should use the name.

**Sea-transport and port agents are not recorded.** They carry no tracked metrics, get no
`sim_agent` row and emit no values, on this path and on the CSV path alike.

---

## 4 · `sim_metric` — one row per kind of measurement

One row means: **this is a quantity the simulation records, in this unit.**

```sql
CREATE TABLE IF NOT EXISTS sim_metric (
    metric_id   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text    NOT NULL UNIQUE,
    unit        text    NOT NULL,
    description text    NOT NULL
);
```

| Column | Type | Meaning |
|---|---|---|
| `metric_id` | `integer` | Surrogate key, assigned by the database. Only `sim_tick` refers to it. |
| `name` | `text` | The metric's name, e.g. `unit_price`. The stable identifier. |
| `unit` | `text` | The unit the value is expressed in. See section 6. |
| `description` | `text` | What the value means, in one sentence. |

The table is shared by all runs. Its content comes from a catalogue in the simenv code, which is
upserted by name at the start of every run. A description corrected in code is corrected here on
the next run.

**A unit is never updated in place.** Every earlier run's values were recorded in the stored
unit, and changing it would silently relabel all of them. If the unit in code differs from the
unit stored for the same name, the run fails at start, naming the metric: a changed unit needs a
new metric name. Likewise a name is never renamed in place; a renamed metric is a new row.

A metric not in the catalogue cannot be written: `sim_tick.metric_id` references this table,
and the code checks that the catalogue matches the set of properties it records.

---

## 5 · `sim_tick` — one row per measured value

One row means: **for this agent, in this scenario, this metric had this value at the end of
this period.** The run is reached through the agent.

```sql
CREATE TABLE IF NOT EXISTS sim_tick (
    agent_key   integer          NOT NULL REFERENCES sim_agent (agent_key),
    id_scenario integer          NOT NULL,
    metric_id   integer          NOT NULL REFERENCES sim_metric (metric_id),
    period      integer          NOT NULL,
    value       double precision NOT NULL,
    PRIMARY KEY (agent_key, id_scenario, metric_id, period)
);
```

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `agent_key` | `integer` | — | The agent. References `sim_agent`, which carries the run. |
| `id_scenario` | `integer` | — | Scenario row within the run. `0` is the unshocked baseline. |
| `metric_id` | `integer` | — | What was measured. References `sim_metric`. |
| `period` | `integer` | day | Simulation period, zero-based, one day per period. |
| `value` | `double precision` | per metric | The measurement. |

The table holds numbers and keys only. Names, units and the run id are one join away and are
not repeated on every row.

**A new PDL adds rows, never tables, columns or views.** Entities the PDL introduces appear as
new `sim_agent` rows and their values as new `sim_tick` rows. Nothing about any table or view
changes.

**Absence is not a null.** A metric a role does not carry produces **no row**, not a row with
`value IS NULL`. `value` is `NOT NULL` to make that unrepresentable rather than merely
conventional. A consumer must therefore treat a missing `(agent, metric)` pair as "this agent
has no such metric", not as a gap in the data.

**The row count is proportional to the PDL.** The `s1-soja` scenario over 2 scenarios × 365
periods produces 97,090 `sim_tick` rows (values): 45 recorded agents carrying 2 or 3 metrics
each, plus 7 environment metrics, against 46 `sim_agent` rows (the 45 agents and the
environment) and 13 `sim_metric` rows.

---

## 6 · Metric catalogue

This is the content of `sim_metric`. The unit column records what the code actually computes.
Where the codebase does not declare a unit, this says so rather than inventing one — the
`s1-soja` scenario is parameterised in tonnes and an unnamed currency, but nothing in the model
enforces either. The `unit` values below are the stored strings, character for character;
section 4 explains why they never change in place.

### Agent metrics

| `name` | Roles | `unit` | Meaning |
|---|---|---|---|
| `quantity_available` | producer, wholesaler, processor, feed_manufacturer, feed_trader | output units per period | How much of its output good the agent has ready this period. |
| `unit_price` | producer, wholesaler, processor, feed_manufacturer, feed_trader | currency per output unit | The agent's asking price this period. `0.0` when it has nothing to sell. |
| `storage_utilization` | wholesaler | ratio, 0.0-1.0 | Stock divided by storage capacity. |
| `feed_received` | consumer | feed units per period | Feed collected from upstream traders, split evenly across active consumers. |
| `livestock_output` | consumer | output units per period | Livestock produced, proportional to `feed_received`. |
| `active` | producer, consumer | flag, 1.0 or 0.0 | Whether the agent is still in the market. See the boolean note in section 8. |

"Output units" are the units of whatever good the agent sells, so `quantity_available` for a
producer is raw soy and for a feed trader is compound feed. The metric is the same; the good
follows the role.

### Environment metrics

All belong to the `environment` agent.

| `name` | `unit` | Meaning |
|---|---|---|
| `soy_price` | currency per unit | Weighted average price across active wholesalers. |
| `feed_price` | currency per unit | Weighted average price across active feed traders. |
| `shock_scale` | multiplier | Largest active shock multiplier this period. `0.0` when nothing is shocked. |
| `drought_severity` | ratio, 0.0-1.0 | Largest active drought severity this period. |
| `total_soy_supply` | output units | Sum of `quantity_available` across the PDL's producer regions. |
| `transport_utilisation` | ratio, 0.0-1.0 | Average utilisation across transport agents. |
| `current_step` | day | The period index. Redundant with `period`; see section 8. |

---

## 7 · Views — how to read the data

The views are how this database is meant to be read, by the export, by the parity test, and by
an external consumer. They are defined with `CREATE OR REPLACE VIEW` at the start of every run,
generated from the fixed role and metric lists in the code. They hold no data of their own.

### `sim_tick_readable` — the long form, with names

One row per `sim_tick` row, keys resolved:

```sql
CREATE OR REPLACE VIEW sim_tick_readable AS
SELECT a.run_id, t.id_scenario, t.period,
       a.entity_id, a.role, a.agent_id,
       m.name AS metric, m.unit, t.value
FROM sim_tick t
JOIN sim_agent  a ON a.agent_key = t.agent_key
JOIN sim_metric m ON m.metric_id = t.metric_id;
```

| Column | Type | From |
|---|---|---|
| `run_id` | `text` | `sim_agent` |
| `id_scenario` | `integer` | `sim_tick` |
| `period` | `integer` | `sim_tick` |
| `entity_id` | `text` | `sim_agent` |
| `role` | `text` | `sim_agent` |
| `agent_id` | `integer` | `sim_agent` |
| `metric` | `text` | `sim_metric.name` |
| `unit` | `text` | `sim_metric` |
| `value` | `double precision` | `sim_tick` |

The absence rule carries over: no row means no such metric.

### `sim_<role>_view` — one row per agent per period

One view per role, each with one column per metric that role carries:

| View | Metric columns |
|---|---|
| `sim_producer_view` | `quantity_available`, `unit_price`, `active` |
| `sim_consumer_view` | `feed_received`, `livestock_output`, `active` |
| `sim_wholesaler_view` | `quantity_available`, `unit_price`, `storage_utilization` |
| `sim_processor_view` | `quantity_available`, `unit_price` |
| `sim_feed_manufacturer_view` | `quantity_available`, `unit_price` |
| `sim_feed_trader_view` | `quantity_available`, `unit_price` |
| `sim_environment_view` | `soy_price`, `feed_price`, `shock_scale`, `drought_severity`, `total_soy_supply`, `transport_utilisation`, `current_step` |

Every agent role view starts with `run_id`, `id_scenario`, `period`, `entity_id`, `agent_id`,
then the metric columns in the order above. `sim_environment_view` starts with `run_id`,
`id_scenario`, `period` only: there is one environment per run, so `entity_id` and `agent_id`
would carry nothing. Metric columns are `double precision`, except `active`, which is cast back
to `boolean`. As an example, the producer view:

```sql
CREATE OR REPLACE VIEW sim_producer_view AS
SELECT a.run_id, t.id_scenario, t.period, a.entity_id, a.agent_id,
       max(t.value) FILTER (WHERE m.name = 'quantity_available') AS quantity_available,
       max(t.value) FILTER (WHERE m.name = 'unit_price')         AS unit_price,
       max(t.value) FILTER (WHERE m.name = 'active') <> 0        AS active
FROM sim_tick t
JOIN sim_agent  a ON a.agent_key = t.agent_key
JOIN sim_metric m ON m.metric_id = t.metric_id
WHERE a.role = 'producer'
GROUP BY a.run_id, t.id_scenario, t.period, a.entity_id, a.agent_id;
```

`max()` never combines two values: the `sim_tick` primary key allows at most one row per agent,
scenario, metric and period, so each group holds at most one value per column.

In these views, and only here, a missing value shows as `NULL`, because a pivoted row has a
column for every metric of the role. A role view never has a column for a metric its role does
not carry.

### Changing a view

`CREATE OR REPLACE VIEW` can only append columns at the end. The column order of each role view
is the order of that role's tuple in `_PROPS_BY_ROLE`, and of the environment's metric list.
Adding a metric to the end of one of those lists therefore needs nothing by hand. Removing,
renaming or reordering a metric in one of them makes `CREATE OR REPLACE VIEW` fail, and needs a hand-written
migration. Nothing in this codebase ever uses `DROP VIEW ... CASCADE`: other views, including
the customer's own, may later depend on ours, and a cascade would drop them silently.

---

## 8 · What an external consumer can rely on

**Stable.** Breaking any of these is a versioned change, announced:

- The names of `sim_run`, `sim_tick_readable` and the seven `sim_<role>_view` views, their
  column names, types and meanings.
- The run id format and the fact that one run id spans every scenario in that invocation.
- `(run_id, id_scenario, entity_id, agent_id, metric, period)` identifying at most one row of
  `sim_tick_readable`.
- The absence rule: a missing row means the metric does not exist for that agent.
- The environment appearing as an agent under the `environment` sentinels.
- A metric's `name` and `unit`. A changed unit is a new metric name.

**Ours, may change without notice.**

- The storage tables `sim_agent`, `sim_metric` and `sim_tick`: their keys, column order and
  indexes. Read the views, not the tables.
- `agent_key` and `metric_id` values. They differ between databases and carry no meaning.
- The set of `entity_id` values — it follows the PDL, and a new PDL legitimately changes it.
  Consumers must discover entities, not hardcode them.
- A metric's `description` text.
- New metric columns appended to the end of a role view, and new rows in `sim_metric`. Existing
  columns are not removed or reordered without a versioned change.

**Three encoding notes a mapping will hit.**

- `active` is a boolean in the simulation. The role views return it as `boolean`;
  `sim_tick_readable` returns it as `1.0` or `0.0`, because `sim_tick` has one numeric `value`
  column. A consumer of the long form must compare against zero.
- `current_step` duplicates `period`. It exists because the CSV path records it as an
  environment property and dropping it would break row-for-row parity. Read `period`.
- `value` is `double precision`, matching what the simulation computes and what the CSVs hold,
  bit for bit. It is not exact decimal. A consumer needing fixed-point money must round at its
  own boundary and own that decision.

---

## 9 · Ordering, indexing and integrity

The `sim_tick` primary key is ordered `(agent_key, id_scenario, metric_id, period)` with
`period` last, so one agent's one metric over time is contiguous in the index. That is the
dominant read — the export asks for a series per entity per metric. A run's agents are found
through the `sim_agent` unique index on `(run_id, entity_id, agent_id)`, and their values through
the `sim_tick` primary key by `agent_key`. No secondary index is defined.

A query filtering primarily by period across all agents is not served well by this order. No
such query exists today; if one appears, it wants its own index rather than a reordered key.

Integrity is carried by foreign keys: `sim_tick` references `sim_agent` and `sim_metric`,
`sim_agent` references `sim_run`. The run row is written before the first tick, agents are
registered the first time they are written, and the catalogue is upserted at the start of the
run. A value can never belong to an agent, a metric or a run this database has no record of.

---

## 10 · What is not in this database

The per-entity `Result_Simulator_*` tables are no longer written to Postgres. They still exist
as CSV files under `data/output/<run-id>/`, which the parity test compares against, and their
names still come from the simenv code. Their shape depends on the input PDL, which is exactly
why they could not carry an external contract.
