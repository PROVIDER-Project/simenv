# PROVIDER simenv — PostgreSQL schema

**Status:** contract, agreed 2026-09-22. Implemented by #43.
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

## 3 · `sim_tick` — one row per measured value

One row means: **in this run, for this scenario, this agent had this value for this metric at
the end of this period.**

```sql
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
);
```

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `run_id` | `text` | — | The run this value belongs to. References `sim_run`. |
| `id_scenario` | `integer` | — | Scenario row within the run. `0` is the unshocked baseline. |
| `entity_id` | `text` | — | PDL entity id, e.g. `brazil_farms`. `environment` for environment rows. |
| `role` | `text` | — | The entity's role: `producer`, `consumer`, `wholesaler`, `processor`, `feed_manufacturer`, `feed_trader`, or `environment`. Denormalised from the PDL for convenience. |
| `agent_id` | `integer` | — | Index of the agent within its own entity list, zero-based. **Unique only within `entity_id`**, never globally. `0` for environment rows. |
| `metric` | `text` | — | What was measured. Catalogue in section 4. |
| `period` | `integer` | day | Simulation period, zero-based, one day per period. |
| `value` | `double precision` | per metric | The measurement. |

**A new PDL adds rows, never tables and never columns.** That is the whole point of this shape.
Entities the PDL introduces appear as new `entity_id` values; metrics a role carries appear as
new `metric` values. Nothing about the table changes.

**Absence is not a null.** A metric a role does not carry produces **no row**, not a row with
`value IS NULL`. `value` is `NOT NULL` to make that unrepresentable rather than merely
conventional. A consumer must therefore treat a missing `(entity_id, agent_id, metric)` pair as
"this agent has no such metric", not as a gap in the data.

**The environment is an agent.** Environment rows live in this table with
`entity_id = 'environment'`, `role = 'environment'`, `agent_id = 0`. There is one table to
join, not two.

**`environment` is a reserved `entity_id`.** A PDL declaring an entity by that name would
collide with the environment's own rows. The primary key surfaces that as an error rather
than merging them silently, but no PDL should use the name.

**Sea-transport and port agents are not recorded.** They carry no tracked metrics and emit no
rows, on this path and on the CSV path alike.

**The row count is proportional to the PDL.** The `s1-soja` scenario over 2 scenarios × 365
periods produces roughly 97,000 rows: 46 recorded agents carrying 2 or 3 metrics each, plus 7
environment properties. The same run produces 33,580 rows across the wide tables.

---

## 4 · Metric catalogue

The unit column records what the code actually computes. Where the codebase does not declare a
unit, this says so rather than inventing one — the `s1-soja` scenario is parameterised in
tonnes and an unnamed currency, but nothing in the model enforces either.

### Agent metrics

| `metric` | Roles | Unit | Meaning |
|---|---|---|---|
| `quantity_available` | producer, wholesaler, processor, feed_manufacturer, feed_trader | output units per period | How much of its output good the agent has ready this period. |
| `unit_price` | producer, wholesaler, processor, feed_manufacturer, feed_trader | currency per output unit | The agent's asking price this period. `0.0` when it has nothing to sell. |
| `storage_utilization` | wholesaler | ratio, 0.0–1.0 | Stock divided by storage capacity. |
| `feed_received` | consumer | feed units per period | Feed collected from upstream traders, split evenly across active consumers. |
| `livestock_output` | consumer | output units per period | Livestock produced, proportional to `feed_received`. |
| `active` | producer, consumer | `1.0` or `0.0` | Whether the agent is still in the market. See the boolean note in section 6. |

### Environment metrics

All carry `entity_id = 'environment'`, `role = 'environment'`, `agent_id = 0`.

| `metric` | Unit | Meaning |
|---|---|---|
| `soy_price` | currency per unit | Weighted average price across active wholesalers. |
| `feed_price` | currency per unit | Weighted average price across active feed traders. |
| `shock_scale` | multiplier | Largest active shock multiplier this period. `0.0` when nothing is shocked. |
| `drought_severity` | ratio, 0.0–1.0 | Largest active drought severity this period. |
| `total_soy_supply` | output units | Sum of `quantity_available` across the PDL's producer regions. |
| `transport_utilisation` | ratio, 0.0–1.0 | Average utilisation across transport agents. |
| `current_step` | day | The period index. Redundant with the `period` column; see section 6. |

This catalogue is descriptive, not enforced. There is no `sim_metric` table constraining the
`metric` column, and a PDL that introduces a role with new properties will produce metric names
not listed here. Adding a registry is a candidate follow-up, not part of #43.

---

## 5 · The wide `Result_Simulator_*` tables

These predate `sim_tick` and are kept. They are cheap to write and convenient for ad-hoc
queries, and the parity test compares them against the CSVs. **They are not the interface.**

- One table per recorded PDL entity, named `Result_Simulator_BrazilFarms` and so on — mixed
  case, so every query against them needs double quotes.
- Columns are `run_id`, `id_scenario`, `period`, `id`, then one column per property the role
  carries. A property a role lacks appears as a `NULL` column.
- **Their shape depends on the input PDL.** A different PDL produces a different table list and
  a different column set. This is precisely why they cannot carry an external contract.
- `run_id` here is `text` and holds the same run id as everywhere else. It replaces the former
  `id_run bigint`, which was always `0`.

An external consumer should read `sim_tick`. These tables may change shape without notice.

---

## 6 · What an external consumer can rely on

**Stable.** Breaking any of these is a versioned change, announced:

- The `sim_run` and `sim_tick` table names and their column names, types and meanings.
- The run id format and the fact that one run id spans every scenario in that invocation.
- The absence rule: a missing row means the metric does not exist for that agent.
- `(run_id, id_scenario, entity_id, agent_id, metric, period)` identifying at most one row.
- Environment rows appearing in `sim_tick` under the `environment` sentinels.

**Ours, may change without notice.**

- Every `Result_Simulator_*` table: names, columns, existence.
- The set of `entity_id` values and the set of `metric` values — both follow the PDL, and a new
  PDL legitimately changes both. Consumers must discover them, not hardcode them.
- `role` as a denormalisation. It is derived from the PDL and convenient, not authoritative;
  the PDL is.
- Index definitions beyond the primary key.

**Three encoding notes a mapping will hit.**

- `active` is a boolean in the simulation and is stored as `1.0` or `0.0`, because `sim_tick`
  has one `value` column and it is numeric. A consumer reading `active` must compare against
  zero, not expect a boolean type.
- `current_step` duplicates the `period` column. It exists because the CSV path records it as
  an environment property and dropping it would break row-for-row parity. Read `period`.
- `value` is `double precision`, matching what the simulation computes and what the CSVs hold,
  bit for bit. It is not exact decimal. A consumer needing fixed-point money must round at its
  own boundary and own that decision.

---

## 7 · Ordering, indexing and integrity

The primary key is ordered `(run_id, id_scenario, entity_id, agent_id, metric, period)` with
`period` last, so the rows of one agent's one metric over time are physically adjacent. That is
the dominant read — the export bundle asks for a series per entity per metric — and it is
served by the primary key index alone, with no secondary index.

A query filtering primarily by period across all entities is not served well by this order. No
such query exists today; if one appears, it wants its own index rather than a reordered key.

`sim_tick.run_id` references `sim_run(run_id)`, so the run row is written at the start of the
run, before any tick. A tick can never belong to a run this database has no record of.
