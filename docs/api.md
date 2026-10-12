# Simulation API

The API accepts PDL YAML, queues a simulation, and exposes its lifecycle,
live progress, and logs. Each job executes the existing baseline scenario
and one PDL scenario in an isolated subprocess. A single worker executes
jobs in submission order while the HTTP service remains responsive.

**Job ID and simulation run ID are the same.** Simulation preparation
generates and reserves the ID before submission is acknowledged. Clients
cannot supply it. The ID returned by submission is used for polling,
the simulation run registry, and the CSV output directory.

## Run with Docker Compose

From the repository root:

```bash
docker compose -f compose.api.yml up --build -d
curl http://localhost:8000/health
```

This Compose file contains only the API service. The image runs as a
non-root user and installs Python runtime dependencies from `uv.lock`
with frozen versions and package hash verification. Update the lock
deliberately when upgrading dependencies, then rebuild the image.
Inputs, metadata, logs, and results are stored in the named
`simenv_api_data` volume mounted at `/data`. To use another host port:

```bash
SIMENV_API_PORT=8080 docker compose -f compose.api.yml up --build -d
```

Stop the service with:

```bash
docker compose -f compose.api.yml down
```

The data volume survives `down`. `down --volumes` deletes the volume and
its recorded jobs. On restart, completed and failed jobs remain inspectable,
previously queued jobs resume, and interrupted running jobs are marked
failed with their last progress retained. They are not automatically retried.

## Run the Docker image directly

```bash
docker build -f Dockerfile.api -t provider-simenv-api .
docker volume create simenv_api_data
docker run --rm --name simenv-api -p 8000:8000 \
  -v simenv_api_data:/data provider-simenv-api
```

Docker is the deployment target. For local testing, build the same image
with Podman's Docker format so the image health check is retained:

```bash
podman build --format docker -f Dockerfile.api -t provider-simenv-api:latest .
podman-compose -f compose.api.yml up -d --no-build
```

`podman compose` with a Compose provider can also launch this configuration.

## Run locally without a container

Python 3.10 or newer is required. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[api]'
SIMENV_API_DATA_DIR=./data/api \
  uvicorn provider_simenv.api.app:app --host 127.0.0.1 --port 8000 --workers 1
```

On Windows, activate with `.venv\Scripts\activate` and set the environment
variable using your shell's syntax. The default local data directory is
`./data/api`, relative to the server's working directory.

Use one Uvicorn worker and one service instance per data directory. Each
instance runs at most one simulation at a time; additional jobs are queued.

### Inactivity timeout

`SIMENV_API_JOB_TIMEOUT` sets the maximum seconds **without advancing
simulation progress**, not a maximum total run duration. The default is
300 seconds; overrides must be positive finite numbers. The timer starts
when the worker launches and resets when a valid progress update advances
a simulation step or scenario. Logs, polling, invalid snapshots, and
rewriting unchanged progress do not reset it. Startup and each individual
step must therefore finish within the configured interval.

For example, allow up to ten minutes between updates with Compose:

```bash
SIMENV_API_JOB_TIMEOUT=600 docker compose -f compose.api.yml up --build -d
```

For a direct container run, pass `-e SIMENV_API_JOB_TIMEOUT=600`; locally,
set the environment variable before starting Uvicorn. Invalid values fail
service startup. On timeout the worker is terminated and reaped, the job
is marked `failed` with a "timed out ... without progress" error and its
last progress retained, and the next queued job can run. Termination may
take up to ten additional seconds if the worker needs to be killed.

Interactive API documentation is available at
<http://localhost:8000/docs>, with OpenAPI at `/openapi.json`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/simulations` | Submit PDL and return a queued job (202) |
| GET | `/simulations` | List all jobs, newest first |
| GET | `/simulations/running` | List only actively executing jobs with live progress |
| GET | `/simulations/{id}` | Inspect lifecycle, progress, and errors |
| GET | `/simulations/{id}/logs` | Read a bounded log chunk |
| GET | `/health` | 200 when the queue controller is healthy, otherwise 503 |

Both list endpoints accept `limit` (default 50, range 1–100) and `offset`
(default 0, nonnegative). Responses are `{ "items": [...], "total": N }`.
The running endpoint excludes queued, completed, and failed jobs. With the
single worker it normally returns zero or one item.

### Submit PDL

The JSON request body contains:

| Field | Type | Meaning |
|---|---|---|
| `pdl` | string, required | Full PDL document as YAML text |
| `roster` | string or null | Optional companion roster document as YAML text |
| `cascade` | string or null | Cascade ID; omitted/null selects the first cascade |
| `label` | string or null | Human-readable run label |

