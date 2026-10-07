# Simulation execution and tracking API

## Intent and scope

Implement GitHub issue #49: a lightweight HTTP service that accepts a PDL
document, executes the existing simulation, and exposes monitoring. Ship a
container image, a single-service Compose configuration, and documentation.

The user selected live progress monitoring: lifecycle status, timestamps,
errors, logs, current scenario, simulation step, and percentage complete.
The user approved isolated subprocess execution with a persistent queue and
requested a dedicated endpoint listing only currently running simulations.

## Architecture

Use FastAPI and Uvicorn as an optional `api` dependency extra. Run one API
process and one queue-controller thread. The controller executes one isolated
simulation subprocess at a time. Requests remain responsive while simulation
work executes. SQLite, from the Python standard library, persists job metadata
and queue ordering; no separate database or broker is required.

Store all API state below a configurable `SIMENV_API_DATA_DIR` (default
`./data/api` for local execution; `/data` in the container):

```
jobs.sqlite3
jobs/<job-id>/
  input/scenario.pdl.yaml
  input/scenario.roster.yaml       # only when submitted
  input/SimulatorScenarios*.csv    # private simulation inputs
  output/runs.json
  output/<run-id>/Result_Simulator_*.csv
  progress.json
  simulation.log
```

The job ID and simulation run ID are the same identifier. A shared simulation
run-preparation function generates it using the existing run-registry
generator and exclusively reserves the job and output directories. If a
directory already exists, generate a fresh ID and retry; never reuse output.
The API calls this simulation-owned preparation function when accepting a
submission and returns the reserved ID immediately, even while queued. The
worker executes the prepared run using its stored identity rather than
generating another ID. HTTP callers cannot supply an ID.
Uploaded content and generated files survive service restart.
The container runs a single Uvicorn worker; multiple API processes sharing
the same data directory are not supported in this first version.

## HTTP contract

### Submit a simulation

`POST /simulations` accepts JSON:

```json
{
  "pdl": "scenario:\n  name: Example\n...",
  "roster": null,
  "cascade": null,
  "label": "Example run"
}
```

`pdl` is required nonempty YAML text. `roster` is optional YAML text for the
existing additive roster sidecar. `cascade` selects a cascade; omitting it
uses the first cascade, as the CLI does. `label` is optional run metadata.
Reject unexpected request fields to surface caller mistakes.

Validate YAML document shapes and exercise the existing event-registry,
roster, and flow-adjacency builders before accepting a job. Invalid input
returns HTTP 422 with a useful explanation. Use safe YAML loading. Never
infer or load the shipped roster for a submitted PDL; callers provide the
sidecar explicitly when they need its declarations.

Successful submission returns HTTP 202, a `Location` header pointing to
`/simulations/<job-id>`, and the job representation. Submission persists the
input and queued job before acknowledging it.

### Job representation

All lifecycle and list endpoints share this representation:

- `id`: simulation-generated ID shared by the job and run, available
  immediately on submission. Use this ID for polling and locating results.
- `status`: `queued`, `running`, `completed`, or `failed`.
- `label`, `cascade`: submitted metadata.
- `created_at`, `started_at`, `finished_at`: UTC timestamps; unset timestamps
  are null.
- `error`: failure explanation or null.
- `progress`: current `scenario_id` (null before execution), `step` (completed
  steps in the current scenario), `scenario_total_steps`,
  `completed_steps` (across scenarios), `total_steps`, and `percent_complete`.

The simulation retains current CLI semantics: execute the baseline scenario
and one PDL scenario. Percentage is computed across both, not reset for the
second scenario. Progress is monotonic; queued jobs start at zero. Completed
jobs report 100 percent; failed jobs retain the last known progress. Completing
all steps does not change lifecycle status until output saving succeeds.

### List and inspect

- `GET /simulations`: paginated list of all jobs, newest first.
- **`GET /simulations/running`**: paginated list containing only `running`
  jobs, with the same live-progress representation. Queued and terminal jobs
  are excluded. Register this static route before the job-ID route.
- `GET /simulations/{id}`: inspect one job; unknown IDs return HTTP 404.

Lists accept `limit` (default 50, range 1–100) and `offset` (default 0,
nonnegative). Return `{ "items": [...], "total": N }`, where `total` counts
matching jobs before pagination. With the initial single worker, the running
list contains at most one job.

### Logs and health

- `GET /simulations/{id}/logs`: return UTF-8 text as JSON with `text`,
  `offset`, and `next_offset`. Pagination uses byte offsets; `limit` defaults
  to 16 KiB and is capped at 64 KiB. Decode chunks with replacement for split
  multibyte characters. Unknown jobs return HTTP 404; jobs without log output
  return an empty chunk. Capture both worker stdout and stderr.
