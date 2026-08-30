# provider-simenv

Agent-based supply chain simulation for the **PROVIDER** research project (BMBF-funded, OFFIS e.V.).

Models the global soya supply chain from Brazil, Argentina, and US farms through wholesalers,
sea transport, EU processors, and feed manufacturers to EU livestock farms. A PDL YAML
describes entities, stages, and shock events; a roster sidecar next to it declares
archetypes and which PDL entities are not modelled. Added trading entities and
edges are listed in the sidecar but not yet wired into the roster builder. The
model applies those shocks (drought,
port capacity, input prices) and records price and sourcing behaviour across the chain.

Built on [Melodie](https://github.com/ABM4ALL/Melodie) (Python ABM framework).

---

## Project Structure

```
simenv/
├── pyproject.toml
├── web/                          ← globe frontend (see web/README.md)
└── src/
    └── provider_simenv/
        ├── main.py               ← entry point
        ├── model.py              ← simulation orchestrator
        ├── scenario.py           ← engine parameters (counts, costs, sigmas)
        ├── topology.py           ← PDL + roster → agent lists and flow graph
        ├── environment.py        ← global state + price aggregation
        ├── pdl_loader.py         ← PDL YAML → events / entities
        ├── data_collector.py     ← Melodie output registration
        ├── tick_writer.py        ← per-tick PostgreSQL writer
        ├── db_config.py          ← PostgreSQL connection config
        ├── export_bundle.py      ← CSV run → web/public/bundle.json
        ├── scenarios/
        │   ├── s1-soja.pdl.yaml
        │   └── s1-soja.roster.yaml
        ├── agents/
        │   ├── farmer.py         ← producers + EU livestock farms
        │   ├── trader.py         ← wholesalers + feed traders
        │   ├── transport.py      ← land + sea transport operators
        │   └── process.py        ← processors + feed manufacturers
        └── data/
            ├── input/
            │   ├── SimulatorScenarios.csv            ← working copy Melodie reads
            │   └── SimulatorScenarios_template.csv   ← edit this; every run copies it
            └── output/                               ← generated at runtime
                └── Result_Simulator_*.csv
```

---

## Dependencies

**Python:** 3.10 or higher

**Required:**

```
Melodie>=0.6.0
pandas
numpy
pyyaml
```

**Optional — only needed for PostgreSQL output:**

```
sqlalchemy
psycopg2-binary
```

If `sqlalchemy` / `psycopg2-binary` are not installed, the tick writer disables itself
silently and the simulation continues normally. CSV output is unaffected.

### Install

```bash
# Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# Install core dependencies (run in project root)
pip install .

# Optional: Install all packages needed for development (run in project root)
pip install '.[dev]'

# This should ususally be done in editable mode for development purposes:
pip install -e '.[dev]'

# Optional: Install with PostgreSQL support (run in project root)
pip install '.[db]'
```

---

## Running the Simulation

After `pip install -e .`, from the **repository root**:

```bash
# Windows: the scenario summary prints characters that fail on cp1252
# $env:PYTHONIOENCODING="utf-8"

# All rows in SimulatorScenarios.csv (no PDL events)
python -m provider_simenv.main

# Shocks and roster from the shipped soja PDL
python -m provider_simenv.main --pdl src/provider_simenv/scenarios/s1-soja.pdl.yaml
```

Alternatively, from the package directory (what the Docker image does):

```bash
cd src/provider_simenv
python main.py --pdl scenarios/s1-soja.pdl.yaml
```

Every run copies `SimulatorScenarios_template.csv` onto `SimulatorScenarios.csv` first.
With `--pdl`, the live CSV is then rewritten to two rows: baseline (`id=0`) and one PDL
scenario (`id=1`). Shock magnitudes and timing come from PDL events at runtime, not from
CSV columns.

**What runs automatically:**

1. Simulation loop — each CSV row, `period_num` steps (default 365)
2. Per-tick PostgreSQL writes via `tick_writer.py` (if Postgres is reachable; silent skip otherwise)

### Update the globe frontend after a run

```bash
python -m provider_simenv.export_bundle --scenario 1
```

The exporter writes `web/public/bundle.json`. See `web/README.md` for the frontend workflow.

---

## Scenarios

`data/input/SimulatorScenarios.csv` is the working table Melodie reads. Change the
**template**, not the live file — every run overwrites the live copy from the template.

Each row is one run. Columns are engine parameters (agent counts, routing, size sigmas,
storage, length). Producer counts use PDL entity ids (`n_brazil_farms`, `n_argentina_farms`,
`n_us_farms`).

Shocks are not CSV columns. Pass `--pdl`; `EventTracker` applies drought, capacity, and
input-price events from the YAML. The shipped files are `scenarios/s1-soja.pdl.yaml` and
`scenarios/s1-soja.roster.yaml` beside it (archetype declarations and not-modelled
exclusions; trading entities and edges are declared but not yet wired into the roster
builder).

| Parameter | Effect |
|---|---|
| `n_brazil_farms` / `n_argentina_farms` / `n_us_farms` | Producer agent counts |
| `share_santos_port` | Explicit weight for the Santos route; unspecified route weights are resolved per origin |
| `shock_ramp_steps` | Ramp length when a PDL shock is active |
| `size_sigma_brazil_farms` | Log-normal farm-size spread (`0` = identical farms) |
| `wholesaler_storage_capacity` | Max tonnes a wholesaler can hold per step (default 2857 t/day) |
| `period_num` | Number of simulation steps (default 365) |

---

## Run in docker container

The simulation can also be run in a docker container.
First, build the container. In the repo root run

```bash
docker build -t provider-simenv .
```

Then you can run the simulation in the container with

```bash
docker run --rm -v <path to pdl file directory>:/scenarios provider-simenv --pdl /scenarios/<pdl filename>
```

You can also configure a PostgreSQL interface for data storage (see next chapter) with

```bash
docker run --rm -v <path to pdl file directory>:/scenarios provider-simenv --pdl /scenarios/<pdl filename> --postgres-url <PostgreSQL URL string>
```

If the PDL has a roster sidecar, mount the directory that contains both files
(`s1-soja.pdl.yaml` and `s1-soja.roster.yaml`).

---

## PostgreSQL Setup (Optional)

PostgreSQL enables live data access during the simulation — required for future palaestrAI
integration. Without it, everything works via CSV + SQLite.

### Start a local instance with Docker

```bash
docker run --name provider-postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres -e POSTGRES_DB=provider_simenv -p 5432:5432 -d postgres:16
```

These credentials match the defaults in `db_config.py`. No further configuration needed.

To persist data across container restarts, add a volume:

```bash
docker run --name provider-postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres -e POSTGRES_DB=provider_simenv -p 5432:5432 -v pgdata:/var/lib/postgresql/data -d postgres:16
```

### Connection defaults (`db_config.py`)

| Field | Default |
|---|---|
| host | `localhost` |
| port | `5432` |
| dbname | `provider_simenv` |
| user | `postgres` |
| password | `postgres` |

Override by constructing `PostgresDBConfig` with different values or passing env vars at runtime.

### Verify data after a run

```sql
-- PDL run: 2 scenarios, each COUNT = period_num (default 365)
SELECT id_scenario, COUNT(*)
FROM "Result_Simulator_Environment"
GROUP BY id_scenario
ORDER BY id_scenario;
```

### Tables written by tick_writer

Table names derive from the PDL entity id (`brazil_farms` ->
`Result_Simulator_BrazilFarms`), identical to the Melodie CSV names, so a PDL
declaring different entities produces the matching tables with no code change.
One table per roster list whose role has recorded properties, plus the
environment table. For the shipped PDL:

```
Result_Simulator_Environment
Result_Simulator_BrazilFarms
Result_Simulator_ArgentinaFarms
Result_Simulator_UsFarms
Result_Simulator_BrazilWholesaler
Result_Simulator_ArgentinaWholesaler
Result_Simulator_UsWholesaler
Result_Simulator_Processors
Result_Simulator_FeedManufacturers
Result_Simulator_FeedTraders
Result_Simulator_EuFarmers
```

Tables are dropped and recreated on the first tick of each full simulation run (first scenario only).
Subsequent scenarios within the same run append to the existing tables.

---

## docker-compose

You can also run a docker compose that sets up a PostgreSQL database and links it to the simulation container.
Using our helper script, everything is configured automatically.
Just run

```bash
./compose-up.sh <path to pdl file>
```
from the repository root. This builds the database container, if it's not already up and runs a simulation of the specified pdl file. You can run different configurations by simply repeating this call with the respective paths.

---

## Output Files

| File | Description |
|---|---|
| `data/output/Result_Simulator_*.csv` | Raw per-agent per-step output written by Melodie |
| `web/public/bundle.json` | Exported run for the globe (`python -m provider_simenv.export_bundle`) |

---

## Known Issues / Notes

- **`python main.py` needs the package directory** (`src/provider_simenv/`). After `pip install -e .`, `python -m provider_simenv.main` from the repo root works — `Config` resolves `data/` from `main.py`'s location, not the cwd.
- **`run_stepwise()`** in `model.py` is the designated integration hook for external control (e.g. palaestrAI). It yields a state dict `{step, shock_scale, soja_price, feed_price, ...}` after every simulation step.

---

## Project

PROVIDER — AI-based supply chain resilience simulation
OFFIS e.V. – Institut für Informatik, Oldenburg
BMBF-funded
