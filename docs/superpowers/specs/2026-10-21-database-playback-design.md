# Database-backed simulation playback — issue #58

Status: approved for implementation.

## Intent and agreed constraints

Users must be able to select a recorded simulation by label, start date, or ID
and play its recorded state on the existing globe. PostgreSQL is the source of
playback measurements. Selecting a run must not construct or download a full
time-series bundle: the browser requests bounded period ranges as needed.

The user approved two independently accessible API services:

```text
Browser ----------> Playback API ----> PostgreSQL
Browser ----------> Simulation API --> PostgreSQL
External services -> Simulation API
```

The playback API is browser-accessible, not restricted to an internal network.
PostgreSQL itself stays internal in the bundled stack. Simulation submission,
status, progress, and logs remain responsibilities of the simulation API.

## Baseline and scope

Implementation starts from the latest `origin/main`, which includes #43
(persistent PostgreSQL runs), #48 (per-entity agents), and the dashboard and
simulation API. The current checkout is the older `49-simulation-api` branch.
Use an isolated worktree based on current main for implementation.

Reuse the normalized schema and documented read views, existing topology
construction, and globe rendering. Playback preserves recorded agent identities
and measurement values rather than adopting the exporter's aggregation or rounding. Extract
shared scene metadata construction rather than implementing a second topology
builder. The static bundle remains an explicitly configured standalone demo
mode; the bundled stack uses database playback and never silently substitutes
demo data when the database is unavailable.

This increment supports completed runs. Running and failed runs can appear in
the catalogue but cannot be selected for playback. Live playback, WebSockets,
run deletion, and general-purpose database query endpoints are outside scope.

## Service boundaries

Add a separate FastAPI application under `provider_simenv/playback/` with its own
entry point, connection-pool lifecycle, health endpoint, configuration, and
OpenAPI document. It does not start the simulation job queue or mount submission
routes. Its repository layer performs parameterized, read-only queries against
`sim_run` and the documented read views.

Both APIs use `PROVIDER_SIMENV_POSTGRES_URL`. The frontend has independent
simulation and playback API base URLs. Each API supports an explicit allowed
frontend origin for direct browser requests across ports. External simulation
clients continue using the existing HTTP contract.

## Historical scene metadata

Measurements do not include ports, edges, names, or coordinates. A playback
service must not infer these from whichever scenario file happens to be present.

Add a nullable, versioned JSONB scene snapshot to `sim_run` using an additive,
idempotent migration. The snapshot contains schema version, nodes, edges, PDL
display name, and the existing geographic honesty note. It contains no ticks.
Build it from the exact PDL and roster used for execution and persist it when
opening the database run, before executing periods. Both CLI and API-created
runs follow this path. CSV-only runs are unaffected. Runs without a PDL have no
scene snapshot and are not playable.

For pre-existing runs without a snapshot, the playback service may reconstruct
metadata from the shipped scenario only when both PDL and roster hashes match
the recorded provenance using the existing validation rules. Do not accept
arbitrary file paths over HTTP or require access to simulation job directories.
If no matching inputs are available, report the run as unavailable for playback
with a useful reason. Do not invent topology or require every old run to work.

Scene availability is included in catalogue entries. Legacy scene reconstruction
uses bounded local scenario discovery, not tick queries or full-bundle export.
The playback service never writes snapshots back during a read request.

## Playback HTTP contract

All IDs and ranges are validated; all successful responses have declared models.

- `GET /runs?limit=50&offset=0`: returns `items` and `total`, ordered by start
  time descending with run ID as a deterministic tie-breaker. Limit is 1–100;
  offset is nonnegative. Entries include `id`, `label`, `started_at`,
  `finished_at`, `status`, `scenario_ids`, `period_num`, `playable`, and
  `unavailable_reason` (null when playable). Listing performs no tick reads.
- `GET /runs/{id}/scenarios/{scenario}/scene`: returns run/scenario identity,
  scene nodes and edges, display metadata, and the inclusive period bounds
  `0` through `period_num - 1`. It contains no measurement series.
- `GET /runs/{id}/scenarios/{scenario}/frames?start=0&limit=100`: returns
  run/scenario identity, `start`, `next_start` (null at the end), and ordered
  `frames`. Start is nonnegative; limit defaults to 100 and is limited to
  1–500. The interval is `[start, min(start + limit, period_num))`.
  Each frame contains `period` and recorded agent states identified by
  `entity_id` and `agent_id`, with their metric names and unrounded numeric
  values. The environment is returned as its recorded agent state, not as
  recalculated summary metrics. Grouping metrics into a state object is only
  response shaping; it must preserve every measurement and agent identity.
  A start at or beyond the end returns an empty terminal page.
- `GET /health`: verifies database connectivity and required schema presence;
  returns 503 when unavailable. A newly initialized empty database is healthy.

Unknown run or scenario returns 404. Invalid query values return 422.
An incomplete run or unavailable scene returns 409 with an actionable message.
Database unavailability returns 503 without connection credentials or SQL details.
Missing committed environment periods in a supposedly completed run are a data
integrity error, returned as a generic 500 and logged with run/range context.
No measurements are fabricated or silently replaced with zero.