The response is a job representation and includes a `Location` header
pointing to `/simulations/{id}`. Invalid YAML, unsupported roster declarations,
invalid topology, or unknown cascade IDs return 422 with an explanation.
Unexpected fields, including client-supplied IDs, are rejected. Unknown job
IDs return 404. Execution failures appear as a `failed` job with an error
and worker logs.

When your PDL needs a roster sidecar, send it explicitly. The API never
implicitly attaches the shipped roster to an uploaded document. For the
shipped scenario, submit both `s1-soja.pdl.yaml` and `s1-soja.roster.yaml`.

### Complete submission and polling example

Run this Python script from the repository root while the API is running;
it uses only the standard library:

```python
import json
import time
import urllib.request
from pathlib import Path

base = "http://localhost:8000"
scenarios = Path("src/provider_simenv/scenarios")
payload = {
    "pdl": (scenarios / "s1-soja.pdl.yaml").read_text(encoding="utf-8"),
    "roster": (scenarios / "s1-soja.roster.yaml").read_text(encoding="utf-8"),
    "cascade": "soy_crisis_cascade",
    "label": "API example",
}
request = urllib.request.Request(
    base + "/simulations",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request) as response:
    job = json.load(response)
run_id = job["id"]
print("Run:", run_id)

while True:
    with urllib.request.urlopen(f"{base}/simulations/{run_id}") as response:
        job = json.load(response)
    print(job["status"], job["progress"])
    if job["status"] in ("completed", "failed"):
        break
    time.sleep(1)

offset = 0
while True:
    url = f"{base}/simulations/{run_id}/logs?offset={offset}&limit=16384"
    with urllib.request.urlopen(url) as response:
        chunk = json.load(response)
    print(chunk["text"], end="")
    if chunk["next_offset"] == offset:
        break
    offset = chunk["next_offset"]
if job["error"]:
    print("Error:", job["error"])
```

List running jobs independently:

```bash
curl http://localhost:8000/simulations/running
curl 'http://localhost:8000/simulations?limit=10&offset=0'
```

### Job status and progress

The job representation includes `id`, `status`, `label`, `cascade`,
`created_at`, `started_at`, `finished_at`, `error`, and `progress`.
Timestamps are UTC; unset timestamps and errors are null.

States are `queued` → `running` → `completed` or `failed`.
Queued jobs start at zero progress. While running, progress reports:

```json
{
  "scenario_id": 1,
  "step": 100,
  "scenario_total_steps": 365,
  "completed_steps": 465,
  "total_steps": 730,
  "percent_complete": 63.6986301369863
}
```

`step` counts completed steps in the current scenario, not a zero-based
step index. `scenario_id` is null before execution, 0 for the baseline,
and 1 for the PDL scenario. Overall progress covers both scenarios and
does not reset when the second starts. The bundled template supplies
engine parameters and duration (365 periods per scenario by default);
submitted PDL supplies topology, events, and cascade timing.

A job becomes completed only after output saving succeeds and its worker
exits successfully. It can still be running at 100 percent while saving.
Failures retain the last known progress and an error explanation.

### Logs

`GET /simulations/{id}/logs?offset=0&limit=16384` returns:

```json
{"text": "worker output...", "offset": 0, "next_offset": 16}
```

Offsets are bytes; use `next_offset` for the next request. `limit` defaults
to 16384 bytes and is capped at 65536. Before any log output or at the end
of a log, `text` is empty and `next_offset` equals `offset`. Chunks decode
as UTF-8 with replacement for split multibyte characters. Both stdout and
stderr are captured.

## Data layout and CSV results

```text
<data-root>/
  jobs.sqlite3
  jobs/<id>/
    context.json
    input/scenario.pdl.yaml
    input/scenario.roster.yaml       # when submitted
    input/SimulatorScenarios_template.csv
    input/SimulatorScenarios.csv
    output/runs.json
    output/<id>/Result_Simulator_*.csv
    progress.json
    simulation.log
```

Each job has independent inputs and outputs, and never changes the bundled
working CSV. The output registry uses the same ID returned by the API.
For local runs, read CSVs directly under the configured data directory.
For Compose, copy one run's output from the container:

```bash
docker compose -f compose.api.yml cp api:/data/jobs/<id>/output ./api-output
python -m provider_simenv.export_bundle --input ./api-output/<id> --scenario 1
```

The API image includes CSV output support; it requires no PostgreSQL
service. The existing CLI/Postgres setup is documented separately in the
repository README.