- `GET /health`: HTTP 200 while the service and queue controller are healthy;
  HTTP 503 if the controller unexpectedly stops.
- FastAPI exposes the generated OpenAPI schema and interactive `/docs`.

Results persist on the volume and can be read with existing CSV tooling.
Result-download, cancellation, authentication, and live model-state endpoints
are outside this issue's agreed API contract.

## Simulation integration

Refactor the CLI entry point into callable argument parsing, run preparation,
and execution while preserving its existing defaults. The API and CLI use
the simulation-owned preparation function to generate and reserve run IDs.
Add an internal worker entry point that loads a persisted prepared-run
context containing the reserved ID, private input and output directories,
and progress-file path. Do not introduce a client-supplied run-ID field or
a public CLI run-ID override. Copy the bundled scenario template to the
job's private input directory; keep package resources and the default roster resolvable
from their existing locations.

Use a small optional model progress callback after each completed `_do_step`
in the normal `run()` loop. The worker writes progress using atomic file
replacement. The API reads the latest snapshot while the job is running;
the controller saves the last snapshot to metadata before making a job
terminal. No progress callback is installed for ordinary CLI runs.

The API launches the worker with an argument list and no shell. Worker class
state and mutable input CSVs are private to that job's subprocess. Existing
run-registry files are also private per job, avoiding shared-manifest races.

## Lifecycle, persistence, and errors

The queue controller claims the oldest queued job transactionally and marks
it running. It redirects subprocess output into the job log, monitors exit,
and records `completed` only on successful worker exit. Startup errors and
nonzero exits record `failed` with an actionable error and a linkable log
endpoint. Request validation failures do not enter the queue.

On startup, mark previously running jobs failed with an interruption reason;
retain progress and output. Resume previously queued jobs in submission
order. On graceful shutdown, stop dequeuing, terminate and reap the active
worker, and mark it failed. Keep queued jobs for the next startup. The worker
is never automatically retried, so partial output is not silently overwritten.

Use short-lived SQLite connections and transactions, parameterized queries,
and atomic progress-file updates. Avoid holding a database transaction while
running or waiting for a subprocess. Restrict filesystem lookup to stored job
IDs and fixed filenames; HTTP callers do not supply server filesystem paths.

## Container and documentation

Add `Dockerfile.api`, installing the package with its `api` extra and copying
the bundled simulation data. Start Uvicorn on `0.0.0.0:8000` with one worker.
Run as a non-root user with write access to `/data`. Use a Python-standard-
library HTTP health check. Add a Docker ignore file to exclude Git metadata,
local environments, generated data, and frontend dependency/build directories
from build context while retaining bundled input files.

Add `compose.api.yml` containing only the API service, port 8000, a named
data volume, and a shutdown grace period suitable for worker cleanup.
The existing CLI container and Postgres Compose workflow continue to have
their own configuration.

Document installation, local startup, image build/run, Compose startup,
volume persistence, all endpoints, status/progress semantics, and a complete
submission-and-polling example using the shipped PDL and optional sidecar.
Explain that submitted PDL events and topology drive the simulation while
the bundled template supplies engine parameters and simulation duration.

## Verification

Use temporary data directories and an injectable subprocess execution
boundary for lifecycle tests. Verify:

1. Input validation, optional sidecar handling, and cascade selection.
2. Accepted submissions, persisted inputs, list pagination, and unknown IDs.
3. The running-only endpoint excludes queued, completed, and failed jobs.
4. Progress advances across baseline and PDL scenarios without regression.
5. Worker failure records errors and exposes logs; byte-offset log pagination
   is bounded.
6. Jobs are isolated and execute in queue order. The accepted job ID matches
   the simulation registry and output-directory run ID; directory collisions
   cause regeneration rather than reuse.
7. Restart preserves history, fails interrupted jobs, and resumes queued jobs.
8. Shutdown terminates and reaps an active subprocess.
9. A real short simulation completes with progress and independent CSV output.
10. Existing simulation and run-registry tests remain passing.

Run relevant lint/type checks. Validate Compose configuration and build/run
the Docker-targeted API image locally with Podman, as requested by the user;
report any environment limitations explicitly in the pull request.

## Delivery

Develop on `49-simulation-api`, commit verified changes, push the branch to
the GitHub origin, and create a pull request targeting `main` with
`Closes #49`, a change summary, and verification evidence. GitHub CLI is
authenticated as `Sponn`, with push and pull-request access verified.
