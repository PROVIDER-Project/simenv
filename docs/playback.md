# Database playback

![Recorded playback with the expanded left panel at step 150 (static demo)](playback-preview.png)

[View or download the full-size screenshot](playback-preview.png).

## Start the complete stack

```bash
docker compose -f compose.playback.yml up --build -d
```

The Python-service builds install `provider-agents` from the latest public
**main** branch, separately from hash-verified third-party requirements. No
GitHub token or build secret is needed. Compose disables caching for those
builds so each rebuild fetches current agent main. For direct image builds,
use `docker build --no-cache -f Dockerfile.api ...` or
`docker build --no-cache -f Dockerfile.playback ...`.

Open **http://localhost:8080**. An empty database is supported: use the scenario
configurator's **Run simulation** button to record the first run. On completion
the catalogue refreshes. Use **View results** to select that exact run's scenario
1, or select a run/scenario manually, then play, pause, or seek. The
newest playable run is selected initially. Refresh and More runs browse records.

Run and scenario selection are stacked in **Recorded playback**, with
**Disturbance impact directly below it** in one narrow left sidebar. Both panels
start expanded and have independent **Hide**/**Show** buttons; run, scenario,
reference, inspected component and current playback are retained. Desktop panels
share a single bounded scroll area, so collapsing run selection moves impact up
naturally without adding an overlay across the globe. On smaller screens the
sidebar becomes full-width page flow with no nested scrolling. Globe connections
remain visible in all status states, including gray for unknown upstream status.
The desktop grid reserves the timeline's actual height below the sidebar so it
cannot cover the scrubber. Very short windows (540px high or less) also use page
flow to keep all controls reachable.

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

Globe colours are display-only assessments using the fixed workshop rules below.
They never mutate or replace measurements, and do not depend on page-cache contents
or full-run minimum/maximum values.

Only completed runs with available scenes are playable. New runs store versioned
topology snapshots in PostgreSQL and remain playable if inputs change or
disappear. Legacy runs can use shipped scenarios only when PDL and roster hashes
match; otherwise their unavailability is explained in the selector.

Errors: unknown run/scenario 404; unavailable/incomplete run 409; invalid range
422; database outage 503; corrupt/incomplete committed measurements 500. No
missing values are invented and database credentials are not returned.

## Workshop status and references

**Disturbance impact** combines a compact legend, reference selection and component
inspection. Select a marker or use the keyboard-accessible **Inspect component**
list, including nodes without geographic placement. Details show step, status,
responsible metric/agent, current/reference values, changes and missing evidence.
Pooled geographic markers share their roster node's assessment. Multi-agent nodes
retain the strongest individual metric status, not an average; ties follow stable
agent identity and metric-registry order.

Clicking an icon or its component label opens **Disturbance impact** and updates
the dropdown in place. Clicking an already selected component also reopens
collapsed details, without automatically scrolling or moving focus. Node labels
are native buttons supporting pointer input and Enter/Space; connection labels
remain informational. Decorative connection layers remain visible but do
not intercept marker clicks. Map and dropdown selection use the same owning node
ID, including pooled components, and preserve playback, reference and run selection.

Selection retains both the sidebar's desktop scroll position and the responsive
page position. Scroll anchoring is disabled in these containers, and the inspector
retains its tallest visible content height at the current width so shorter details
cannot clamp a bottom-scrolled position. Hidden/collapsed measurements do not erase
that reservation. It resets on an actual width change or new run/scenario.

A shared English presentation scene supplies node/placement/connection labels,
dropdown options, headings and pooled member names. Exact built-in German names
are normalized using represented entity IDs, including historical roster aliases.
Custom English names are retained. Original recordings, metric values, coordinates
and reference compatibility checks are unaffected.

### Fixed illustrative workshop policy

| Indicator | Adverse evidence | Green | Amber | Red |
| --- | --- | --- | --- | --- |
| Prices | Relative increase | through 5% | 20% | 50% and above |
| Availability / output | Relative decrease | through 5% | 20% | 50% and above |
| Capacity pressure | Absolute recorded fraction | below 80% | 80% | 95% and above |
| Participation | Recorded `active` | active | — | inactive |

Relative colors interpolate green–amber from 5–20% and amber–red from 20–50%.
Capacity is green below 80%, then interpolates amber–red from 80–95%. Improvements
return toward green. These are initial workshop defaults pending domain review,
centrally configured in `web/src/playback/status.ts`; shared palette/interpolation
live in `web/src/design/`. Selection rings and illustrative placement labels do
not change status fill.

Evaluate all role-applicable measurements: asking price and quantity for producers,
wholesalers, processors, feed manufacturers/traders; feed received and livestock
output for consumers; participation where recorded; storage/handling pressure for
wholesalers. Optional processor/manufacturer `input_received` means **input
offered**, while `input_processed` means transformed input. Their relative
decreases contribute to status when supported; `unused_input` is diagnostic only.
Historical optional diagnostics absent on both sides do not imply incomplete data.
One-sided missing diagnostics do. These values cannot establish production-capacity
utilization without a recorded capacity denominator. Storage pressure is not
production utilization or persistent inventory, and low quantity alone does not
establish unmet demand.

Gray means missing measurements, unusable references, incompatible identities,
or insufficient evidence. Relative references must be positive: zero-to-zero is
unknown, not healthy. Zero current availability against a positive reference is
a severe decline. Zero price is **no quote / no contributing volume**, not recovery.
Inactivity and absolute capacity remain evaluable even if references fail.
Known adverse evidence with missing comparisons retains its color and is labeled
**Incomplete evidence**; green-only evidence with missing comparisons is gray.
Expected-agent checks use the first-frame census; the API has no independent
manifest to detect agents absent from every frame.

### Choosing normal

1. Default to **scenario 0 from the same recorded run**, when available, comparing
   corresponding periods and exact `(entity_id, agent_id, role)` identities.
2. API workshop submissions record **scenario 1 only**. Select a completed
   reference run containing scenario 0; use **More runs** to load older choices.
   A normal CLI PDL invocation records baseline and PDL scenarios. Structure
   (nodes, represented entities, roles, recording flags, directed edges), period
   coverage and recorded identities must match. Cosmetic labels, coordinates,
   ordering and PDL filenames do not need to match.
3. Otherwise default to **Relative to scenario start**, also selectable explicitly.
   This pins the first recorded **end-of-step** frame outside the evictable cache.
   It cannot reveal disturbances already present at the first step. The static
   exported demo uses this mode and retains its legacy exporter aggregation.

An external run is a **structurally compatible recorded baseline**; the existing
API cannot verify equivalent economic settings, seed or implementation version.
Do not interpret that comparison as a controlled causal experiment. Scenario 1
is never offered as a verified unshocked reference. Missing periods, identities,
metrics or requests explain unavailable comparison without silently switching
mode. **Retry reference** retries the chosen source independently of playback.
Initial agent censuses must match for a recorded baseline selection. If an agent
later disappears, its assessment is unavailable but exact matches for surviving
agents and unaffected network indicators retain their comparison evidence.
Current and reference frames are published together. During a same-reference seek
or page load, playback holds the last complete pair at its existing displayed step
until both measurements for the requested step are ready; the playback clock waits
too. Cached periods do not insert loading states or gray flashes. Both streams
prefetch their next page. A user pause while waiting remains paused after loading.
Changing source/run/scenario/reference (or retrying a reference) immediately
invalidates old reference evidence. A genuine reference failure settles to explicit
unavailable comparison until **Retry reference**; it does not trigger a new request
at every step. Current-page failures retain the display and stop playback. Details,
markers, connections and all four network indicators always share the displayed
pair, and late responses cannot replace a newer selection or seek.

The bottom indicators use fixed grid cells and tabular numbers. Loading messages
have reserved space, and detail values use separate current/reference/change rows,
so changing text and digit counts do not move the readouts while playing. Long
indicator explanations retain their full accessible text, focus label and tooltip.

### Connections and workshop results

Connections show **inferred upstream status**: inherit only their source node's
assessment. Unknown source means gray, without target fallback or recursive
propagation through unrecorded ports. The four synchronized timeline indicators
are soy price, feed price, total soy supply and average transport utilization.
The last is network-wide; individual route/port utilization is not recorded.

After completion, **View results** searches catalogue pages for the submitted ID
and opens its scenario 1. It never substitutes the newest run. Errors retain the
displayed selection and allow retry. In static mode, configure
`VITE_PLAYBACK_API_BASE_URL` to view database results. The caption identifies
displayed recorded results; later configurator changes are **Unsubmitted edits
for the next run**, separate from the submitted input snapshot.

### Review screenshots

- [Before: previous static demo interface, step 150](status-before.png) — main
  checkout `9dee6b0`, before issue #75. Different data from the controlled states.
- [Healthy: step 0](status-healthy.png).
- [Disturbed: step 100](status-disturbed.png) — quantity down 50%, price increases,
  and near-full network transport utilization.
- [Recovered: step 250](status-recovered.png) — availability/prices return to reference.
- [Unavailable: step 290](status-unavailable.png) — missing measurements stay gray.
- [Metric breakdown: disturbed step 100](status-details.png) — current/reference
  values and percentage changes in the scrollable inspector.
- [Mobile inspection layout](status-mobile.png).
- [Collapsed impact sidebar](status-sidebar-collapsed.png).
- [Static-demo network with restored connections](status-static-network.png) and
  [the same network with impact collapsed](status-static-network-collapsed.png).
- [Map-label selection with synchronized English details/dropdown](status-map-selection.png).
  Compare the [reader's position immediately before selection](status-label-selection-before.png).

The after screenshots use explicitly **controlled recorded-response fixtures**,
not empirical simulation results. Reproduce from `web/` with Vite configured for
`VITE_PLAYBACK_API_BASE_URL=http://127.0.0.1:8001`:
`SIMENV_WEB_URL=http://127.0.0.1:5175 SIMENV_STATIC_WEB_URL=http://127.0.0.1:5176 node tests/capture-status.mjs`.
The static-network images use the committed demo bundle rather than intercepted
responses. For comparison, the
[previous overlapping layout](https://github.com/PROVIDER-Project/simenv/blob/f216590f2da88b106c2441af1189bff96f1cc00d/docs/status-disturbed.png)
documents the interface before the sidebar correction.
Real-service coverage separately submits and opens both supported cascades.

## Verification

Install `.[dev]` and run against an isolated database:

```bash
SIMENV_TEST_POSTGRES_URL=postgresql+psycopg2://postgres:postgres@localhost/test_db \
  python -m pytest tests
```

Most fixtures create private schemas and remove only those schemas; the schema
test also initializes the configured database's default schema. Use a disposable
test database. The integration test submits a real 105-period run, deletes its
private inputs, fetches scenario 1 across pages, and compares every identity/value
to PostgreSQL. Set `PROVIDER_SIMENV_POSTGRES_URL` as well to enable live tick-writer
checks. CSV parity is separately opt-in via `PROVIDER_SIMENV_PARITY_RUN`.

From `web/`, run `npm run test:playback`. For browser tests, start Vite with
`VITE_PLAYBACK_API_BASE_URL=http://127.0.0.1:8001` and run
`npm run test:playback-browser`; only these tests intercept API responses.
`npm run test:simulation` uses real APIs: set `SIMENV_WEB_URL` to the running
stack. It submits both cascades, verifies catalogue refresh, opens each exact
completed run via **View results**, and seeks into a later database page. Status
browser regressions cover day-0 comparison, recovery, missing/reference failures,
keyboard inspection, reference switching/refresh, delayed responses, cache eviction
and exact-ID pagination/retry. Edge-bearing globe regressions inspect finite
THREE curve geometry and RGBA buffers, geographic endpoints, and visible canvas
pixels through healthy/disturbed/recovered/unknown states and run/scenario changes.
Sidebar regressions cover independent collapse, continuous playback and resizing.
Continuous commit/animation-frame observation checks no transient unknown status,
stable desktop/mobile readout bounds, and coherent holding at delayed current and
reference page boundaries. Loader regressions cover sticky failures, explicit retry,
cache inspection/disposal and superseded-request failures.
Static-demo verification requires a Vite server
without `VITE_PLAYBACK_API_BASE_URL`; no database fallback is implicit.
Set `SIMENV_STATIC_WEB_URL` to that second server when running
`npm run test:playback-browser` to include its static-demo acceptance case;
without this setting that case is explicitly skipped.

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
