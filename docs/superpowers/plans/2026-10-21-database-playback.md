# Database Playback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for native execution or superpowers:subagent-driven-development if the user selects delegation. Steps use checkbox syntax for tracking.

**Goal:** Select recorded database runs and play their unchanged measurements through a separate range-based playback API.

**Architecture:** PostgreSQL serves both independent FastAPI services. Playback reads scene snapshots and bounded measurement windows; the browser caches three pages and renders individual recorded agent states. Simulation execution remains in its existing API.

**Tech Stack:** Python, FastAPI, SQLAlchemy 2.0, PostgreSQL 16, React 18, TypeScript, Vite, Playwright, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-21-database-playback-design.md`

## Global Constraints

- Implement against latest `origin/main` in an isolated worktree.
- Preserve entity, agent, period, metric, and numeric value; no aggregation, rounding, interpolation, or downsampling in playback responses.
- Playback queries are read-only and bounded in SQL before fetching rows.
- Completed runs only; other runs appear with an unavailable reason.
- Frame windows default to 100 periods, maximum 500; catalogue limit defaults to 50, maximum 100.
- Frontend keeps at most three 100-period pages per active selection.
- Both APIs are browser-accessible; PostgreSQL has no published port in the new stack.
- Keep static demo mode explicit; never fall back to demo measurements on database errors.
- Do not commit or push without an explicit user request.

## Review Focus

- A selectable run occurs beyond catalogue page one: initial selection must discover the newest playable run (Task 5).
- A request finishes after cancellation: its result must not overwrite the new selection (Task 4).
- A snapshot has an unknown schema version: fail that run's playback clearly without breaking the catalogue (Tasks 1–3).
- Missing environment data or non-finite database values: return an integrity error, never fabricated measurements or invalid JSON (Tasks 2–3).
- Empty-stack startup and browser URLs: a simulation must be submittable before any playback data exists (Tasks 5–6).

## File structure and shared interfaces

- `scene.py`: shared scene metadata construction from exact scenario inputs.
- `db_schema.py`, `tick_writer.py`, `execution.py`: additive snapshot persistence and shared schema initializer.
- `playback/models.py`: typed wire contract; `playback/store.py`: bounded read repository; `playback/app.py`: separate HTTP application.
- `web/src/data/playback.ts`, `httpPlaybackSource.ts`, `staticPlaybackSource.ts`: typed source contract and implementations.
- `web/src/playback/buffer.ts`: cancellable bounded cache; `usePlayback.ts`: React playback orchestration; `frame.ts`: pure visual projection.
- `web/src/playback/RunSelector.tsx`: catalogue/selection UI; existing globe/timeline keep rendering responsibilities.
- `compose.playback.yml`, `Dockerfile.playback`, `web/Dockerfile`: executable stack; existing deployment entry points retained.

Paths above Python files are relative to `src/provider_simenv/`.

### Task 1: Preserve historical scenes and initialize the schema

**Files:** Create `src/provider_simenv/scene.py`; modify `db_schema.py`, `tick_writer.py`, `execution.py`, `export_bundle.py`, `api/app.py`; add `tests/test_scene.py`, `tests/test_playback_schema.py`; update `docs/postgres-schema.md`.

**Interfaces:**
- `build_scene(pdl_path: Path) -> dict`: `{schema_version: 1, pdl: str, honesty_note: str, nodes: list, edges: list}`; existing frontend node/edge shapes.
- `initialize_schema(engine: Engine) -> None`: idempotently install tables, additive migrations, and views without creating a run.
- `TickWriter.open_run(record: dict, *, scene: dict | None = None) -> None`: persist nullable `sim_run.scene` JSONB with the run record; retain existing callers.

- [ ] Write scene tests proving node/edge metadata equals the existing export metadata, no ticks exist in the snapshot, and input edits after snapshot construction do not change it.
- [ ] Write database tests proving repeated initialization keeps existing measurements, adds a nullable scene column to an old schema, and round-trips the versioned snapshot.
- [ ] Run `python -m pytest tests/test_scene.py tests/test_playback_schema.py -v`; expect failures for the missing interfaces.
- [ ] Extract metadata helpers into `scene.py`, retaining exporter imports/behavior needed by existing tests. Add typed JSONB binding for scene persistence; do not add snapshot fields to `runs.json` metadata.
- [ ] Build scene from execution's exact PDL before opening the run; omit for CSV-only/no-PDL execution. Initialize schema at simulation API startup before queue execution so an empty database is usable.
- [ ] Run the new tests plus `tests/test_execution.py`, `tests/test_api.py`, and existing topology/export tests; expect passes. Real PostgreSQL tests must run against an isolated test database, with connection URL supplied explicitly.

### Task 2: Build the read-only range repository

**Files:** Create `src/provider_simenv/playback/__init__.py`, `models.py`, `store.py`; add `tests/test_playback_store.py` and shared fixtures in `tests/playback_helpers.py`.

**Interfaces:**
- `RunSummary`: `id`, nullable label/finish timestamp, start timestamp, status, scenario IDs, period count, playable flag, nullable unavailable reason.
- `RunList`: `items: list[RunSummary]`, `total: int`.
- `Scene`: `run_id`, `scenario_id`, `min_period`, `max_period`, `pdl`, `honesty_note`, `nodes`, `edges`.
- `AgentState`: `entity_id: str`, `agent_id: int`, `role: str`, `values: dict[str, float]`.
- `RecordedFrame`: `period: int`, `agents: list[AgentState]`; environment included as its own agent.
- `FramePage`: `run_id`, `scenario_id`, `start`, nullable `next_start`, `frames`.
- `PlaybackStore(engine: Engine, scenario_dir: Path)` with `list_runs(limit: int, offset: int) -> RunList`, `get_scene(run_id: str, scenario_id: int) -> Scene`, `get_frames(run_id: str, scenario_id: int, start: int, limit: int) -> FramePage`, `check_health() -> None`.
- Domain exceptions: `PlaybackNotFound`, `PlaybackUnavailable`, `PlaybackIntegrityError`. Unknown snapshot versions are unavailable, not crashes.

- [ ] Seed two completed runs, an incomplete run, two scenarios, multiple agents of one entity, seven environment metrics, and `1.123456789012345` values. Write tests asserting identity/value equality, cross-run/scenario isolation, no catalogue tick queries, ordering, clipping, and empty terminal pages.
- [ ] Add tests for legacy matching/mismatched PDL and roster hashes, unsupported snapshot versions, missing environment periods, and non-finite measurements. Catalogue must remain usable when one scene is unavailable.
- [ ] Run `python -m pytest tests/test_playback_store.py -v`; expect missing repository failures.
- [ ] Implement snapshot validation and bounded local legacy scene discovery using existing provenance validation. Never use an HTTP-supplied path or write a snapshot on read.
- [ ] Implement a parameterized `sim_tick_readable` query filtered by run/scenario and `period >= :start AND period < :end`, ordered by period/entity/agent/metric. Group only into response objects; preserve all values. Assert complete environment metric sets for each requested period.
- [ ] Run store tests against PostgreSQL; expect passes. Record `EXPLAIN (ANALYZE, BUFFERS)` for representative range queries; add an index only if measured plans justify it, then repeat the affected query.

### Task 3: Expose the independent playback service

**Files:** Create `src/provider_simenv/playback/app.py`; modify simulation `api/app.py` for configured CORS; add `tests/test_playback_api.py`; update API dependency declarations/lockfile only if necessary.

**Interfaces:** `create_app(*, store_factory=None) -> FastAPI` reads database URL, `SIMENV_PLAYBACK_ALLOWED_ORIGINS`, and owns/disposes its engine. Module-level `app` is the uvicorn entry point. Simulation API uses `SIMENV_API_ALLOWED_ORIGINS` without changing submission routes.

- [ ] Write HTTP tests for `/runs`, scene, frames, health, pagination bounds, negative/oversized ranges, unknown identities, and status mappings (404/409/422/503/500).
- [ ] Assert `/simulations` does not exist on playback, no queue starts, CORS accepts the configured frontend origin and rejects other origins, and database errors do not expose credentials or SQL.
- [ ] Run `python -m pytest tests/test_playback_api.py -v`; expect missing app failures.
- [ ] Implement endpoints with Task 2 response models and lifespan-owned connection pool. Use synchronous route functions for synchronous database I/O. Add domain exception mapping and safe database error logging; health checks required schema without creating it.
- [ ] Run playback API tests and existing simulation API tests; expect passes, including empty initialized database health and non-finite/missing-data integrity failures.

### Task 4: Implement faithful frontend sources and bounded buffering

**Files:** Create `web/src/data/playback.ts`, `httpPlaybackSource.ts`, `staticPlaybackSource.ts`, `web/src/playback/buffer.ts`, `frame.ts`, `web/tsconfig.test.json`; modify `web/package.json`, `.gitignore`; add `web/tests/playback.test.mjs` using Node's existing test runner.

**Interfaces:**
- TypeScript interfaces mirror Task 2's wire models with snake_case keys and numeric `values`.
- `PlaybackSource`: `name`, `listRuns(limit, offset, signal): Promise<RunList>`, `getScene(runId, scenarioId, signal): Promise<Scene>`, `getFrames(runId, scenarioId, start, limit, signal): Promise<FramePage>`.
- `createPlaybackBuffer(source, runId, scenarioId)`: `load(period): Promise<RecordedFrame>`, `prefetch(period): void`, `dispose(): void`; page size 100, maximum three pages, per-page request deduplication, selection cancellation.
- `projectFrame(scene, frame, baseline): {markerIntensity, edgeIntensity, env}`: pure display adapter; never mutate frames. Baseline is period zero, stored separately from page cache.

- [ ] Write tests for HTTP validation preserving precision/agent IDs, partial last pages, request deduplication, seek page alignment, three-page eviction, and late results after disposal.
- [ ] Add `test:playback` to compile pure data/buffer/projection modules into ignored `web/.test-build` with `tsc -p tsconfig.test.json`, then execute `node --test tests/playback.test.mjs`; use a test tsconfig with Node-compatible ES module imports. Add `test:playback-browser` as `node --test tests/playback-browser.test.mjs` in Task 5, reusing Playwright and a documented running Vite server.
- [ ] Write projection tests proving input immutability and stable intensity independent of loaded pages. For each agent prefer price, otherwise livestock output, otherwise quantity: adverse relative change from its period-zero value is clamped to 0–1. Zero/missing baseline yields zero intensity. Multiple-agent nodes use the maximum individual display intensity; recorded agent states remain distinct. Environment fields are mapped by name without rounding.
- [ ] Run `npm run test:playback` from `web`; expect failures for missing modules.
- [ ] Implement HTTP source with AbortSignal propagation and structural response validation. Adapt static bundle into one explicit demo run; its legacy values stay as provided and are not represented as raw database measurements.
- [ ] Implement cache and projection interfaces above. Protect the currently displayed page from eviction; reject obsolete loads even if fetch ignores cancellation. Baseline is a display reference, not a cached full series.
- [ ] Run `npm run test:playback` and `npm run typecheck` from `web`; expect passes.

### Task 5: Connect run selection, playback, and dashboard completion

**Files:** Create `web/src/playback/usePlayback.ts`, `RunSelector.tsx`; modify `App.tsx`, `main.tsx`, `app.css`, `vite-env.d.ts`, `configurator/ScenarioConfigurator.tsx`, `configurator/SimulationRunner.tsx`; add `web/tests/playback-browser.test.mjs`.

**Interfaces:** `App` receives a `PlaybackSource`; `usePlayback(source)` owns catalogue, selection, buffer, period, playing, loading/buffering/errors, retry, refresh, seek, and toggle actions. Configurator/runner accept `onCompleted(runId: string): void` and notify once per completed job. `VITE_PLAYBACK_API_BASE_URL` selects HTTP mode; absent configuration selects explicit demo mode.

- [ ] Write browser tests with mocked API routes for initial newest-playable discovery beyond page one, same-length run switching, scenario switching, stale delayed responses, empty catalogue, and scene failure with working selectors.
- [ ] Add tests proving a seek pauses and fetches the aligned page, automatic advancement waits for missing data then resumes, a failed page preserves the last frame and supports retry, and completion refresh discovers a submitted run without automatic selection replacement.
- [ ] Run `npm run test:playback-browser` from `web`; expect failures on the existing bundle-only UI.
- [ ] Implement hook with independent catalogue and selected-run state, initial scenario 1 preference, paginated discovery until a playable run is found, scene/first-page loading, period-zero visual reference, next-page prefetch, and bounded cache disposal on selection changes.
- [ ] Integrate selectors and frame-based rendering; remove database-mode dependence on `buildDynamics(bundle)`. Keep selectors and configurator available with an empty database so users can submit the first run. Supply configurator the selected scene metadata or explicit shipped scenario defaults when none is selected.
- [ ] Wire completion notification through configurator to catalogue refresh. Replace the obsolete completion message about the globe's static bundle.
- [ ] Run `npm run test:playback`, `npm run test:playback-browser`, `npm run test:simulation`, `npm run typecheck`, `npm run lint`, and `npm run build` from `web`; expect passes.

### Task 6: Bundle and verify the complete stack

**Files:** Create `compose.playback.yml`, `Dockerfile.playback`, `web/Dockerfile`, `web/nginx.conf`, `docs/playback.md`; modify `README.md`, `web/README.md`; add `tests/test_playback_integration.py`.

**Interfaces:** `docker compose -f compose.playback.yml up --build -d`; frontend port defaults to 8080, simulation API 8000, playback API 8001, all configurable. Both API containers listen internally on 8000. `SIMENV_BROWSER_HOST` defaults to localhost and forms documented browser URLs; frontend Vite URLs are build arguments. Allowed frontend origins derive from the browser host/frontend port. PostgreSQL has no host port.

- [ ] Write end-to-end PostgreSQL test: prepare a short simulation, complete it through the simulation API, list it through playback, fetch scene and multiple bounded pages, flatten states, and compare keys/values exactly to `sim_tick_readable`.
- [ ] Add snapshot independence verification by changing/removing the run inputs before playback reads. Assert playback data do not change and database rows are not modified by reads.
- [ ] Run `python -m pytest tests/test_playback_integration.py -v`; expect failures until full integration is wired.
- [ ] Implement images/Compose with persistent PostgreSQL and simulation-job volumes. Simulation API initializes schema before playback starts; health checks enforce ordering. Frontend nginx serves SPA/assets only; both API URLs remain independently browser-accessible.
- [ ] Document direct URLs, CORS, build-time base URLs, first submission, completed-run selection, legacy availability, demo mode, and unchanged raw measurements. Document visual-intensity baseline behavior separately from measurement fidelity.
- [ ] Run `docker compose -f compose.playback.yml config --quiet`; expect exit zero. Start an empty stack and execute the short-run smoke test through published API ports; verify catalogue starts empty and becomes playable after completion.
- [ ] Run focused Python tests plus existing execution, topology/export, and simulation API regressions. Run Ruff on changed Python files and the Task 5 frontend commands. Report actual skips and any environment blockers instead of counting them as passes.
- [ ] Perform browser verification of selection/seek/buffering and inspect requests: frame limit 100, no full bundle in HTTP mode, no whole-run request on seek. Record query-plan evidence, tested commands, and outcomes in the final report.
- [ ] Add `web/tests/playback-performance.test.mjs` and a `test:playback-performance` script using Playwright against the production frontend. Exercise a representative recorded run and a deterministic large fixture with 1,000 recorded agents, 13 numeric metrics per agent, 300 periods, and 100-period responses. Preserve distinct agent identities and full numeric precision in the fixture. Warm up, then run three playback/seek trials in Chromium on the same machine; record browser version, hardware, and CPU-throttling setting.
- [ ] Instrument and report API request latency, JSON decoding/validation, cache insertion, `projectFrame`, and React/globe rendering separately using browser Performance APIs and performance marks. Measure work after each page arrives as well as steady-state playback. Report p50/p95 durations, input-to-next-paint latency for seek/pause actions, and main-thread long tasks (over 50 ms). Keep network and rendering time out of the calculation-only measurement so their costs cannot be misattributed to arithmetic.
- [ ] Use a p95 calculation budget of 16.7 ms per displayed frame and a 100 ms seek/pause responsiveness target on the recorded test machine. Identify whether page decoding/preparation causes long tasks that delay interactions. Treat these as investigation thresholds, not machine-independent CI timing assertions; fixture fidelity, instrumentation output, and absence of full-run loading remain deterministic test assertions.
- [ ] If post-response calculations exceed the budget or cause interaction-delaying long tasks, profile the responsible calculation. Compare the browser implementation with an API-side preparation prototype on identical inputs and hardware, measuring server CPU, response size, end-to-end time to display, browser calculation time, and interaction responsiveness. Keep raw measurement fields unchanged; any derived display fields must be separately named and must not sum, round, replace, or omit raw measurements. Move a calculation only if the comparison demonstrates an end-to-end/responsiveness benefit. If decoding or WebGL rendering is the bottleneck, report that evidence rather than moving unrelated calculations to the API. Record the placement decision and measurements in `docs/playback.md`; add equivalence tests for any calculation moved server-side.

## Self-review and handoff

Coverage: Task 1 owns historical topology and schema startup; Tasks 2–3 own faithful range access and API separation; Tasks 4–5 own bounded browser playback; Task 6 owns deployment, end-to-end evidence, and measured frontend-versus-API calculation placement. Review Focus inputs are assigned to tests above.

The existing full-series colour normalization is intentionally replaced by a frontend-only period-zero reference. No backend summary query or measurement transformation is introduced to support colours.

Review this plan and select native or subagent-driven execution before implementation. Native execution is recommended because the tasks share wire models, frame semantics, and lifecycle behavior across the API/frontend boundary.