## Range queries and data fidelity

Filter by run, scenario, and requested period interval in SQL before fetching
rows. Query the whole requested window rather than making one query per entity
or period.
Bound the amount fetched by the requested window; no endpoint calls the full
bundle builder and slices its result.

Read the documented `sim_tick_readable` view, preserving each measurement's
entity, agent, metric, period, and numeric value. Do not sum or average agents,
apply boolean-any, round values, interpolate, or downsample. The long-form view
exposes flags as recorded numeric values (0 or 1); the API preserves that
representation. Preserve absence semantics and deterministic ordering. Ports
and unrecorded actors have no measurements. The API performs no writes.

Frontend-only adapters may interpret flags and derive visual intensity from
the recorded values, as required by the globe, but must not mutate cached
measurements or present derived visual values as recorded measurements.
Multiple agents remain individually identifiable; the API must not collapse
them into one entity value. Existing exporter behavior remains a separate
static-export concern.

Inspect actual range query plans on representative PostgreSQL data. Existing
indexes may suffice for current run sizes; add an additive index only when
query-plan evidence demonstrates it improves this access pattern. Record that
evidence during implementation verification.

## Frontend playback

Introduce a playback-source contract for catalogue, scene, and frame ranges.
Keep concrete HTTP access outside globe and timeline components. Adapt the
explicit static-demo source to this contract, using its in-memory bundle.

Provide paginated run discovery and run/scenario selectors near the existing
dashboard controls. Display label (falling back to ID), start date, and ID;
show unavailable entries with their reason. Select the newest playable run on
initial load, preferring scenario 1 when present, otherwise the first scenario.
Refresh the catalogue after a dashboard-submitted simulation completes, so
the new run can be selected without rebuilding or exporting frontend assets.

Load the scene and the first aligned 100-period page on selection. Keep at most
three pages for the active run/scenario, protecting the currently displayed
page from eviction. Prefetch the next page while playing. A seek fetches its
aligned page immediately. Use one in-flight request per page, cancellation,
and selection-generation checks to prevent duplicate reads and stale responses.

Advancing into an unloaded page holds the displayed frame and shows buffering;
it does not advance simulated time until the frame is ready. Switching run or
scenario resets playback even when both have the same number of periods.
Seeking preserves the current pause-on-seek behavior. Auto-play starts after
the first page is ready, matching existing playback behavior.

Provide explicit initial loading, empty catalogue, buffering, and retryable
error states. Keep the selectors accessible during failures. On a page error,
retain the last valid frame and allow retry; a selection error must not leave
the previous run displayed under the new run's identity. Derive dynamics from
the active frame rather than requiring the entire run in browser memory.

## Executable stack

Add a dedicated playback-stack Compose file with PostgreSQL, the existing
simulation API, the new playback API, and a production-built frontend. Preserve
existing CLI and API-only Compose entry points.

Publish independently configurable frontend, simulation API, and playback API
ports. Do not publish PostgreSQL's port in this stack. Both APIs use the same
database volume; simulation job files retain their existing separate volume.
Initialize the additive schema before API health checks can succeed, without
requiring a simulation to have run first. The simulation side owns schema
initialization; playback requests remain read-only. Declare service dependencies
and health checks accordingly.

Document one-command startup, the three browser/client URLs, API base URL and
CORS settings, submitting the first simulation, selecting its completed run,
and empty-database behavior. Frontend configuration must use browser-reachable
addresses, not Compose-only service names. Build-time URL configuration is
acceptable if documented and wired through Compose build arguments.

## Verification and acceptance criteria

1. Real PostgreSQL integration tests establish that catalogue entries come from
   the database, run/scenario filters isolate data, range boundaries and terminal
   pages work, and scene responses contain no time series.
2. Joined bounded frame pages match database measurements one-for-one by run,
   scenario, period, entity, agent, and metric, with unchanged numeric values.
   Include multiple agents for one entity and values with more than four
   decimal places to detect accidental aggregation or rounding.
3. A newly recorded run still plays after its input files change or disappear.
   Legacy fallback accepts matching provenance and rejects mismatches.
4. API tests cover invalid inputs, unknown identities, unavailable/incomplete
   runs, empty databases, database outages, and allowed browser origins.
5. Focused frontend behavioral tests cover same-length run switching, stale
   responses, seeking outside the buffer, buffering/resume, bounded cache
   eviction, retry, and catalogue refresh after submission completion.
6. Frontend typecheck, lint, and production build pass. Relevant Python tests
   and lint pass, including existing exporter and simulation API regressions.
7. Compose configuration validates; a stack smoke test submits a short run,
   observes completion through the simulation API, discovers it through the
   playback API, and reads scene plus multiple frame ranges. Browser verification
   checks run selection, seeking, and bounded network requests during playback.

## Review and implementation handoff

The architecture and HTTP-window approach were approved in conversation.
This written specification requires user review before the implementation plan
is created. No implementation changes are included in this document stage.
