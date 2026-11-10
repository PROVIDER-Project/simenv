# Automatic Unshocked Reference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task with independent review gates requested by the user.

**Goal:** Default recorded playback to a reusable, frontend-created disruption-free reference and lock workshop configuration to soy.

**Architecture:** Add one read-only preserved-input endpoint. A source-scoped
frontend coordinator verifies and reuses references or explicitly submits and
monitors a separate empty-events job. Playback consumes an evidence-bearing
reference descriptor without changing its coherent frame publication.

**Tech Stack:** Python/FastAPI, existing YAML/CSV readers, React/TypeScript,
node:test and Playwright. No new dependencies or database migration.

**Spec:** `docs/superpowers/specs/2026-11-04-automatic-reference-design.md`.

## Global constraints

- Simulation POST/worker still execute one submitted scenario (ID 1), never an implicit baseline.
- Creation is a browser request; defaults/inputs/empty events must be verified.
- No relative comparison before automatic reference readiness; static mode never POSTs.
- Fail closed on discovery errors; retain accepted IDs across monitoring failures.
- Ambiguous POST outcomes never automatically resubmit. Only confirmed failed jobs
  may be replaced after explicit retry. Local deduplication is not global exactly-once.
- Preserve all raw recordings, English labels, coherent snapshots and selection/scroll behavior.

## Review focus

- A later-page baseline or queued job must prevent duplicate submission (Task 2).
- An incompatible first candidate must not mask a later valid one (Task 2).
- Template changes around POST must not produce a mismatched reference (Tasks 1/2).
- Selection cleanup/remount and ambiguous POST failures must not create duplicates (Tasks 2/3).
- Scenario-1 empty-event evidence must not admit a disturbed job with a baseline label (Tasks 1/2/3).

### Task 1: Preserved submission input contract

**Files:** create `src/provider_simenv/api/inputs.py`; modify `api/app.py`;
add `tests/test_api_inputs.py` or extend `tests/test_api.py` using existing fixtures.

**Interface:** GET `/simulations/{id}/inputs` returns
`{pdl: object, roster: object|null, cascade: string, parameters: object,
current_parameters: object, evidence: 'preserved'|'execution-hashes'}`.
Cascade is resolved through the same loader rule as execution and is nonempty.
Completed jobs require a matching manifest and executed scenario-1 CSV; missing
evidence, changed roster absence or mismatched hashes never downgrade to preserved.
Only the scenario identifier is excluded from copied/executed parameter comparison.

- [ ] Write failing HTTP tests for exact parsed documents/null roster, unknown
  membership, missing/changed inputs, corrupt manifest, unsupported JSON values,
  copied-versus-executed parameter mismatch and unchanged single-scenario execution.
  Include missing completed manifest/CSV, changed recorded roster absence and no
  integrity-evidence downgrade as separate cases.
- [ ] Run affected pytest cases and observe missing endpoint failures.
- [ ] Implement bounded input reads, raw hash checks when recorded, complete JSON
  compatibility validation, CSV parameter normalization excluding only ID, and
  current-default reporting. Return 404/409 accurately; never expose paths.
- [ ] Run affected tests, Python lint/type checks and independent boundary review.

### Task 2: Pure frontend recipe and coordinator

**Files:** extend `web/src/configurator/simulationApi.ts`; create
`web/src/playback/automaticReference.ts`; extend `web/tests/playback.test.mjs`.

**Interfaces:** `SimulationInputs` matches Task 1; client adds `getSimulationInputs`
and paginated `listSimulations` with identity/range validation.
`RecordedReference = {runId: string; scenarioId: number;
evidence: 'scenario-zero'|'empty-events'}`. `ReferenceChoice` additionally accepts
legacy run strings, `'start'`, and null for preparation.
`createAutomaticReferenceCoordinator(source, api)` exposes
`ensure(runId,scenarioId): Entry`; Entry has immutable preparation state,
subscribe/unsubscribe and explicit retry. Cache per source and deduplicate recipes.
`PreparationState` has phase (`discovering`, `submitting`, `monitoring`,
`awaiting-playback`, `ready`, `error`), jobId, progress, reference and structured
failure kind (`discovery`, `inputs`, `rejected`, `unknown-submission`, `monitoring`,
`failed-job`, `playback`, `incompatible`). Retry rediscoveries unaccepted failures;
accepted monitoring/playback failures retain jobId; only failed-job permits an
explicit replacement POST. Unknown-submission can only rediscover, never POST.
`SimulationApiError` retains HTTP status and operation: candidate 404/409 can be
ineligible, selected-input 404/409 explains unavailable reproduction, network/5xx/
malformed reads fail closed, and unreadable successful POST responses are ambiguous.
`SimulationSubmission.roster` accepts string or null, preserving true absence.

