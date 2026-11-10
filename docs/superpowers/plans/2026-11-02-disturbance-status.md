# Explainable Disturbance Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement issue #75's explainable workshop results and reference comparison workflow.

**Architecture:** Pure role-aware evaluation feeds one projection shared by globe,
details and timeline. An independently buffered reference hook matches each
displayed period; App opens exact completed runs through the existing catalogue.

**Tech Stack:** React 18, TypeScript, existing Globe/Three renderer, node:test,
Playwright, existing Python/PostgreSQL APIs (no new runtime dependencies).

**Spec:** `docs/superpowers/specs/2026-11-02-disturbance-status-design.md`

## Global Constraints

- Preserve raw values, precision and individual agents; join measurements to Node.id.
- Relative green through 5%, amber at 20%, red at 50%; capacity green below 80%,
  amber at 80%, red at or above 95%; inactive red; unavailable gray.
- Optional processing input metrics score decreases; unused_input is diagnostic only.
- Complete/partial/unavailable coverage; green plus unknown is gray, adverse plus
  unknown retains known adverse severity with incomplete coverage.
- Scenario 0 references match current period; scenario-start stays pinned to first
  frame. No silent fallback, min/max normalization or cache-derived baseline.
- External baseline guarantees are structural only, not economic equivalence.
- Preserve original checkout's staged AGENTS.md; work on 75-disturbance-status.

## Review Focus

- Same-number agents in different entities/roles must never share references (Task 1).
- Metrics disappearing after initial playback must produce incomplete coverage (Task 1).
- Out-of-order reference replies must not repaint a newer seek/selection (Task 2).
- Completed run beyond catalogue page one must open exactly, despite refresh (Task 4).
- Small screens and missing geographic placements retain accessible inspection (Task 3/5).

### Task 1: Pure status/reference contracts

**Files:** Create `web/src/playback/status.ts`, `reference.ts`; modify `frame.ts`,
`web/tests/playback.test.mjs`.

**Interfaces:** `MetricStatus` carries key/label/current/reference/change/score/reason;
`Assessment` carries score (number|null), coverage, reason and metrics. Node
assessments also retain constituent agent assessments, the winning metric and
exact `(entity_id, agent_id, role)` identity, and missing-agent evidence from the
first-frame census. The projection sorts agents by stable identity before
aggregation; metric ties follow registry order.
`evaluateAgent(current: AgentState, reference?: AgentState, expected?: AgentState): Assessment`;
`aggregateAssessments(items: Assessment[]): Assessment` uses stable input order.
`referenceCompatibility(current: Scene, reference: Scene): string | null`;
`agentIdentity(agent: AgentState): string` includes entity, agent and role.
`projectFrame(scene, frame, reference: RecordedFrame|null, expected?: RecordedFrame)`
returns `nodes`, `edges`, `indicators`, plus legacy `markerIntensity`,
`edgeIntensity`, `env` for existing consumers/performance probes during migration.

- [ ] Add node:test cases asserting price + supply uses strongest change; 5/20/50%
  maps to 0/.5/1, capacity .8/.95 maps .5/1; recovery returns 0. Assert zero
  quote/reference gray, zero quantity red, inactivity red, role mismatch gray,
  optional inputs and unused_input semantics, agent ordering invariance and
  partial coverage. Deep-compare/freeze both raw frames.
- [ ] Run `npm run test:playback` and confirm new tests fail for missing behavior.
- [ ] Implement registry/evaluation/coverage, canonical topology and identity checks,
  source-only edge projection and four environment indicators with exact contracts.
- [ ] Run `npm run test:playback` and typecheck; independently review this boundary.
- [ ] Inspect diff/status/history and commit evaluator changes.

### Task 2: Reference loading and coherent projection

**Files:** Create `web/src/playback/useReference.ts`, `ReferenceSelector.tsx`;
modify `usePlayback.ts`, `App.tsx`, data `playback.ts`, `httpPlaybackSource.ts`,
`staticPlaybackSource.ts`; extend `web/tests/playback-browser.test.mjs`.

**Interfaces:** `PlaybackSource.mode: 'recorded'|'static'`.
`useReference(source, scene, frame, baseline, choice)` returns matching frame or
null, explanation, loading/error and retry. Choice is start or recorded run ID
(scenario 0). `ReferenceSelector` consumes choice, loaded catalogue and callbacks.

- [ ] Add browser tests for scenario-0 day-0 comparison, selected external baseline,
  incompatible topology/identities/periods, request error/retry and stale seek replies.
  Explicitly cover stale replies after reference-run switching, first-page
  eviction followed by forward/backward seeking with identical start-mode
  assessments, relative unavailable with absolute capacity/participation still
  evaluated, and delayed loads keeping marker projection/details/all four
  indicators on the same displayed period and reference generation.
