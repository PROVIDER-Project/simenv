# Database playback

![Recorded playback with the expanded left panel at step 150 (static demo)](playback-preview.png)

[View or download the full-size screenshot](playback-preview.png).

## Start the complete stack

```bash
docker compose -f compose.playback.yml up --build -d
```

Open **http://localhost:8080**. An empty database is supported: use the scenario
configurator's **Run simulation** button to record the first run. On completion
the catalogue refreshes. Select a run/scenario, then play, pause, or seek. The
newest playable run is selected initially. Refresh and More runs browse records.

Run and scenario selection are stacked in the **Recorded playback** panel on
the left, leaving the central globe clear. The panel starts expanded. Use
**Hide** to minimize it to its header and **Show** to reopen it; the selected
run, scenario, and current playback are retained. On smaller screens the panel
is part of the scrollable page.

Interface examples (using the bundled static demo):
[collapsed panel](playback-selector-collapsed.png) and
[mobile layout](playback-selector-mobile.png).

| Service | Default address | Purpose |
| --- | --- | --- |
| Frontend | http://localhost:8080 | Globe, run selection, scenario submission |
| Simulation API | http://localhost:8000/docs | Submission, status, progress, logs; also usable by external services |
| Playback API | http://localhost:8001/docs | Read-only discovery, scene metadata, frame ranges |
| PostgreSQL | Compose network only | Shared persistent database |

PostgreSQL and simulation job files have separate named volumes. `docker compose
-f compose.playback.yml down` keeps both volumes.

## Configuration

Compose variables: `SIMENV_BROWSER_HOST` (default `localhost`), `SIMENV_WEB_PORT`
(`8080`), `SIMENV_API_PORT` (`8000`), `SIMENV_PLAYBACK_PORT` (`8001`), and
`SIMENV_API_JOB_TIMEOUT` (`300`). Use the configured browser hostname exactly:
`localhost` and `127.0.0.1` are distinct CORS origins. For remote browsers use the
server's browser-reachable hostname, not a Compose service name. API URLs are
build-time frontend settings; rebuild after changing hostnames or ports.

Outside Compose, set both services' `PROVIDER_SIMENV_POSTGRES_URL` to the same
database. Start the simulation API first with that variable set: it initializes
the additive schema before any submission. Then start playback:

```bash
python -m uvicorn provider_simenv.playback.app:app --port 8001
```

Set `SIMENV_PLAYBACK_ALLOWED_ORIGINS` and `SIMENV_API_ALLOWED_ORIGINS` to
comma-separated frontend origins, e.g. `http://localhost:5173`. Configure Vite
with `VITE_PLAYBACK_API_BASE_URL=http://localhost:8001` and
`VITE_SIMENV_API_BASE_URL=http://localhost:8000` for independent direct API access.
Omitting the playback URL explicitly selects **Static demo (exported values)**;
API failures never switch database playback to demo data.

## API and fidelity

```text
GET /runs?limit=50&offset=0
GET /runs/{run_id}/scenarios/{scenario_id}/scene
GET /runs/{run_id}/scenarios/{scenario_id}/frames?start=200&limit=100
GET /health
```

Runs are ordered newest first. Catalogue limits are 1–100; frame limits are
1–500, default 100. Ranges are start-inclusive, end-exclusive and clipped to the
run. Beyond-end requests return empty terminal pages; `next_start` is null at
the end. The browser caches three 100-period pages and prefetches the next page
while playing. It holds its last frame when buffering.

Frames contain `period` and `agents`. Each agent contains `entity_id`, `agent_id`,
`role`, and numeric `values` keyed by metric name. Environment is entity
`environment`, agent 0. Values come from `sim_tick_readable`: no summing,
averaging, rounding, downsampling, or interpolation. Flags remain numeric 0/1.
JSON numbers retain the database's double precision and agents stay distinct.

Globe colours are display-only relative changes from period zero: rising prices
or falling output/quantity increase intensity, clipped to 0–1. Zero/missing
references yield zero intensity. A multi-agent node shows its strongest
individual visual intensity. These values never mutate or replace measurements.
Colours no longer require full-run minimum/maximum values.