- [ ] Write failing unit cases for stable recursive canonicalization, all-event
  removal preserving roster/non-event declarations, ready later-page/identity
  fallback, verified scenario-1 reuse and false-label rejection, active job reuse,
  concurrent ensure, accepted-ID recovery, ambiguous outcomes and defaults drift.
  Explicitly cover queued matches on later history pages, zero POSTs after discovery
  failure, post-acceptance mismatch, completion revalidation, and monitoring retry
  versus terminal-failure replacement. Add all unit entries to the build harness.
- [ ] Implement catalogue exhaustion, initial census checks, recipe derivation,
  matching preserved-input discovery, newest-job refresh, single POST registration,
  accepted-input verification, monitoring and playable-result wait. Inject API and
  polling wait in coordinator tests; production uses existing real HTTP clients.
- [ ] Monitor failures retain job ID; terminal failure is latched until explicit
  replacement retry; unknown submission outcomes only rediscover, never POST again.
- [ ] Run `npm run test:playback`; independently review this boundary.

### Task 3: Default automatic comparison and soy-only controls

**Files:** `App.tsx`, `ReferenceSelector.tsx`, `reference.ts`, `referenceLoader.ts`,
`usePlayback.ts`, a focused `useAutomaticReference.ts`, `ScenarioConfigurator.tsx`.
Tests: new automatic-reference browser file, existing browser fixtures/tests and
`web/tests/simulation.test.mjs`.

- [ ] Add failing browser tests: automatic default, missing-reference one POST,
  no comparison until completion/playability, second soy submission reuses it,
  preparation/retry/status visibility, static no POST, and disabled soy dropdown.
  Include detach/remount/StrictMode one-POST behavior, selection changes rejecting
  stale readiness, and a created scenario-1 baseline revealing a day-0 disturbance.
  Include the new browser file in `test:playback-browser`.
- [ ] Hook subscribers to shared entries without aborting accepted work on cleanup;
  expose progress/errors and retry. Auto pending passes null to playback and gates
  relative comparison; resolved descriptors fetch their actual scenario ID.
- [ ] Evidence-aware compatibility rejects arbitrary scenario 1. Scenario-zero
  references retain structural/economic-limitation wording; recipe-matched API
  references retain runtime-version limitations. Preserve manual start/0 controls.
- [ ] Disable cascade select at soy and remove switching handler; generation,
  summary, export and submit remain soy. Keep general energy template/API support.
- [ ] Adapt old default-reference assertions and real acceptance to two soy jobs
  with different settings and automatic baseline reuse. Keep no-flash/cache/race,
  label/icon and stationary-camera regressions intact.
- [ ] Run typecheck/lint/build/unit/browser and real-service acceptance; review.

### Task 4: Verification and handoff

- [ ] Review/update root README, frontend README, API/playback guides, and original
  reference spec; document endpoint/evidence/reuse/error behavior and soy locking.
- [ ] Run `.venv/bin/python -m pytest tests -ra` with isolated PostgreSQL and
  `.venv/bin/python -m tox`; record skips/warnings/blockers honestly.
- [ ] Run frontend typecheck/lint/build/unit/full browser and real simulation checks
  against the separate APIs; use static URL to include demo coverage.
- [ ] Capture labeled preparing/ready/soy-locked screenshots and review full diff.
- [ ] Obtain independent final agreement; commit all scoped code/tests/docs, push
  issue branch and update PR #78, preserving `Closes #75` and verifying linkage.
- [ ] Add required PR completion comment with exact verification results.

## Self-review

Every spec boundary has task/test ownership. No new execution defaults, implicit
jobs, schema migration or general provenance framework are introduced. Runtime
equivalence and missing historical inputs remain explicitly bounded. User has
delegated decision-point approvals to independent reviewers; execute inline after
written-plan review.