- [ ] Run browser tests against Vite and confirm new selectors/behavior fail.
- [ ] Implement bounded separate reference buffer with abort and generation guards;
  no cross-period references, pinned start frame and role/identity validation.
  Add source mode and scene identity checking. Default reference from catalogue.
- [ ] Integrate one projection in SelectedPlayback for every status consumer;
  preserve current-frame buffering behavior and independent reference errors.
- [ ] Run playback unit/browser checks and typecheck; independently review and commit.

### Task 3: Shared status presentation and inspection

**Files:** Create `web/src/design/status.ts`, `web/src/playback/StatusPanel.tsx`,
`status.css`; modify `design/tokens.ts`, `GlobeView.tsx`, `Timeline.tsx`,
`timeline.css`, `App.tsx` and browser tests.

**Interfaces:** `statusColor(score: number|null): string` interpolates shared palette;
`statusLabel(assessment): string` supplies text. Globe takes nullable intensity
maps plus `selectedNode`/`onSelectNode`; StatusPanel takes scene, projection,
period, reference explanation and shared selection. Timeline takes indicators.

- [ ] Add browser assertions for native keyboard component selection, current/ref
  values, responsible metric/agent, unrecorded/unplaced nodes and seeking updates.
- [ ] Run and observe missing UI failures before implementation.
- [ ] Implement compact legend, list/details, pooled-agent explanations and four
  network indicator badges. Use shared colors for all markers/connections/readouts;
  remove role fill overrides and quantization, keep selection ring independent.
  Label connections inferred upstream, with no route utilization claim.
- [ ] Verify mobile no horizontal overflow; run typecheck/lint/build/unit/browser;
  independently review and commit.

### Task 4: Exact workshop result opening

**Files:** Modify `App.tsx`, `configurator/ScenarioConfigurator.tsx`,
`SimulationRunner.tsx`, `web/tests/simulation.test.mjs` and playback browser tests.
Create a focused catalogue helper if pagination logic otherwise duplicates.

**Interfaces:** Configurator/runner receive
`onViewResults: (runId: string) => Promise<void>`;
App resolves ID through source.listRuns pages, validates playable/scenario1,
then updates catalogue and keyed selection. Async errors shown in execution UI.
Runner awaits the callback, displays opening state, catches errors and retries
the same completed ID. Generation guards reject stale results when tracked job
or requested selection changes; App guards against catalogue refresh races.

- [ ] Add browser assertions that completed exact run (beyond first page) opens
  scenario 1 while a newer run exists; edit-after-submit text; static explanation.
- [ ] Run tests to observe missing View results behavior.
- [ ] Capture submission snapshot at submit start, show next-run edit state,
  implement exact-ID results action/error/retry and protect against refresh races.
  Use source.mode, never display-name detection. Correct real simulation step
  expectation to 365 and exercise View results in real acceptance.
- [ ] Run relevant browser checks and real simulation acceptance; independent review
  of workshop loop, then commit.

### Task 5: Verification, docs and handoff

**Files:** Update README.md, web/README.md, docs/playback.md; capture review
screenshots under docs with labeled before/healthy/disturbed/recovered/unavailable.

- [ ] Capture before UI from unchanged baseline with same controlled fixture.
- [ ] Update documented thresholds/semantics, reference compatibility/limitations,
  direct results workflow and scenario-1 integration description; verify links.
- [ ] Install dev dependencies in venv (`pip install -e '.[dev]'`); run
  `python -m pytest tests` with isolated PostgreSQL integration where available.
- [ ] From web run `npm ci`, `npm run typecheck`, `npm run lint`, `npm run build`,
  `npm run test:playback`, `npm run test:playback-browser`, `npm run test:simulation`.
  Record exact results, skips and service blockers; rerun affected checks after fixes.
- [ ] Independently review full branch against spec/issue; resolve findings until
  reviewer and implementer agree. Capture final state screenshots and mobile.
- [ ] Inspect status/full diff/recent history, commit remaining scoped artifacts,
  push branch, open PR against main with `Closes #75`, verification and screenshots.
- [ ] Verify GitHub closing issue linkage, add required PR summary comment, return URL.

## Review and execution choice

Self-review: all spec sections map to tasks; five likely input failures have
explicit test ownership. Existing source/cache contracts remain bounded. User
delegated approvals to independent subagents; written-spec review approved.
Execute inline with independent decision-point reviews, optionally delegating
nonoverlapping implementation units under the defined contracts.
