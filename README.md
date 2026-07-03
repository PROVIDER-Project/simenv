# provider-simenv

Agent-based supply chain simulation for the **PROVIDER** research project (BMBF-funded, OFFIS e.V.).

Models the global soya supply chain from Brazilian/US farms through wholesalers, sea transport,
EU processors, and feed manufacturers to EU livestock farms. Scenarios apply KG-derived shock
parameters (drought, port capacity, input price shocks) and observe emergent price and sourcing
behaviour across the chain.

Built on [Melodie](https://github.com/ABM4ALL/Melodie) (Python ABM framework).

---

## Project Structure

```
simenv/
├── pyproject.toml
└── src/
    └── provider_simenv/
        ├── main.py               ← entry point
        ├── model.py              ← simulation orchestrator
        ├── scenario.py           ← all scenario parameters
        ├── environment.py        ← global state + price aggregation
        ├── data_collector.py     ← Melodie output registration
        ├── tick_writer.py        ← per-tick PostgreSQL writer
        ├── db_config.py          ← PostgreSQL connection config
        ├── visualize_sql.py      ← plots from SQLite (post-run)
        ├── visualize_csv.py      ← plots from CSV (fallback)
        ├── agents/
        │   ├── farmer.py         ← BRA / USA / EU farmers
        │   ├── trader.py         ← wholesalers + feed traders
        │   ├── transport.py      ← land + sea transport operators
        │   └── process.py        ← processors + feed manufacturers
        └── data/
            ├── input/
            │   └── SimulatorScenarios.csv   ← scenario definitions
            └── output/                      ← generated at runtime
                ├── Result_Simulator_*.csv
                ├── provider-simenv.sqlite
                ├── price_curves.png
                └── volume_flow.png
```

---

## Dependencies

**Python:** 3.10 or higher

**Required:**

```
Melodie>=0.6.0
pandas
numpy
matplotlib
pyyaml
```

**Optional — only needed for PostgreSQL output:**

```
sqlalchemy
psycopg2-binary
```

If `sqlalchemy` / `psycopg2-binary` are not installed, the tick writer disables itself
silently and the simulation continues normally. CSV and SQLite outputs are unaffected.

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

```bash
# Navigate to the simulation package — Melodie resolves data/ paths from here
cd src/provider_simenv

# Run
python main.py
```

The simulation reads scenarios from `data/input/SimulatorScenarios.csv`, runs all scenarios
in sequence, and writes output to `data/output/`.

**What runs automatically:**

1. Simulation loop — all scenarios, 52 steps each, per-tick stdout
2. Per-tick PostgreSQL writes via `tick_writer.py` (if Postgres is reachable; silent skip otherwise)
3. Post-run: CSV → SQLite merge → `provider-simenv.sqlite`

### Generate Plots (after a run)

```bash
# From src/provider_simenv/

# Recommended: plots from SQLite — price curves + BRA/USA volume flow
python visualize_sql.py

# Fallback: plots from CSV
python visualize_csv.py
```

Output PNGs are saved to `data/output/`.

---

## Scenarios

Scenarios are defined in `data/input/SimulatorScenarios.csv`. Each row is one scenario run.

| Parameter | Effect |
|---|---|
| `farm_capacity_bra` | BRA farm output multiplier — `1.0` = normal, `0.7` = 30% drought loss |
| `port_capacity_sa` | SA export port throughput multiplier |
| `fertilizer_price_factor` | Multiplier on BRA farmer fixed costs (GTA Red interventions) |
| `energy_price_factor` | Multiplier on all transport fixed costs |
| `oil_mill_capacity` | EU processor output multiplier |
| `feed_mill_capacity` | Feed manufacturer output multiplier |
| `shock_onset_step` | Step at which shock starts ramping in |
| `shock_ramp_steps` | Steps to ramp from baseline to full shock value |
| `wholesaler_storage_capacity` | Max tonnes a wholesaler can hold per step (default: 20 000 t) |
| `period_num` | Number of simulation steps (default: 52) |

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
-- Should return 3 rows, each COUNT = 52 (for a 3-scenario, 52-step run)
SELECT id_scenario, COUNT(*)
FROM "Result_Simulator_Environment"
GROUP BY id_scenario
ORDER BY id_scenario;
```

### Tables written by tick_writer

```
Result_Simulator_Environment
Result_Simulator_BraFarmers
Result_Simulator_UsaFarmers
Result_Simulator_Wholesalers
Result_Simulator_Processors
Result_Simulator_FeedManufacturers
Result_Simulator_FeedTraders
Result_Simulator_EuFarmers
```

Tables are dropped and recreated at the start of each full simulation run (first scenario only).
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
| `data/output/provider-simenv.sqlite` | All CSVs merged into one SQLite database (post-run) |
| `data/output/price_curves.png` | Soja + feed price development across all scenarios |
| `data/output/volume_flow.png` | BRA vs USA sourcing volumes per scenario |

---

## Known Issues / Notes

- **Run from `src/provider_simenv/`** — Melodie resolves `data/` paths relative to the working directory. Running from the repo root will fail to find input files.
- **Melodie SQLite mode is disabled** — `data_output_type="sqlite"` silently drops all rows due to a missing `conn.commit()` in SQLAlchemy 2.0. The `csv_to_sqlite()` function in `main.py` is used instead and called automatically.
- **`run_stepwise()`** in `model.py` is the designated integration hook for external control (e.g. palaestrAI). It yields a state dict `{step, shock_scale, soja_price, feed_price, ...}` after every simulation step.

---

## Project

PROVIDER — AI-based supply chain resilience simulation  
OFFIS e.V. – Institut für Informatik, Oldenburg  
BMBF-funded