Only completed runs with available scenes are playable. New runs store versioned
topology snapshots in PostgreSQL and remain playable if inputs change or
disappear. Legacy runs can use shipped scenarios only when PDL and roster hashes
match; otherwise their unavailability is explained in the selector.

Errors: unknown run/scenario 404; unavailable/incomplete run 409; invalid range
422; database outage 503; corrupt/incomplete committed measurements 500. No
missing values are invented and database credentials are not returned.

## Verification

Install `.[dev]` and run against an isolated database:

```bash
SIMENV_TEST_POSTGRES_URL=postgresql+psycopg2://postgres:postgres@localhost/test_db \
  python -m pytest tests
```

Fixtures create private schemas and remove only those schemas. The integration
test submits a real 105-period run, deletes its private inputs, fetches both
scenarios across pages, and compares every identity/value to PostgreSQL.

From `web/`, run `npm run test:playback`. For browser tests, start Vite with
`VITE_PLAYBACK_API_BASE_URL=http://127.0.0.1:8001` and run
`npm run test:playback-browser`; only these tests intercept API responses.
`npm run test:simulation` uses real APIs: set `SIMENV_WEB_URL` to the running
stack. It submits both cascades, verifies catalogue refresh, selects each
completed run, and seeks into a later database page.

### Frontend-versus-API performance

Build a production frontend with playback URL `http://127.0.0.1:8001`, serve
with `npm run preview`, then run
`SIMENV_WEB_URL=http://127.0.0.1:4173 npm run test:playback-performance`.
The Playwright test records browser/hardware configuration, warm-up and three
trials, p50/p95 durations, input-to-paint latency and main-thread long tasks.
Transport/body transfer, decoding, validation, cache insertion, frame calculation
and commit-to-next-paint are measured separately. Commit-to-paint is a scheduling
proxy, not a GPU timer; development builds additionally report React CPU time.

Fixtures contain 45 agents and 1,000 agents × 13 metrics × 300 periods, preserving
identities/precision in 100-period responses. The 16.7 ms calculation budget and
100 ms interaction target are investigation thresholds, not CI timing assertions.

Initial production results: Chromium 153, Intel Xeon w7-3455, 48 logical CPUs,
no CPU throttling, headless software rendering:

| p95 (ms) | 45 agents | 1,000 agents |
| --- | ---: | ---: |
| Frame calculation | 0.6 | 8.0 |
| JSON decoding (also includes small metadata responses) | 15.8 | 228.2 |
| Validation | 4.9 | 149.7 |
| Commit to next paint | 24.5 | 14.8 |
| Input to paint | 173.8 | 97.1 |

**Placement decision:** keep visual arithmetic in the browser: measured cost
is below the frame budget. Large-payload parsing/validation and software globe
rendering are the bottlenecks. Moving arithmetic to the API would not eliminate
them and would increase response size if raw measurements remain. Larger
deployments should investigate worker decoding or smaller windows first. The
representative interaction target was exceeded on this headless renderer; this
is reported rather than labelled a performance pass. Repeat on target hardware.

A real stack run's 100-period query used existing run-agent/tick indexes and
returned 4,000 metric rows in 14.9 ms (`EXPLAIN (ANALYZE, BUFFERS)`). No new index
was justified.

The performance test also supports `SIMENV_REAL_WEB_URL` pointing to a stack
with a completed run. This trial uses its persisted topology and real API
responses (no intercepted data). A recorded 16-node, 16-edge run measured p95
projection 0.6 ms, decoding 0.9 ms, validation 6.8 ms, commit-to-paint 70.2 ms,
and input-to-paint 186.3 ms in the same headless environment. This confirms
rendering/scheduling, rather than frame arithmetic, dominates that run; the
interaction target is not met there either. Reproduce both synthetic and real
trials with:

```bash
SIMENV_WEB_URL=http://127.0.0.1:4173 \
SIMENV_REAL_WEB_URL=http://localhost:8080 npm run test:playback-performance
```
